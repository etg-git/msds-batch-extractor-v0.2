# patterns/sec1_company_info.py
from __future__ import annotations
import re
from typing import Dict, List, Optional

from .utils_text import (
    squash_ws, strip_special_ws, best_label,
    split_label_value, split_label_value_smart,
    till_next_label, BULLET_RE
)
from .loader import SPLITTERS
# ──────────────────────────────────────────────────────────────────────────────
# 라벨 사전
# ──────────────────────────────────────────────────────────────────────────────
LABELS = {
    "product_name": [
        "제품명", "제품 명", "제품명칭", "상품명", "물질명", "물질의 명칭",
        "제품 식별자", "제 품 명",
        "Product name", "Product identifier", "Trade name",
    ],
    "company_name": [
        "회사명", "제조사명", "제조자", "제조 회사", "제조업체", "생산자",
        "공급자", "공급회사명", "판매사", "공급업체",
        "수입자", "수입사",
        "제조자명",
        "제조자/공급자", "제조자/공급자명",
        "생산업체", "생산업체 공급회사명",
        "생산 및 공급 회사명",
        "생산 및 공급자",
    ],
    "address": [
        "주소", "주 소", "소재지", "본사주소", "사업장주소", "사업장 소재지",
        "Address", "所在地",
    ],
}


VALUE_CLEANERS = [
    (re.compile(r"^Tel\s*[:：]?", re.IGNORECASE), ""),
]

NUM_ENUM_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.|[①-⑨])\s*")
KOR_ENUM_RE = re.compile(r"^\s*[가-힣]\.\s*")
BULLET_PREFIX_RE = re.compile(r"^\s*[-•●◦○]\s*")

JUNK_WORDS = ("정보", "기재", "경우", "문의", "연락")
COMPANY_HINT_RE = re.compile(
    r"(주식회사|\(주\)|㈜|회사|Co\.?|Ltd\.?|유한|\(유\)|산업|공업|Chemical|Chem|Gas|Corp\.?|Inc\.?)",
    re.IGNORECASE
)

PRODUCT_HINT_RE = re.compile(
    r"^(?=.*[A-Za-z가-힣])[A-Za-z0-9가-힣][A-Za-z0-9가-힣\s,#\-\.\(\)%/™]{1,160}$"
)
PRODUCT_FORBIDDEN = (
    "전화", "전화번호", "긴급", "tel", "fax",
    "주소", "회사", "제조", "공급자", "판매사",
    "권고 용도", "용도", "제한",
    "정보", "기재", "문의", "연락"
)

NEAR_SPAN = 6
ADDR_HINT_RE = re.compile(r"[시군구읍면동리로길]", re.UNICODE)
PHONE_RE = re.compile(
    r"\b(?:\+?\d{1,3}[-\s]?)?(0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4})\b",
    re.IGNORECASE
)

PROD_LINE_FALLBACKS = [
    re.compile(
        r"(?:제품\s*명|Product\s*(?:name|identifier)|Trade\s*name)\s*[:：]?\s*([^\s,;:/|]+(?:[-_/\.][^\s,;:/|]+)*)",
        re.IGNORECASE,
    ),
]
PROD_CODE_TOKEN_RE = re.compile(
    r"(?=.*[A-Za-z가-힣])(?=.*\d)[A-Za-z가-힣0-9][A-Za-z0-9#\-\._/]{1,}$"
)
WORD_ONLY_RE = re.compile(r"^[A-Za-z가-힣]{2,}$")

# 라벨 한줄 패턴
_COMPANY_LABEL_RE = re.compile(
    r"^(회사명|공급회사명|공급자명|제조자명|생산업체\s*공급회사명|생산\s*및\s*공급\s*회사명|Manufacturer|Supplier|수입자)\s*[:：]\s*(.+)$",
    re.IGNORECASE,
)

COMPANY_PREFIX_RE = re.compile(
    r"^(?:회사명|제조\s*회사|제조자|제조사명|제조업체명?|제조업체|공급자명?|공급자|공급회사명|공급업체|Manufacturer|Supplier|수입자)\s*[:：]?\s*",
    re.IGNORECASE,
)

# 'SP-33', 'IS-102K', 'R-134a' 같은 코드형 제품명
LETTER_CODE_RE = re.compile(r"\b[A-Za-z]{1,4}-\d+[A-Za-z0-9]*\b")

# ──────────────────────────────────────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────────────────────────────────────
def _prep_line(raw: str) -> str:
    s = strip_special_ws(raw)
    s = BULLET_RE.sub("", s)
    s = KOR_ENUM_RE.sub("", s)
    s = NUM_ENUM_RE.sub("", s)
    return s.strip()


def _strip_bullet(s: str) -> str:
    return BULLET_PREFIX_RE.sub("", s or "").strip()


def _clean_value(v: str) -> str:
    v = squash_ws(v or "")
    for rx, repl in VALUE_CLEANERS:
        v = rx.sub(repl, v)
    return v.strip(" -")


