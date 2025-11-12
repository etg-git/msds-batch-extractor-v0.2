# patterns/sec1_company_info.py
from __future__ import annotations
import re
from typing import Dict, List, Optional
from .utils_text import (
    squash_ws, strip_special_ws, best_label,
    split_label_value, split_label_value_smart,
    till_next_label, BULLET_RE
)

LABELS = {
    "product_name": [
        "제품명", "제품 명", "제품명칭", "상품명", "물질명", "물질의 명칭",
        "제품 식별자", "제 품 명",
        "Product name", "Product identifier", "Trade name",
    ],
    "company_name": [
        "회사명", "제조사명", "제조자", "제조 회사", "제조업체", "생산자",
        "공급자", "공급회사명", "판매사", "공급업체",
        "Manufacturer", "Supplier",
    ],
    "address": [
        "주소", "소재지", "본사주소", "사업장주소", "사업장 소재지",
        "Address", "所在地",
    ],
}

VALUE_CLEANERS = [
    (re.compile(r"^Tel\s*[:：]?", re.IGNORECASE), ""),
]

JUNK_WORDS = ("정보", "기재", "경우", "문의", "연락")
COMPANY_HINT_RE = re.compile(r"(주식회사|\(주\)|㈜|회사|Co\.?|Ltd\.?|유한|산업|공업|Chemical|Chem|Gas)", re.IGNORECASE)

# 제품명은 글자 1개 이상 포함(+ 숫자/기호 허용)
PRODUCT_HINT_RE = re.compile(
    r"^(?=.*[A-Za-z가-힣])[A-Za-z0-9가-힣][A-Za-z0-9가-힣\s\-\.\(\)%/]{1,60}$"
)

PRODUCT_FORBIDDEN = (
    "전화", "전화번호", "긴급", "tel", "fax",
    "주소", "회사", "제조", "공급자", "판매사",
    "권고 용도", "용도", "제한",
    "정보", "기재", "문의", "연락"
)

NEAR_SPAN = 6
ADDR_HINT_RE = re.compile(r"(시|군|구|읍|면|동|리|로|길)\s*\d", re.UNICODE)
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-\s]?)?(0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4})\b", re.IGNORECASE)
KOR_ENUM_RE = re.compile(r"^\s*[가-힣]\.\s*")

# ✅ 제품명 ‘문장 내’ 페일세이프 (라벨 근처 한 줄/윈도우 스캔)
PROD_LINE_FALLBACKS = [
    re.compile(r"(?:제품\s*명|Product\s*(?:name|identifier)|Trade\s*name)\s*[:：]?\s*([^\s,;:/|]+(?:[-_/\.][^\s,;:/|]+)*)", re.IGNORECASE),
]
PROD_CODE_TOKEN_RE = re.compile(r"(?=.*[A-Za-z가-힣])(?=.*\d)[A-Za-z가-힣0-9][A-Za-z가-힣0-9\-\._/]{1,}$")

def _clean_value(v: str) -> str:
    v = squash_ws(v)
    for rx, repl in VALUE_CLEANERS:
        v = rx.sub(repl, v)
    return v.strip(" -")

def _looks_company_like(v: str) -> bool:
    if not v:
        return False
    if any(w in v for w in JUNK_WORDS):
        return bool(COMPANY_HINT_RE.search(v))
    return bool(COMPANY_HINT_RE.search(v)) or ("회사" in v)

def _has_forbidden_for_product(v: str) -> bool:
    low = v.lower()
    return any(k in low for k in PRODUCT_FORBIDDEN)

def _looks_product_like(v: str) -> bool:
    if not v:
        return False
    if v.isdigit() or PHONE_RE.search(v) or _has_forbidden_for_product(v):
        return False
    if any(w in v for w in JUNK_WORDS):
        return False
    return bool(PRODUCT_HINT_RE.match(v))

def _prep_line(raw: str) -> str:
    s = strip_special_ws(raw)
    s = BULLET_RE.sub("", s)
    s = KOR_ENUM_RE.sub("", s)
    return s.strip()

def _split_two_col(raw: str) -> tuple[str, str]:
    s = _prep_line(raw)
    m = re.split(r"(?:\s{2,}|\t+)", s, maxsplit=1)
    if len(m) == 2:
        return m[0].strip(), m[1].strip()
    return s, ""

