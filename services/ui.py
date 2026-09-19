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


def inject_global_css(view_mode: str = "Desktop") -> None:
    max_width = "1710px" if view_mode == "Desktop" else "820px"
    st.markdown(
        f"""
        <style>
            :root {{
                --bg: #f4f7fb;
                --surface: #ffffff;
                --border: #dfe7f0;
                --text: #10243f;
                --muted: #6f8096;
                --navy: #071d37;
                --navy-2: #0c3158;
                --teal: #18b8ad;
                --success: #12a66d;
                --danger: #d95662;
                --shadow: 0 5px 16px rgba(17,48,82,.055);
            }}

            html, body, [class*="css"] {{
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }}

            .stApp {{ background: var(--bg); }}

            header[data-testid="stHeader"],
            [data-testid="stToolbar"],
            [data-testid="stAppToolbar"],
            [data-testid="stDecoration"],
            .stAppDeployButton,
            #MainMenu,
            footer {{
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
            }}

            [data-testid="collapsedControl"],
            [data-testid="stSidebarCollapseButton"],
            button[aria-label="Close sidebar"],
            button[aria-label="Open sidebar"] {{
                display: none !important;
                visibility: hidden !important;
            }}

            .block-container {{
                padding-top: .22rem !important;
                padding-bottom: .65rem !important;
                padding-left: .72rem !important;
                padding-right: .72rem !important;
                max-width: {max_width};
            }}

            /* SIDEBAR FIXA E SEM O ESPAÇO SUPERIOR PADRÃO DO STREAMLIT */
            section[data-testid="stSidebar"],
            [data-testid="stSidebar"] {{
                background: linear-gradient(180deg, #071d37 0%, #0c3158 58%, #092541 100%) !important;
                border-right: 1px solid rgba(255,255,255,.06) !important;
                min-width: 232px !important;
                width: 232px !important;
                max-width: 232px !important;
                transform: none !important;
            }}

            section[data-testid="stSidebar"] > div,
            [data-testid="stSidebar"] > div:first-child {{
                width: 232px !important;
                padding-top: 0 !important;
                margin-top: 0 !important;
            }}

            [data-testid="stSidebarUserContent"],
            [data-testid="stSidebarContent"],
            section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
                padding-top: .35rem !important;
                margin-top: 0 !important;
            }}

            [data-testid="stSidebarUserContent"],
            [data-testid="stSidebarContent"] {{
                padding-left: .70rem !important;
                padding-right: .70rem !important;
                padding-bottom: .65rem !important;
            }}

            [data-testid="stSidebar"] * {{ color: #dce9f7; }}
            [data-testid="stSidebarNav"] {{ display: none !important; }}

            .gf-brand {{
                display: flex;
                align-items: center;
                gap: 9px;
                padding: 3px 5px 10px;
                margin: 0 0 6px 0;
                border-bottom: 1px solid rgba(255,255,255,.08);
            }}

            .gf-brand-mark {{
                width: 29px;
                height: 29px;
                border-radius: 9px;
                background: linear-gradient(145deg, #14bfb4, #42d4b4);
                display: flex;
                align-items: flex-end;
                justify-content: center;
                gap: 2px;
                padding: 6px;
                box-shadow: 0 4px 14px rgba(20,166,158,.18);
                flex: 0 0 auto;
            }}

            .gf-brand-mark span {{ display:block; width:3px; border-radius:3px; background:#fff; }}
            .gf-brand-mark span:nth-child(1) {{ height:8px; opacity:.8; }}
            .gf-brand-mark span:nth-child(2) {{ height:13px; }}
            .gf-brand-mark span:nth-child(3) {{ height:18px; opacity:.92; }}
            .gf-brand-title {{ color:#fff; font-size:.94rem; font-weight:800; line-height:1.1; }}
            .gf-brand-sub {{ color:#9fb7cf; font-size:.60rem; margin-top:2px; }}

            /* MENU LATERAL: RADIO TRANSFORMADO EM NAVEGAÇÃO DE APP */
            [data-testid="stSidebar"] [data-testid="stRadio"] > div[role="radiogroup"] {{
                gap: 4px !important;
            }}

            [data-testid="stSidebar"] [data-baseweb="radio"] {{
                width: 100% !important;
                min-height: 37px !important;
                padding: 0 9px !important;
                border-radius: 7px !important;
                background: transparent !important;
                border-left: 3px solid transparent !important;
                display: flex !important;
                align-items: center !important;
                transition: background .14s ease, border-color .14s ease !important;
                cursor: pointer !important;
            }}

            [data-testid="stSidebar"] [data-baseweb="radio"]:hover {{
                background: rgba(255,255,255,.055) !important;
            }}

            [data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child {{
                display: none !important;
            }}

            [data-testid="stSidebar"] [data-baseweb="radio"] [data-testid="stMarkdownContainer"] {{
                width: 100% !important;
            }}

            [data-testid="stSidebar"] [data-baseweb="radio"] [data-testid="stMarkdownContainer"] p {{
                margin: 0 !important;
                color: #d7e5f3 !important;
                font-size: .77rem !important;
                line-height: 1.2 !important;
                font-weight: 620 !important;
                white-space: nowrap !important;
            }}

            [data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked),
            [data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="true"] {{
                background: linear-gradient(90deg, #154b78, #174a75) !important;
                border-left-color: #20c6bb !important;
                box-shadow: inset 0 0 0 1px rgba(255,255,255,.025) !important;
            }}

            [data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) [data-testid="stMarkdownContainer"] p,
            [data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="true"] [data-testid="stMarkdownContainer"] p {{
                color: #ffffff !important;
                font-weight: 760 !important;
            }}

            .gf-view-label {{
                color:#7896b5;
                font-size:.62rem;
                font-weight:800;
                letter-spacing:.10em;
                text-transform:uppercase;
                margin: 12px 4px 5px;
            }}

            /* SEGMENTO DESKTOP / MOBILE */
            [data-testid="stSidebar"] .gf-mode-wrap + div [data-testid="stRadio"] > div[role="radiogroup"] {{
                display: grid !important;
                grid-template-columns: 1fr 1fr !important;
                gap: 5px !important;
            }}

            .gf-trust {{
                margin-top: 14px;
                padding: 11px 10px;
                border-radius: 11px;
                background: rgba(255,255,255,.052);
                border: 1px solid rgba(255,255,255,.065);
            }}
            .gf-trust-title {{ color:#f4fbff; font-size:.72rem; font-weight:800; margin-bottom:4px; }}
            .gf-trust-text {{ color:#9fb7cf; font-size:.61rem; line-height:1.38; }}
            .gf-status {{
                display:inline-flex;
                align-items:center;
                gap:4px;
                margin-top:8px;
                padding:3px 6px;
                border-radius:999px;
                font-size:.60rem;
                font-weight:800;
            }}
            .gf-status-ok {{ background:rgba(20,166,158,.14); color:#80e8dd; }}
            .gf-status-test {{ background:rgba(234,155,57,.14); color:#ffd39e; }}

            /* CABEÇALHO PRINCIPAL COM ALTURA MÍNIMA */
            .gf-page-header {{
                padding: 0 .02rem .28rem !important;
                margin: 0 !important;
            }}

            .gf-page-eyebrow {{
                color: var(--teal);
                font-size: .58rem !important;
                font-weight: 850;
                letter-spacing: .11em;
                text-transform: uppercase;
                margin: 0 0 1px !important;
            }}

            .gf-title-row {{
                display: grid;
                grid-template-columns: minmax(0,1fr) auto;
                align-items: center;
                gap: 12px;
            }}

            .gf-page-title {{
                color: var(--text);
                font-size: 1.23rem !important;
                font-weight: 850;
                line-height: 1 !important;
                margin: 0;
            }}

            .gf-page-subtitle {{
                color: var(--muted);
                font-size: .64rem !important;
                margin: 2px 0 0 !important;
            }}

            .gf-month {{
                display:inline-flex;
                align-items:center;
                gap:5px;
                padding:4px 7px;
                border:1px solid var(--border);
                border-radius:8px;
                background:#fff;
                color:#31506f;
                font-size:.62rem;
                font-weight:750;
                white-space:nowrap;
                margin:0;
                justify-self:end;
            }}

            .gf-card {{
                background:#fff;
                border:1px solid var(--border);
                border-radius:12px;
                padding:9px 10px 7px;
                box-shadow:var(--shadow);
                min-height:92px;
                height:100%;
            }}
            .gf-card-tonal-success {{ background:linear-gradient(180deg,#f0fbf7,#ffffff); }}
            .gf-card-tonal-info {{ background:linear-gradient(180deg,#f2f7fd,#ffffff); }}
            .gf-card-tonal-danger {{ background:linear-gradient(180deg,#fff4f5,#ffffff); }}
            .gf-card-tonal-neutral {{ background:linear-gradient(180deg,#ffffff,#fbfdff); }}

            .gf-card-label {{
                display:flex;
                align-items:center;
                gap:7px;
                color:#405a74;
                font-size:.70rem;
                font-weight:750;
                margin-bottom:6px;
                white-space:nowrap;
            }}
            .gf-card-icon {{
                width:26px;
                height:26px;
                border-radius:8px;
                display:flex;
                align-items:center;
                justify-content:center;
                background:#edf4fb;
                font-size:.76rem;
                flex:0 0 auto;
            }}
            .gf-card-value {{
                color:var(--text);
                font-size:1.06rem;
                line-height:1.05;
                font-weight:850;
                margin-bottom:5px;
                white-space:nowrap;
            }}
            .gf-card-footnote {{ color:#78899c; font-size:.60rem; line-height:1.32; }}
            .gf-card-trend-up {{ color:var(--success); font-weight:850; }}
            .gf-card-trend-down {{ color:var(--danger); font-weight:850; }}

            div[data-testid="stVerticalBlock"] {{ gap: .42rem !important; }}
            div[data-testid="stHorizontalBlock"] {{ gap: .42rem !important; }}

            div[data-testid="stVerticalBlockBorderWrapper"] {{
                background:#fff;
                border-color:var(--border) !important;
                border-radius:11px !important;
                box-shadow:var(--shadow);
            }}
            div[data-testid="stVerticalBlockBorderWrapper"] > div {{
                padding-top:.54rem;
                padding-bottom:.46rem;
            }}

            .gf-section-title {{ color:var(--text); font-size:.80rem; font-weight:850; margin-bottom:2px; }}
            .gf-section-caption {{ color:var(--muted); font-size:.63rem; margin-bottom:.38rem; }}

            .stDataFrame, div[data-testid="stTable"] {{
                border:1px solid var(--border);
                border-radius:9px;
                overflow:hidden;
            }}

            .stProgress > div > div > div > div {{
                background:linear-gradient(90deg,var(--teal),var(--success));
            }}

            .gf-checklist {{ margin:0; padding-left:.9rem; color:var(--muted); }}
            .gf-checklist li {{ margin:.16rem 0; font-size:.62rem; }}
            .gf-footer-note {{ text-align:center; color:#8998aa; font-size:.63rem; margin-top:.55rem; }}
            .gf-empty-note {{
                margin:.20rem 0 .32rem;
                border:1px dashed #c9d7e6;
                border-radius:9px;
                background:#f8fbff;
                color:#66809a;
                font-size:.64rem;
                padding:6px 9px;
            }}

            @media (max-width: 900px) {{
                section[data-testid="stSidebar"],
                [data-testid="stSidebar"] {{
                    min-width: 220px !important;
                    width: 220px !important;
                    max-width: 220px !important;
                }}
                section[data-testid="stSidebar"] > div,
                [data-testid="stSidebar"] > div:first-child {{
                    width: 220px !important;
                }}
                .gf-title-row {{
                    grid-template-columns: 1fr;
                    gap:5px;
                }}
                .gf-month {{ justify-self:start; }}
                .block-container {{
                    padding-left:.55rem !important;
                    padding-right:.55rem !important;
                }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(is_db_configured: bool) -> str:
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

        current = st.session_state.get("current_page", "Dashboard")
        selected = st.radio(
            "Navegação",
            NAV_OPTIONS,
            index=NAV_OPTIONS.index(current),
            format_func=lambda option: f"{NAV_ICONS.get(option, '')}  {option}",
            key="nav_menu",
            label_visibility="collapsed",
        )
        if selected != current:
            st.session_state["current_page"] = selected
            st.rerun()

        st.markdown("<div class='gf-view-label'>Visualização</div><div class='gf-mode-wrap'></div>", unsafe_allow_html=True)
        view = st.session_state.get("view_mode", "Desktop")
        selected_view = st.radio(
            "Modo de visualização",
            ["Desktop", "Mobile"],
            index=0 if view == "Desktop" else 1,
            horizontal=True,
            key="view_mode_radio",
            label_visibility="collapsed",
        )
        if selected_view != view:
            st.session_state["view_mode"] = selected_view
            st.rerun()

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
    month_label = f"{MONTHS_PT[now.month]} de {now.year}"
    st.markdown(
        f"""
        <div class="gf-page-header">
            <div class="gf-page-eyebrow">Sua gestão em primeiro lugar</div>
            <div class="gf-title-row">
                <h1 class="gf-page-title">{page_title}</h1>
                <div class="gf-month">▣ {month_label}</div>
            </div>
            <p class="gf-page-subtitle">{subtitle}</p>
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
