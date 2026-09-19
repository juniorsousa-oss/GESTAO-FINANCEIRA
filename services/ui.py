from __future__ import annotations

import math
from datetime import datetime
from textwrap import dedent

import streamlit as st


NAV_OPTIONS = [
    "Dashboard",
    "Movimentações",
    "Contas e Previsões",
    "Contas e Saldos",
    "Dívidas",
    "Importar Excel",
    "Configurações",
]

NAV_ICONS = {
    "Dashboard": "⌂",
    "Movimentações": "⇄",
    "Contas e Previsões": "▤",
    "Contas e Saldos": "▦",
    "Dívidas": "▧",
    "Importar Excel": "⇩",
    "Configurações": "⚙",
}

MONTHS_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _set_page(page: str) -> None:
    st.session_state["current_page"] = page


def _set_view(view: str) -> None:
    st.session_state["view_mode"] = view


def inject_global_css(view_mode: str = "Desktop") -> None:
    max_width = "1500px" if view_mode == "Desktop" else "760px"
    css = """
    <style>
        :root {
            --bg: #f4f7fb;
            --surface: #ffffff;
            --border: #dfe7ef;
            --text: #10243f;
            --muted: #6c7d91;
            --navy: #082541;
            --navy-2: #0b3155;
            --teal: #19b5aa;
            --success: #13a66d;
            --danger: #d95560;
            --shadow: 0 5px 16px rgba(21, 48, 78, .06);
        }

        html, body, [class*="css"] {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .stApp { background: var(--bg); }

        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stAppToolbar"],
        [data-testid="stDecoration"],
        .stAppDeployButton,
        #MainMenu,
        footer {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
        }

        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapseButton"],
        button[aria-label="Close sidebar"],
        button[aria-label="Open sidebar"] {
            display: none !important;
        }

        .block-container {
            max-width: __MAX_WIDTH__;
            padding: 12px 16px 20px !important;
        }

        section[data-testid="stSidebar"],
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #071e38 0%, #0b3158 58%, #092644 100%) !important;
            border-right: 1px solid rgba(255,255,255,.06) !important;
            min-width: 220px !important;
            width: 220px !important;
            max-width: 220px !important;
            transform: none !important;
        }

        section[data-testid="stSidebar"] > div,
        [data-testid="stSidebar"] > div:first-child {
            width: 220px !important;
            padding: 0 !important;
        }

        [data-testid="stSidebarUserContent"],
        [data-testid="stSidebarContent"] {
            padding: 0 !important;
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: .28rem !important;
        }

        .gf-sidebar-brand {
            display:flex;
            align-items:center;
            gap:10px;
            margin:16px 14px 12px;
            padding:4px 4px 15px;
            border-bottom:1px solid rgba(255,255,255,.08);
        }

        .gf-brand-mark {
            width:34px;
            height:34px;
            border-radius:10px;
            background:linear-gradient(145deg,#12b9ae,#45d4b6);
            display:flex;
            align-items:flex-end;
            justify-content:center;
            gap:2px;
            padding:7px;
            box-shadow:0 5px 14px rgba(20,166,158,.20);
            flex:0 0 auto;
        }

        .gf-brand-mark span { display:block; width:4px; border-radius:3px; background:#fff; }
        .gf-brand-mark span:nth-child(1) { height:9px; opacity:.8; }
        .gf-brand-mark span:nth-child(2) { height:15px; }
        .gf-brand-mark span:nth-child(3) { height:21px; opacity:.92; }
        .gf-brand-title { color:#fff; font-size:15px; font-weight:800; line-height:1.1; }
        .gf-brand-sub { color:#9fb7cf; font-size:9px; margin-top:3px; }

        [data-testid="stSidebar"] .stButton {
            padding:0 14px;
        }

        [data-testid="stSidebar"] .stButton > button {
            width:100% !important;
            min-height:38px !important;
            justify-content:flex-start !important;
            border-radius:9px !important;
            padding:0 11px !important;
            font-size:12px !important;
            font-weight:650 !important;
            border:0 !important;
            box-shadow:none !important;
            transition:background .14s ease,color .14s ease !important;
        }

        [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
            background:transparent !important;
            color:#d7e5f3 !important;
        }

        [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover {
            background:rgba(255,255,255,.055) !important;
            color:#fff !important;
        }

        [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
            background:linear-gradient(90deg,#164b78,#174a75) !important;
            color:#fff !important;
            border-left:3px solid #20c6bb !important;
            font-weight:760 !important;
        }

        .gf-trust {
            margin:16px 14px 0;
            padding:12px 11px;
            border-radius:12px;
            background:rgba(255,255,255,.052);
            border:1px solid rgba(255,255,255,.065);
        }

        .gf-trust-title { color:#f4fbff; font-size:11px; font-weight:800; margin-bottom:4px; }
        .gf-trust-text { color:#9fb7cf; font-size:9px; line-height:1.45; }

        .gf-status {
            display:inline-flex;
            align-items:center;
            gap:4px;
            margin-top:8px;
            padding:4px 7px;
            border-radius:999px;
            font-size:9px;
            font-weight:800;
        }

        .gf-status-ok { background:rgba(20,166,158,.14); color:#80e8dd; }
        .gf-status-test { background:rgba(234,155,57,.14); color:#ffd39e; }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) {
            background:#fff;
            border:1px solid var(--border) !important;
            border-radius:12px !important;
            box-shadow:var(--shadow);
            margin-bottom:14px;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) > div {
            padding:10px 12px !important;
        }

        .gf-topbar-marker { display:none; }

        .gf-search {
            height:36px;
            background:#f5f8fb;
            border:1px solid #e3ebf3;
            border-radius:8px;
            display:flex;
            align-items:center;
            gap:8px;
            padding:0 11px;
            color:#8795a7;
            font-size:11px;
        }

        .gf-top-layout-label {
            height:36px;
            display:flex;
            align-items:center;
            justify-content:flex-end;
            color:#5e7086;
            font-size:10px;
            font-weight:750;
        }

        .block-container > div > div > div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"]:first-of-type .stButton > button {
            min-height:36px !important;
            border-radius:8px !important;
            padding:0 13px !important;
            font-size:10px !important;
            font-weight:750 !important;
            box-shadow:none !important;
        }

        .block-container button[data-testid="stBaseButton-primary"] {
            background:#0f4f78 !important;
            border-color:#0f4f78 !important;
            color:#fff !important;
        }

        .block-container button[data-testid="stBaseButton-secondary"] {
            background:#f8fafc !important;
            border:1px solid #e2e9f1 !important;
            color:#53677d !important;
        }

        .gf-top-icon {
            width:34px;
            height:34px;
            border-radius:50%;
            border:1px solid #e2e9f1;
            display:flex;
            align-items:center;
            justify-content:center;
            color:#244766;
            background:#fff;
            font-size:14px;
            margin:auto;
        }

        .gf-user {
            display:flex;
            align-items:center;
            gap:8px;
            min-height:36px;
            padding-left:10px;
            border-left:1px solid #e5ebf1;
        }

        .gf-avatar {
            width:30px;
            height:30px;
            border-radius:50%;
            display:flex;
            align-items:center;
            justify-content:center;
            background:#0d3158;
            color:white;
            font-size:10px;
            font-weight:800;
        }

        .gf-user-name { color:#16314e; font-size:10px; font-weight:800; line-height:1.1; }
        .gf-user-sub { color:#8a98a8; font-size:8px; margin-top:2px; }

        .gf-page-header {
            display:grid;
            grid-template-columns:minmax(0,1fr) auto;
            gap:12px;
            align-items:end;
            padding:2px 2px 12px;
        }

        .gf-page-eyebrow {
            color:var(--teal);
            font-size:9px;
            font-weight:850;
            letter-spacing:.10em;
            text-transform:uppercase;
            margin-bottom:4px;
        }

        .gf-page-title {
            color:var(--text);
            font-size:26px !important;
            font-weight:850;
            line-height:1.05;
            margin:0 !important;
        }

        .gf-page-subtitle {
            color:var(--muted);
            font-size:12px;
            margin:5px 0 0;
        }

        .gf-month {
            display:inline-flex;
            align-items:center;
            gap:6px;
            padding:7px 10px;
            border:1px solid var(--border);
            border-radius:8px;
            background:#fff;
            color:#31506f;
            font-size:10px;
            font-weight:750;
            white-space:nowrap;
        }

        .gf-card {
            background:#fff;
            border:1px solid var(--border);
            border-radius:12px;
            padding:11px;
            box-shadow:var(--shadow);
            min-height:102px;
            height:100%;
        }

        .gf-card-tonal-success { background:linear-gradient(180deg,#f1fbf7,#fff); }
        .gf-card-tonal-info { background:linear-gradient(180deg,#f3f8fd,#fff); }
        .gf-card-tonal-danger { background:linear-gradient(180deg,#fff5f6,#fff); }
        .gf-card-tonal-neutral { background:linear-gradient(180deg,#fff,#fbfdff); }

        .gf-card-label {
            display:flex;
            align-items:center;
            gap:7px;
            color:#405a74;
            font-size:10px;
            font-weight:750;
            margin-bottom:7px;
            white-space:nowrap;
        }

        .gf-card-icon {
            width:26px;
            height:26px;
            border-radius:8px;
            display:flex;
            align-items:center;
            justify-content:center;
            background:#edf4fb;
            font-size:11px;
        }

        .gf-card-value {
            color:var(--text);
            font-size:18px;
            font-weight:850;
            line-height:1.05;
            margin-bottom:5px;
            white-space:nowrap;
        }

        .gf-card-footnote { color:#78899c; font-size:9px; line-height:1.25; }
        .gf-card-trend-up { color:var(--success); font-weight:850; }
        .gf-card-trend-down { color:var(--danger); font-weight:850; }

        div[data-testid="stVerticalBlock"] { gap:.65rem !important; }
        div[data-testid="stHorizontalBlock"] { gap:.68rem !important; }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background:#fff;
            border-color:var(--border) !important;
            border-radius:12px !important;
            box-shadow:var(--shadow);
        }

        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding-top:.72rem;
            padding-bottom:.66rem;
        }

        .gf-section-title { color:var(--text); font-size:12px; font-weight:850; margin-bottom:3px; }
        .gf-section-caption { color:var(--muted); font-size:9px; margin-bottom:.48rem; }

        .stDataFrame, div[data-testid="stTable"] {
            border:1px solid var(--border);
            border-radius:9px;
            overflow:hidden;
        }

        .stProgress > div > div > div > div {
            background:linear-gradient(90deg,var(--teal),var(--success));
        }

        .gf-checklist { margin:0; padding-left:1rem; color:var(--muted); }
        .gf-checklist li { margin:.18rem 0; font-size:9px; }
        .gf-footer-note { text-align:center; color:#8998aa; font-size:9px; margin-top:.65rem; }
        .gf-gap-sm { height:7px; }
        .gf-gap-md { height:12px; }

        @media (max-width:900px) {
            section[data-testid="stSidebar"],
            [data-testid="stSidebar"] {
                min-width:205px !important;
                width:205px !important;
                max-width:205px !important;
            }

            section[data-testid="stSidebar"] > div,
            [data-testid="stSidebar"] > div:first-child {
                width:205px !important;
            }

            .gf-page-header { grid-template-columns:1fr; }
            .gf-month { justify-self:start; }
            .gf-user { display:none; }
            .gf-top-icon { display:none; }
            .block-container { padding:10px 10px 16px !important; }
        }
    </style>
    """
    st.markdown(css.replace("__MAX_WIDTH__", max_width), unsafe_allow_html=True)


