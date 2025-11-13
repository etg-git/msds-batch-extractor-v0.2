# msds_streamlit_app.py 
# 가벼운 UI: 설정 없음 / 50개 업로드 / 섹션 1 요약(제품명, 회사명, 주소) + 섹션 2 요약 표시

from __future__ import annotations
import json
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st
import pandas as pd

import msds_section_extractor as extractor
from patterns import parse_section, preview_packs_sec1, parse_section_sec1_with_debug  # 섹션 파서 레지스트리

SECTION_TITLES = {
    "화학제품과_회사정보": "1. 화학제품과 회사에 관한 정보",
    "유해성위험성": "2. 유해성·위험성",
    "구성성분": "3. 구성성분의 명칭 및 함유량",
    "물리화학적특성": "9. 물리 화학적 특성/특징",
    "법적규제": "15. 법적 규제현황",
}
SECTION_ORDER = [
    "화학제품과_회사정보",
    "유해성위험성",
    "구성성분",
    "물리화학적특성",
    "법적규제",
]

# -----------------------------
# 세션 상태: 업로더 key, 임시파일 경로 추적
# -----------------------------
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "uploaded_tmp_paths" not in st.session_state:
    st.session_state["uploaded_tmp_paths"] = []

def _save_bytes_to_temp(data: bytes) -> Path:
    with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(data)
        p = Path(tmp.name)
        st.session_state["uploaded_tmp_paths"].append(str(p))
        return p

def _download_json_button(data: dict, file_basename: str):
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button(
        label="섹션 JSON 다운로드",
        data=payload,
        file_name=f"{file_basename}_sections.json",
        mime="application/json",
        use_container_width=True,
    )

def _section_len_map(sections: dict) -> dict:
    keys = ["화학제품과_회사정보", "유해성위험성", "구성성분", "물리화학적특성", "법적규제"]
    return {k: len(sections.get(k, "") or "") for k in keys}

def _found_missing_lists(sections: dict):
    found = [SECTION_TITLES[k] for k in SECTION_ORDER if k in sections and sections.get(k)]
    missing = [SECTION_TITLES[k] for k in SECTION_ORDER if k not in sections or not sections.get(k)]
    return found, missing

def _render_badge(text: str, color: str = "#6c757d"):
    st.markdown(
        f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
        f'background:{color};color:white;font-size:12px;margin-right:6px;">{text}</span>',
        unsafe_allow_html=True,
    )

st.set_page_config(page_title="MSDS Section Extractor", layout="wide")
st.title("MSDS Section Extractor")
st.caption("여러 PDF를 한 번에 업로드하고, 섹션 분리와 요약 정보를 확인합니다. (섹션 1: 제품명/회사명/주소, 섹션 2: 신호어·H/P 코드)")

# -----------------------------
# 업로드 전체 삭제 버튼 + 업로더
# -----------------------------
cbtn, _ = st.columns([1, 5])
with cbtn:
    if st.button("업로드 전체 삭제", help="업로드 목록과 세션의 임시 파일을 모두 정리합니다."):
        # 남은 임시파일 제거
        for p in st.session_state["uploaded_tmp_paths"]:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        st.session_state["uploaded_tmp_paths"] = []
        # 업로더 key 변경(위젯 재생성으로 목록 리셋)
        st.session_state["uploader_key"] += 1
        st.success("업로드 목록과 임시 파일을 모두 삭제했어요.")
        st.rerun()

uploaded_files = st.file_uploader(
    "PDF 파일 업로드 (여러 개 선택 가능, ~50권 권장)",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}",  # ← key가 바뀌면 업로더가 초기화됨
)

colf1, colf2 = st.columns([2, 1])
with colf1:
    name_filter = st.text_input("파일명 필터 (부분 일치)", value="")
with colf2:
    only_missing = st.checkbox("섹션 누락 파일만 보기", value=False)

if not uploaded_files:
    st.info("위에서 PDF를 업로드하세요.")
    st.stop()

# Read bytes once
entries = []
for uf in uploaded_files:
    b = uf.getvalue()
    if not b:
        continue
    entries.append({
        "name": uf.name,
        "size_kb": round(uf.size/1024, 1),
        "bytes": b,
        "is_pdf": b.startswith(b"%PDF"),
    })

# Filter
if name_filter.strip():
    needle = name_filter.strip().lower()
    entries = [e for e in entries if needle in e["name"].lower()]

