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
    max_width = "1480px" if view_mode == "Desktop" else "760px"
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
                background: linear-gradient(180deg, #edf3f9 0%, #f6f9fc 60%, #f4f8fb 100%);
            }}
            .block-container {{
                padding-top: 1.2rem;
                padding-bottom: 2.5rem;
                max-width: {max_width};
            }}
            [data-testid="stSidebar"] {{
                background: linear-gradient(180deg, #0a1e39 0%, #0e2b52 55%, #10243f 100%);
                border-right: 1px solid rgba(255,255,255,.06);
            }}
            [data-testid="stSidebar"] * {{ color: #e7eef7; }}
            [data-testid="stSidebarNav"] {{ display:none; }}
            .gf-brand {{
                background: linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0.03));
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 20px;
                padding: 18px 16px;
                box-shadow: inset 0 1px 0 rgba(255,255,255,.08);
                margin-bottom: 10px;
            }}
            .gf-brand h2 {{
                color: #ffffff !important;
                font-size: 1.45rem;
                line-height: 1.1;
                margin: 0 0 4px 0;
            }}
            .gf-brand p {{
                color: #bbcee5;
                font-size: .86rem;
                margin: 0;
            }}
            .gf-sidebar-box {{
                background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.04));
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 18px;
                padding: 14px 14px;
                margin-top: 14px;
            }}
            .gf-status-pill {{
                display: inline-block;
                padding: 6px 10px;
                border-radius: 999px;
                font-weight: 700;
                font-size: .80rem;
                margin-top: 4px;
            }}
            .gf-status-ok {{ background: rgba(22,166,161,.18); color: #8ff1ea; border: 1px solid rgba(143,241,234,.18); }}
            .gf-status-test {{ background: rgba(242,159,61,.18); color: #ffd5a2; border: 1px solid rgba(255,213,162,.16); }}
            [data-testid="stRadio"] label p {{ font-size: .95rem !important; font-weight: 600; }}
            [data-testid="stRadio"] > div {{ gap: 0.55rem; }}
            .gf-topbar {{
                background: rgba(255,255,255,.88);
                border: 1px solid var(--border);
                border-radius: 22px;
                padding: 18px 20px;
                box-shadow: var(--shadow);
                margin-bottom: 16px;
                backdrop-filter: blur(6px);
            }}
            .gf-page-eyebrow {{
                font-size: .80rem;
                letter-spacing: .11em;
                text-transform: uppercase;
                color: var(--teal);
                font-weight: 800;
                margin-bottom: 6px;
            }}
            .gf-page-title {{
                color: var(--text);
                font-weight: 800;
                font-size: 2rem;
                line-height: 1.05;
                margin: 0;
            }}
            .gf-page-subtitle {{
                color: var(--muted);
                margin: 4px 0 0 0;
                font-size: .98rem;
            }}
            div[data-testid="stMetric"] {{
                background: linear-gradient(180deg, #ffffff, #fbfdff);
                border: 1px solid var(--border);
                border-radius: 18px;
                padding: 10px 14px;
                box-shadow: var(--shadow);
            }}
            div[data-testid="stMetric"] label {{ color: var(--muted) !important; font-weight: 700 !important; }}
            div[data-testid="stMetricValue"] > div {{ color: var(--text); font-weight: 800; }}
            div[data-testid="stMetricDelta"] > div {{ font-weight: 700; }}
            .gf-card {{
                background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
                border: 1px solid var(--border);
                border-radius: 18px;
                padding: 18px;
                box-shadow: var(--shadow);
                height: 100%;
            }}
            .gf-card-tonal-success {{ background: linear-gradient(180deg, #f4fffb, #ffffff); }}
            .gf-card-tonal-info {{ background: linear-gradient(180deg, #f4f9ff, #ffffff); }}
            .gf-card-tonal-danger {{ background: linear-gradient(180deg, #fff7f7, #ffffff); }}
            .gf-card-tonal-neutral {{ background: linear-gradient(180deg, #ffffff, #fbfdff); }}
            .gf-card-label {{
                display:flex;
                align-items:center;
                gap:10px;
                font-size:.92rem;
                color:var(--muted);
                font-weight:700;
                margin-bottom:10px;
            }}
            .gf-card-icon {{
                width:34px;
                height:34px;
                border-radius:12px;
                display:flex;
                align-items:center;
                justify-content:center;
                background:#eef5fc;
                font-size:1rem;
            }}
            .gf-card-value {{
                color:var(--text);
                font-weight:800;
                font-size:1.75rem;
                line-height:1.1;
                margin: 2px 0 6px 0;
            }}
            .gf-card-footnote {{
                color:var(--muted);
                font-size:.84rem;
                line-height:1.35;
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
                font-size: .92rem;
            }}
            .stDataFrame, div[data-testid="stTable"] {{
                border: 1px solid var(--border);
                border-radius: 16px;
                overflow: hidden;
            }}
            .stProgress > div > div > div > div {{ background: linear-gradient(90deg, var(--teal), var(--success)); }}
            .gf-checklist {{ margin: 0; padding-left: 1rem; color: var(--muted); }}
            .gf-checklist li {{ margin: .25rem 0; }}
            .gf-footer-note {{
                text-align:center;
                color: var(--muted);
                font-size: .84rem;
                margin-top: 1rem;
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
        state_cls = "gf-status-ok" if is_db_configured else "gf-status-test"
        state_text = "Banco conectado" if is_db_configured else "Modo de teste"
        st.markdown(
            f"""
            <div class="gf-sidebar-box">
                <div style="font-size:.86rem; color:#b9cae0; font-weight:700; margin-bottom:6px;">Infraestrutura</div>
                <div class="gf-status-pill {state_cls}">● {state_text}</div>
                <div style="height:10px"></div>
                <div style="font-size:.90rem; font-weight:700;">Seus dados estão protegidos</div>
                <div style="font-size:.82rem; color:#b9cae0; line-height:1.45; margin-top:4px;">
                    Segurança, privacidade e confiabilidade visual como base do sistema.
                </div>
            </div>
            <div class="gf-sidebar-box">
                <div style="font-size:.86rem; color:#b9cae0; font-weight:700; margin-bottom:8px;">Base inicial</div>
                <div style="font-size:.92rem; font-weight:700;">ACOMPANHAMENTOS.xlsx</div>
                <div style="font-size:.80rem; color:#b9cae0; margin-top:5px;">Importação e conferência já prontas para a V1.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    return page


def render_topbar(page_title: str, subtitle: str) -> str:
    c1, c2 = st.columns([1.9, 1.1], vertical_alignment="center")
    with c1:
        st.markdown(
            f"""
            <div class="gf-topbar">
                <div class="gf-page-eyebrow">Sua gestão em primeiro lugar</div>
                <h1 class="gf-page-title">{page_title}</h1>
                <p class="gf-page-subtitle">{subtitle}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        with st.container(border=False):
            st.markdown("<div class='gf-topbar'>", unsafe_allow_html=True)
            st.text_input(
                "Buscar",
                placeholder="Buscar movimentações, contas, categorias...",
                label_visibility="collapsed",
                key="global_search",
            )
            layout = st.radio(
                "Layout",
                ["Desktop", "Mobile"],
                index=0 if st.session_state.get("view_mode", "Desktop") == "Desktop" else 1,
                horizontal=True,
                key="view_mode_selector",
            )
            st.session_state["view_mode"] = layout
            st.caption("Alterne livremente entre a visão ampla e a visão mobile para validar o layout responsivo.")
            st.markdown("</div>", unsafe_allow_html=True)
    return st.session_state.get("view_mode", "Desktop")


def metric_card(title: str, value: str, note: str = "", tone: str = "neutral", icon: str = "●", trend: str | None = None) -> str:
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
    cols_per_row = 3 if view_mode == "Desktop" else 1
    total_rows = math.ceil(len(cards) / cols_per_row)
    for row in range(total_rows):
        cols = st.columns(cols_per_row, gap="medium")
        slice_start = row * cols_per_row
        slice_end = slice_start + cols_per_row
        for col, card in zip(cols, cards[slice_start:slice_end]):
            with col:
                st.markdown(card, unsafe_allow_html=True)


def section_header(title: str, caption: str = "") -> None:
    st.markdown(f"<div class='gf-section-title'>{title}</div>", unsafe_allow_html=True)
    if caption:
        st.markdown(f"<div class='gf-section-caption'>{caption}</div>", unsafe_allow_html=True)