def render_sidebar(is_db_configured: bool) -> str:
    current = st.session_state.get("current_page", "Dashboard")
    if current not in NAV_OPTIONS:
        current = "Dashboard"
        st.session_state["current_page"] = current

    with st.sidebar:
        st.markdown(
            """
            <div class="gf-sidebar-brand">
                <div class="gf-brand-mark"><span></span><span></span><span></span></div>
                <div>
                    <div class="gf-brand-title">Gestão Financeira</div>
                    <div class="gf-brand-sub">Controle, clareza e confiança.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for option in NAV_OPTIONS:
            st.button(
                f"{NAV_ICONS.get(option, '')}   {option}",
                key=f"nav_{option}",
                use_container_width=True,
                type="primary" if option == current else "secondary",
                on_click=_set_page,
                args=(option,),
            )

        state_class = "gf-status-ok" if is_db_configured else "gf-status-test"
        state_text = "Banco conectado" if is_db_configured else "Modo de teste"
        st.markdown(
            f"""
            <div class="gf-trust">
                <div class="gf-trust-title">▱ Seus dados estão protegidos</div>
                <div class="gf-trust-text">Segurança, privacidade e confiabilidade como base do controle financeiro.</div>
                <div class="gf-status {state_class}">● {state_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return st.session_state.get("current_page", "Dashboard")


def render_topbar(page: str, view_mode: str) -> None:
    with st.container(border=True):
        st.markdown("<div class='gf-topbar-marker'></div>", unsafe_allow_html=True)
        c_search, c_label, c_desktop, c_mobile, c_icon, c_user = st.columns(
            [4.8, .55, .72, .72, .42, 1.2],
            gap="small",
            vertical_alignment="center",
        )

        with c_search:
            st.markdown(
                "<div class='gf-search'>⌕ <span>Buscar movimentações, contas, categorias...</span></div>",
                unsafe_allow_html=True,
            )

        with c_label:
            st.markdown("<div class='gf-top-layout-label'>Layout</div>", unsafe_allow_html=True)

        with c_desktop:
            st.button(
                "Desktop",
                key="top_desktop",
                use_container_width=True,
                type="primary" if view_mode == "Desktop" else "secondary",
                on_click=_set_view,
                args=("Desktop",),
            )

        with c_mobile:
            st.button(
                "Mobile",
                key="top_mobile",
                use_container_width=True,
                type="primary" if view_mode == "Mobile" else "secondary",
                on_click=_set_view,
                args=("Mobile",),
            )

        with c_icon:
            st.markdown("<div class='gf-top-icon'>♢</div>", unsafe_allow_html=True)

        with c_user:
            st.markdown(
                """
                <div class="gf-user">
                    <div class="gf-avatar">GF</div>
                    <div>
                        <div class="gf-user-name">Gestão Financeira</div>
                        <div class="gf-user-sub">Conta principal</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_page_header(page_title: str, subtitle: str) -> str:
    now = datetime.now()
    month_label = f"{MONTHS_PT[now.month]} de {now.year}"

    st.markdown(
        f"""
        <div class="gf-page-header">
            <div>
                <div class="gf-page-eyebrow">Sua gestão em primeiro lugar</div>
                <h1 class="gf-page-title">{page_title}</h1>
                <p class="gf-page-subtitle">{subtitle}</p>
            </div>
            <div class="gf-month">▣ {month_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return st.session_state.get("view_mode", "Desktop")


def metric_card(
    title: str,
    value: str,
    note: str = "",
    tone: str = "neutral",
    icon: str = "●",
    trend: str | None = None,
) -> str:
    tone_class = {
        "success": "gf-card-tonal-success",
        "info": "gf-card-tonal-info",
        "danger": "gf-card-tonal-danger",
        "neutral": "gf-card-tonal-neutral",
    }.get(tone, "gf-card-tonal-neutral")

    trend_html = ""
    if trend:
        css = "gf-card-trend-up" if not trend.strip().startswith("-") and "↓" not in trend else "gf-card-trend-down"
        trend_html = f"<span class='{css}'>{trend}</span>"

    return dedent(
        f"""
        <div class="gf-card {tone_class}">
            <div class="gf-card-label">
                <div class="gf-card-icon">{icon}</div>
                <div>{title}</div>
            </div>
            <div class="gf-card-value">{value}</div>
            <div class="gf-card-footnote">{trend_html}{' · ' if trend_html and note else ''}{note}</div>
        </div>
        """
    )


def show_metric_grid(cards: list[str], view_mode: str = "Desktop") -> None:
    if view_mode == "Desktop":
        cols_per_row = 6
        total_rows = math.ceil(len(cards) / cols_per_row)
        for row in range(total_rows):
            cols = st.columns(cols_per_row, gap="small")
            start = row * cols_per_row
            end = start + cols_per_row
            for col, card in zip(cols, cards[start:end]):
                with col:
                    st.markdown(card, unsafe_allow_html=True)
        return

    for card in cards:
        st.markdown(card, unsafe_allow_html=True)


def section_header(title: str, caption: str = "") -> None:
    st.markdown(f"<div class='gf-section-title'>{title}</div>", unsafe_allow_html=True)
    if caption:
        st.markdown(f"<div class='gf-section-caption'>{caption}</div>", unsafe_allow_html=True)
