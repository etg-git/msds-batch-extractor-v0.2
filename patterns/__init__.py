# patterns/__init__.py
from __future__ import annotations
from typing import Dict

from pathlib import Path

from .loader import pick_packs, load_packs
from .sec1_company_info import (
    extract_section1_fields,                # 기존 로직
    extract_section1_fields_with_packs      # 패턴팩 보완용
)
from .sec2_hazard_info import parse_section_sec2_hazard
from .sec15_regulatory import extract as extract_section15_regulatory

GENERIC_SEEDS = {"제품명", "회사명", "주소", "전화", "전화번호", "긴급", "권고", "제한"}


def parse_section(section_key: str, text: str) -> Dict | str:
    """
    section_key:
      - "sec1"  → dict(product_name, company_name, address)
      - "sec2"  → dict(signal_word, hazard_statements, precautionary_statements, pictograms, ...)
      - "sec15" → dict(items, coverage, unmatched_lines, ...)
      - 그 외   → raw text 그대로 반환(임시; 기존 UI 유지)
    """
    text = text or ""

    if section_key == "sec1":
        # 1) 먼저 기존 로직
        base = extract_section1_fields(text)
        # 2) 패턴팩으로 보완 (하나라도 비었으면)
        if (
            not base.get("product_name")
            or not base.get("company_name")
            or not base.get("address")
        ):
            packs = pick_packs("sec1", text, topk=3)
            patched = extract_section1_fields_with_packs(
                text, packs=packs, seed=base
            )
            # base 값이 있으면 유지, 없으면 패턴팩 값 사용
            for k, v in patched.items():
                if not base.get(k) and v:
                    base[k] = v
        return base

    if section_key == "sec2":
        # 섹션 2(유해·위험성) 파서
        return parse_section_sec2_hazard(text)

    if section_key == "sec15":
        # 섹션 15(법적 규제현황) 파서
        return extract_section15_regulatory(text)

    # 아직 지원 안 한 섹션은 원문 그대로
    return text


def preview_packs(section_id: str, text: str, top_k: int = 3):
    packs = load_packs(section_id) or []
    low = (text or "").lower()
    scored = []
    for p in packs:
        name = p.get("__name__") or p.get("name") or "unnamed"
        meta = p.get("meta", {}) or {}
        sigs = [s.lower() for s in meta.get("doc_signatures", []) if s]
        seeds = [
            s.lower()
            for s in meta.get("seed_keywords", [])
            if s and s not in GENERIC_SEEDS
        ]
        sig_hits = sum(1 for s in sigs if s in low)
        if sig_hits == 0:
            score = 0
        else:
            score = sig_hits * 5 + sum(1 for s in seeds if s in low)
        scored.append(
            {
                "id": meta.get("id") or name,  # meta.id 우선
                "name": name,
                "score": score,
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"total": len(packs), "top": scored[:top_k]}


def preview_packs_sec1(text: str, top_k: int = 3) -> dict:
    """섹션1 전용 간편 래퍼"""
    return preview_packs("sec1", text, top_k=top_k)


def parse_section_sec1_with_debug(text: str):
    """
    섹션1 디버그용: 어떤 패턴팩이 실제로 값 채우기에 기여했는지 확인.
    """
    packs = load_packs("sec1") or []
    used = None
    out = {"product_name": "", "company_name": "", "address": ""}
    for pk in packs:
        before = out.copy()
        out = extract_section1_fields_with_packs(text, [pk], seed=out)
        if any(out[k] and not before[k] for k in out):
            meta = pk.get("meta", {}) or {}
            used = (
                meta.get("id")
                or pk.get("__name__")
                or pk.get("name")
                or "unnamed"
            )
        if all(out.values()):
            break
    return out, (used or ("core" if any(out.values()) else None))