def _is_digit_code(v: str) -> bool:
    """
    제품명으로 허용할 '숫자 코드' 판정:
    - 공백 제거 후 전부 숫자
    - 길이 2~5 자리
    - 전화번호 패턴과는 매치되지 않을 것
    """
    v = squash_ws(v or "")
    return v.isdigit() and 2 <= len(v) <= 5 and not PHONE_RE.search(v)


def _is_garbage_company_value(v: str) -> bool:
    s = squash_ws(v or "").strip().lower()
    if not s:
        return True
    if s in {"정보", "information", "info"}:
        return True
    if any(tok in s for tok in [
        "정보(", "information:", "국내 공급자", "공급자 정보", "긴급 연락", "기재",
        "수입품의 경우", "연락 가능한", "담당자", "문의", "refer", "see", "해당 없음"
    ]):
        return True
    if any(tok in s for tok in [
        "주소", "address", "전화", "tel", "fax", "웹사이트", "homepage", "http", "www."
    ]):
        return True
    if len(s) <= 1 or re.fullmatch(r"[-–—:：\.]+", s):
        return True
    return False


def _normalize_company(val: str) -> str:
    # 1) 번호/불릿/이상한 공백 먼저 정리
    v = _prep_line(val or "")
    v = _clean_value(v)

    # 2) '회사명:', '제조 회사 :' 같은 라벨 제거
    v = COMPANY_PREFIX_RE.sub("", v)
    v = re.sub(r"\s*\(수입품의 경우.*?기재\)\s*$", "", v)
    v = v.strip(" -:·")

    # 3) 전화/팩스 정보가 붙어 있으면 그 앞까지만 사용
    v = re.split(r"(전화|tel|TEL|Phone|Fax|FAX)", v)[0].strip(" ,;:")

    # 4) 콤마로 회사명 + 주소/기타가 같이 있을 수 있으므로 콤마 앞까지만
    if "," in v:
        v = v.split(",", 1)[0].strip()

    if not v or _is_garbage_company_value(v) or PHONE_RE.search(v):
        return ""
    return v


def _looks_company_like(v: str) -> bool:
    if not v:
        return False
    if any(w in v for w in JUNK_WORDS):
        return bool(COMPANY_HINT_RE.search(v))
    return bool(COMPANY_HINT_RE.search(v)) or ("회사" in v)


def _has_forbidden_for_product(v: str) -> bool:
    return any(k in (v or "").lower() for k in PRODUCT_FORBIDDEN)


def _looks_product_like(v: str) -> bool:
    if not v:
        return False

    v = squash_ws(v)

    # 전화번호 / 금지 키워드 포함 라인은 제외
    if PHONE_RE.search(v) or _has_forbidden_for_product(v):
        return False

    # '정보', '문의' 같은 잡단어 섞여 있으면 제외
    if any(w in v for w in JUNK_WORDS):
        return False

    return bool(PRODUCT_HINT_RE.match(v))


def _split_for_address(line: str) -> tuple[str, str]:
    """
    주소 라벨 전용 split 함수.
    - '주소 : xxx', '주소   xxx', '사업장주소 xxx' 같은 패턴 모두 처리
    """
    s = _prep_line(line)

    # 0) '주소 (18630) 경기 …' 처럼 콜론 없이 라벨+값이 붙은 케이스
    m = re.match(
        r"^(주소|주\s*소|소재지|본사주소|사업장주소|사업장\s*소재지)\s*(.+)$",
        s,
    )
    if m:
        return m.group(1), m.group(2)

    # 1) '주소 :' / '사업장주소 :' 같은 패턴
    lab, val = split_label_value_smart(s, LABELS["address"])
    if val:
        return lab, val

    # 2) '주소: xxx' 같은 콜론/대시 분리
    lab, val = split_label_value(s)
    if val:
        return lab, val

    # 3) 공백 2칸 이상(2컬럼) 분리
    return _split_two_col(line)


def _address_from_company_line(raw: str) -> str:
    """
    '수입자: 회사명, 주소...' 처럼 회사/주소가 한 줄에 있을 때
    - 회사 라벨과 회사명을 제거하고
    - 첫 번째 콤마 뒤를 주소 후보로 본다.
    """
    if not raw:
        return ""

    s = _prep_line(raw)               # 불릿/번호 정리
    s = COMPANY_PREFIX_RE.sub("", s)  # '회사명:', 'Manufacturer:', '수입자:' 제거

    # 콤마가 없다면 주소가 같이 있지 않은 걸로 간주
    if "," not in s:
        return ""

    _, tail = s.split(",", 1)
    tail = tail.strip()

    # 전화/팩스 쪽은 잘라버림
    tail = re.split(r"(전화|Tel|TEL|Phone|Fax|FAX)", tail)[0]
    tail = tail.strip(" ,;:")
    if not tail:
        return ""

    # 주소 힌트(시/구/로/길 등)가 없으면 버림
    if not ADDR_HINT_RE.search(tail):
        return ""

    return tail


def _first_value_after_label(lines: List[str], label_idx: int) -> str:
    for j in range(label_idx + 1, min(len(lines), label_idx + 1 + NEAR_SPAN)):
        s = squash_ws(lines[j] or "")
        if not s:
            continue
        if _is_label_like(s) or PHONE_RE.search(s):
            break
        return s
    return ""


