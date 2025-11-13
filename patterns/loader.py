# patterns/loader.py
from __future__ import annotations
import yaml, re
from pathlib import Path
from typing import List, Dict

PACKS_ROOT = Path(__file__).parent / "packs"
  
def _load_yaml(p: Path) -> dict:
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def load_packs(section_key: str) -> List[dict]:
    d = PACKS_ROOT / section_key
    if not d.exists():
        return []
    packs = []
    for p in sorted(d.glob("*.yaml")):
        data = _load_yaml(p)
        data["_path"] = str(p)
        data.setdefault("priority", 50)
        packs.append(data)
    # base.yaml이 있으면 항상 맨 앞에 머지 기준으로 둔다
    bases = [x for x in packs if Path(x["_path"]).name == "base.yaml"]
    others = [x for x in packs if Path(x["_path"]).name != "base.yaml"]
    return bases + others

def score_pack(pack: dict, text: str) -> int:
    score = int(pack.get("priority", 50))
    t = (text or "").lower()
    # 라벨 alias 힌트로 가산
    for k in ("product", "company", "address"):
        aliases = [a.lower() for a in pack.get("labels", {}).get(k, {}).get("aliases", [])]
        if any(a in t for a in aliases[:4]):
            score += 3
    return score

def pick_packs(section_key: str, text: str, topk: int = 3) -> List[dict]:
    packs = load_packs(section_key)
    if not packs:
        return []
    ranked = sorted(packs, key=lambda p: score_pack(p, text), reverse=True)
    # base.yaml을 머지 기반으로 사용하기 쉽게, 항상 포함되도록 보정
    base = next((p for p in ranked if Path(p["_path"]).name == "base.yaml"), None)
    top = ranked[:topk]
    if base and base not in top:
        top = [base] + top
    return top

# 유틸: 분리기 이름 → 정규식/동작 설명
SPLITTERS = {
    "colon_or_dash": r"(?:\s*[:：\-]\s*)",
    "two_col_space": r"(?:\s{2,}|\t+)",
    "loose_space":   r"(?:\s+)",   # 1칸↑ (제품/회사 한정)
    "prefix_smart":  None,         # utils_text.split_label_value_smart 사용
}

FORBIDDEN_DEFAULT = ["전화", "전화번호", "긴급", "tel", "fax", "주소", "권고 용도", "용도", "제한", "정보", "기재", "문의", "연락"]