# Process
progress = st.progress(0, text="처리 중...")
rows = []
start = time.time()

for i, ent in enumerate(entries, start=1):
    fname = ent["name"]
    status = "OK"
    err = ""
    sections = {}

    # 섹션 1/2 요약 정보
    s1_summary = {"product_name": "", "company_name": "", "address": ""}
    s1_applied = None  # 실제 적용된 YAML 팩 id/name

    s2_summary = {}  # 섹션 2 구조화 결과 (ghs_classification, signal_word 등)

    if not ent["is_pdf"]:
        status = "INVALID"
        err = "%PDF 헤더 없음"
    else:
        temp = _save_bytes_to_temp(ent["bytes"])
        try:
            sections = extractor.extract_sections(str(temp)) or {}

            # 섹션 1 요약
            s1_text = sections.get("화학제품과_회사정보", "")
            if s1_text:
                s1_summary, s1_applied = parse_section_sec1_with_debug(s1_text)
                if not s1_summary:
                    s1_summary = {"product_name": "", "company_name": "", "address": ""}

            # 섹션 2 요약 (유해성·위험성)
            s2_text = sections.get("유해성위험성", "")
            if s2_text:
                try:
                    # patterns.parse_section가 섹션 키 기반으로 적절한 파서를 호출한다고 가정
                    s2_summary = parse_section("유해성위험성", s2_text) or {}
                except Exception as e2:
                    s2_summary = {}
                    err = (err + " | " if err else "") + f"sec2 parse error: {e2}"

        except Exception as e:
            status = "ERROR"
            err = str(e)
        finally:
            try:
                if temp and os.path.exists(temp):
                    os.remove(temp)
            except Exception:
                pass

    found, missing = _found_missing_lists(sections)
    lens = _section_len_map(sections)

    # 섹션 2 요약값 일부를 테이블용으로 정리
    s2_sig = s2_summary.get("signal_word") if isinstance(s2_summary, dict) else None
    s2_h_list = s2_summary.get("hazard_statements") if isinstance(s2_summary, dict) else None
    s2_p_list = s2_summary.get("precautionary_statements") if isinstance(s2_summary, dict) else None

    s2_h_count = len(s2_h_list or [])
    s2_p_count = len(s2_p_list or [])

    rows.append({
        "#": i,
        "File": fname,
        "KB": ent["size_kb"],
        "Status": status,
        "Found": len(found),
        "Missing": len(missing),
        "len_1": lens["화학제품과_회사정보"],
        "len_2": lens["유해성위험성"],
        "len_3": lens["구성성분"],
        "len_9": lens["물리화학적특성"],
        "len_15": lens["법적규제"],
        "제품명": s1_summary.get("product_name", ""),
        "회사명": s1_summary.get("company_name", ""),
        "주소": s1_summary.get("address", ""),
        "S2_신호어": s2_sig or "",
        "S2_H개수": s2_h_count,
        "S2_P개수": s2_p_count,
        "_sections": sections,
        "_s1": s1_summary,
        "_s1_applied": s1_applied,
        "_s2": s2_summary,
        "_err": err,
    })

    progress.progress(i / max(1, len(entries)), text=f"처리 중... ({i}/{len(entries)})")

elapsed = time.time() - start
progress.empty()
st.success(f"총 {len(rows)}개 파일 처리 완료 (약 {elapsed:.1f}초)")

df = pd.DataFrame([{
    "#": r["#"],
    "File": r["File"],
    "KB": r["KB"],
    "Status": r["Status"],
    "Found": r["Found"],
    "Missing": r["Missing"],
    "len_1": r["len_1"],
    "len_2": r["len_2"],
    "len_3": r["len_3"],
    "len_9": r["len_9"],
    "len_15": r["len_15"],
    "제품명": r["제품명"],
    "회사명": r["회사명"],
    "주소": r["주소"],
    "S2_신호어": r["S2_신호어"],
    "S2_H개수": r["S2_H개수"],
    "S2_P개수": r["S2_P개수"],
} for r in rows])

if only_missing:
    df_view = df[df["Missing"] > 0].reset_index(drop=True)
else:
    df_view = df

