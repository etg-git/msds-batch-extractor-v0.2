# patterns/sec2_hazxard_info.py
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ---------------------------------------------------------------------------
# 공통 정규식
# ---------------------------------------------------------------------------
# H220, H280, H360D 이런 것까지 포함
H_CODE_RE = re.compile(r"\bH\d{3}[A-Z]?\b")
# P210, P301+P310 같은 조합까지 한 번에
P_CODE_RE = re.compile(r"\bP\d{3}(?:\+P\d{3})*\b")

# 신호어 라벨 / 값
SIGNAL_LABEL_RE = re.compile(r"(신호어|Signal\s*word)", re.IGNORECASE)
KOR_SIGNAL_RE = re.compile(r"(위험|경고)")
ENG_SIGNAL_RE = re.compile(r"\b(Danger|Warning)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# GHS 그림문자 매핑
#   - 키: GHS01 ~ GHS09
#   - 값: 관련된 H코드 집합
#   (완전한 목록은 아니고, 실무에서 자주 나오는 코드 중심으로 구성.
#    필요하면 나중에 여기만 추가해주면 됨.)
# ---------------------------------------------------------------------------
GHS_H_CODES: Dict[str, Set[str]] = {
    # GHS01: 폭발물 / 자체반응 / 유기과산화물 등
    "GHS01": {
        "H200", "H201", "H202", "H203", "H204", "H205",
        "H240", "H241",
    },
    # GHS02: 인화성 (가스/에어로졸/액체/고체 등)
    "GHS02": {
        "H220", "H221",  # Flammable gas
        "H222", "H223",  # Flammable aerosol
        "H224", "H225", "H226", "H228",  # Flammable liquid/solid
        "H230", "H231",  # May react explosively…
        "H242",          # Heating may cause a fire
        "H250", "H251", "H252",  # Pyrophoric / self-heating
        "H261",          # In contact with water releases flammable gas
    },
    # GHS03: 산화성
    "GHS03": {
        "H270", "H271", "H272",
    },
    # GHS04: 고압가스
    "GHS04": {
        "H280", "H281", "H282", "H283",
    },
    # GHS05: 부식성 (피부부식, 심한 눈손상, 금속부식)
    "GHS05": {
        "H290",          # May be corrosive to metals
        "H314",          # Causes severe skin burns and eye damage
        "H318",          # Causes serious eye damage
    },
    # GHS06: 급성 독성(치명적/유독)
    "GHS06": {
        "H300", "H301",
        "H310", "H311",
        "H330", "H331",
    },
    # GHS07: 자극/저독성 (피부·눈 자극, STOT SE, 피부감작성 등)
    "GHS07": {
        "H302", "H303",
        "H312", "H313",
        "H315", "H316",
        "H317",
        "H319", "H320",
        "H332",
        "H335",
    },
    # GHS08: 건강유해(발암성, 생식독성, STOT RE 등)
    "GHS08": {
        "H334",
        "H340", "H341",
        "H350", "H351",
        "H360", "H360D", "H360F",
        "H361", "H361d", "H361f",
        "H362",
        "H370", "H371",
        "H372", "H373",
    },
    # GHS09: 환경유해
    "GHS09": {
        "H400", "H401", "H402",
        "H410", "H411", "H412", "H413",
        "H420",
    },
}

# 그림문자 이미지 경로 (프로젝트 루트 기준으로 msds/image/GHS01.gif ...)
BASE_DIR = Path(__file__).resolve().parents[1]  # patterns/ 의 상위 폴더
GHS_IMAGE_DIR = BASE_DIR / "msds" / "image"


# ---------------------------------------------------------------------------
# 유틸 함수
# ---------------------------------------------------------------------------
def _sorted_codes(codes: Set[str]) -> List[str]:
    def _key(c: str) -> Tuple[int, str]:
        # 'H220', 'H360D' -> (220, 'D')
        num_match = re.search(r"(\d{3})", c)
        num = int(num_match.group(1)) if num_match else 999
        suffix = c[len("H") + 3:]
        return num, suffix
    return sorted(codes, key=_key)


def extract_h_and_p_codes(text: str) -> Dict[str, List[str]]:
    """
    섹션 2 본문에서 H코드, P코드를 전부 긁어오기.
    - hazard_codes: H220, H280, H360D ...
    - precautionary_codes_raw: P210, P301+P310 ...
    - precautionary_codes_flat: P210, P301, P310 ... (조합 풀어서 중복 제거)
    """
    text = text or ""

    # H코드
    h_codes: Set[str] = set(m.group(0).upper() for m in H_CODE_RE.finditer(text))

    # P코드 (조합 포함)
    p_raw: Set[str] = set(m.group(0).upper() for m in P_CODE_RE.finditer(text))
    p_flat: Set[str] = set()
    for raw in p_raw:
        # P301+P310 → P301, P310
        parts = raw.split("+")
        for p in parts:
            if p.startswith("P") and len(p) >= 4:
                p_flat.add(p)

    return {
        "hazard_codes": _sorted_codes(h_codes),
        "precautionary_codes_raw": sorted(p_raw),
        "precautionary_codes_flat": sorted(p_flat),
    }


def extract_signal_word(text: str) -> str:
    """
    섹션 2에서 신호어(위험/경고, Danger/Warning) 추출.
    1) '신호어:' / 'Signal word:' 라인 우선
    2) 없으면 전체 텍스트에서 처음 나오는 신호어를 사용
    """
    text = text or ""
    lines = text.splitlines()

    # 1) 라벨 기반
    for ln in lines:
        if SIGNAL_LABEL_RE.search(ln):
            # 라벨 부분 제거
            tail = SIGNAL_LABEL_RE.sub("", ln)
            tail = re.sub(r"[:：]\s*", " ", tail)
            # 한국어 우선
            m = KOR_SIGNAL_RE.search(tail)
            if m:
                return m.group(1)
            m = ENG_SIGNAL_RE.search(tail)
            if m:
                # Danger / Warning 의 대소문자 정리
                return m.group(1).title()

    # 2) fallback: 전체 텍스트에서 검색
    m = KOR_SIGNAL_RE.search(text)
    if m:
        return m.group(1)
    m = ENG_SIGNAL_RE.search(text)
    if m:
        return m.group(1).title()

    return ""


def infer_pictograms(h_codes: List[str]) -> List[Dict[str, str]]:
    """
    H코드 목록을 보고 필요한 GHS 그림문자를 추론.
    반환값 예시:
    [
      {"id": "GHS04", "image": ".../msds/image/GHS04.gif"},
      {"id": "GHS07", "image": ".../msds/image/GHS07.gif"},
    ]
    """
    h_set = {c.upper() for c in h_codes}
    used: Set[str] = set()

    for ghs_id, code_set in GHS_H_CODES.items():
        if h_set & code_set:
            used.add(ghs_id)

    pictos = []
    for ghs_id in sorted(used):
        img_path = GHS_IMAGE_DIR / f"{ghs_id}.gif"
        pictos.append({
            "id": ghs_id,
            "image": str(img_path),
        })
    return pictos


# ---------------------------------------------------------------------------
# 섹션 2 메인 파서
# ---------------------------------------------------------------------------
def parse_section_sec2_hazard(text: str) -> Dict[str, object]:
    """
    섹션 2 '유해·위험성에 관한 정보'용 파서.

    반환 예시:
    {
      "signal_word": "경고",
      "hazard_codes": ["H280"],
      "precautionary_codes_raw": ["P410+P403"],
      "precautionary_codes_flat": ["P403", "P410"],
      "pictograms": [
        {"id": "GHS04", "image": ".../msds/image/GHS04.gif"}
      ],
    }
    """
    text = text or ""
    codes = extract_h_and_p_codes(text)
    signal = extract_signal_word(text)
    pictos = infer_pictograms(codes["hazard_codes"])

    return {
        "signal_word": signal,
        **codes,
        "pictograms": pictos,
    }


# 디버그용(원하면 Streamlit에 붙이기 쉽게)
def parse_section_sec2_with_debug(text: str) -> Dict[str, object]:
    data = parse_section_sec2_hazard(text or "")
    debug = {
        "raw_text": text or "",
        "lines": (text or "").splitlines(),
    }
    return {
        "data": data,
        "debug": debug,
    }
