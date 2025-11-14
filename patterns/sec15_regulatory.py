# patterns/sec15_regulatory.py (핵심 변경 포함 전체)

from __future__ import annotations
import re
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional

from .utils_text import strip_special_ws

# ──────────────────────────────────────────────────────────────────────────────
# 1. 규제항목 마스터 리스트
# ──────────────────────────────────────────────────────────────────────────────
MASTER_ITEMS: List[str] = [
    # 1차
    "기존화학물질",
    "유독물질",
    "허가물질",
    "제한물질",
    "금지물질",
    "사고대비물질",
    "배출량조사대상화학물질",
    "PRTR1그룹",
    "PRTR2그룹",
    "등록대상기존화학물질",
    "중점관리물질(2019년시행)",
    "중점관리물질(2021년시행)",
    "CMR등록물질(2021년까지)",
    "중점관리물질",
    "제조금지물질",
    "제조허가물질",
    "제조미등록화학물질",
    "노출기준설정대상물질",
    "작업자노출기준",
    "관리대상유해물질",
    "작업환경측정대상유해인자",
    # 2차
    "특수건강진단대상유해인자",
    "특별관리물질",
    "허용기준설정대상유해인자",
    "공정안전관리대상물질",
    "영업비밀대체물질",
    "소비자제품안전검사대상물질",
    "특수고압가스",
    "가연성가스",
    "독성고압가스",
    "제1류",
    "제2류",
    "제3류",
    "제4류",
    "제5류",
    "제6류",
    "제7류",
    "위험물",
    "대기오염물질",
    "특정대기유해물질",
    "휘발성유기화합물",
    # 3차
    "기후생태계변화유발물질",
    "온실가스",
    "유해성대기감시물질",
    "장거리이동대기오염물질",
    "수질오염물질",
    "특정수질유해물질",
    "토양오염물질",
    "지정악취물질",
    "특정물질",
    "폐유기용제",
    "지정폐기물",
]

# alias: 원문 표현 → canonical 항목
ALIASES: Dict[str, List[str]] = {
    # 네가 말한 매핑
    "작업환경측정대상유해인자": [
        "작업환경측정물질",
        "작업환경측정대상물질",
    ],
}

# 규제법규명(법 이름) 힌트: 매핑 대상에서 제외
LAW_NAME_HINTS = [
    "산업안전보건법",
    "화학물질관리법",
    "화학물질 등록 및 평가 등에 관한 법률",
    "화학물질의 등록 및 평가 등에 관한 법률",
    "고압가스안전관리법",
    "위험물안전관리법",
    "대기환경보전법",
    "물환경보전법",
    "토양환경보전법",
    "악취방지법",
    "오존층보호를 위한 특정물질의 제조, 규제 등에 관한 법률",
    "폐기물관리법",
]

NEGATIVE_HINTS = [
    "해당없음",
    "해당 없음",
    "미해당",
    "비대상",
    "대상이 아님",
    "포함되지 않음",
]

POSITIVE_HINTS = [
    "해당",
    "대상",
    "포함",
    "적용",
]


def _normalize(s: str) -> str:
    if not s:
        return ""
    s = strip_special_ws(s)
    s = s.lower()
    s = re.sub(r"[\s\.\,\(\)\[\]\-_/·]", "", s)
    return s


NORMALIZED_LAW_HINTS = [_normalize(x) for x in LAW_NAME_HINTS]


def _is_law_name(line: str) -> bool:
    raw = line.strip()
    if not raw:
        return False
    norm = _normalize(raw)

    for h in NORMALIZED_LAW_HINTS:
        if h and h in norm:
            return True

    if len(norm) <= 30 and (raw.endswith("법") or raw.endswith("법률")):
        if "물질" not in raw and "대상" not in raw:
            return True

    return False


def _candidate_lines(section_text: str):
    text = strip_special_ws(section_text or "")
    lines = [l.strip() for l in text.splitlines()]

    cand_lines, law_lines = [], []
    for l in lines:
        if not l:
            continue
        if _is_law_name(l):
            law_lines.append(l)
        else:
            cand_lines.append(l)
    return cand_lines, law_lines


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _infer_presence(raw_line: str) -> Optional[bool]:
    norm = _normalize(raw_line)
    if not norm:
        return None

    for kw in NEGATIVE_HINTS:
        if _normalize(kw) in norm:
            return False
    for kw in POSITIVE_HINTS:
        if _normalize(kw) in norm:
            return True
    return None


def _best_match_for_item(
    item_name: str,
    cand_lines: List[str],
    min_score: float = 0.72,
) -> Optional[Dict[str, Any]]:
    norm_item = _normalize(item_name)
    if not norm_item:
        return None

    # alias 정규화
    alias_norms = [_normalize(a) for a in ALIASES.get(item_name, [])]

    best_score = 0.0
    best_line = None

    for line in cand_lines:
        norm_line = _normalize(line)
        if not norm_line:
            continue

        # 1) alias가 들어 있으면 무조건 최고 점수
        if any(an and an in norm_line for an in alias_norms):
            score = 1.0
        # 2) canonical 이름 포함/포함됨
        elif norm_item in norm_line or norm_line in norm_item:
            score = 1.0
        else:
            score = _similarity(norm_item, norm_line)

        if score > best_score:
            best_score = score
            best_line = line

    if not best_line or best_score < min_score:
        return None

    presence = _infer_presence(best_line)

    return {
        "canonical_name": item_name,
        "source_line": best_line,
        "score": round(best_score, 3),
        "present": presence,
    }


def extract(section_text: str) -> Dict[str, Any]:
    if not section_text:
        return {"items": [], "coverage": 0.0, "unmatched_lines": [], "law_lines": []}

    cand_lines, law_lines = _candidate_lines(section_text)

    results: List[Dict[str, Any]] = []
    used_lines_idx = set()

    for item in MASTER_ITEMS:
        match = _best_match_for_item(item, cand_lines)
        if not match:
            continue

        try:
            idx = cand_lines.index(match["source_line"])
        except ValueError:
            idx = -1
        if idx >= 0:
            used_lines_idx.add(idx)

        results.append(match)

    coverage = round(len(results) / max(1, len(MASTER_ITEMS)), 3)
    unmatched_lines = [
        cand_lines[i] for i in range(len(cand_lines)) if i not in used_lines_idx
    ]

    return {
        "items": results,
        "coverage": coverage,
        "unmatched_lines": unmatched_lines,
        "law_lines": law_lines,
    }