st.subheader("요약")
st.caption("섹션 길이와 함께 1번 섹션 요약(제품명/회사명/주소)과 2번 섹션 요약(신호어, H/P 문구 개수)을 표로 제공합니다.")
st.dataframe(
    df_view,
    use_container_width=True,
    height=min(1000, 100 + 50 * max(4, len(df_view))),
)

st.divider()
st.subheader("파일별 상세")

targets = rows if not only_missing else [rr for rr in rows if rr["Missing"] > 0]
for r in targets:
    with st.container(border=True):
        topc1, topc2, topc3 = st.columns([5, 1, 2])
        with topc1:
            st.markdown(f"### {r['#']}. {r['File']}")
        with topc2:
            _render_badge(f"{r['KB']} KB")
        with topc3:
            color = "#28a745" if r["Missing"] == 0 and r["Status"] == "OK" else ("#dc3545" if r["Status"] != "OK" or r["Missing"] > 0 else "#6c757d")
            _render_badge(r["Status"], color)

        if r["_err"]:
            st.error(f"에러: {r['_err']}")

        # 실제 적용된 YAML 팩 id/name 배지
        if r.get("_s1_applied"):
            _render_badge(f"applied: {r['_s1_applied']}", "#7952b3")

        # 미리보기 후보(YAML 팩 스코어)
        s1_text = r["_sections"].get("화학제품과_회사정보", "")
        if s1_text:
            s1_dbg = preview_packs_sec1(s1_text)
            top = s1_dbg.get("top", [])
            if top:
                pack_id = top[0].get("id") or top[0].get("name")
                _render_badge(f"apply? {pack_id} · {top[0]['score']}", "#17a2b8")

        # 섹션별 탭: 탭 안에서 섹션 요약 카드가 바뀌도록 구성
        sections = r["_sections"]
        keys = [k for k in SECTION_ORDER if sections.get(k)]
        if not keys:
            st.warning("추출된 섹션이 없습니다.")
        else:
            tabs = st.tabs([SECTION_TITLES[k] for k in keys])
            for k, tab in zip(keys, tabs):
                with tab:
                    text = sections.get(k, "") or ""
                    st.caption(f"길이: {len(text):,}자")

                    # 섹션 1 탭: 제품명/회사명/주소 요약
                    if k == "화학제품과_회사정보":
                        s1 = r.get("_s1") or {}
                        product_name = s1.get("product_name", "") or "—"
                        company_name = s1.get("company_name", "") or "—"
                        address_html = (s1.get("address", "") or "").replace("\n", "<br/>") or "—"

                        st.markdown(
                            f"""
                            <div style="padding:12px;border:1px solid #e9ecef;border-radius:12px;background:#f8f9fa;margin:6px 0;">
                                <div style="font-weight:600;margin-bottom:6px;">섹션 1 요약</div>
                                <div><b>제품명</b>: {product_name}</div>
                                <div><b>회사명</b>: {company_name}</div>
                                <div><b>주소</b>: {address_html}</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                    # 섹션 2 탭: 신호어 + H/P 코드 리스트
                    if k == "유해성위험성":
                        s2 = r.get("_s2") or {}
                        if isinstance(s2, dict) and s2:
                            signal_word = s2.get("signal_word") or "—"
                            h_list = s2.get("hazard_statements") or []
                            p_list = s2.get("precautionary_statements") or []

                            h_codes = sorted({(item.get("code") or "").strip() for item in h_list if item.get("code")})
                            p_codes = sorted({(item.get("code") or "").strip() for item in p_list if item.get("code")})

                            h_codes_str = ", ".join(h_codes) if h_codes else "—"
                            p_codes_str = ", ".join(p_codes) if p_codes else "—"

                            st.markdown(
                                f"""
                                <div style="padding:12px;border:1px solid #e9ecef;border-radius:12px;background:#fff;margin:6px 0;">
                                    <div style="font-weight:600;margin-bottom:6px;">섹션 2 요약 (유해성·위험성)</div>
                                    <div><b>신호어</b>: {signal_word}</div>
                                    <div><b>H 코드</b>: {h_codes_str}</div>
                                    <div><b>P 코드</b>: {p_codes_str}</div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )

                    # 섹션 원문
                    st.text_area(
                        label=SECTION_TITLES[k],
                        value=text,
                        height=360,
                        key=f"{r['#']}_txt_{k}_{len(text)}",
                    )

        # 파일별 섹션 JSON 다운로드
        _download_json_button(r["_sections"], Path(r["File"]).stem)