def _find_next_company(lines: List[str], start_idx: int) -> str:
    for j in range(start_idx + 1, min(len(lines), start_idx + 1 + NEAR_SPAN)):
        s = _clean_value(_prep_line(lines[j] or ""))
        if not s:
            continue
        if any(lbl in s for lbl in ["주소", "Address", "전화", "Tel", "Fax"]):
            break
        if (
            not _is_garbage_company_value(s)
            and _looks_company_like(s)
            and not PHONE_RE.search(s)
        ):
            return s
    return ""


def _apply_split(line: str, splitter_name: str, address_aliases=None):
    """
    YAML용 공용 split 함수.
    - colon_or_dash 의 경우: ':' 우선, 그다음 ' - ' 처럼 양옆에 공백이 있는 하이픈만 구분자로 사용.
      'SP-33', 'R-134a' 같이 토큰 안에 들어가는 하이픈은 절대 잘라내지 않는다.
    """
    s = strip_special_ws(line)
    s = BULLET_RE.sub("", s)
    s = KOR_ENUM_RE.sub("", s)
    s = NUM_ENUM_RE.sub("", s)

    if splitter_name == "prefix_smart":
        return split_label_value_smart(s, address_aliases or [])

    if splitter_name == "colon_or_dash":
        # 1) 콜론 기준
        m = re.match(r"^(.*?)[：:]\s*(.+)$", s)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        # 2) '라벨 - 값' (하이픈 양옆에 공백 있을 때만)
        m = re.match(r"^(.*?)\s*[-–—]\s+(.+)$", s)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return s, ""

    if splitter_name == "two_col_space":
        parts = re.split(r"(?:\s{2,}|\t+)", s, maxsplit=1)
        return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (s, "")

    if splitter_name == "loose_space":
        m = re.match(r"^(.+?)\s+([^:：\-].+)$", s)
        return (m.group(1).strip(), m.group(2).strip()) if m else (s, "")

    return s, ""


def _best_label(lab: str, aliases: List[str]) -> bool:
    best, _ = best_label(lab, aliases, threshold=0.72)
    return bool(best)

# ──────────────────────────────────────────────────────────────────────────────
# 제품명 토큰 선택기
# ──────────────────────────────────────────────────────────────────────────────
def _pick_product_token(v: str) -> str:
    if not v:
        return v

    # 3M™ 처럼 특정 패턴은 전체 문자열 우선
    if ("™" in v or "3M" in v) and "," in v and any(ch.isdigit() for ch in v):
        return squash_ws(v).strip(":- ")

    # 전화번호 제거 + 금지 키워드 제거
    v = PHONE_RE.sub("", v)
    for bad in PRODUCT_FORBIDDEN:
        v = re.sub(re.escape(bad), "", v, flags=re.IGNORECASE)
    v = squash_ws(v).strip(":- ")

    # 전체가 이미 제품명처럼 보이면 그대로 반환
    if _looks_product_like(v):
        return v

    # 토큰 단위로 다시 시도
    tokens = re.split(r"[,\s;/]+", v)
    for i, t in enumerate(tokens):
        t_clean = t.strip(":- ")
        if not t_clean:
            continue

        # 코드형(문자+숫자) 또는 순수 숫자 코드
        if PROD_CODE_TOKEN_RE.match(t_clean) or t_clean.isdigit():
            left_tokens: List[str] = []
            j = i - 1
            while j >= 0 and len(left_tokens) < 3:
                w = tokens[j].strip(":- ")
                if not w:
                    break
                # 2글자 이상 단어 또는 1글자 알파벳(R 등)은 허용
                if WORD_ONLY_RE.match(w) or re.fullmatch(r"[A-Za-z]", w):
                    left_tokens.append(w)
                    j -= 1
                else:
                    break
            left_tokens.reverse()

            # 왼쪽 한 글자(R) + 숫자 코드(134a) 조합이면 R-134a 로 붙이기
            if left_tokens:
                if (
                    len(left_tokens) == 1
                    and len(left_tokens[0]) == 1
                    and t_clean[0].isdigit()
                ):
                    phrase = f"{left_tokens[0]}-{t_clean}"
                else:
                    phrase = " ".join(left_tokens + [t_clean]).strip()
            else:
                phrase = t_clean

            if 0 < len(phrase) <= 64 and _looks_product_like(phrase):
                return phrase
            if _looks_product_like(t_clean):
                return t_clean

            # 숫자 코드(예: 630) – 글자가 없어도 코드로 허용되는 경우
            if _is_digit_code(t_clean):
                return t_clean

    # 마지막 fallback: 개별 토큰 중 하나라도 그럴듯하면 사용
    for t in tokens:
        t = t.strip(":- ")
        if t and _looks_product_like(t):
            return t

    return ""


def _pick_product(val: str) -> str:
    return _pick_product_token(val)

