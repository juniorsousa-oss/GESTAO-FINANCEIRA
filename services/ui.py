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


def _set_sidebar_open(opened: bool) -> None:
    """O controle próprio é a única fonte de estado da navegação lateral."""
    st.session_state["gf_sidebar_open"] = opened


@st.fragment
def render_sidebar_toggle() -> None:
    """Atualiza só o menu; não reexecuta o Dashboard nem consulta novamente o banco."""
    opened = st.session_state.get("gf_sidebar_open", True)
    st.button(
        "«" if opened else "»",
        key="gf_sidebar_toggle",
        help="Fechar menu lateral" if opened else "Abrir menu lateral",
        on_click=_set_sidebar_open,
        args=(not opened,),
    )

    # Estilo emitido pelo fragmento: o próprio navegador anima a largura,
    # sem reconstruir os indicadores ou os gráficos financeiros.
    width = "var(--gf-sidebar-width)" if opened else "0px"
    opacity = "1" if opened else "0"
    pointer_events = "auto" if opened else "none"
    border = "1px" if opened else "0px"
    st.markdown(
        f"""
        <style>
            section[data-testid="stSidebar"] {{
                display: flex !important;
                visibility: visible !important;
                transform: none !important;
                width: {width} !important;
                min-width: {width} !important;
                max-width: {width} !important;
                flex: 0 0 {width} !important;
                opacity: {opacity} !important;
                pointer-events: {pointer_events} !important;
                border-right-width: {border} !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_global_css(view_mode: str = "Desktop") -> None:
    content_max = "1460px" if view_mode == "Desktop" else "760px"

    css = """
    <style>
        /* Tema claro único, independente do modo escuro do sistema/navegador.
           A identidade azul do cabeçalho e da lateral é preservada. */
        :root, html, body, .stApp {
            color-scheme: light !important;
        }

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
            --gf-sidebar-width: 238px;
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

        /* O header nativo não participa da navegação. O controle próprio
           não depende dos identificadores internos das versões Streamlit. */
        header[data-testid="stHeader"] {
            height: 70px !important;
            min-height: 70px !important;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            z-index: 1 !important;
            pointer-events: none !important;
        }

        /* A estrutura visível é fixa; este wrapper não cria espaço no fluxo. */
        div[data-testid="stElementContainer"]:has(.gf-app-header) {
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            overflow: visible !important;
        }
        .gf-app-header {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 70px;
            z-index: 100002;
            box-sizing: border-box;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 0 24px 0 70px;
            color: #fff;
            background: var(--nav);
            border-bottom: 1px solid rgba(255,255,255,.08);
            pointer-events: none; /* não cobre o botão nativo da sidebar */
        }
        .gf-header-brand {
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 0;
        }
        .gf-header-logo {
            width: 40px;
            height: 40px;
            flex: 0 0 40px;
            border-radius: 10px;
            display: flex;
            align-items: flex-end;
            justify-content: center;
            gap: 3px;
            padding: 9px 0;
            box-sizing: border-box;
            background: linear-gradient(145deg,#14bdb1,#43d0b2);
        }
        .gf-header-logo i {
            width: 5px;
            border-radius: 3px;
            background: white;
            display: block;
        }
        .gf-header-logo i:nth-child(1) { height: 12px; opacity: .8; }
        .gf-header-logo i:nth-child(2) { height: 18px; }
        .gf-header-logo i:nth-child(3) { height: 24px; }
        .gf-header-name {
            font-size: 21px;
            font-weight: 800;
            line-height: 1.12;
            white-space: nowrap;
            letter-spacing: -.02em;
        }
        .gf-header-tagline {
            font-size: 10px;
            color: #b3c8dc;
            margin-top: 3px;
            white-space: nowrap;
        }
        .gf-header-user {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            font-weight: 750;
            white-space: nowrap;
            color: #f4f9ff;
        }
        .gf-header-user-avatar {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 34px;
            border-radius: 50%;
            border: 2px solid rgba(255,255,255,.74);
            background: rgba(255,255,255,.13);
            color: #fff;
            font-size: 15px;
            font-weight: 800;
        }
        .gf-header-user-caption {
            margin-top: 2px;
            color: #b3c8dc;
            font-size: 9px;
            font-weight: 500;
        }

        /* Os controles nativos são ocultados por completo para não criar
           dois estados independentes de abertura/fechamento. */
        [data-testid="stToolbar"],
        [data-testid="stAppToolbar"],
        [data-testid="stHeaderActionElements"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stDecoration"],
        [data-testid="stAppDeployButton"],
        #MainMenu {
            display: none !important;
        }

        /* Único botão próprio: mesma posição e o mesmo widget ao abrir/fechar. */
        .st-key-gf_sidebar_toggle {
            position: fixed !important;
            top: 15px !important;
            left: 12px !important;
            width: 40px !important;
            height: 40px !important;
            z-index: 2147483000 !important;
            padding: 0 !important;
            margin: 0 !important;
            pointer-events: auto !important;
        }
        .st-key-gf_sidebar_toggle button {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 40px !important;
            min-width: 40px !important;
            height: 40px !important;
            min-height: 40px !important;
            padding: 0 !important;
            border: 1px solid rgba(255,255,255,.16) !important;
            border-radius: 9px !important;
            background: rgba(255,255,255,.09) !important;
            color: #fff !important;
            font-size: 25px !important;
            font-weight: 700 !important;
            line-height: 1 !important;
            box-shadow: none !important;
        }
        .st-key-gf_sidebar_toggle button:hover {
            background: rgba(255,255,255,.19) !important;
        }
        .st-key-gf_sidebar_toggle button p {
            color: #fff !important;
            font-size: 25px !important;
            line-height: 1 !important;
            margin: 0 !important;
        }
        [data-testid="stElementContainer"]:has(.st-key-gf_sidebar_toggle) {
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            overflow: visible !important;
        }

        /* Conteúdo sempre ocupa a largura liberada pela sidebar. */
        .block-container {
            width: 100% !important;
            max-width: __CONTENT_MAX__ !important;
            margin-inline: auto !important;
            padding: 83px 14px 18px !important;
            box-sizing: border-box !important;
        }

        /* Uma única fonte para a largura: a classe CSS e o estado do fragmento.
           Manter o elemento montado torna possível a animação sem display:none. */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--nav) 0%, var(--nav-2) 100%) !important;
            border-right: 1px solid rgba(255,255,255,.06) !important;
            box-sizing: border-box !important;
            overflow: hidden !important;
            z-index: 100020 !important;
            transition: width .23s ease, min-width .23s ease,
                        max-width .23s ease, flex-basis .23s ease,
                        opacity .18s ease !important;
            will-change: width;
        }

        section[data-testid="stSidebar"] > div {
            width: var(--gf-sidebar-width) !important;
            min-width: var(--gf-sidebar-width) !important;
            padding: 0 !important;
        }

        @media (prefers-reduced-motion: reduce) {
            section[data-testid="stSidebar"] { transition: none !important; }
        }

        [data-testid="stSidebarUserContent"],
        [data-testid="stSidebarContent"] {
            padding: 78px 0 12px !important;
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

        /* Camada única para KPIs: a moldura controla o respiro externo,
           enquanto a grade controla exclusivamente a distância entre os cards. */
        .gf-kpi-layer {
            display: block;
            width: 100%;
            min-width: 0;
            box-sizing: border-box;
            margin: 8px 0 18px;
            padding: 12px;
            border: 1px solid var(--line);
            border-radius: 14px;
            background: #edf3f8;
        }

        .gf-kpi-layer .gf-kpi-grid {
            margin: 0;
        }

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

        /* Faixas de gráficos e painéis inferiores: mesma camada externa dos KPIs. */
        .gf-panel-layer-marker { display: none; }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-panel-layer-marker) {
            width: 100%;
            min-width: 0;
            box-sizing: border-box;
            margin: 0 0 18px !important;
            padding: 0 !important;
            border: 1px solid var(--line) !important;
            border-radius: 14px !important;
            background: #edf3f8 !important;
            box-shadow: none !important;
            overflow: visible !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-panel-layer-marker) > div {
            padding: 12px !important;
        }

        /* O marcador apenas identifica a camada; não consome espaço na grade. */
        div[data-testid="stElementContainer"]:has(.gf-panel-layer-marker) {
            display: none !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-panel-layer-marker) div[data-testid="stHorizontalBlock"] {
            gap: var(--gf-dashboard-gap) !important;
            align-items: stretch !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-panel-layer-marker) div[data-testid="column"] {
            min-width: 0;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-panel-layer-marker) div[data-testid="stVerticalBlockBorderWrapper"]:not(:has(.gf-panel-layer-marker)) {
            margin: 0 !important;
            width: 100%;
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

        /* Espaçamento físico entre faixas: não depende das margens dos cards. */
        .gf-dashboard-band-gap {
            display: block !important;
            height: 12px !important;
            min-height: 12px !important;
            flex-shrink: 0 !important;
        }

        /* As faixas ocupam toda a largura disponível sem invadir a próxima. */
        .st-key-gf_dashboard_kpis,
        .st-key-gf_dashboard_charts,
        .st-key-gf_dashboard_bottom {
            width: 100%;
            min-width: 0;
            box-sizing: border-box;
        }

        .gf-kpi-layer { margin: 0 !important; }

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
            color: var(--ink) !important;
        }

        /* Legibilidade dos campos mesmo quando o dispositivo utiliza tema escuro. */
        [data-testid="stMain"] input,
        [data-testid="stMain"] textarea,
        [data-testid="stMain"] select,
        [data-testid="stMain"] [data-baseweb="select"],
        [data-testid="stMain"] [data-baseweb="input"] {
            color-scheme: light !important;
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

        /* Notebook: escala intermediária sem redimensionar o mobile.
           A sidebar usa o recolhimento nativo; não travar transform/flex dos pais. */
        @media (min-width: 901px) and (max-width: 1600px) {
            :root {
                --gf-dashboard-gap: 10px;
                --gf-sidebar-width: 212px;
            }

            .block-container {
                max-width: min(100%, 1380px) !important;
                padding: 82px 12px 16px !important;
            }

            .gf-brand { margin: 10px 11px 8px; padding-bottom: 11px; }
            [data-testid="stSidebar"] .stButton { padding: 0 11px !important; }
            [data-testid="stSidebar"] .stButton > button {
                min-height: 34px !important;
                padding: 0 9px !important;
                font-size: 11px !important;
            }
            .gf-trust { margin: 12px 11px 0; padding: 10px; }


            .gf-page-header { padding: 0 2px 8px; }
            .gf-page-title { font-size: 23px !important; }
            .gf-page-subtitle { font-size: 10px; margin-top: 4px; }
            .gf-eyebrow { margin-bottom: 3px; }
            .gf-period { padding: 5px 8px; }

            /* Cada camada decide seu padding e suas margens.
               Evita somar margens externas a gaps globais do Streamlit. */
            .gf-kpi-layer {
                padding: 10px;
                border-radius: 12px;
            }
            .gf-kpi { min-height: 84px; padding: 9px; border-radius: 10px; }
            .gf-kpi-head { gap: 6px; margin-bottom: 5px; font-size: 9px; }
            .gf-kpi-icon { width: 22px; height: 22px; flex-basis: 22px; }
            .gf-kpi-value { font-size: 16px; margin-bottom: 4px; }
            .gf-kpi-note { font-size: 8.5px; }

            div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-panel-layer-marker) {
                margin: 0 !important;
                border-radius: 12px !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-panel-layer-marker) > div {
                padding: 10px !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.gf-panel-layer-marker)
            div[data-testid="stVerticalBlockBorderWrapper"]:not(:has(.gf-panel-layer-marker)) > div {
                padding-top: 7px;
                padding-bottom: 7px;
            }
            .gf-section-title { font-size: 11px; }
            .gf-section-caption { margin-bottom: 4px; }
        }

        @media (max-width: 900px) {
            .gf-app-header {
                height: 64px;
                padding: 0 12px 0 60px;
                gap: 8px;
            }
            header[data-testid="stHeader"] {
                height: 64px !important;
                min-height: 64px !important;
            }
            .gf-header-logo { width: 32px; height: 32px; flex-basis: 32px; padding: 6px 0; gap: 2px; }
            .gf-header-logo i { width: 4px; }
            .gf-header-logo i:nth-child(1) { height: 9px; }
            .gf-header-logo i:nth-child(2) { height: 14px; }
            .gf-header-logo i:nth-child(3) { height: 19px; }
            .gf-header-brand { gap: 7px; }
            .gf-header-name { font-size: 13px; }
            .gf-header-tagline { display: none; }
            .gf-header-user { gap: 5px; font-size: 10px; }
            .gf-header-user-avatar { width: 25px; height: 25px; font-size: 10px; border-width: 1px; }
            .gf-header-user-caption { display: none; }
            [data-testid="stSidebarUserContent"],
            [data-testid="stSidebarContent"] { padding-top: 70px !important; }
            .st-key-gf_sidebar_toggle { top: 12px !important; left: 7px !important; }

            :root { --gf-sidebar-width: 210px; }

            .block-container {
                padding: 80px 10px 18px !important;
            }

            .gf-page-header {
                grid-template-columns: 1fr;
            }

            .gf-period {
                justify-self: start;
            }

        }
    </style>
    """

    st.markdown(css.replace("__CONTENT_MAX__", content_max), unsafe_allow_html=True)
def render_app_header() -> None:
    """Faixa de identidade fixa, sem controles falsos ou uma segunda navegação."""
    st.markdown(
        """
        <div class="gf-app-header" role="banner">
            <div class="gf-header-brand">
                <div class="gf-header-logo" aria-label="Marca Gestão Financeira"><i></i><i></i><i></i></div>
                <div>
                    <div class="gf-header-name">Gestão Financeira</div>
                    <div class="gf-header-tagline">Controle, clareza e confiança.</div>
                </div>
            </div>
            <div class="gf-header-user">
                <div class="gf-header-user-avatar" aria-hidden="true">U</div>
                <div>Olá, Usuário<div class="gf-header-user-caption">Conta principal</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_sidebar(is_db_configured: bool) -> str:
    current = st.session_state.get("current_page", "Dashboard")
    if current not in NAV_OPTIONS:
        current = "Dashboard"
        st.session_state["current_page"] = current

    with st.sidebar:
        for option in NAV_OPTIONS:
            st.button(
                f"{NAV_ICONS.get(option, '')}   {option}",
                key=f"nav_{option}",
                use_container_width=True,
                type="primary" if option == current else "secondary",
                on_click=_set_page,
                args=(option,),
            )

        # O seletor de visualização migra para a lateral ao retirar a topbar.
        view_mode = st.session_state.get("view_mode", "Desktop")
        if st.session_state.get("_view_selector") != view_mode:
            st.session_state["_view_selector"] = view_mode
        st.radio(
            "Visualização",
            ["Desktop", "Mobile"],
            horizontal=True,
            key="_view_selector",
            on_change=_sync_view,
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
    # Todos os cards vivem na mesma camada, com padding e margem próprios.
    # O HTML é emitido num único bloco para não criar wrappers/colunas por card.
    html = (
        f'<section class="gf-kpi-layer"><div class="gf-kpi-grid {layout}">'
        + "".join(card.strip() for card in cards)
        + "</div></section>"
    )
    st.markdown(html, unsafe_allow_html=True)


def section_header(title: str, caption: str = "") -> None:
    st.markdown(f"<div class='gf-section-title'>{title}</div>", unsafe_allow_html=True)
    if caption:
        st.markdown(f"<div class='gf-section-caption'>{caption}</div>", unsafe_allow_html=True)
