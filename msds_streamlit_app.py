# msds_streamlit_app.py
# Streamlit UI for MSDS Section Extraction (No settings, high-visibility, multi-file)
# Usage:
#   streamlit run msds_streamlit_app.py
#
# Requires:
#   pip install streamlit pdfplumber pdf2image pytesseract pillow pandas
#
# Notes:
#   - This UI imports your local module: msds_section_extractor.py
#   - Focuses on section-split verification and readability for ~50 PDFs.

from __future__ import annotations
import json
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st
import pandas as pd

import msds_section_extractor as extractor

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


# -------------------------- Helpers -------------------------- #
def _save_bytes_to_temp(data: bytes) -> Path:
    with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(data)
        return Path(tmp.name)

def _render_badge(text: str, color: str = "gray"):
    # lightweight badge using HTML (Streamlit safe)
    st.markdown(
        f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
        f'background:{color};color:white;font-size:12px;margin-right:6px;">{text}</span>',
        unsafe_allow_html=True,
    )

def _download_json_button(data: dict, file_basename: str):
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button(
        label="섹션 JSON 다운로드",
        data=payload,
        file_name=f"{file_basename}_sections.json",
        mime="application/json",
        use_container_width=True,
    )

def _extract_sections_from_bytes(file_bytes: bytes) -> dict:
    tmp_path = _save_bytes_to_temp(file_bytes)
    try:
        sections = extractor.extract_sections(str(tmp_path))
        return sections or {}
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

def _section_len_map(sections: dict) -> dict:
    return {k: len(sections.get(k, "") or "") for k in SECTION_TITLES.keys()}

def _found_missing_lists(sections: dict):
    found = [SECTION_TITLES[k] for k in SECTION_ORDER if k in sections and sections.get(k)]
    missing = [SECTION_TITLES[k] for k in SECTION_ORDER if k not in sections or not sections.get(k)]
    return found, missing

def _render_sections_tabs(sections: dict, key_prefix: str = ""):
    keys = [k for k in SECTION_ORDER if sections.get(k)]
    if not keys:
        st.warning("추출된 섹션이 없습니다.")
        return
    tabs = st.tabs([SECTION_TITLES[k] for k in keys])
    for k, tab in zip(keys, tabs):
        with tab:
            text = sections.get(k, "") or ""
            st.caption(f"길이: {len(text):,}자")
            st.text_area(
                label=SECTION_TITLES[k],
                value=text,
                height=360,
                key=f"{key_prefix}_txt_{k}_{len(text)}",
            )


# -------------------------- Page -------------------------- #
st.set_page_config(page_title="MSDS Section Extractor", layout="wide")
st.title("MSDS Section Extractor")
st.caption("여러 PDF를 한 번에 업로드하고, 섹션(1/2/3/9/15)이 제대로 분리되었는지 빠르게 검증할 수 있는 화면입니다.")

uploaded_files = st.file_uploader(
    "PDF 파일 업로드 (여러 개 선택 가능, ~50권 권장)",
    type=["pdf"],
    accept_multiple_files=True,
)

# Quick filters (not settings)
colf1, colf2 = st.columns([2, 1])
with colf1:
    name_filter = st.text_input("파일명 필터 (부분 일치)", value="")
with colf2:
    only_missing = st.checkbox("섹션 누락 파일만 보기", value=False)

if not uploaded_files:
    st.info("위에서 PDF를 업로드하세요.")
    st.stop()

# Read all bytes once to avoid stream exhaustion
file_entries = []
for uf in uploaded_files:
    b = uf.getvalue()
    file_entries.append({
        "name": uf.name,
        "size_kb": round(uf.size / 1024, 1),
        "bytes": b,
        "is_pdf": b.startswith(b"%PDF"),
    })

# Optional name filter pre-apply for performance
if name_filter.strip():
    file_entries = [e for e in file_entries if name_filter.strip().lower() in e["name"].lower()]

# Process
progress = st.progress(0, text="추출 준비 중...")
results = []
start = time.time()

for i, ent in enumerate(file_entries, start=1):
    fname = ent["name"]
    status = "OK"
    err = ""
    sections = {}
    if not ent["is_pdf"]:
        status = "INVALID"
        err = "%PDF 헤더 없음"
    else:
        try:
            sections = _extract_sections_from_bytes(ent["bytes"])
        except Exception as e:
            status = "ERROR"
            err = str(e)

    s_found, s_missing = _found_missing_lists(sections)
    lens = _section_len_map(sections)

    results.append({
        "index": i,
        "file": fname,
        "size_kb": ent["size_kb"],
        "status": status,
        "found_count": len(s_found),
        "missing_count": len(s_missing),
        "missing_list": ", ".join(s_missing),
        "sections": sections,
        **{f"len_{k}": lens[k] for k in SECTION_TITLES.keys()},
        "error": err,
    })

    progress.progress(i / max(1, len(file_entries)), text=f"처리 중... ({i}/{len(file_entries)})")

elapsed = time.time() - start
progress.empty()
st.success(f"총 {len(results)}개 파일 처리 완료 (약 {elapsed:.1f}초)")

# Build summary table
df = pd.DataFrame([{
    "#": r["index"],
    "File": r["file"],
    "KB": r["size_kb"],
    "Status": r["status"],
    "Found": r["found_count"],
    "Missing": r["missing_count"],
    "Missing List": r["missing_list"],
    "len_1": r["len_화학제품과_회사정보"],
    "len_2": r["len_유해성위험성"],
    "len_3": r["len_구성성분"],
    "len_9": r["len_물리화학적특성"],
    "len_15": r["len_법적규제"],
} for r in results])

if only_missing:
    df_view = df[df["Missing"] > 0].reset_index(drop=True)
else:
    df_view = df

st.subheader("요약")
st.caption("섹션 분리 품질을 한눈에 확인할 수 있도록 길이(len_*)와 누락(Missing)을 표로 제공합니다.")
st.dataframe(df_view, use_container_width=True, height=min(600, 100 + 28 * max(4, len(df_view))))

st.divider()
st.subheader("파일별 상세")

# Render detailed panels, filtered same as table
filtered_results = results if not only_missing else [r for r in results if r["missing_count"] > 0]

for r in filtered_results:
    with st.container(border=True):
        topc1, topc2, topc3, topc4 = st.columns([4, 1, 1, 2])
        with topc1:
            st.markdown(f"### {r['index']}. {r['file']}")
        with topc2:
            _render_badge(f"{r['size_kb']} KB", "#6c757d")
        with topc3:
            color = "#28a745" if r["missing_count"] == 0 and r["status"] == "OK" else ("#dc3545" if r["status"] != "OK" or r["missing_count"] > 0 else "#6c757d")
            _render_badge(r["status"], color)
        with topc4:
            # quick summary badges
            _render_badge(f"Found {r['found_count']}", "#17a2b8")
            _render_badge(f"Missing {r['missing_count']}", "#ffc107")

        if r["error"]:
            st.error(f"에러: {r['error']}")

        # Missing list quick glance
        if r["missing_count"] > 0:
            st.warning("누락된 섹션: " + (r["missing_list"] if r["missing_list"] else "없음"))

        # Visible tabs with section text
        _render_sections_tabs(r["sections"], key_prefix=f"{r['index']}")

        # Download per-file JSON
        _download_json_button(r["sections"], Path(r["file"]).stem)

