from __future__ import annotations

import math
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
    "Dashboard": "📊",
    "Movimentações": "💸",
    "Contas e Previsões": "🗓️",
    "Contas e Saldos": "🏦",
    "Dívidas": "📌",
    "Importar Excel": "📥",
    "Configurações": "⚙️",
}


def inject_global_css(view_mode: str = "Desktop") -> None:
    max_width = "1760px" if view_mode == "Desktop" else "860px"
    st.markdown(
        f"""
        <style>
            :root {{
                --bg: #f3f7fb;
                --surface: #ffffff;
                --surface-soft: #f8fbff;
                --border: #dce7f2;
                --text: #10223e;
                --muted: #60738d;
                --primary: #0d2e55;
                --primary-2: #123f72;
                --teal: #16a6a1;
                --success: #0a9b66;
                --danger: #d5525c;
                --warning: #f29f3d;
                --shadow: 0 10px 24px rgba(13, 46, 85, 0.08);
            }}

            .stApp {{
                background: linear-gradient(180deg, #eef3f8 0%, #f5f8fc 100%);
            }}

            /* Remove toda a barra superior nativa do Streamlit */
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

            /* Mantém o menu lateral fixo, aberto e sem controles de recolhimento */
            [data-testid="collapsedControl"],
            [data-testid="stSidebarCollapseButton"],
            button[aria-label="Close sidebar"],
            button[aria-label="Open sidebar"] {{
                display: none !important;
                visibility: hidden !important;
            }}

            [data-testid="stSidebar"] {{
                background: linear-gradient(180deg, #071c36 0%, #0c2f59 52%, #0c2647 100%);
                border-right: 1px solid rgba(255,255,255,.06);
                min-width: 300px !important;
                width: 300px !important;
                max-width: 300px !important;
                transform: none !important;
            }}

            [data-testid="stSidebar"] > div:first-child {{
                width: 300px !important;
            }}

            [data-testid="stSidebar"] * {{ color: #e7eef7; }}
            [data-testid="stSidebarNav"] {{ display:none; }}

            .block-container {{
                padding-top: .7rem;
                padding-bottom: 1.8rem;
                max-width: {max_width};
            }}

            .gf-brand {{
                background: linear-gradient(180deg, rgba(255,255,255,0.11), rgba(255,255,255,0.03));
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 20px;
                padding: 19px 16px;
                box-shadow: inset 0 1px 0 rgba(255,255,255,.08);
                margin-bottom: 12px;
            }}

            .gf-brand h2 {{
                color: #ffffff !important;
                font-size: 1.42rem;
                line-height: 1.1;
                margin: 0 0 7px 0;
            }}

            .gf-brand p {{
                color: #cad8ea;
                font-size: .86rem;
                margin: 0;
                line-height: 1.45;
            }}

            .gf-sidebar-box {{
                background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.04));
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
                padding: 13px 13px;
                margin-top: 12px;
            }}

            .gf-status-pill {{
                display: inline-block;
                padding: 6px 10px;
                border-radius: 999px;
                font-weight: 700;
                font-size: .80rem;
                margin-top: 4px;
            }}

            .gf-status-ok {{
                background: rgba(22,166,161,.18);
                color: #8ff1ea;
                border: 1px solid rgba(143,241,234,.18);
            }}

            .gf-status-test {{
                background: rgba(242,159,61,.18);
                color: #ffd5a2;
                border: 1px solid rgba(255,213,162,.16);
            }}

            [data-testid="stSidebar"] [data-testid="stRadio"] label p {{
                font-size: .92rem !important;
                font-weight: 700;
            }}

            [data-testid="stSidebar"] [data-testid="stRadio"] > div {{
                gap: 0.45rem;
            }}

            .gf-page-intro {{
                background: transparent;
                padding: 0 0 6px 0;
                margin-bottom: 10px;
            }}

            .gf-page-eyebrow {{
                font-size: .76rem;
                letter-spacing: .11em;
                text-transform: uppercase;
                color: var(--teal);
                font-weight: 800;
                margin-bottom: 4px;
            }}

            .gf-page-title {{
                color: var(--text);
                font-weight: 900;
                font-size: 2.02rem;
                line-height: 1.05;
                margin: 0;
            }}

            .gf-page-subtitle {{
                color: var(--muted);
                margin: 5px 0 0 0;
                font-size: .95rem;
            }}

            .gf-layout-label {{
                color: #b9cae0;
                font-size: .79rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: .05em;
                margin: 12px 0 2px;
            }}

            div[data-testid="stMetric"] {{
                background: linear-gradient(180deg, #ffffff, #fbfdff);
                border: 1px solid var(--border);
                border-radius: 18px;
                padding: 10px 14px;
                box-shadow: var(--shadow);
            }}

            div[data-testid="stMetric"] label {{
                color: var(--muted) !important;
                font-weight: 700 !important;
            }}

            div[data-testid="stMetricValue"] > div {{
                color: var(--text);
                font-weight: 800;
            }}

            div[data-testid="stMetricDelta"] > div {{ font-weight: 700; }}

            .gf-card {{
                background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 15px;
                box-shadow: var(--shadow);
                min-height: 138px;
                height: 100%;
            }}

            .gf-card-tonal-success {{ background: linear-gradient(180deg, #f2fcf8, #ffffff); }}
            .gf-card-tonal-info {{ background: linear-gradient(180deg, #f3f8ff, #ffffff); }}
            .gf-card-tonal-danger {{ background: linear-gradient(180deg, #fff5f6, #ffffff); }}
            .gf-card-tonal-neutral {{ background: linear-gradient(180deg, #ffffff, #fbfdff); }}

            .gf-card-label {{
                display:flex;
                align-items:center;
                gap:8px;
                font-size:.82rem;
                color:var(--muted);
                font-weight:700;
                margin-bottom:8px;
                white-space: nowrap;
            }}

            .gf-card-icon {{
                width:30px;
                height:30px;
                border-radius:10px;
                display:flex;
                align-items:center;
                justify-content:center;
                background:#eef5fc;
                font-size:.9rem;
                flex: 0 0 auto;
            }}

            .gf-card-value {{
                color:var(--text);
                font-weight:800;
                font-size:1.42rem;
                line-height:1.1;
                margin: 2px 0 6px 0;
                white-space: nowrap;
            }}

            .gf-card-footnote {{
                color:var(--muted);
                font-size:.76rem;
                line-height:1.3;
            }}

            .gf-card-trend-up {{ color: var(--success); font-weight: 800; }}
            .gf-card-trend-down {{ color: var(--danger); font-weight: 800; }}

            .gf-section-title {{
                color: var(--text);
                font-weight: 800;
                margin-bottom: 0.25rem;
            }}

            .gf-section-caption {{
                color: var(--muted);
                margin-bottom: .9rem;
                font-size: .90rem;
            }}

            .stDataFrame, div[data-testid="stTable"] {{
                border: 1px solid var(--border);
                border-radius: 16px;
                overflow: hidden;
            }}

            .stProgress > div > div > div > div {{
                background: linear-gradient(90deg, var(--teal), var(--success));
            }}

            .gf-checklist {{
                margin: 0;
                padding-left: 1rem;
                color: var(--muted);
            }}

            .gf-checklist li {{ margin: .25rem 0; }}

            .gf-footer-note {{
                text-align:center;
                color: var(--muted);
                font-size: .84rem;
                margin-top: 1rem;
            }}

            @media (max-width: 900px) {{
                [data-testid="stSidebar"] {{
                    min-width: 270px !important;
                    width: 270px !important;
                    max-width: 270px !important;
                }}
                [data-testid="stSidebar"] > div:first-child {{
                    width: 270px !important;
                }}
                .block-container {{
                    padding-left: .8rem;
                    padding-right: .8rem;
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
                <h2>Gestão Financeira</h2>
                <p>Mais controle para um amanhã mais tranquilo.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        page = st.radio(
            "Navegação",
            NAV_OPTIONS,
            index=NAV_OPTIONS.index(st.session_state.get("current_page", "Dashboard")),
            format_func=lambda option: f"{NAV_ICONS.get(option,'')}  {option}",
            label_visibility="collapsed",
        )
        st.session_state["current_page"] = page

        st.markdown("<div class='gf-layout-label'>Visualização</div>", unsafe_allow_html=True)
        layout = st.radio(
            "Layout",
            ["Desktop", "Mobile"],
            index=0 if st.session_state.get("view_mode", "Desktop") == "Desktop" else 1,
            horizontal=True,
            key="view_mode_selector",
            label_visibility="collapsed",
        )
        st.session_state["view_mode"] = layout

        state_cls = "gf-status-ok" if is_db_configured else "gf-status-test"
        state_text = "Banco conectado" if is_db_configured else "Modo de teste"

        st.markdown(
            f"""
            <div class="gf-sidebar-box">
                <div style="font-size:.82rem; color:#b9cae0; font-weight:700; margin-bottom:6px;">Infraestrutura</div>
                <div class="gf-status-pill {state_cls}">● {state_text}</div>
                <div style="height:9px"></div>
                <div style="font-size:.88rem; font-weight:700;">Seus dados estão protegidos</div>
                <div style="font-size:.78rem; color:#b9cae0; line-height:1.4; margin-top:4px;">
                    Segurança, privacidade e confiabilidade como base do sistema.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return page


def render_page_header(page_title: str, subtitle: str) -> str:
    st.markdown(
        f"""
        <div class="gf-page-intro">
            <div class="gf-page-eyebrow">Sua gestão em primeiro lugar</div>
            <h1 class="gf-page-title">{page_title}</h1>
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
            <div class="gf-card-footnote">{trend_html} {' • ' if trend_html and note else ''}{note}</div>
        </div>
        """
    )


def show_metric_grid(cards: list[str], view_mode: str = "Desktop") -> None:
    cols_per_row = 6 if view_mode == "Desktop" else 1
    total_rows = math.ceil(len(cards) / cols_per_row)

    for row in range(total_rows):
        cols = st.columns(cols_per_row, gap="small")
        slice_start = row * cols_per_row
        slice_end = slice_start + cols_per_row

        for col, card in zip(cols, cards[slice_start:slice_end]):
            with col:
                st.markdown(card, unsafe_allow_html=True)


def section_header(title: str, caption: str = "") -> None:
    st.markdown(f"<div class='gf-section-title'>{title}</div>", unsafe_allow_html=True)
    if caption:
        st.markdown(f"<div class='gf-section-caption'>{caption}</div>", unsafe_allow_html=True)