# ──────────────────────────────────────────────────────────────────────────────
# block_bullet 엔진
# ──────────────────────────────────────────────────────────────────────────────
def _apply_block_bullet(lines: List[str], pack: dict, out: Dict[str, str]) -> Dict[str, str]:
    """
    불릿형(가./○/-) 서브블록 처리.
    - '다. 공급자 정보' 같은 라벨 라인 아래에
      '수입자: 회사명, 주소...' 형식이 오는 벤더를 타겟으로 함.
    """
    stop_res = []
    for m in (pack.get("stop_markers") or []):
        try:
            stop_res.append(re.compile(m))
        except re.error:
            pass

    la = pack.get("label_aliases", {}) or {}
    prod_alias = la.get("product_name", [])
    comp_alias = la.get("company_name", [])
    addr_alias = la.get("address", [])

    validators = (pack.get("validators") or {}).get("product", {})
    forbid_kw = validators.get("forbid_keywords", PRODUCT_FORBIDDEN)
    require_letter = validators.get("require_letter", True)
    forbid_phone = validators.get("forbid_phone", True)

    def _is_stop(s: str) -> bool:
        return any(rx.search(s) for rx in stop_res)

    N = len(lines)
    i = 0
    while i < N:
        raw_line = lines[i] or ""
        label_line = _prep_line(raw_line)  # '다. 공급자 정보' -> '공급자 정보'

        for tgt, aliases in (
            ("product_name", prod_alias),
            ("company_name", comp_alias),
            ("address", addr_alias),
        ):
            # product/address 는 이미 값 있으면 건너뛰고,
            # company 는 주소가 비어 있을 때 한 번 더 보도록 예외 처리
            if tgt == "product_name" and out.get("product_name"):
                continue
            if tgt == "address" and out.get("address"):
                continue
            if tgt == "company_name" and out.get("company_name") and out.get("address"):
                continue

            if not aliases:
                continue

            best, _ = best_label(label_line, aliases, threshold=0.72)
            if not best:
                continue

            # 이 라인은 라벨이므로, 아래 줄들(가/나/다/○/전화 등 stop 이전)을 한 덩어리로 모은다
            j = i + 1
            buf: List[str] = []
            while j < N:
                ss = squash_ws(lines[j] or "")
                if not ss:
                    j += 1
                    continue
                if _is_stop(ss):
                    break
                buf.append(_strip_bullet(ss))
                j += 1

            val_join = squash_ws(" ".join(buf)).strip()

            if tgt == "product_name":
                cand = _pick_product_token(val_join)
                if _valid_product(cand, forbid_kw, require_letter, forbid_phone):
                    out["product_name"] = cand

            elif tgt == "company_name":
                # 이 벤더에서는 보통 buf[0] == '수입자: 회사명, 주소...'
                first = buf[0] if buf else val_join

                # 1) 회사명
                cand = _normalize_company(first)
                if not cand:
                    cand = _find_next_company(lines, i)
                if cand and _looks_company_like(cand) and not PHONE_RE.search(cand):
                    # seed 로 이미 company_name 이 있어도, 값이 비어있지 않으면 덮지 말고 유지
                    if not out.get("company_name"):
                        out["company_name"] = cand

                    # 2) 주소: 같은 줄 꼬리에서 강제 분리
                    if not out.get("address"):
                        addr_from_company = _address_from_company_line(first)
                        if addr_from_company:
                            out["address"] = addr_from_company

            else:  # tgt == "address"
                cand = _clean_value(val_join)
                if cand:
                    out["address"] = cand

        i += 1

    return out

