from __future__ import annotations

import math
from datetime import datetime
from textwrap import dedent
from urllib.parse import quote_plus

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


def inject_global_css(view_mode: str = "Desktop") -> None:
    max_width = "1480px" if view_mode == "Desktop" else "760px"
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
            padding: 10px 14px 18px !important;
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

        .gf-sidebar-shell {
            min-height: 100vh;
            box-sizing: border-box;
            padding: 16px 14px;
        }

        .gf-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 4px 4px 14px;
            border-bottom: 1px solid rgba(255,255,255,.08);
            margin-bottom: 10px;
        }

        .gf-brand-mark {
            width: 34px;
            height: 34px;
            border-radius: 10px;
            background: linear-gradient(145deg, #12b9ae, #45d4b6);
            display: flex;
            align-items: flex-end;
            justify-content: center;
            gap: 2px;
            padding: 7px;
            box-shadow: 0 5px 14px rgba(20,166,158,.20);
        }

        .gf-brand-mark span { display:block; width:4px; border-radius:3px; background:white; }
        .gf-brand-mark span:nth-child(1) { height:9px; opacity:.8; }
        .gf-brand-mark span:nth-child(2) { height:15px; }
        .gf-brand-mark span:nth-child(3) { height:21px; opacity:.92; }

        .gf-brand-title { color:#fff; font-size:15px; font-weight:800; line-height:1.1; }
        .gf-brand-sub { color:#9fb7cf; font-size:10px; margin-top:3px; }

        .gf-nav {
            display:flex;
            flex-direction:column;
            gap:5px;
        }

        .gf-nav-item {
            display:flex;
            align-items:center;
            gap:9px;
            min-height:38px;
            padding:0 10px;
            border-radius:9px;
            border-left:3px solid transparent;
            color:#d7e5f3 !important;
            text-decoration:none !important;
            font-size:12px;
            font-weight:650;
            transition:background .14s ease,border-color .14s ease,color .14s ease;
        }

        .gf-nav-item:hover {
            background:rgba(255,255,255,.055);
            color:#fff !important;
        }

        .gf-nav-item.active {
            background:linear-gradient(90deg,#164b78,#174a75);
            border-left-color:#20c6bb;
            color:#fff !important;
            font-weight:760;
        }

        .gf-nav-icon {
            width:16px;
            flex:0 0 16px;
            text-align:center;
            color:#a9c4dc;
            font-size:14px;
        }

        .gf-view-label {
            color:#7896b5;
            font-size:10px;
            font-weight:800;
            letter-spacing:.10em;
            text-transform:uppercase;
            margin:16px 4px 7px;
        }

        .gf-mode {
            display:grid;
            grid-template-columns:1fr 1fr;
            gap:6px;
        }

        .gf-mode-item {
            display:flex;
            align-items:center;
            justify-content:center;
            min-height:34px;
            border-radius:8px;
            color:#a9c4dc !important;
            text-decoration:none !important;
            font-size:11px;
            font-weight:700;
            background:rgba(255,255,255,.025);
            border:1px solid rgba(255,255,255,.05);
        }

        .gf-mode-item.active {
            background:#174d79;
            border-color:rgba(32,198,187,.36);
            color:#fff !important;
            box-shadow:inset 3px 0 0 #20c6bb;
        }

        .gf-trust {
            margin-top:16px;
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

        .gf-topbar {
            min-height: 54px;
            background:#fff;
            border:1px solid var(--border);
            border-radius:12px;
            box-shadow:var(--shadow);
            display:grid;
            grid-template-columns:minmax(260px,1fr) auto auto auto;
            align-items:center;
            gap:12px;
            padding:8px 12px;
            margin-bottom:10px;
        }

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

        .gf-top-layout {
            display:flex;
            align-items:center;
            gap:6px;
        }

        .gf-top-layout-label {
            font-size:10px;
            color:#5e7086;
            font-weight:700;
            margin-right:2px;
        }

        .gf-top-mode {
            min-width:72px;
            height:32px;
            border-radius:8px;
            display:flex;
            align-items:center;
            justify-content:center;
            text-decoration:none !important;
            font-size:10px;
            font-weight:750;
            color:#53677d !important;
            border:1px solid #e2e9f1;
            background:#f8fafc;
        }

        .gf-top-mode.active {
            color:#fff !important;
            background:#0f4f78;
            border-color:#0f4f78;
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
        }

        .gf-user {
            display:flex;
            align-items:center;
            gap:8px;
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
            padding:0 2px 8px;
        }

        .gf-page-eyebrow {
            color:var(--teal);
            font-size:10px;
            font-weight:850;
            letter-spacing:.10em;
            text-transform:uppercase;
            margin-bottom:3px;
        }

        .gf-page-title {
            color:var(--text);
            font-size:28px !important;
            font-weight:850;
            line-height:1.05;
            margin:0 !important;
        }

        .gf-page-subtitle {
            color:var(--muted);
            font-size:13px;
            margin:4px 0 0;
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
            font-size:11px;
            font-weight:750;
            white-space:nowrap;
        }

        .gf-card {
            background:#fff;
            border:1px solid var(--border);
            border-radius:12px;
            padding:12px;
            box-shadow:var(--shadow);
            min-height:106px;
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
            font-size:11px;
            font-weight:750;
            margin-bottom:8px;
            white-space:nowrap;
        }

        .gf-card-icon {
            width:28px;
            height:28px;
            border-radius:8px;
            display:flex;
            align-items:center;
            justify-content:center;
            background:#edf4fb;
            font-size:12px;
        }

        .gf-card-value {
            color:var(--text);
            font-size:20px;
            font-weight:850;
            line-height:1.05;
            margin-bottom:6px;
            white-space:nowrap;
        }

        .gf-card-footnote { color:#78899c; font-size:10px; line-height:1.25; }
        .gf-card-trend-up { color:var(--success); font-weight:850; }
        .gf-card-trend-down { color:var(--danger); font-weight:850; }

        div[data-testid="stVerticalBlock"] { gap:.55rem !important; }
        div[data-testid="stHorizontalBlock"] { gap:.60rem !important; }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background:#fff;
            border-color:var(--border) !important;
            border-radius:12px !important;
            box-shadow:var(--shadow);
        }

        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding-top:.70rem;
            padding-bottom:.62rem;
        }

        .gf-section-title { color:var(--text); font-size:13px; font-weight:850; margin-bottom:2px; }
        .gf-section-caption { color:var(--muted); font-size:10px; margin-bottom:.45rem; }

        .stDataFrame, div[data-testid="stTable"] {
            border:1px solid var(--border);
            border-radius:9px;
            overflow:hidden;
        }

        .stProgress > div > div > div > div {
            background:linear-gradient(90deg,var(--teal),var(--success));
        }

        .gf-checklist { margin:0; padding-left:1rem; color:var(--muted); }
        .gf-checklist li { margin:.18rem 0; font-size:10px; }
        .gf-footer-note { text-align:center; color:#8998aa; font-size:9px; margin-top:.65rem; }
        .gf-gap-sm { height:6px; }
        .gf-gap-md { height:10px; }

        @media (max-width:900px) {
            section[data-testid="stSidebar"],
            [data-testid="stSidebar"] {
                min-width:210px !important;
                width:210px !important;
                max-width:210px !important;
            }

            section[data-testid="stSidebar"] > div,
            [data-testid="stSidebar"] > div:first-child {
                width:210px !important;
            }

            .gf-topbar {
                grid-template-columns:1fr;
                gap:7px;
            }

            .gf-user { display:none; }
            .gf-top-icon { display:none; }
            .gf-page-header { grid-template-columns:1fr; }
            .gf-month { justify-self:start; }
            .block-container { padding:8px 10px 14px !important; }
        }
    </style>
    """
    st.markdown(css.replace("__MAX_WIDTH__", max_width), unsafe_allow_html=True)


def _current_context() -> tuple[str, str]:
    params = st.query_params

    page_param = params.get("page", st.session_state.get("current_page", "Dashboard"))
    if isinstance(page_param, list):
        page_param = page_param[0] if page_param else "Dashboard"
    page = page_param if page_param in NAV_OPTIONS else "Dashboard"

    view_param = params.get("view", st.session_state.get("view_mode", "Desktop"))
    if isinstance(view_param, list):
        view_param = view_param[0] if view_param else "Desktop"
    view = view_param if view_param in {"Desktop", "Mobile"} else "Desktop"

    st.session_state["current_page"] = page
    st.session_state["view_mode"] = view
    return page, view


def render_sidebar(is_db_configured: bool) -> str:
    current, view = _current_context()

    nav_items = []
    for option in NAV_OPTIONS:
        active = " active" if option == current else ""
        href = f"?page={quote_plus(option)}&view={quote_plus(view)}"
        nav_items.append(
            f'<a class="gf-nav-item{active}" href="{href}" target="_self">'
            f'<span class="gf-nav-icon">{NAV_ICONS.get(option, "")}</span>'
            f'<span>{option}</span></a>'
        )

    desktop_active = " active" if view == "Desktop" else ""
    mobile_active = " active" if view == "Mobile" else ""
    state_class = "gf-status-ok" if is_db_configured else "gf-status-test"
    state_text = "Banco conectado" if is_db_configured else "Modo de teste"

    sidebar_html = (
        '<div class="gf-sidebar-shell">'
        '<div class="gf-brand">'
        '<div class="gf-brand-mark"><span></span><span></span><span></span></div>'
        '<div><div class="gf-brand-title">Gestão Financeira</div>'
        '<div class="gf-brand-sub">Controle, clareza e confiança.</div></div>'
        '</div>'
        '<nav class="gf-nav">' + ''.join(nav_items) + '</nav>'
        '<div class="gf-view-label">Visualização</div>'
        '<div class="gf-mode">'
        f'<a class="gf-mode-item{desktop_active}" href="?page={quote_plus(current)}&view=Desktop" target="_self">Desktop</a>'
        f'<a class="gf-mode-item{mobile_active}" href="?page={quote_plus(current)}&view=Mobile" target="_self">Mobile</a>'
        '</div>'
        '<div class="gf-trust">'
        '<div class="gf-trust-title">▱ Seus dados estão protegidos</div>'
        '<div class="gf-trust-text">Segurança, privacidade e confiabilidade como base do controle financeiro.</div>'
        f'<div class="gf-status {state_class}">● {state_text}</div>'
        '</div>'
        '</div>'
    )

    with st.sidebar:
        st.markdown(sidebar_html, unsafe_allow_html=True)

    return current


def render_topbar(page: str, view_mode: str) -> None:
    desktop_active = " active" if view_mode == "Desktop" else ""
    mobile_active = " active" if view_mode == "Mobile" else ""

    html = (
        '<div class="gf-topbar">'
        '<div class="gf-search">⌕ <span>Buscar movimentações, contas, categorias...</span></div>'
        '<div class="gf-top-layout">'
        '<span class="gf-top-layout-label">Layout</span>'
        f'<a class="gf-top-mode{desktop_active}" href="?page={quote_plus(page)}&view=Desktop" target="_self">Desktop</a>'
        f'<a class="gf-top-mode{mobile_active}" href="?page={quote_plus(page)}&view=Mobile" target="_self">Mobile</a>'
        '</div>'
        '<div class="gf-top-icon">♢</div>'
        '<div class="gf-user">'
        '<div class="gf-avatar">GF</div>'
        '<div><div class="gf-user-name">Gestão Financeira</div>'
        '<div class="gf-user-sub">Conta principal</div></div>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


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