def _split_loose_one_space(raw: str) -> tuple[str, str]:
    s = _prep_line(raw)
    m = re.match(r"^(.+?)\s+([^:：\-].+)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return s, ""

def _split_no_prefix_for_pc(line: str) -> tuple[str, str]:
    lab, val = split_label_value(_prep_line(line))
    if val:
        return lab, val
    lab, val = _split_two_col(line)
    if val:
        return lab, val
    lab, val = _split_loose_one_space(line)
    return lab, val

def _split_for_address(line: str) -> tuple[str, str]:
    s = _prep_line(line)
    lab, val = split_label_value(s)
    if val:
        return lab, val
    lab, val = _split_two_col(s)
    if val:
        return lab, val
    lab, val = split_label_value_smart(s, LABELS["address"])
    return lab, val

def _pick_product_token(v: str) -> str:
    if not v:
        return v
    v = PHONE_RE.sub("", v)
    for bad in PRODUCT_FORBIDDEN:
        v = re.sub(re.escape(bad), "", v, flags=re.IGNORECASE)
    v = squash_ws(v).strip(":- ")
    if _looks_product_like(v):
        return v
    tokens = re.split(r"[,\s;/]+", v)
    for t in tokens:
        t = t.strip(":- ")
        if t and PROD_CODE_TOKEN_RE.match(t) and _looks_product_like(t):
            return t
    for t in tokens:
        t = t.strip(":- ")
        if t and _looks_product_like(t):
            return t
    return ""

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
    lab, val = _split_for_address(line)
    if not val:
        return None
    best, _ = best_label(lab, LABELS["address"], threshold=0.72)
    if not best:
        return None
    return _clean_value(val)

def _block_after(lines: List[str], idx: int) -> str:
    return _clean_value(till_next_label(lines, idx + 1, stop_at_blank=True))

def _is_label_like(line: str) -> bool:
    s = squash_ws(line)
    return (
        any(k in s for k in ("제품명", "회사명", "주소")) or
        s.endswith(("권고 용도", "사용상의 제한", "정보 기재", "공급자 정보"))
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

def _global_best(lines: List[str], check_fn, prefer_re: Optional[re.Pattern] = None, post=None) -> str:
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

# 🔒 제품명 전용 페일세이프: 한 줄 정규식 & 윈도우 스캔
def _fallback_product_from_text(text: str) -> str:
    # 1) 한 줄 정규식
    for rx in PROD_LINE_FALLBACKS:
        m = rx.search(text)
        if m:
            cand = _pick_product_token(m.group(1))
            if cand and _looks_product_like(cand):
                return cand
    # 2) 라벨 주변 40자 윈도우
    win = re.search(r"(제품\s*명|Product\s*(?:name|identifier)|Trade\s*name).{0,40}", text, re.IGNORECASE | re.DOTALL)
    if win:
        tail = win.group(0)
        # 코드형 토큰 우선
        for m in re.finditer(r"[A-Za-z가-힣0-9][A-Za-z가-힣0-9\-\._/]{1,}", tail):
            tok = _pick_product_token(m.group(0))
            if tok and _looks_product_like(tok):
                return tok
    return ""

def extract_section1_fields(text: str) -> Dict[str, str]:
    """
    섹션 1에서 제품명(product_name), 회사명(company_name), 주소(address) 추출.
    - 콜론/하이픈/2칸 공백 + (제품/회사 한정) 1칸 공백 분리
    - 근접 탐색(±6줄) + 전역 스캔
    - 제품명 페일세이프: 한줄 정규식 + 라벨 주변 40자 윈도우
    """
    out = {"product_name": "", "company_name": "", "address": ""}
    if not text:
        return out

    lines = [l for l in (text or "").splitlines() if l is not None]

    # 1) 인라인 우선
    for ln in lines:
        if not out["product_name"]:
            v = _inline_try_pc(ln, LABELS["product_name"], is_product=True)
            if v and _looks_product_like(v):
                out["product_name"] = v
        if not out["company_name"]:
            v = _inline_try_pc(ln, LABELS["company_name"])
            if v and _looks_company_like(v):
                out["company_name"] = v
        if not out["address"]:
            v = _inline_try_addr(ln)
            if v:
                out["address"] = v

    # 2) 블록/근접/전역 보완
    if not out["address"]:
        addr_idx = []
        for i, ln in enumerate(lines):
            lab, _ = _split_for_address(ln)
            best, _ = best_label(lab, LABELS["address"], threshold=0.72)
            if best:
                addr_idx.append(i)
        found = ""
        for idx in addr_idx:
            cand = _block_after(lines, idx) or _nearest_value_after(lines, idx, lambda v: bool(ADDR_HINT_RE.search(v)))
            if cand:
                found = cand; break
        if not found:
            found = _global_best(lines, lambda v: bool(ADDR_HINT_RE.search(v)))
        if found:
            out["address"] = found

    if not out["company_name"]:
        comp_idx = []
        for i, ln in enumerate(lines):
            lab, _ = _split_no_prefix_for_pc(ln)
            best, _ = best_label(lab, LABELS["company_name"], threshold=0.72)
            if best:
                comp_idx.append(i)
        found = ""
        for idx in comp_idx:
            cand = _inline_try_pc(lines[idx], LABELS["company_name"])
            cand = cand or _nearest_value_after(lines, idx, _looks_company_like)
            cand = cand or _nearest_value_before(lines, idx, _looks_company_like)
            if cand and _looks_company_like(cand) and not PHONE_RE.search(cand):
                found = cand; break
        if not found:
            found = _global_best(lines, _looks_company_like, prefer_re=COMPANY_HINT_RE)
        if found and _looks_company_like(found):
            out["company_name"] = found

    if not out["product_name"]:
        prod_idx = []
        for i, ln in enumerate(lines):
            lab, _ = _split_no_prefix_for_pc(ln)
            best, _ = best_label(lab, LABELS["product_name"], threshold=0.72)
            if best:
                prod_idx.append(i)
        found = ""
        for idx in prod_idx:
            cand = _inline_try_pc(lines[idx], LABELS["product_name"], is_product=True)
            cand = cand or _nearest_value_after(lines, idx, _looks_product_like)
            cand = cand or _nearest_value_before(lines, idx, _looks_product_like)
            if cand and _looks_product_like(cand):
                found = cand; break
        if not found:
            code_like = re.compile(r"(?=.*[A-Za-z])(?=.*\d)^[A-Za-z0-9][A-Za-z0-9\-\._/]{1,}$")
            found = _global_best(lines, _looks_product_like, prefer_re=code_like, post=_pick_product_token)
        # 🔚 최후의 안전망: 원문 전체에서 ‘제품명 …’ 윈도우/한줄 패턴
        if not found:
            found = _fallback_product_from_text("\n".join(lines))
        if found and _looks_product_like(found):
            out["product_name"] = found

    return out
