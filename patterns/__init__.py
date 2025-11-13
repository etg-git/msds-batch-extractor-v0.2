# patterns/__init__.py
from __future__ import annotations
from typing import Dict, Any
from .loader import pick_packs, load_packs
from .sec1_company_info import (
    extract_section1_fields,
    extract_section1_fields_with_packs,
)
from .sec2_hazard_info import parse_section_sec2_hazard   # ← 네가 추가한 부분

from pathlib import Path
GENERIC_SEEDS = {"제품명","회사명","주소","전화","전화번호","긴급","권고","제한"}


def parse_section(section_key: str, text: str) -> Dict[str, Any] | str:
    """
    section_key:
      - "sec1" → dict(product_name, company_name, address)
      - "sec2" → dict(signal_word, hazard_codes, precautionary_codes_*, pictograms)
      - 그 외 → raw text 그대로 반환(임시; 기존 UI 유지)
    """
    if section_key == "sec1":
        # 1) 먼저 기존 로직
        base = extract_section1_fields(text)
        # 2) 패턴팩으로 보완 (하나라도 비었으면)
        if not base.get("product_name") or not base.get("company_name") or not base.get("address"):
            packs = pick_packs("sec1", text, topk=3)
            patched = extract_section1_fields_with_packs(text, packs=packs, seed=base)
            for k, v in patched.items():
                if not base.get(k) and v:
                    base[k] = v
        return base

    if section_key == "sec2":
        # ← 여기에서 우리가 만든 섹션2 파서를 실제로 사용
        return parse_section_sec2_hazard(text or "")

    # 아직 지원 안 한 섹션은 원문 그대로
    return text
