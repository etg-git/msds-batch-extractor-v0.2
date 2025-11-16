# pages/msds_upload_page.py
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st
import pandas as pd

import msds_section_extractor as extractor
from patterns import preview_packs_sec1, parse_section_sec1_with_debug
from patterns.sec2_hazard_info import parse_section_sec2_hazard
from patterns.sec3_composition import extract_section3_composition  # ← 섹션3 파서 추가

# extractor에서 전체 섹션 정보 재사용
SECTION_TITLES = extractor.SECTION_TITLES
ALL_SECTION_KEYS = extractor.ALL_SECTION_KEYS
SECNUM = extractor.SECNUM

SUMMARY_SECTION_KEYS = [
    "화학제품과_회사정보",
    "유해성위험성",
    "구성성분",
    "물리화학적특성",
    "법적규제",
]

# -----------------------------
# 공통 유틸
# -----------------------------
def _ensure_session_state():
    if "uploader_key" not in st.session_state:
        st.session_state["uploader_key"] = 0
    if "uploaded_tmp_paths" not in st.session_state:
        st.session_state["uploaded_tmp_paths"] = []


def _save_bytes_to_temp(data: bytes) -> Path:
    from tempfile import NamedTemporaryFile
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
    return {k: len(sections.get(k, "") or "") for k in SUMMARY_SECTION_KEYS}


def _found_missing_lists(sections: dict):
    found = [SECTION_TITLES[k] for k in SUMMARY_SECTION_KEYS if k in sections and sections.get(k)]
    missing = [SECTION_TITLES[k] for k in SUMMARY_SECTION_KEYS if k not in sections or not sections.get(k)]
    return found, missing


def _render_badge(text: str, color: str = "#6c757d"):
    st.markdown(
        f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
        f'background:{color};color:white;font-size:12px;margin-right:6px;">{text}</span>',
        unsafe_allow_html=True,
    )

