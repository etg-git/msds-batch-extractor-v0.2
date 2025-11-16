# pages/msds_manage_page.py
from __future__ import annotations
import streamlit as st

def render():
    st.title("MSDS 데이터 관리")
    st.info("향후: 추출된 섹션 데이터를 DB에 저장하고, 검색/정정/삭제 등을 하는 화면으로 확장할 예정입니다.")
