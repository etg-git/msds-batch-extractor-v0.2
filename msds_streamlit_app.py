# msds_streamlit_app.py
# 사이드바: 아이콘 + 텍스트 메뉴 리스트 (버튼처럼 안 보이게, session_state 라우팅)

from __future__ import annotations
import streamlit as st

# 개별 페이지 import
from msds_pages.msds_upload_page import render as render_msds_upload
from msds_pages.msds_manage_page import render as render_msds_manage
from msds_pages.msds_summary_page import render as render_msds_summary
from msds_pages.shms_regulation_page import render as render_shms_regulation
from msds_pages.shms_composition_page import render as render_shms_composition

st.set_page_config(page_title="MSDS AI / SHMS 연계", layout="wide")

# ------------------------ NAV 정의 (아이콘 + 라벨 + 키) ------------------------
NAV_ITEMS = [
    ("🟦", "MSDS 파일 업로드", "msds_upload"),
    ("📁", "MSDS 데이터 관리", "msds_manage"),
    ("📄", "MSDS 요약본", "msds_summary"),
    ("⚖️", "규제사항 검증", "shms_regulation"),
    ("🧪", "구성성분 업데이트", "shms_composition"),
]

if "active_page" not in st.session_state:
    st.session_state["active_page"] = "msds_upload"

current_page = st.session_state["active_page"]

# ------------------------ 스타일: 버튼 크롬 제거 + 리스트형 메뉴 ------------------------
st.markdown(
    """
    <style>
    /* 사이드바 배경 */
    div[data-testid="stSidebar"] {
        background: #f8f9fa;
    }
    div[data-testid="stSidebar"] > div {
        padding-top: 1rem;
    }

    /* 헤더 */
    .sidebar-app-title {
        font-size: 1.4rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .sidebar-app-subtitle {
        font-size: 0.82rem;
        color: #868e96;
        margin-bottom: 1.2rem;
        font-weight: 500;
        letter-spacing: 0.3px;
    }

    /* 전체 메뉴 컨테이너 */
    .sidebar-nav {
        margin-top: 0.2rem;
    }

    /* 한 줄 메뉴 wrapper */
    div[data-testid="stSidebar"] .nav-row {
        margin: 2px 0;
        padding: 0;
        border-radius: 12px;
    }

    /* 기본 stButton 껍데기 제거 */
    div[data-testid="stSidebar"] .nav-row .stButton {
        margin: 0 !important;
        padding: 0 !important;
    }

    /* 진짜 버튼을 “아이콘+텍스트 리스트”처럼 보이게 */
    div[data-testid="stSidebar"] .nav-row .stButton > button {
        display: flex !important;
        align-items: center !important;
        gap: 0.45rem !important;

        width: 100% !important;
        padding: 0.30rem 0.45rem !important;

        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 12px !important;

        font-size: 0.9rem !important;
        color: #495057 !important;
        text-align: left !important;
        font-weight: 500 !important;

        cursor: pointer !important;
    }

    /* hover 시 살짝만 배경 */
    div[data-testid="stSidebar"] .nav-row .stButton > button:hover {
        background: #f1f3f5 !important;
        color: #343a40 !important;
    }

    div[data-testid="stSidebar"] .nav-row .stButton > button:focus {
        outline: none !important;
        box-shadow: none !important;
    }

    /* 활성 메뉴 하이라이트 */
    div[data-testid="stSidebar"] .nav-row-active .stButton > button {
        background: #e7f0ff !important;
        color: #1c7ed6 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------ 사이드바: 메뉴 리스트 (세션 상태 라우팅) ------------------------
with st.sidebar:
    st.markdown('<div class="sidebar-app-title">MSDS AI 콘솔</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sidebar-app-subtitle">MSDS 분석 · SHMS 연계 대시보드</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sidebar-nav">', unsafe_allow_html=True)

    for icon, label, key in NAV_ITEMS:
        is_active = (key == current_page)
        row_cls = "nav-row nav-row-active" if is_active else "nav-row"
        st.markdown(f'<div class="{row_cls}">', unsafe_allow_html=True)

        # 버튼 라벨 = 아이콘 + 텍스트
        if st.button(f"{icon}  {label}", key=f"nav_{key}", use_container_width=True):
            st.session_state["active_page"] = key
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------ 메인 컨텐츠 라우팅 ------------------------
page = st.session_state.get("active_page", "msds_upload")

if page == "msds_upload":
    render_msds_upload()
elif page == "msds_manage":
    render_msds_manage()
elif page == "msds_summary":
    render_msds_summary()
elif page == "shms_regulation":
    render_shms_regulation()
elif page == "shms_composition":
    render_shms_composition()
else:
    st.error(f"알 수 없는 페이지 키: {page}")