# -----------------------------
# 메인 렌더 함수
# -----------------------------
def render():
    _ensure_session_state()

    st.title("MSDS Section Extractor - MSDS 파일 업로드")
    st.caption(
        "여러 PDF를 한 번에 업로드하고, 섹션 분리와 요약 정보를 확인합니다. "
        "(섹션 1: 제품명/회사명/주소, 섹션 2: 신호어·H/P 개수·GHS 그림문자 개수, "
        "섹션 1~16: 탭에서 전체 원문 확인)"
    )

    # 업로드/필터 영역
    cbtn, _ = st.columns([1, 5])
    with cbtn:
        if st.button("업로드 전체 삭제", help="업로드 목록과 세션의 임시 파일을 모두 정리합니다."):
            for p in st.session_state["uploaded_tmp_paths"]:
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
            st.session_state["uploaded_tmp_paths"] = []
            st.session_state["uploader_key"] += 1
            st.success("업로드 목록과 임시 파일을 모두 삭제했어요.")
            st.rerun()

    uploaded_files = st.file_uploader(
        "PDF 파일 업로드 (여러 개 선택 가능, ~50권 권장)",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_key']}",
    )

    colf1, colf2 = st.columns([2, 1])
    with colf1:
        name_filter = st.text_input("파일명 필터 (부분 일치)", value="")
    with colf2:
        only_missing = st.checkbox("섹션 누락 파일만 보기(요약 대상 1/2/3/9/15 기준)", value=False)

    if not uploaded_files:
        st.info("위에서 PDF를 업로드하세요.")
        return

    # 파일 읽기
    entries = []
    for uf in uploaded_files:
        b = uf.getvalue()
        if not b:
            continue
        entries.append(
            {
                "name": uf.name,
                "size_kb": round(uf.size / 1024, 1),
                "bytes": b,
                "is_pdf": b.startswith(b"%PDF"),
            }
        )

    if name_filter.strip():
        needle = name_filter.strip().lower()
        entries = [e for e in entries if needle in e["name"].lower()]

    # 섹션 추출/요약
    progress = st.progress(0, text="처리 중...")
    rows = []
    start = time.time()

    for i, ent in enumerate(entries, start=1):
        fname = ent["name"]
        status = "OK"
        err = ""
        sections = {}

        s1_summary = {"product_name": "", "company_name": "", "address": ""}
        s1_applied = None
        s2_summary = {}
        s3_summary = {}   # ← 섹션3 요약

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

                # 섹션 2 요약
                s2_text = sections.get("유해성위험성", "")
                if s2_text:
                    try:
                        s2_summary = parse_section_sec2_hazard(s2_text) or {}
                    except Exception as e2:
                        s2_summary = {}
                        err = (err + " | " if err else "") + f"sec2 parse error: {e2}"

                # 섹션 3 요약 (구성성분 → 조성표)
                s3_text = sections.get("구성성분", "")
                if s3_text:
                    try:
                        s3_summary = extract_section3_composition(s3_text) or {}
                    except Exception as e3:
                        s3_summary = {}
                        err = (err + " | " if err else "") + f"sec3 parse error: {e3}"

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

        # 섹션 2 요약값
        s2_sig = ""
        s2_h_codes = []
        s2_p_codes = []
        s2_pic_ids = []
        if isinstance(s2_summary, dict) and s2_summary:
            s2_sig = s2_summary.get("signal_word") or ""
            s2_h_codes = s2_summary.get("hazard_codes") or []
            s2_p_codes = (
                s2_summary.get("precautionary_codes_flat")
                or s2_summary.get("precautionary_codes_raw")
                or []
            )
            pictos = s2_summary.get("pictograms") or []
            s2_pic_ids = [p.get("id") for p in pictos if p.get("id")]

        rows.append(
            {
                "#": i,
                "File": fname,
                "KB": ent["size_kb"],
                "Status": status,
                "Found": len(found),
                "Missing": len(missing),
                "len_1": lens.get("화학제품과_회사정보", 0),
                "len_2": lens.get("유해성위험성", 0),
                "len_3": lens.get("구성성분", 0),
                "len_9": lens.get("물리화학적특성", 0),
                "len_15": lens.get("법적규제", 0),
                "제품명": s1_summary.get("product_name", ""),
                "회사명": s1_summary.get("company_name", ""),
                "주소": s1_summary.get("address", ""),
                "S2_신호어": s2_sig or "",
                "S2_H개수": len(s2_h_codes),
                "S2_P개수": len(s2_p_codes),
                "S2_그림문자개수": len(s2_pic_ids),
                "_sections": sections,
                "_s1": s1_summary,
                "_s1_applied": s1_applied,
                "_s2": s2_summary,
                "_s3": s3_summary,   # ← 섹션3 요약 저장
                "_err": err,
            }
        )

        progress.progress(i / max(1, len(entries)), text=f"처리 중... ({i}/{len(entries)})")

    elapsed = time.time() - start
    progress.empty()
    st.success(f"총 {len(rows)}개 파일 처리 완료 (약 {elapsed:.1f}초)")

    # 요약 테이블
    df = pd.DataFrame(
        [
            {
                "#": r["#"],
                "File": r["File"],
                "KB": r["KB"],
                "제품명": r["제품명"],
                "회사명": r["회사명"],
                "주소": r["주소"],
                "S2_신호어": r["S2_신호어"],
                "S2_H개수": r["S2_H개수"],
                "S2_P개수": r["S2_P개수"],
                "S2_그림문자개수": r["S2_그림문자개수"],
            }
            for r in rows
        ]
    )

    if only_missing:
        missing_indices = [idx for idx, r in enumerate(rows) if r["Missing"] > 0]
        df_view = df.iloc[missing_indices].reset_index(drop=True)
    else:
        df_view = df

    st.subheader("요약")
    st.caption(
        "파일별로 제품명·회사명·주소와, 섹션 2에서 추출된 신호어 / H코드 개수 / P코드 개수 / GHS 그림문자 개수를 표로 제공합니다. "
        "섹션 1~16 전체 원문은 아래 '파일별 상세'에서 탭으로 확인할 수 있습니다."
    )
    st.dataframe(
        df_view,
        use_container_width=True,
        height=min(1000, 100 + 40 * max(4, len(df_view))),
    )

    # 파일별 상세
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
                color = (
                    "#28a745"
                    if r["Missing"] == 0 and r["Status"] == "OK"
                    else ("#dc3545" if r["Status"] != "OK" or r["Missing"] > 0 else "#6c757d")
                )
                _render_badge(r["Status"], color)

            if r["_err"]:
                st.error(f"에러: {r['_err']}")

            # 실제 적용된 YAML 팩 id/name 배지
            if r.get("_s1_applied"):
                _render_badge(f"applied: {r['_s1_applied']}", "#7952b3")

            # 섹션1 텍스트 기준 패턴팩 후보 표시
            s1_text = r["_sections"].get("화학제품과_회사정보", "")
            if s1_text:
                s1_dbg = preview_packs_sec1(s1_text)
                top = s1_dbg.get("top", [])
                if top:
                    pack_id = top[0].get("id") or top[0].get("name")
                    _render_badge(f"apply? {pack_id} · {top[0]['score']}", "#17a2b8")

            sections = r["_sections"]
            keys = [k for k in ALL_SECTION_KEYS if sections.get(k)]
            if not keys:
                st.warning("추출된 섹션이 없습니다.")
            else:
                # 번호 탭 (1~16)
                tab_labels = []
                for k in keys:
                    n = SECNUM.get(k)
                    tab_labels.append(str(n) if n is not None else k)
                tabs = st.tabs(tab_labels)

                for k, tab in zip(keys, tabs):
                    with tab:
                        text = sections.get(k, "") or ""
                        full_title = SECTION_TITLES.get(k, k)
                        st.caption(f"{full_title} · 길이: {len(text):,}자")

                        # 섹션 1 요약 카드
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
                                unsafe_allow_html=True,
                            )

                        # 섹션 2 요약 카드
                        if k == "유해성위험성":
                            s2 = r.get("_s2") or {}
                            if isinstance(s2, dict) and s2:
                                signal_word = s2.get("signal_word") or "—"
                                h_codes = s2.get("hazard_codes") or []
                                p_codes = (
                                    s2.get("precautionary_codes_flat")
                                    or s2.get("precautionary_codes_raw")
                                    or []
                                )
                                pictos = s2.get("pictograms") or []

                                h_codes_str = ", ".join(h_codes) if h_codes else "—"
                                p_codes_str = ", ".join(p_codes) if p_codes else "—"
                                pic_ids_str = (
                                    ", ".join([p.get("id", "") for p in pictos if p.get("id")]) or "—"
                                )

                                st.markdown(
                                    f"""
                                    <div style="padding:12px;border:1px solid #e9ecef;border-radius:12px;background:#fff;margin:6px 0;">
                                        <div style="font-weight:600;margin-bottom:6px;">섹션 2 요약 (유해성·위험성)</div>
                                        <div><b>신호어</b>: {signal_word}</div>
                                        <div><b>H 코드</b>: {h_codes_str}</div>
                                        <div><b>P 코드</b>: {p_codes_str}</div>
                                        <div><b>GHS 그림문자 코드</b>: {pic_ids_str}</div>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )

                                if pictos:
                                    st.markdown("##### GHS 그림문자")
                                    cols = st.columns(len(pictos))
                                    for col, pic in zip(cols, pictos):
                                        with col:
                                            img_path = pic.get("image")
                                            pic_id = pic.get("id", "")
                                            if img_path and os.path.exists(img_path):
                                                st.image(img_path, caption=pic_id, width=100)
                                            else:
                                                st.write(pic_id)

                        # 섹션 3 요약 카드 (구성성분)
                        if k == "구성성분":
                            s3 = r.get("_s3") or {}
                            rows3 = s3.get("rows") if isinstance(s3, dict) else None

                            if rows3:
                                st.markdown(
                                    """
                                    <div style="padding:12px;border:1px solid #e9ecef;border-radius:12px;background:#fff;margin:6px 0;">
                                        <div style="font-weight:600;margin-bottom:6px;">섹션 3 요약 (구성성분)</div>
                                        <div style="font-size:13px;color:#495057;">
                                            CAS 번호, 상·하한, 함유량과 대표값만 간단히 표로 정리했습니다.
                                        </div>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )

                                import numpy as np
                                df_comp = pd.DataFrame(rows3)
                                if not df_comp.empty:
                                    n = len(df_comp)

                                    def _col(name):
                                        if name in df_comp.columns:
                                            return df_comp[name]
                                        # 컬럼이 없으면 빈 값으로 채움
                                        return pd.Series([""] * n)

                                    df_view = pd.DataFrame(
                                        {
                                            "cas_no": _col("cas"),
                                            "상한": _col("conc_max"),
                                            "하한": _col("conc_min"),
                                            "함유량": _col("concentration_raw"),
                                            "대표값": _col("conc_repr"),
                                        }
                                    )

                                    st.dataframe(
                                        df_view,
                                        use_container_width=True,
                                        height=min(400, 80 + 30 * len(df_view)),
                                    )
                            else:
                                st.info("섹션 3 텍스트는 있으나, CAS/함유량 패턴을 찾지 못했습니다.")

                        # 섹션 15: 지금은 규제 매핑 없이 안내 + 원문
                        if k == "법적규제":
                            st.markdown(
                                """
                                <div style="padding:12px;border:1px solid #e9ecef;border-radius:12px;background:#fff;margin:6px 0;">
                                    <div style="font-weight:600;margin-bottom:4px;">섹션 15 (법적 규제현황)</div>
                                    <div style="font-size:13px;color:#495057;">
                                        현재 버전에서는 별도의 규제항목 매핑 없이, 아래에 섹션 15 전체 원문을 그대로 제공합니다.
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                        # 공통: 섹션 원문
                        st.text_area(
                            label=full_title,
                            value=text,
                            height=360,
                            key=f"{r['#']}_txt_{k}_{len(text)}",
                        )

        _download_json_button(r["_sections"], Path(r["File"]).stem)
