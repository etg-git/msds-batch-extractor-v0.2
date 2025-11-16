# patterns/sec3_composition.py
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional


"""
섹션 3(성분 및 함유량) 추출 모듈

핵심 기능
- CAS 번호 인식: 00-00-0 ~ 0000000-00-0 형태만 인정
- 함유량(농도) 파싱:
    1) 범위: 10 - 20%, 0.1~1 %, 1 – <5 등
    2) 부등호: >= 10%, <1 %, <= 0.1 w/w 등
    3) 단일값: 5%, 0.1 % w/w 등
- 대표값(conc_repr) 계산:
    - range  : (min + max) / 2
    - cmp/single : 해당 값 그대로
- 결과는 row 리스트(dict)로 반환
"""

# ──────────────────────────────────────────────────────────────
# 공통 정규식
# ──────────────────────────────────────────────────────────────

# CAS 번호: 2~7 자리 - 2자리 - 1자리
CAS_RE = re.compile(
    r"\b(?P<cas>\d{2,7}-\d{2}-\d)\b"
)

# 범위: 0.1 - 1, 0.1~1, 0.1 – <1, 1 to 5 등
CONC_RANGE_RE = re.compile(
    r"""
    (?P<min>\d+(?:\.\d+)?)
    \s*(?:~|–|-|to)\s*
    (?P<max_cmp><=|>=|<|>)?      # 예: 0.1 - <1
    \s*(?P<max>\d+(?:\.\d+)?)
    \s*(?P<unit>w/w|v/v|wt\.?\s*%|vol\.?\s*%|%)?
    """,
    re.X | re.I,
)

# 부등호: >= 10, < 1 등
CONC_CMP_RE = re.compile(
    r"""
    (?P<op><=|>=|<|>)
    \s*
    (?P<value>\d+(?:\.\d+)?)
    \s*(?P<unit>w/w|v/v|wt\.?\s*%|vol\.?\s*%|%)?
    """,
    re.X | re.I,
)

# 단일값: 5%, 0.1 % w/w 등
CONC_SINGLE_RE = re.compile(
    r"""
    (?P<value>\d+(?:\.\d+)?)
    \s*(?P<unit>w/w|v/v|wt\.?\s*%|vol\.?\s*%|%)\b
    """,
    re.X | re.I,
)


@dataclass
class CompositionRow:
    cas: str = ""
    name: str = ""
    concentration_raw: str = ""
    conc_type: Optional[str] = None   # "range", "cmp", "single"
    conc_min: Optional[float] = None
    conc_max: Optional[float] = None
    conc_repr: Optional[float] = None
    unit: Optional[str] = None        # "%", "wt%", "vol%" 등
    source_line: str = ""             # 디버깅용


# ──────────────────────────────────────────────────────────────
# 유틸 함수들
# ──────────────────────────────────────────────────────────────

def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _norm_unit(unit: Optional[str]) -> Optional[str]:
    if not unit:
        return "%"
    u = unit.lower().replace(" ", "")
    if "wt" in u or "w/w" in u:
        return "wt%"
    if "vol" in u or "v/v" in u:
        return "vol%"
    if "%" in u:
        return "%"
    return unit.strip()


