# patterns/__init__.py
from __future__ import annotations
from typing import Callable, Dict

from .sec1_company_info import extract_section1_fields

# 섹션별 파서 레지스트리
# 키는 msds_section_extractor.extract_sections()가 반환하는 섹션 키를 사용
PARSERS: Dict[str, Callable[[str], dict]] = {
    "화학제품과_회사정보": extract_section1_fields,
    # 추후: "구성성분": extract_section3_fields, ...
}

def parse_section(section_key: str, text: str) -> dict:
    fn = PARSERS.get(section_key)
    if not fn:
        return {}
    return fn(text or "")
