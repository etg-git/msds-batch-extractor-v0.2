# msds_streamlit_app.py
# 사이드바: 아이콘 + 텍스트 메뉴 리스트 (radio 기반, 버튼/링크 X)

from __future__ import annotations
import streamlit as st

from msds_pages.msds_upload_page import render as render_msds_upload
from msds_pages.msds_manage_page import render as render_msds_manage
from msds_pages.msds_summary_page import render as render_msds_summary
from msds_pages.shms_regulation_page import render as render_shms_regulation
from msds_pages.shms_composition_page import render as render_shms_composition

st.set_page_config(page_title="MSDS AI / SHMS 연계", layout="wide")

# ----------------------------------------------------------------------
# 네비게이션 정의 (아이콘 + 라벨 + 키)
# ----------------------------------------------------------------------
NAV_ITEMS = [
    ("🟦", "MSDS 파일 업로드", "msds_upload"),
    ("📁", "MSDS 데이터 관리", "msds_manage"),
    ("📄", "MSDS 요약본", "msds_summary"),
    ("⚖️", "규제사항 검증", "shms_regulation"),
    ("🧪", "구성성분 업데이트", "shms_composition"),
]

if "active_page" not in st.session_state:
    st.session_state["active_page"] = "msds_upload"

# ----------------------------------------------------------------------
# 스타일: radio 동그라미 숨기고, 리스트형 텍스트 메뉴로 보이게
# ----------------------------------------------------------------------
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

    /* 전체 메뉴 wrapper */
    div[data-testid="stSidebar"] .sidebar-nav {
        margin-top: 0.2rem;
        font-size: 0.9rem;
    }

    /* stRadio 컨테이너 */
    div[data-testid="stSidebar"] .stRadio > div {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
    }

    /* 라디오 동그라미 숨기기 */
    div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }

    /* 각 항목(label)을 아이콘+텍스트 한 줄로 */
    div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label {
        display: flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.20rem 0.35rem;
        border-radius: 10px;
        cursor: pointer;
        transition: background 0.15s ease, color 0.15s ease;
    }

    /* 텍스트 span */
    div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label > div:last-child {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        font-size: 0.9rem;
        color: #495057;
    }

    /* hover 효과 */
    div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:hover {
        background: #f1f3f5;
    }

    /* 선택된 항목: background + 텍스트 색 변경 */
    div[data-testid="stSidebar"] .stRadio div[role="radio"][aria-checked="true"] + div {
        font-weight: 600;
        color: #1c7ed6;
    }
    div[data-testid="stSidebar"] .stRadio div[role="radio"][aria-checked="true"]::before {
        /* 선택된 항목의 label 배경 처리 (부모 label에 영향 주기 어려워서 약하게만) */
    }
    /* 선택된 label 전체 배경 (부모 label 기준) */
    div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:has(div[role="radio"][aria-checked="true"]) {
        background: #e7f0ff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# 사이드바: radio 기반 메뉴
# ----------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="sidebar-app-title">MSDS AI 콘솔</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sidebar-app-subtitle">MSDS 분석 · SHMS 연계 대시보드</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sidebar-nav">', unsafe_allow_html=True)

    # 라디오 옵션 텍스트: "아이콘  라벨"
    options = [f"{icon}  {label}" for icon, label, _ in NAV_ITEMS]

    # 현재 active_page에 맞는 index 찾기
    current_key = st.session_state["active_page"]
    default_index = 0
    for i, (_, _, key) in enumerate(NAV_ITEMS):
        if key == current_key:
            default_index = i
            break

    choice = st.radio(
        label="메뉴 선택",
        options=options,
        index=default_index,
        label_visibility="collapsed",
        key="nav_radio",
    )

    # 선택된 라벨을 다시 key로 매핑
    for (icon, label, key), opt in zip(NAV_ITEMS, options):
        if opt == choice:
            st.session_state["active_page"] = key
            break

    st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------------------------------------------------
# 메인 컨텐츠 라우팅 (session_state 기반, 링크/새페이지 없음)
# ----------------------------------------------------------------------
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