# ──────────────────────────────────────────────────────────────────────────────
# YAML 패턴팩 적용
# ──────────────────────────────────────────────────────────────────────────────
def extract_section1_fields_with_packs(
    text: str,
    packs: List[dict],
    seed: Dict[str, str] | None = None,
) -> Dict[str, str]:
    out = {"product_name": "", "company_name": "", "address": ""}
    if seed:
        out.update({k: (seed.get(k) or "") for k in out})

    lines = [l for l in (text or "").splitlines() if l]

    if not packs:
        return out

    for pack in packs:
        # 0) block_bullet
        bb = pack.get("block_bullet")
        if bb:
            out = _apply_block_bullet(lines, bb, out)
            if all(out.values()):
                break

        # 1) split/label
        labels = pack.get("labels", {}) or {}
        validators = pack.get("validators", {}) or {}
        addr_aliases = labels.get("address", {}).get("aliases", [])
        forbid_kw = validators.get("product", {}).get("forbid_keywords", [])
        require_letter = validators.get("product", {}).get("require_letter", True)
        forbid_phone = validators.get("product", {}).get("forbid_phone", True)

        for idx, ln in enumerate(lines):
            # 주소
            if not out["address"] and "address" in labels:
                for sp in labels["address"].get("split", []):
                    lab, val = _apply_split(ln, sp, address_aliases=addr_aliases)
                    if val and _best_label(lab, addr_aliases):
                        out["address"] = _clean_value(val)
                        break

            # 회사명
            if not out["company_name"] and "company" in labels:
                comp_alias = labels["company"].get("aliases", []) or LABELS["company_name"]
                for sp in labels["company"].get("split", []):
                    lab, val = _apply_split(ln, sp)
                    if _best_label(lab, comp_alias):
                        raw = val if val else _first_value_after_label(lines, idx)

                        # 1) 회사명
                        cand = _normalize_company(raw) if raw else ""
                        if not cand:
                            cand = _find_next_company(lines, idx)
                        if cand and _looks_company_like(cand) and not PHONE_RE.search(cand):
                            out["company_name"] = cand

                            # 2) 같은 줄 꼬리에서 주소도 시도 (수입자: 회사, 주소... 케이스)
                            if not out["address"]:
                                addr_from_company = _address_from_company_line(ln)
                                if addr_from_company:
                                    out["address"] = addr_from_company
                            break

            # 제품명
            if not out["product_name"] and "product" in labels:
                prod_alias = labels["product"].get("aliases", [])
                for sp in labels["product"].get("split", []):
                    lab, val = _apply_split(ln, sp)
                    if _best_label(lab, prod_alias):
                        raw = val if val else _first_value_after_label(lines, idx)
                        cand = _pick_product(_clean_value(raw)) if raw else ""
                        if cand and _valid_product(cand, forbid_kw, require_letter, forbid_phone):
                            out["product_name"] = cand
                            break

        if all(out.values()):
            break

    # 회사명 보정: 라벨 한줄 + 다음 줄 후보
    if not out["company_name"]:
        for i, raw in enumerate(lines):
            s = _prep_line(raw)
            m = _COMPANY_LABEL_RE.match(s)
            if not m:
                continue
            cand = _normalize_company(m.group(2))
            if not cand:
                cand = _find_next_company(lines, i)
            if cand and _looks_company_like(cand) and not PHONE_RE.search(cand):
                out["company_name"] = cand
                break

    # 반환 직전 한 번 더 정규화(안전장치)
    out["company_name"] = _normalize_company(out["company_name"])
    return out

# ──────────────────────────────────────────────────────────────────────────────
# 인라인/근접/전역 + 페일세이프 (base extractor)
# ──────────────────────────────────────────────────────────────────────────────
def _inline_try_pc(line: str, want_aliases: List[str], is_product: bool = False) -> Optional[str]:
    lab, val = _split_no_prefix_for_pc(line)
    if not val:
        return None
    best, _ = best_label(lab, want_aliases, threshold=0.72)
    if not best:
        return None
    val = _clean_value(val)
    if is_product:
        val = _pick_product_token(val)
    return val or None


def _inline_try_addr(line: str) -> Optional[str]:
    raw = _prep_line(line)

    # 1) '주소 + 값' (공백 없어도 OK)
    m = re.match(
        r"^(주소|주\s*소|소재지|본사주소|사업장주소|사업장\s*소재지)\s*(.+)$",
        raw,
    )
    if m:
        return _clean_value(m.group(2))

    # 2) 일반 split
    lab, val = _split_for_address(raw)
    if val:
        best, _ = best_label(lab, LABELS["address"], threshold=0.72)
        if best:
            return _clean_value(val)

    return None


def _block_after(lines: List[str], idx: int) -> str:
    return _clean_value(till_next_label(lines, idx + 1, stop_at_blank=True))


def _is_label_like(line: str) -> bool:
    s = squash_ws(line)
    return (
        any(k in s for k in ("제품명", "회사명", "주소"))
        or s.endswith(("권고 용도", "사용상의 제한", "정보 기재", "공급자 정보"))
    )


def _nearest_value_after(lines: List[str], label_idx: int, check_fn, max_look: int = NEAR_SPAN) -> str:
    for i in range(label_idx + 1, min(len(lines), label_idx + 1 + max_look)):
        ln = squash_ws(lines[i])
        if not ln or PHONE_RE.search(ln):
            continue
        if _is_label_like(ln):
            break
        if check_fn(ln):
            return ln
    return ""


def _nearest_value_before(lines: List[str], label_idx: int, check_fn, max_look: int = NEAR_SPAN) -> str:
    for i in range(label_idx - 1, max(-1, label_idx - max_look), -1):
        ln = squash_ws(lines[i])
        if not ln or PHONE_RE.search(ln):
            continue
        if _is_label_like(ln):
            break
        if check_fn(ln):
            return ln
    return ""


def _global_best(
    lines: List[str],
    check_fn,
    prefer_re: Optional[re.Pattern] = None,
    post=None,
) -> str:
    best = ""
    best_score = -1.0
    for ln in lines:
        s = squash_ws(ln)
        if not s or _is_label_like(s) or PHONE_RE.search(s):
            continue
        if check_fn(s):
            val = post(s) if post else s
            if not val or PHONE_RE.search(val):
                continue
            if check_fn is _looks_product_like and _has_forbidden_for_product(val):
                continue
            score = 2.0
            if prefer_re and prefer_re.search(val):
                score += 2.0
            score += max(0, 20 - len(val)) / 10.0
            if score > best_score:
                best_score, best = score, val
    return best