def _to_float(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# 농도(concentration) 파서
# ──────────────────────────────────────────────────────────────

def parse_concentration(text: str) -> Optional[Dict[str, Any]]:
    """
    주어진 문자열에서 농도(함유량) 정보를 파싱한다.
    우선순위: range → cmp → single
    """
    if not text:
        return None

    raw = _norm_space(text)

    # 1) 범위: "10 - 20%", "0.1~1 %", "0.1 - <1"
    m = CONC_RANGE_RE.search(raw)
    if m:
        v_min = _to_float(m.group("min"))
        v_max = _to_float(m.group("max"))
        unit = _norm_unit(m.group("unit"))
        conc_repr = None
        if v_min is not None and v_max is not None:
            conc_repr = (v_min + v_max) / 2.0   # ← 하한/상한 평균

        return {
            "concentration_raw": m.group(0).strip(),
            "conc_type": "range",
            "conc_min": v_min,
            "conc_max": v_max,
            "conc_repr": conc_repr,             # ← 대표값 = 평균
            "unit": unit,
        }

    # 2) 부등호: >= 10%, <1 %
    m = CONC_CMP_RE.search(raw)
    if m:
        value = _to_float(m.group("value"))
        unit = _norm_unit(m.group("unit"))
        op = m.group("op")
        conc_min = None
        conc_max = None
        if op in (">", ">="):
            conc_min = value
        else:  # "<" or "<="
            conc_max = value

        return {
            "concentration_raw": m.group(0).strip(),
            "conc_type": "cmp",
            "conc_min": conc_min,               # > 100이면 여기, < 100이면 아래
            "conc_max": conc_max,
            "conc_repr": value,                 # ← 대표값 = 원래 값 그대로
            "unit": unit,
        }

    # 3) 단일값: "5%", "0.1 % w/w"
    m = CONC_SINGLE_RE.search(raw)
    if m:
        value = _to_float(m.group("value"))
        unit = _norm_unit(m.group("unit"))
        return {
            "concentration_raw": m.group(0).strip(),
            "conc_type": "single",
            "conc_min": value,
            "conc_max": value,
            "conc_repr": value,
            "unit": unit,
        }

    return None


# ──────────────────────────────────────────────────────────────
# 섹션 3 전체 텍스트 → 조성표 추출
# ──────────────────────────────────────────────────────────────

def _clean_name(name: str) -> str:
    # 앞의 번호/기호 제거 (예: "1.", "가.", "•" 등)
    name = name.strip()
    name = re.sub(r"^[\-\*\u2022\uf0b7·\u00b7]+", "", name).strip()
    name = re.sub(r"^[0-9]+[\.\)]\s*", "", name).strip()
    name = re.sub(r"^[가-힣A-Za-z]\.\s*", "", name).strip()
    return name


def extract_section3_composition(sec3_text: str) -> Dict[str, Any]:
    """
    섹션 3 원문 텍스트에서 조성 정보를 추출한다.

    반환 형식:
    {
        "rows": [
            {
                "cas": "64-17-5",
                "name": "에탄올",
                "concentration_raw": "10 - 20%",
                "conc_type": "range",
                "conc_min": 10.0,
                "conc_max": 20.0,
                "conc_repr": 15.0,
                "unit": "%",
                "source_line": "에탄올 64-17-5 10 - 20%"
            },
            ...
        ],
        "engine": "sec3_line_cas",
        "success": True/False,
    }
    """
    if not sec3_text:
        return {"rows": [], "engine": "sec3_line_cas", "success": False}

    lines = [ln.rstrip() for ln in sec3_text.splitlines()]
    rows: List[CompositionRow] = []

    prev_nonempty: Optional[str] = None

    for idx, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # 헤더만 있는 줄은 대부분 CAS가 없음 → 바로 넘기기
        cas_matches = list(CAS_RE.finditer(line_stripped))
        if not cas_matches:
            prev_nonempty = line_stripped
            continue

        for m in cas_matches:
            cas = m.group("cas")

            # 이름 candidate: CAS 앞 부분
            prefix = line_stripped[: m.start()].strip(" \t|-")
            name = _clean_name(prefix)

            # 이름이 비어있거나 "CAS No" 같은 헤더 느낌이면 이전 줄을 이름 후보로 사용
            if not name or re.search(r"CAS\s*No", name, re.I):
                if prev_nonempty:
                    name = _clean_name(prev_nonempty)

            # 농도 candidate: CAS 뒤 + 필요시 다음 줄도 붙여서 검사
            substr_after_cas = line_stripped[m.end():]
            next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
            conc_info = (
                parse_concentration(substr_after_cas)
                or parse_concentration(line_stripped)
                or parse_concentration(next_line)
            )

            if conc_info is None:
                # 농도를 못 찾은 경우에도 최소한 CAS/이름은 기록해 둔다
                row = CompositionRow(
                    cas=cas,
                    name=name,
                    concentration_raw="",
                    conc_type=None,
                    conc_min=None,
                    conc_max=None,
                    conc_repr=None,
                    unit=None,
                    source_line=line_stripped,
                )
            else:
                row = CompositionRow(
                    cas=cas,
                    name=name,
                    concentration_raw=conc_info["concentration_raw"],
                    conc_type=conc_info["conc_type"],
                    conc_min=conc_info["conc_min"],
                    conc_max=conc_info["conc_max"],
                    conc_repr=conc_info["conc_repr"],
                    unit=conc_info["unit"],
                    source_line=line_stripped,
                )

            rows.append(row)

        prev_nonempty = line_stripped

    return {
        "rows": [asdict(r) for r in rows],
        "engine": "sec3_line_cas",
        "success": bool(rows),
    }


# 디버깅용 간단 테스트
if __name__ == "__main__":
    sample = """
    물질명        CAS No.       함유량(%)
    에탄올        64-17-5       10 - 20%
    물            7732-18-5     80~90 %
    불소계 용제   123-45-6      < 1 %
    """

    result = extract_section3_composition(sample)
    from pprint import pprint
    pprint(result)
