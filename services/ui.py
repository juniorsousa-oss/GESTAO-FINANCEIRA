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
    "Dashboard": "▣",
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
                --navy: #08233f;
                --navy-2: #0d3157;
                --teal: #14a69e;
                --success: #12a66d;
                --danger: #d95662;
                --warning: #ea9b39;
                --shadow: 0 5px 16px rgba(17, 48, 82, .055);
            }}

            html, body, [class*="css"] {{
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }}
            .stApp {{ background: #f4f7fb; }}

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

            [data-testid="stSidebar"] {{
                background: linear-gradient(180deg, #071d37 0%, #0b2c50 58%, #09233f 100%);
                border-right: 1px solid rgba(255,255,255,.06);
                min-width: 232px !important;
                width: 232px !important;
                max-width: 232px !important;
                transform: none !important;
            }}
            [data-testid="stSidebar"] > div:first-child {{ width: 248px !important; }}
            [data-testid="stSidebar"] * {{ color: #dce9f7; }}
            [data-testid="stSidebarNav"] {{ display: none !important; }}
            [data-testid="stSidebarContent"] {{ padding: .9rem .72rem .8rem .72rem; }}

            .block-container {{
                padding-top: .35rem;
                padding-bottom: .75rem;
                padding-left: .75rem;
                padding-right: .75rem;
                max-width: {max_width};
            }}

            .gf-brand {{
                display: flex;
                align-items: center;
                gap: 11px;
                padding: 3px 5px 12px 5px;
                margin-bottom: 5px;
                border-bottom: 1px solid rgba(255,255,255,.08);
            }}
            .gf-brand-mark {{
                width: 30px;
                height: 30px;
                border-radius: 10px;
                background: linear-gradient(145deg, #13b7ad, #38d0ae);
                display: flex;
                align-items: flex-end;
                justify-content: center;
                gap: 2px;
                padding: 7px;
                box-shadow: 0 4px 14px rgba(20,166,158,.20);
            }}
            .gf-brand-mark span {{ display:block; width:4px; border-radius:3px; background:white; }}
            .gf-brand-mark span:nth-child(1) {{ height: 9px; opacity:.8; }}
            .gf-brand-mark span:nth-child(2) {{ height: 15px; }}
            .gf-brand-mark span:nth-child(3) {{ height: 21px; opacity:.9; }}
            .gf-brand-title {{ color:#fff; font-size:.98rem; font-weight:800; line-height:1.1; }}
            .gf-brand-sub {{ color:#9fb7cf; font-size:.64rem; margin-top:2px; }}

            [data-testid="stSidebar"] .stButton > button {{
                justify-content: flex-start !important;
                width: 100% !important;
                min-height: 34px !important;
                border-radius: 8px !important;
                border: 0 !important;
                padding: .28rem .58rem !important;
                box-shadow: none !important;
                font-weight: 650 !important;
                font-size: .79rem !important;
                transition: all .12s ease;
            }}
            [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {{
                background: transparent !important;
                color: #dce9f7 !important;
            }}
            [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover {{
                background: rgba(255,255,255,.06) !important;
                color: #ffffff !important;
            }}
            [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {{
                background: linear-gradient(90deg, #123c68, #164875) !important;
                color: #ffffff !important;
                border-left: 3px solid #1bc1b5 !important;
            }}

            .gf-view-label {{
                color:#7896b5;
                font-size:.67rem;
                font-weight:800;
                letter-spacing:.10em;
                text-transform:uppercase;
                margin: 13px 4px 6px;
            }}
            .gf-trust {{
                margin-top: 16px;
                padding: 13px 12px;
                border-radius: 12px;
                background: rgba(255,255,255,.055);
                border: 1px solid rgba(255,255,255,.07);
            }}
            .gf-trust-title {{ color:#f5fbff; font-size:.79rem; font-weight:800; margin-bottom:4px; }}
            .gf-trust-text {{ color:#9fb7cf; font-size:.65rem; line-height:1.42; }}
            .gf-status {{
                display:inline-flex;
                align-items:center;
                gap:5px;
                margin-top:9px;
                padding:4px 7px;
                border-radius:999px;
                font-size:.67rem;
                font-weight:800;
            }}
            .gf-status-ok {{ background:rgba(20,166,158,.14); color:#80e8dd; }}
            .gf-status-test {{ background:rgba(234,155,57,.14); color:#ffd39e; }}

            .gf-page-header {{
                display:flex;
                justify-content:space-between;
                align-items:flex-end;
                gap: 18px;
                padding: .04rem .05rem .24rem .05rem;
            }}
            .gf-page-eyebrow {{
                color:var(--teal);
                font-size:.66rem;
                font-weight:850;
                letter-spacing:.12em;
                text-transform:uppercase;
                margin-bottom:4px;
            }}
            .gf-page-title {{
                color:var(--text);
                font-size:1.36rem;
                font-weight:850;
                line-height:1.05;
                margin:0;
            }}
            .gf-page-subtitle {{ color:var(--muted); font-size:.71rem; margin:4px 0 0; }}
            .gf-month {{
                display:inline-flex;
                align-items:center;
                gap:7px;
                padding:6px 9px;
                border:1px solid var(--border);
                border-radius:9px;
                background:#fff;
                color:#31506f;
                font-size:.71rem;
                font-weight:700;
                white-space:nowrap;
            }}

            .gf-card {{
                background:#fff;
                border:1px solid var(--border);
                border-radius:12px;
                padding:10px 10px 8px;
                box-shadow:var(--shadow);
                min-height:98px;
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
                font-size:.72rem;
                font-weight:750;
                margin-bottom:7px;
                white-space:nowrap;
            }}
            .gf-card-icon {{
                width:27px;
                height:27px;
                border-radius:8px;
                display:flex;
                align-items:center;
                justify-content:center;
                background:#edf4fb;
                font-size:.80rem;
                flex:0 0 auto;
            }}
            .gf-card-value {{
                color:var(--text);
                font-size:1.08rem;
                line-height:1.05;
                font-weight:850;
                margin-bottom:6px;
                white-space:nowrap;
            }}
            .gf-card-footnote {{ color:#78899c; font-size:.62rem; line-height:1.35; }}
            .gf-card-trend-up {{ color:var(--success); font-weight:850; }}
            .gf-card-trend-down {{ color:var(--danger); font-weight:850; }}

            div[data-testid="stVerticalBlockBorderWrapper"] {{
                background:#ffffff;
                border-color:var(--border) !important;
                border-radius:12px !important;
                box-shadow:var(--shadow);
            }}
            div[data-testid="stVerticalBlockBorderWrapper"] > div {{
                padding-top:.58rem;
                padding-bottom:.50rem;
            }}
            .gf-section-title {{ color:var(--text); font-size:.82rem; font-weight:850; margin-bottom:2px; }}
            .gf-section-caption {{ color:var(--muted); font-size:.65rem; margin-bottom:.45rem; }}

            .stDataFrame, div[data-testid="stTable"] {{
                border:1px solid var(--border);
                border-radius:9px;
                overflow:hidden;
            }}
            .stProgress > div > div > div > div {{
                background:linear-gradient(90deg,var(--teal),var(--success));
            }}
            .gf-checklist {{ margin:0; padding-left:.9rem; color:var(--muted); }}
            .gf-checklist li {{ margin:.18rem 0; font-size:.64rem; }}
            .gf-footer-note {{ text-align:center; color:#8998aa; font-size:.67rem; margin-top:.65rem; }}
            .gf-empty-note {{
                margin: .35rem 0 .55rem;
                border:1px dashed #c9d7e6;
                border-radius:10px;
                background:#f8fbff;
                color:#66809a;
                font-size:.72rem;
                padding:8px 10px;
            }}

            @media (max-width: 900px) {{
                [data-testid="stSidebar"] {{
                    min-width:224px !important;
                    width:224px !important;
                    max-width:224px !important;
                }}
                [data-testid="stSidebar"] > div:first-child {{ width:224px !important; }}
                .gf-page-header {{ align-items:flex-start; flex-direction:column; gap:7px; }}
                .block-container {{ padding-left:.65rem; padding-right:.65rem; }}
            }}

            /* Ajustes finos: elimina vazio superior da sidebar e alinha competência */
            [data-testid="stSidebar"] > div:first-child {{
                width: 232px !important;
                padding-top: 0 !important;
                margin-top: 0 !important;
            }}

            [data-testid="stSidebarContent"],
            [data-testid="stSidebarUserContent"],
            [data-testid="stSidebar"] > div > div {{
                padding-top: .28rem !important;
                margin-top: 0 !important;
            }}

            [data-testid="stSidebarContent"],
            [data-testid="stSidebarUserContent"] {{
                padding-left: .72rem !important;
                padding-right: .72rem !important;
                padding-bottom: .72rem !important;
            }}

            .gf-brand {{
                gap: 10px !important;
                padding: 1px 5px 9px 5px !important;
                margin-top: 0 !important;
                margin-bottom: 3px !important;
            }}

            .gf-page-header {{
                display: grid !important;
                grid-template-columns: minmax(0,1fr) auto !important;
                align-items: center !important;
                column-gap: 12px !important;
                padding: .02rem .05rem .13rem .05rem !important;
                min-height: 58px !important;
            }}

            .gf-page-eyebrow {{
                margin-bottom: 2px !important;
                font-size: .63rem !important;
            }}

            .gf-page-title {{
                font-size: 1.30rem !important;
                line-height: 1.01 !important;
            }}

            .gf-page-subtitle {{
                font-size: .69rem !important;
                margin-top: 2px !important;
            }}

            .gf-month {{
                align-self: center !important;
                justify-self: end !important;
                gap: 5px !important;
                padding: 5px 8px !important;
                border-radius: 8px !important;
                font-size: .67rem !important;
                font-weight: 750 !important;
                margin: 0 !important;
            }}

            @media (max-width: 900px) {{
                .gf-page-header {{
                    grid-template-columns: 1fr !important;
                    row-gap: 5px !important;
                    align-items: start !important;
                }}
                .gf-month {{
                    justify-self: start !important;
                    margin-top: 0 !important;
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
        for idx, option in enumerate(NAV_OPTIONS):
            active = option == current
            if st.button(
                f"{NAV_ICONS.get(option, '')}   {option}",
                key=f"nav_{idx}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                if option != current:
                    st.session_state["current_page"] = option
                    st.rerun()

        st.markdown("<div class='gf-view-label'>Visualização</div>", unsafe_allow_html=True)
        view = st.session_state.get("view_mode", "Desktop")
        c1, c2 = st.columns(2, gap="small")
        with c1:
            if st.button(
                "Desktop",
                key="mode_desktop",
                use_container_width=True,
                type="primary" if view == "Desktop" else "secondary",
            ):
                if view != "Desktop":
                    st.session_state["view_mode"] = "Desktop"
                    st.rerun()
        with c2:
            if st.button(
                "Mobile",
                key="mode_mobile",
                use_container_width=True,
                type="primary" if view == "Mobile" else "secondary",
            ):
                if view != "Mobile":
                    st.session_state["view_mode"] = "Mobile"
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