def _fallback_product_from_text(text: str) -> str:
    for rx in PROD_LINE_FALLBACKS:
        m = rx.search(text)
        if m:
            cand = _pick_product_token(m.group(1))
            if cand and _looks_product_like(cand):
                return cand
    win = re.search(
        r"(제품\s*명|Product\s*(?:name|identifier)|Trade\s*name).{0,40}",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if win:
        tail = win.group(0)
        for m in re.finditer(r"[A-Za-z가-힣0-9][A-Za-z가-힣0-9\-\._/]{1,}", tail):
            tok = _pick_product_token(m.group(0))
            if tok and _looks_product_like(tok):
                return tok
    return ""


def _refine_product_from_text(text: str, cur: str) -> str:
    """
    섹션1 전체 텍스트를 보고 제품명을 살짝 보정.

    - 섹션 1 안에서 SP-33, IS-102K, R-134a 같은
      '문자 1~4개 - 숫자들 (+옵션 알파벳/숫자)' 패턴을 모두 찾는다.
    - 현재 제품명(cur)이 이들 중 하나와 대소문자 무시 비교로 일치하면 그대로 유지.
    - 현재 제품명이 숫자 코드(630) 이고, 텍스트 안에 이런 코드형 제품명이
      하나라도 있으면 그 코드형 제품명을 우선 사용한다.
    - 아무 후보도 없으면 cur 를 그대로 반환.
    """
    text = text or ""
    cur = (cur or "").strip()
    if not text:
        return cur

    # 섹션1 전체에서 후보 코드형 제품명들 뽑기
    candidates = LETTER_CODE_RE.findall(text)
    if not candidates:
        return cur

    # 전부 공백/중복 정리
    norm_cands = []
    seen = set()
    for c in candidates:
        c_norm = squash_ws(c).strip(" :-")
        if not c_norm:
            continue
        key = c_norm.lower()
        if key in seen:
            continue
        seen.add(key)
        norm_cands.append(c_norm)

    if not norm_cands:
        return cur

    # 1) 현재 값이 이미 후보 중 하나라면 그대로 둠
    if cur:
        cur_norm = cur.strip().lower()
        for c in norm_cands:
            if c.lower() == cur_norm:
                return c  # 같은 값이니 그냥 정규화된 후보로

    # 2) 현재 값이 순수 숫자 코드(예: 630, 134a 제외)라면
    #    섹션 텍스트에 있는 코드형 후보 중 첫 번째를 사용
    if cur and _is_digit_code(cur):
        return norm_cands[0]

    # 3) 그 외에는:
    #    - cur 가 비어 있으면 첫 후보 사용
    #    - cur 가 있고, 길이가 너무 짧거나 숫자+문자 혼합이지만 형태가 애매하면
    #      그래도 코드형 후보가 더 그럴듯하므로 첫 후보로 교체
    if not cur:
        return norm_cands[0]

    # cur 가 "134a" 처럼 숫자로 시작하는 혼합코드인 경우 → 후보로 보정 (R-134a 등)
    if re.fullmatch(r"\d+[A-Za-z]*", cur):
        return norm_cands[0]

    # 그 외에는 기존 값 유지
    return cur


def extract_section1_fields(text: str) -> Dict[str, str]:
    out = {"product_name": "", "company_name": "", "address": ""}
    if not text:
        return out

    lines = [l for l in (text or "").splitlines() if l is not None]

    # ─────────────────────────────────────────
    # 1차 인라인 스캔
    # ─────────────────────────────────────────
    for ln in lines:
        # 제품명
        if not out["product_name"]:
            v = _inline_try_pc(ln, LABELS["product_name"], is_product=True)
            if v and (_looks_product_like(v) or _is_digit_code(v)):
                out["product_name"] = v

        # 회사명 + 같은 줄 주소
        if not out["company_name"]:
            v = _inline_try_pc(ln, LABELS["company_name"])
            v_norm = _normalize_company(v) if v else ""
            if v_norm and _looks_company_like(v_norm):
                out["company_name"] = v_norm

                if not out["address"]:
                    addr_from_company = _address_from_company_line(ln)
                    if addr_from_company:
                        out["address"] = addr_from_company

        # 주소 인라인
        if not out["address"]:
            v = _inline_try_addr(ln)
            if v:
                out["address"] = v

    # ─────────────────────────────────────────
    # 주소 보정
    # ─────────────────────────────────────────
    if not out["address"]:
        idxs = []
        for i, ln in enumerate(lines):
            lab, _ = _split_for_address(ln)
            best, _ = best_label(lab, LABELS["address"], threshold=0.72)
            if best:
                idxs.append(i)

        found = ""
        for idx in idxs:
            cand = _block_after(lines, idx) or _nearest_value_after(
                lines, idx, lambda v: bool(ADDR_HINT_RE.search(v))
            )
            if cand:
                found = cand
                break

        if not found:
            found = _global_best(lines, lambda v: bool(ADDR_HINT_RE.search(v)))

        if found:
            out["address"] = _clean_value(found)

        # fallback 1: "주소" 라인 + 같은 줄/다음 줄에서 강제 추출
        if not out["address"]:
            for i, raw in enumerate(lines):
                # 현재 줄 + 다음 줄까지 하나의 윈도우로 본다
                window = (raw or "") + " " + (lines[i + 1] if i + 1 < len(lines) else "")
                if "주소" not in window:
                    continue

                win_norm = _prep_line(window)
                m = re.search(r"주소\s*[:：]?\s*(.+)$", win_norm)
                if not m:
                    continue

                cand = m.group(1)
                # 전화/팩스/긴급 같은 꼬리 제거
                cand = re.split(r"(긴급|전화|Tel|TEL|Phone|Fax|FAX)", cand)[0]
                cand = cand.strip(" ,;:-")

                # 진짜 주소처럼 보이는지 (시/군/구/읍/면/동/리/로/길 포함)
                if not ADDR_HINT_RE.search(cand):
                    continue

                cleaned = _clean_value(cand)
                if cleaned:
                    out["address"] = cleaned
                    break

        # fallback 2: "주소 값" (콜론 없이 붙은 케이스)
        if not out["address"]:
            for ln in lines:
                raw = _prep_line(ln)
                m = re.match(
                    r"^(주소|소재지|본사주소|사업장주소|사업장\s*소재지)\s*(.+)$",
                    raw,
                )
                if m:
                    out["address"] = _clean_value(m.group(2))
                    break

    # ─────────────────────────────────────────
    # 회사명 보정
    # ─────────────────────────────────────────
    if not out["company_name"]:
        for i, raw in enumerate(lines):
            s = _prep_line(raw)
            m = _COMPANY_LABEL_RE.match(s)
            if not m:
                continue
            cand = _normalize_company(m.group(2))
            if not cand:
                cand = _find_next_company(lines, i)
            if cand and _looks_company_like(cand) and not PHONE_RE.search(cand):
                out["company_name"] = cand
                break

        if not out["company_name"]:
            for raw in lines:
                s = _prep_line(raw)
                m2 = re.search(r"회사명\s*[:：]?\s*(.+)$", s)
                if not m2:
                    continue
                cand = _normalize_company(m2.group(1))
                if cand and _looks_company_like(cand) and not PHONE_RE.search(cand):
                    out["company_name"] = cand
                    break

        if not out["company_name"]:
            found = _global_best(
                lines,
                lambda v: (not _is_garbage_company_value(v)) and _looks_company_like(v),
                prefer_re=COMPANY_HINT_RE,
            )
            found = _normalize_company(found)
            if found and _looks_company_like(found):
                out["company_name"] = found

    # ─────────────────────────────────────────
    # 제품명 보정
    # ─────────────────────────────────────────
    if not out["product_name"]:
        idxs = []
        for i, ln in enumerate(lines):
            lab, _ = _split_no_prefix_for_pc(ln)
            best, _ = best_label(lab, LABELS["product_name"], threshold=0.72)
            if best:
                idxs.append(i)

        found = ""
        for idx in idxs:
            cand = _inline_try_pc(lines[idx], LABELS["product_name"], is_product=True)
            if not cand:
                nxt = _first_value_after_label(lines, idx)
                if nxt:
                    cand_try = _pick_product_token(_clean_value(nxt))
                    if cand_try and _looks_product_like(cand_try):
                        cand = cand_try
            cand = cand or _nearest_value_after(lines, idx, _looks_product_like)
            cand = cand or _nearest_value_before(lines, idx, _looks_product_like)
            if cand and _looks_product_like(cand):
                found = cand
                break

        if not found:
            code_like = re.compile(
                r"(?=.*[A-Za-z])(?=.*\d)^[A-Za-z0-9][A-Za-z0-9\-\._/]{1,}$"
            )
            found = _global_best(
                lines,
                _looks_product_like,
                prefer_re=code_like,
                post=_pick_product_token,
            )
        if not found:
            found = _fallback_product_from_text("\n".join(lines))
        if found and _looks_product_like(found):
            out["product_name"] = found

    # 마지막 안전장치
    out["company_name"] = _normalize_company(out["company_name"])
    return out




# ──────────────────────────────────────────────────────────────────────────────
# 제품명 유효성 검사
# ──────────────────────────────────────────────────────────────────────────────
def _valid_product(
    val: str,
    forbid_kw: List[str],
    require_letter: bool = True,
    forbid_phone: bool = True,
) -> bool:
    if not val:
        return False

    v = squash_ws(val)
    has_letter = bool(re.search(r"[A-Za-z가-힣]", v))

    # 글자가 없으면: '숫자 코드'만 예외적으로 허용
    if require_letter and not has_letter:
        if _is_digit_code(v):
            return True   # ← 제품명 630 같은 케이스
        return False

    if forbid_phone and PHONE_RE.search(v):
        return False

    low = v.lower()
    if any(k.lower() in low for k in (forbid_kw or [])):
        return False

    # 여기까지 왔는데 숫자 코드면 그대로 통과
    if _is_digit_code(v):
        return True

    # 나머지는 전부 일반 제품명 규칙을 따른다
    return _looks_product_like(v)


def _split_two_col(raw: str) -> tuple[str, str]:
    s = _prep_line(raw)
    m = re.split(r"(?:\s{2,}|\t+)", s, maxsplit=1)
    return (m[0].strip(), m[1].strip()) if len(m) == 2 else (s, "")


def _split_loose_one_space(raw: str) -> tuple[str, str]:
    s = _prep_line(raw)
    m = re.match(r"^(.+?)\s+([^:：\-].+)$", s)
    return (m.group(1).strip(), m.group(2).strip()) if m else (s, "")


def _split_label_value_pc(raw: str) -> tuple[str, str]:
    """
    제품명/회사명 전용 라벨 분리.
    - ':' 기준 우선
    - 그다음 '라벨   값' (2칸 이상 공백)
    - 마지막으로 '라벨 값' 한 칸
    하이픈('-')은 절대 구분자로 쓰지 않는다. (R-134a, SP-33 보호)
    """
    s = _prep_line(raw)

    # 1) 콜론
    m = re.match(r"^(.*?)[：:]\s*(.+)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # 2) 두 칸 이상 공백
    parts = re.split(r"(?:\s{2,}|\t+)", s, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()

    # 3) 한 칸 공백: 단순히 나눠서 label/value 로 사용
    m = re.match(r"^(.+?)\s+(.+)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    return s, ""


def _split_no_prefix_for_pc(line: str) -> tuple[str, str]:
    lab, val = _split_label_value_pc(line)
    if val:
        return lab, val
    lab, val = _split_two_col(line)
    if val:
        return lab, val
    return _split_loose_one_space(line)

# ──────────────────────────────────────────────────────────────────────────────
# 섹션 1용 공용 래퍼 (기존 코드 유지 + 이름만 맞춰주기)extract_section1_fields
# ──────────────────────────────────────────────────────────────────────────────
def extract_section1_company_info(
    text: str,
    packs: List[dict] | None = None,
    seed: Dict[str, str] | None = None,
) -> Dict[str, str]:
    """
    섹션 1 공통 래퍼.
    - packs가 있으면: YAML 패턴팩 먼저 적용
    - 그 결과에 base extractor(extract_section1_fields) 결과를 머지해서
      빠진 값(특히 address)을 채워 넣는다.
    """
    text = text or ""

    if packs:
        # 1) 패턴팩 기반 1차 추출
        data = extract_section1_fields_with_packs(text, packs, seed=seed) or {
            "product_name": "",
            "company_name": "",
            "address": "",
        }

        # 2) base extractor 로 fallback 값 추출
        base = extract_section1_fields(text)

        # 주소가 비어 있으면 base 주소로 보충
        if not (data.get("address") or "").strip() and base.get("address"):
            data["address"] = base["address"]

        # 회사명/제품명도 비어 있으면 base 값 사용 (선택)
        if not (data.get("company_name") or "").strip() and base.get("company_name"):
            data["company_name"] = base["company_name"]
        if not (data.get("product_name") or "").strip() and base.get("product_name"):
            data["product_name"] = base["product_name"]

    else:
        # 패턴팩 없으면 기존대로 base extractor만 사용
        data = extract_section1_fields(text)

    # 섹션 전체를 보고 SP-33 / R-134a 같은 코드형 제품명 보정
    data["product_name"] = _refine_product_from_text(
        text, data.get("product_name") or ""
    )
    return data


def parse_section_sec1_with_debug(
    text: str,
    packs: List[dict] | None = None,
    seed: Dict[str, str] | None = None,
) -> Dict[str, dict]:
    """
    Streamlit 디버그/프리뷰용 래퍼.
    patterns.__init__ / msds_streamlit_app 쪽에서 이 이름을 import 할 수 있음.
    """
    data = extract_section1_company_info(text or "", packs=packs, seed=seed)

    debug = {
        "raw_text": text or "",
        "lines": (text or "").splitlines(),
        "packs_count": len(packs or []),
    }

    return {
        "data": data,
        "debug": debug,
    }


def preview_packs_sec1(packs: List[dict], sample_text: str | None = None) -> List[dict]:
    """
    섹션 1용 패턴팩 프리뷰.
    - UI에서 '어떤 패턴팩이 적용돼 있는지' 대략적으로만 보여줄 때 사용.
    - 기존 코드가 단순히 리스트를 받아서 뿌리는 형태라면 이 정도 스펙이면 충분.
    """
    previews: List[dict] = []
    if not packs:
        return previews

    for idx, pack in enumerate(packs):
        name = pack.get("name") or pack.get("id") or f"pack_{idx}"
        info = {
            "idx": idx,
            "name": name,
            "has_block_bullet": bool(pack.get("block_bullet")),
            "has_labels": bool(pack.get("labels")),
            "has_validators": bool(pack.get("validators")),
        }

        # 샘플 텍스트가 들어온 경우, 간단히 한 번 돌려봄 (에러 나도 앱 죽지 않게 try)
        if sample_text:
            try:
                fields = extract_section1_fields_with_packs(sample_text, [pack])
                info["sample_company_name"] = fields.get("company_name") or ""
                info["sample_product_name"] = fields.get("product_name") or ""
            except Exception:
                info["sample_company_name"] = ""
                info["sample_product_name"] = ""

        previews.append(info)

    return previews
