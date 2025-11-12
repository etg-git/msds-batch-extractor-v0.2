# Streamlit UI for MSDS Section Extraction
# - Multiple PDF upload
# - Clear, scrollable section previews per file (visibility first)
#
# Usage:
#   streamlit run msds_streamlit_app.py
#
# Requirements (typical):
#   pip install streamlit pdfplumber pdf2image pytesseract pillow
#   - Poppler is required for pdf2image OCR on Windows/macOS.
#
# App notes:
#   - This UI imports your local module: msds_section_extractor.py
#   - You can toggle OCR and set POPPLER_PATH in the sidebar at runtime.
#   - For each uploaded PDF, sections are extracted and shown in tabs.

from __future__ import annotations
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st

# Import your extractor module (must be in the same directory or in PYTHONPATH)
import msds_section_extractor as extractor

# -----------------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------------
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


def _save_uploaded_to_temp(uploaded) -> Path:
    """Persist the uploaded file to a temp .pdf and return its path."""
    with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded.read())
        return Path(tmp.name)


def _download_json_button(label: str, data: dict, file_basename: str):
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button(
        label=label,
        data=payload,
        file_name=f"{file_basename}_sections.json",
        mime="application/json",
        use_container_width=True,
    )


def _render_sections(sections: dict):
    keys = [k for k in SECTION_ORDER if k in sections]
    if not keys:
        st.warning("추출된 섹션이 없습니다.")
        return

    tabs = st.tabs([SECTION_TITLES[k] for k in keys])
    for k, tab in zip(keys, tabs):
        with tab:
            text = sections.get(k, "") or ""
            meta = f"길이: {len(text):,}자"
            st.caption(meta)
            # Big, readable text area to emphasize visibility and easy copy
            st.text_area(
                label=SECTION_TITLES[k],
                value=text,
                height=360,
                key=f"txt_{k}_{len(text)}",
            )


# -----------------------------------------------------------------------------
# Streamlit page config
# -----------------------------------------------------------------------------
st.set_page_config(page_title="MSDS Section Extractor", layout="wide")
st.title("MSDS Section Extractor (텍스트+OCR 하이브리드)")
st.write("여러 개의 PDF를 업로드하면 아래에 섹션별로 가시성 높게 표시합니다.")

# Sidebar controls
with st.sidebar:
    st.header("설정")
    enable_ocr = st.checkbox("OCR 사용", value=getattr(extractor, "ENABLE_OCR", True))
    extractor.ENABLE_OCR = enable_ocr

    poppler_default = getattr(extractor, "POPPLER_PATH", "") or ""
    poppler_path = st.text_input("POPPLER_PATH (Windows/macOS)", value=poppler_default)
    extractor.POPPLER_PATH = poppler_path

    tess_lang_default = getattr(extractor, "TESS_LANG", "kor+eng")
    tess_lang = st.text_input("Tesseract 언어 (예: kor+eng)", value=tess_lang_default)
    extractor.TESS_LANG = tess_lang

    ocr_dpi_default = getattr(extractor, "OCR_DPI", 300)
    ocr_dpi = st.number_input("OCR DPI", min_value=100, max_value=600, value=int(ocr_dpi_default), step=25)
    extractor.OCR_DPI = int(ocr_dpi)

    min_chars_default = getattr(extractor, "OCR_TEXT_MIN_CHARS", 40)
    min_chars = st.number_input("텍스트 길이 임계값 (OCR 트리거)", min_value=0, max_value=500, value=int(min_chars_default), step=5)
    extractor.OCR_TEXT_MIN_CHARS = int(min_chars)

    st.divider()
    st.caption("변경 사항은 즉시 적용됩니다. 모듈 전역 변수를 런타임에 설정합니다.")

# Uploader (multiple)
uploaded_files = st.file_uploader(
    "PDF 파일 업로드 (여러 개 선택 가능)",
    type=["pdf"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("좌측 설정을 확인하고, 위에 PDF 파일을 하나 이상 업로드하세요.")
else:
    for idx, uf in enumerate(uploaded_files, start=1):
        file_label = f"{idx}. {uf.name}"
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="center")
            with c1:
                st.subheader(file_label)
            with c2:
                st.caption(f"크기: {uf.size/1024:.1f} KB")
            with c3:
                st.caption("상태: 처리 중")

            # 저장 → 추출
            tmp_path = _save_uploaded_to_temp(uf)
            try:
                with st.spinner("추출 중..."):
                    sections = extractor.extract_sections(str(tmp_path))
            except Exception as e:
                st.error(f"오류 발생: {e}")
                sections = {}
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

            # Summary row (what was found)
            found = [SECTION_TITLES[k] for k in SECTION_ORDER if k in sections]
            missing = [SECTION_TITLES[k] for k in SECTION_ORDER if k not in sections]
            st.markdown("발견된 섹션:")
            st.write(", ".join(found) if found else "없음")
            if missing:
                with st.expander("누락된 섹션 보기"):
                    st.write(", ".join(missing))

            # Visible content panels
            _render_sections(sections)

            # Download JSON (per file)
            _download_json_button("섹션 JSON 다운로드", sections, Path(uf.name).stem)

            # Optional debug: page texts preview
            with st.expander("디버그: 페이지 텍스트 미리보기"):
                # extract_text_pages_hybrid는 파일 경로를 요구하므로 임시로 다시 저장
                tmp2 = _save_uploaded_to_temp(uf)
                try:
                    pages = extractor.extract_text_pages_hybrid(str(tmp2))
                finally:
                    try:
                        os.remove(tmp2)
                    except Exception:
                        pass
                st.caption(f"총 {len(pages)} 페이지")
                for i, ptxt in enumerate(pages, start=1):
                    with st.expander(f"p{i:02d}"):
                        st.text_area(label=f"페이지 {i}", value=ptxt or "", height=220, key=f"pg_{idx}_{i}")

    st.success("처리가 완료되었습니다.")
