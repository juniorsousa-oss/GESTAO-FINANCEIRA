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
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def _set_page(page: str) -> None:
    st.session_state["current_page"] = page


def _sync_view() -> None:
    st.session_state["view_mode"] = st.session_state.get("_view_selector", "Desktop")


def inject_global_css(view_mode: str = "Desktop") -> None:
    content_max = "100%" if view_mode == "Desktop" else "760px"

    css = """
    <style>
        :root {
            --page: #f4f7fb;
            --panel: #ffffff;
            --panel-soft: #f8fafc;
            --line: #dce5ee;
            --line-soft: #e8eef4;
            --ink: #10233f;
            --ink-2: #36506b;
            --muted: #73859a;
            --nav: #082643;
            --nav-2: #0b355d;
            --accent: #19b7aa;
            --primary: #124c77;
            --success: #159769;
            --danger: #d95b65;
            --shadow: 0 6px 18px rgba(20, 48, 78, .055);
        }

        html, body, [class*="css"] {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        main {
            background: var(--page) !important;
        }

        footer {
            display: none !important;
        }

        /* Header nativo permanece funcional: Share, GitHub, menu e recolhimento da sidebar. */
        header[data-testid="stHeader"] {
            height: 46px !important;
            min-height: 46px !important;
            background: var(--page) !important;
            border-bottom: 1px solid var(--line-soft) !important;
        }

        [data-testid="stToolbar"],
        [data-testid="stAppToolbar"] {
            align-items: center !important;
        }

        /* Conteúdo sempre ocupa a largura liberada pela sidebar. */
        .block-container {
            width: 100% !important;
            max-width: __CONTENT_MAX__ !important;
            padding: 12px 16px 20px !important;
            box-sizing: border-box !important;
        }

        /* SIDEBAR */
        section[data-testid="stSidebar"],
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--nav) 0%, var(--nav-2) 100%) !important;
            border-right: 1px solid rgba(255,255,255,.06) !important;
            min-width: 238px !important;
            width: 238px !important;
            max-width: 238px !important;
        }

        section[data-testid="stSidebar"] > div,
        [data-testid="stSidebar"] > div:first-child {
            width: 238px !important;
            padding: 0 !important;
        }

        [data-testid="stSidebarUserContent"],
        [data-testid="stSidebarContent"] {
            padding: 0 !important;
        }

        section[data-testid="stSidebar"][aria-expanded="false"],
        [data-testid="stSidebar"][aria-expanded="false"] {
            min-width: 0 !important;
            width: 0 !important;
            max-width: 0 !important;
            border-right: 0 !important;
            overflow: hidden !important;
        }

        .gf-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 12px 14px 10px;
            padding: 4px 2px 15px;
            border-bottom: 1px solid rgba(255,255,255,.09);
        }

        .gf-brand-mark {
            width: 34px;
            height: 34px;
            border-radius: 10px;
            padding: 7px;
            display: flex;
            gap: 2px;
            align-items: flex-end;
            justify-content: center;
            flex: 0 0 34px;
            background: linear-gradient(145deg, #14bdb1, #43d0b2);
            box-shadow: 0 7px 18px rgba(14,178,165,.18);
        }

        .gf-brand-mark span {
            width: 4px;
            background: #fff;
            border-radius: 3px;
        }

        .gf-brand-mark span:nth-child(1) { height: 9px; opacity: .78; }
        .gf-brand-mark span:nth-child(2) { height: 15px; }
        .gf-brand-mark span:nth-child(3) { height: 21px; opacity: .92; }

        .gf-brand-title {
            color: #fff;
            font-size: 15px;
            font-weight: 800;
            line-height: 1.05;
        }

        .gf-brand-sub {
            color: #a6bdd3;
            font-size: 9px;
            margin-top: 3px;
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 4px !important;
        }

        [data-testid="stSidebar"] .stButton {
            padding: 0 14px !important;
            margin: 0 !important;
        }

        [data-testid="stSidebar"] .stButton > button {
            width: 100% !important;
            min-height: 38px !important;
            justify-content: flex-start !important;
            padding: 0 11px !important;
            border: 0 !important;
            border-radius: 9px !important;
            box-shadow: none !important;
            font-size: 12px !important;
            font-weight: 650 !important;
        }

        [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
            color: #dbe7f2 !important;
            background: transparent !important;
        }

        [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover {
            color: #fff !important;
            background: rgba(255,255,255,.055) !important;
        }

        [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
            color: #fff !important;
            background: linear-gradient(90deg, #174f7d, #17466f) !important;
            border-left: 3px solid var(--accent) !important;
            font-weight: 780 !important;
        }

        .gf-trust {
            margin: 16px 14px 0;
            padding: 12px;
            border: 1px solid rgba(255,255,255,.07);
            border-radius: 11px;
            background: rgba(255,255,255,.045);
        }

        .gf-trust-title {
            color: #fff;
            font-size: 10px;
            font-weight: 800;
            margin-bottom: 4px;
        }

        .gf-trust-text {
            color: #a8bdd1;
            font-size: 8.5px;
            line-height: 1.45;
        }

        .gf-status {
            display: inline-flex;
            align-items: center;
            margin-top: 8px;
            padding: 3px 7px;
            border-radius: 999px;
            font-size: 8px;
            font-weight: 800;
        }

        .gf-status-ok {
            color: #88eadf;
            background: rgba(25,183,170,.14);
        }

        .gf-status-test {
            color: #ffd39c;
            background: rgba(235,157,60,.14);
        }

        /* TOPBAR DO APP */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) {
            margin: 0 0 14px !important;
            background: rgba(255,255,255,.50) !important;
            border: 1px solid var(--line) !important;
            border-radius: 12px !important;
            box-shadow: none !important;
            overflow: visible !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) > div {
            padding: 8px 10px !important;
        }

        .gf-topbar-marker {
            display: none;
        }

        .gf-search {
            height: 34px;
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 0 11px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: rgba(255,255,255,.66);
            color: #8493a5;
            font-size: 10px;
        }

        .gf-layout-caption {
            color: var(--muted);
            font-size: 9px;
            font-weight: 750;
            margin-bottom: 4px;
            text-align: center;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) [data-testid="stRadio"] > div {
            display: flex !important;
            flex-direction: row !important;
            justify-content: center !important;
            gap: 6px !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) [data-baseweb="radio"] {
            min-width: 78px !important;
            min-height: 32px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 0 12px !important;
            border: 1px solid var(--line) !important;
            border-radius: 8px !important;
            background: rgba(255,255,255,.62) !important;
            cursor: pointer !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) [data-baseweb="radio"] > div:first-child {
            display: none !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) [data-baseweb="radio"] p {
            margin: 0 !important;
            color: #5d7086 !important;
            font-size: 10px !important;
            font-weight: 750 !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) [data-baseweb="radio"]:has(input:checked) {
            border-color: var(--primary) !important;
            background: var(--primary) !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-topbar-marker) [data-baseweb="radio"]:has(input:checked) p {
            color: #fff !important;
        }

        .gf-top-icon {
            width: 32px;
            height: 32px;
            margin: auto;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--line);
            border-radius: 50%;
            color: var(--ink-2);
            background: rgba(255,255,255,.68);
            font-size: 12px;
        }

        .gf-user {
            min-height: 34px;
            display: flex;
            align-items: center;
            gap: 8px;
            padding-left: 10px;
            border-left: 1px solid var(--line);
        }

        .gf-avatar {
            width: 29px;
            height: 29px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--nav);
            color: #fff;
            font-size: 9px;
            font-weight: 800;
        }

        .gf-user-name {
            color: var(--ink);
            font-size: 9px;
            font-weight: 800;
            line-height: 1.05;
        }

        .gf-user-sub {
            color: var(--muted);
            font-size: 7px;
            margin-top: 2px;
        }

        /* CABEÇALHO DE PÁGINA */
        .gf-page-header {
            display: grid;
            grid-template-columns: minmax(0,1fr) auto;
            align-items: end;
            gap: 12px;
            padding: 0 2px 12px;
        }

        .gf-eyebrow {
            color: var(--accent);
            font-size: 9px;
            font-weight: 850;
            letter-spacing: .12em;
            text-transform: uppercase;
            margin-bottom: 4px;
        }

        .gf-page-title {
            margin: 0 !important;
            color: var(--ink);
            font-size: 28px !important;
            font-weight: 850;
            line-height: 1.02;
        }

        .gf-page-subtitle {
            margin: 5px 0 0;
            color: var(--muted);
            font-size: 11px;
        }

        .gf-period {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 6px 9px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--panel);
            color: var(--ink-2);
            font-size: 9px;
            font-weight: 750;
            white-space: nowrap;
        }

        /* Uma só régua de espaçamento para os seis KPIs e as faixas do Dashboard. */
        :root { --gf-dashboard-gap: 12px; }

        .gf-kpi-grid {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: var(--gf-dashboard-gap);
            width: 100%;
        }

        .gf-kpi-grid--mobile { grid-template-columns: minmax(0, 1fr); }

        .gf-kpi-grid > .gf-kpi {
            min-width: 0;
            width: 100%;
            height: 100%;
        }

        @media (max-width: 1100px) {
            .gf-kpi-grid:not(.gf-kpi-grid--mobile) {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }
        }

        @media (max-width: 640px) {
            .gf-kpi-grid {
                grid-template-columns: minmax(0, 1fr) !important;
            }
        }

        /* KPI CARDS */
        .gf-kpi {
            min-height: 94px;
            padding: 11px;
            box-sizing: border-box;
            border: 1px solid var(--line);
            border-radius: 11px;
            background: var(--panel);
            box-shadow: var(--shadow);
        }

        .gf-kpi-success { background: linear-gradient(180deg, #f1fbf7 0%, #fff 100%); }
        .gf-kpi-info { background: linear-gradient(180deg, #f3f8fd 0%, #fff 100%); }
        .gf-kpi-danger { background: linear-gradient(180deg, #fff5f6 0%, #fff 100%); }

        .gf-kpi-head {
            display: flex;
            align-items: center;
            gap: 7px;
            color: #405a74;
            font-size: 9.5px;
            font-weight: 760;
            margin-bottom: 7px;
            white-space: nowrap;
        }

        .gf-kpi-icon {
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 24px;
            border-radius: 7px;
            background: #edf4fb;
            color: #315a7a;
            font-size: 10px;
        }

        .gf-kpi-value {
            color: var(--ink);
            font-size: 17px;
            line-height: 1.02;
            font-weight: 850;
            margin-bottom: 5px;
            white-space: nowrap;
        }

        .gf-kpi-note {
            color: var(--muted);
            font-size: 8.5px;
            line-height: 1.25;
        }

        .gf-up { color: var(--success); font-weight: 850; }
        .gf-down { color: var(--danger); font-weight: 850; }

        /* PAINÉIS */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--line) !important;
            border-radius: 11px !important;
            background: var(--panel) !important;
            box-shadow: var(--shadow);
        }

        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding-top: .62rem;
            padding-bottom: .56rem;
        }

        .gf-section-title {
            color: var(--ink);
            font-size: 11px;
            font-weight: 850;
            margin-bottom: 2px;
        }

        .gf-section-caption {
            color: var(--muted);
            font-size: 8.5px;
            margin-bottom: .34rem;
        }

        div[data-testid="stVerticalBlock"] {
            gap: var(--gf-dashboard-gap) !important;
        }

        div[data-testid="stHorizontalBlock"] {
            gap: var(--gf-dashboard-gap) !important;
        }

        /* Separadores antigos deixavam distâncias diferentes entre as faixas. */
        .gf-gap { display: none !important; }

        /* COMPONENTES PADRÃO DAS PÁGINAS INTERNAS */
        h1 {
            color: var(--ink) !important;
        }

        h2, h3 {
            color: var(--ink) !important;
        }

        [data-testid="stMetric"] {
            padding: 12px 14px !important;
            border: 1px solid var(--line) !important;
            border-radius: 10px !important;
            background: var(--panel) !important;
        }

        [data-testid="stMetricLabel"] {
            color: var(--muted) !important;
        }

        [data-testid="stMetricValue"] {
            color: var(--ink) !important;
        }

        [data-testid="stExpander"] {
            border: 1px solid var(--line) !important;
            border-radius: 10px !important;
            background: var(--panel) !important;
        }

        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input {
            border-color: var(--line) !important;
            border-radius: 8px !important;
            background: #fff !important;
        }

        .stDataFrame,
        div[data-testid="stTable"] {
            overflow: hidden;
            border: 1px solid var(--line);
            border-radius: 9px;
        }

        .stProgress > div > div > div > div {
            background: linear-gradient(90deg, var(--accent), var(--success));
        }

        .gf-checklist {
            margin: 0;
            padding-left: 1rem;
            color: var(--muted);
        }

        .gf-checklist li {
            margin: .16rem 0;
            font-size: 9px;
        }

        .gf-footer-note {
            margin-top: .55rem;
            text-align: center;
            color: #92a0af;
            font-size: 8px;
        }

        @media (max-width: 900px) {
            section[data-testid="stSidebar"],
            [data-testid="stSidebar"] {
                min-width: 210px !important;
                width: 210px !important;
                max-width: 210px !important;
            }

            section[data-testid="stSidebar"] > div,
            [data-testid="stSidebar"] > div:first-child {
                width: 210px !important;
            }

            .block-container {
                padding: 10px 10px 18px !important;
            }

            .gf-page-header {
                grid-template-columns: 1fr;
            }

            .gf-period {
                justify-self: start;
            }

            .gf-user {
                display: none;
            }

            .gf-top-icon {
                display: none;
            }
        }
    </style>
    """

    st.markdown(css.replace("__CONTENT_MAX__", content_max), unsafe_allow_html=True)


