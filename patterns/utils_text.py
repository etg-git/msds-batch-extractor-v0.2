# patterns/utils_text.py
from __future__ import annotations
import re
from difflib import SequenceMatcher
from typing import Iterable, Tuple, List, Optional

# 특수 공백
SPECIAL_WS = r"[\u00A0\u2000-\u200B]"

# 불릿/번호 라인
BULLET_RE = re.compile(
    r"^\s*("               # 시작 공백 허용
    r"[○●◦∙•□■\-–—\*]"     # 불릿 기호
    r"|[①-⑳]"              # 원형 번호
    r"|[\(\[]?\d{1,2}[\)\].]"  # (1) 1. [1] 1)
    r")\s*"
)

def squash_ws(s: str) -> str:
    """모든 공백/특수공백을 하나의 공백으로 평탄화"""
    return re.sub(rf"{SPECIAL_WS}|\s+", " ", s or "").strip()

def strip_special_ws(s: str) -> str:
    """특수공백만 일반 공백으로 치환"""
    return re.sub(rf"{SPECIAL_WS}", " ", s or "")

def similar(a: str, b: str) -> float:
    """유사도(공백/대소문자 무시)"""
    aa = re.sub(rf"{SPECIAL_WS}|\s+", "", a or "").lower()
    bb = re.sub(rf"{SPECIAL_WS}|\s+", "", b or "").lower()
    return SequenceMatcher(None, aa, bb).ratio()

def best_label(line: str, aliases: Iterable[str], threshold: float = 0.78) -> Tuple[Optional[str], float]:
    """line과 가장 가까운 라벨 별칭을 찾고 임계치 이상일 때만 반환"""
    scores = [(al, similar(line, al)) for al in aliases]
    if not scores:
        return None, 0.0
    al, sc = max(scores, key=lambda x: x[1])
    return (al if sc >= threshold else None, sc)

def looks_like_label(line: str) -> bool:
    """라벨처럼 보이는 최소 패턴(불릿/구분자/두 칸 이상 공백)"""
    s = strip_special_ws(line)
    if BULLET_RE.match(s):
        return True
    if re.search(r"[:：\-]\s*", s):             # 콜론/전각콜론/하이픈
        return True
    if re.search(r"\S\s{2,}\S", s):            # 두 칸 이상 공백으로 라벨/값 구분
        return True
    return False

def split_label_value(line: str) -> Tuple[str, str]:
    """라벨:값 / 라벨-값 1차 분리"""
    s = strip_special_ws(line)
    s = BULLET_RE.sub("", s).strip()
    m = re.split(r"\s*[:：\-]\s*", s, maxsplit=1)
    if len(m) == 2:
        return m[0].strip(), m[1].strip()
    return s.strip(), ""

def split_label_value_smart(line: str, label_aliases: Iterable[str]) -> Tuple[str, str]:
    """
    스마트 분리 우선순위:
      1) 콜론/전각콜론/하이픈
      2) 2칸↑ 공백/탭
      3) 라벨 접두사 기반 분리
    """
    raw = strip_special_ws(line)
    raw = BULLET_RE.sub("", raw)

    # 1) 콜론/하이픈
    lab, val = split_label_value(raw)
    if val:
        return lab, val

    # 2) 2칸 이상 공백/탭
    m = re.split(r"(?:\s{2,}|\t+)", raw.strip(), maxsplit=1)
    if len(m) == 2:
        return m[0].strip(), m[1].strip()

    # 3) 라벨 접두사
    low = raw.lower().strip()
    for al in label_aliases:
        al_low = re.sub(r"\s+", " ", al.lower().strip())
        if low.startswith(al_low):
            rest = raw[len(raw[:len(al_low)]) :].strip(" ：:-—-\t ")
            return al, rest
    return raw.strip(), ""

def till_next_label(lines: List[str], start_idx: int, stop_at_blank: bool = False) -> str:
    """
    다음 라벨/불릿/빈줄이 나오기 전까지를 블록으로 모아 반환.
    주소처럼 여러 줄 값을 이어붙일 때 사용.
    """
    buf: List[str] = []
    for i in range(start_idx, len(lines)):
        ln = lines[i]
        if i > start_idx and looks_like_label(ln):
            break
        if stop_at_blank and not (ln or "").strip():
            break
        txt = squash_ws(ln)
        if txt:
            buf.append(txt)
    return "\n".join(buf)

__all__ = [
    "SPECIAL_WS", "BULLET_RE",
    "squash_ws", "strip_special_ws",
    "similar", "best_label",
    "looks_like_label",
    "split_label_value", "split_label_value_smart",
    "till_next_label",
]