def render_sidebar(is_db_configured: bool) -> str:
    current = st.session_state.get("current_page", "Dashboard")
    if current not in NAV_OPTIONS:
        current = "Dashboard"
        st.session_state["current_page"] = current

    with st.sidebar:
        st.markdown(
            """
            <div class="gf-brand">
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
    if "_view_selector" not in st.session_state:
        st.session_state["_view_selector"] = view_mode
    elif st.session_state["_view_selector"] != view_mode:
        st.session_state["_view_selector"] = view_mode

    with st.container(border=True):
        st.markdown("<div class='gf-topbar-marker'></div>", unsafe_allow_html=True)
        c_search, c_view, c_icon, c_user = st.columns(
            [5.7, 1.8, .42, 1.45],
            gap="small",
            vertical_alignment="center",
        )

        with c_search:
            st.markdown(
                "<div class='gf-search'>⌕ <span>Buscar movimentações, contas, categorias...</span></div>",
                unsafe_allow_html=True,
            )

        with c_view:
            st.markdown("<div class='gf-layout-caption'>Layout</div>", unsafe_allow_html=True)
            st.radio(
                "Layout",
                ["Desktop", "Mobile"],
                horizontal=True,
                key="_view_selector",
                label_visibility="collapsed",
                on_change=_sync_view,
            )

        with c_icon:
            st.markdown("<div class='gf-top-icon'>◇</div>", unsafe_allow_html=True)

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
    period = f"{MONTHS_PT[now.month]} de {now.year}"

    st.markdown(
        f"""
        <div class="gf-page-header">
            <div>
                <div class="gf-eyebrow">Sua gestão em primeiro lugar</div>
                <h1 class="gf-page-title">{page_title}</h1>
                <p class="gf-page-subtitle">{subtitle}</p>
            </div>
            <div class="gf-period">▣ {period}</div>
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
        "success": "gf-kpi-success",
        "info": "gf-kpi-info",
        "danger": "gf-kpi-danger",
        "neutral": "",
    }.get(tone, "")

    trend_html = ""
    if trend:
        trend_class = "gf-down" if "↓" in trend or trend.strip().startswith("-") else "gf-up"
        trend_html = f"<span class='{trend_class}'>{trend}</span>"

    separator = " · " if trend_html and note else ""

    return dedent(
        f"""
        <div class="gf-kpi {tone_class}">
            <div class="gf-kpi-head">
                <div class="gf-kpi-icon">{icon}</div>
                <div>{title}</div>
            </div>
            <div class="gf-kpi-value">{value}</div>
            <div class="gf-kpi-note">{trend_html}{separator}{note}</div>
        </div>
        """
    )


def show_metric_grid(cards: list[str], view_mode: str = "Desktop") -> None:
    """Renderiza KPIs numa única grade, com o mesmo vão em todas as direções."""
    if not cards:
        return

    layout = "gf-kpi-grid--mobile" if view_mode == "Mobile" else ""
    # Um único bloco HTML evita margens individuais do Markdown/colunas Streamlit.
    html = f'<div class="gf-kpi-grid {layout}">' + "".join(card.strip() for card in cards) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def section_header(title: str, caption: str = "") -> None:
    st.markdown(f"<div class='gf-section-title'>{title}</div>", unsafe_allow_html=True)
    if caption:
        st.markdown(f"<div class='gf-section-caption'>{caption}</div>", unsafe_allow_html=True)
