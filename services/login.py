"""Tela de acesso com identidade visual do Gestão Financeira.

Somente a apresentação vive aqui; autenticação e acesso ao banco permanecem
no ponto de entrada do aplicativo (streamlit_app.py).
"""

import streamlit as st


_LOGIN_CSS = """
<style>
:root {
    color-scheme: light !important;
}
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"], main {
    background: #f8fbff !important;
    color: #15243b !important;
}
[data-testid="stHeader"], [data-testid="stToolbar"],
[data-testid="stAppToolbar"], [data-testid="stHeaderActionElements"],
[data-testid="stSidebarCollapsedControl"], [data-testid="stDecoration"] {
    display: none !important;
}
[data-testid="stAppViewContainer"] {
    position: relative;
    isolation: isolate;
}
[data-testid="stAppViewContainer"]::before,
[data-testid="stAppViewContainer"]::after {
    content: "";
    position: fixed;
    width: min(25vw, 350px);
    aspect-ratio: 1;
    border-radius: 50%;
    background: #e8faff;
    z-index: 0;
    pointer-events: none;
}
[data-testid="stAppViewContainer"]::before {
    left: max(-12vw, -170px);
    bottom: max(-12vw, -175px);
}
[data-testid="stAppViewContainer"]::after {
    right: max(-12vw, -170px);
    top: max(-12vw, -175px);
}
[data-testid="stMain"] .block-container {
    position: relative;
    z-index: 1;
    max-width: none !important;
    width: 100% !important;
    box-sizing: border-box !important;
    padding: clamp(88px, 11vh, 118px) 18px 24px !important;
    margin: 0 auto !important;
}
div[data-testid="stElementContainer"]:has(.gf-login-brandbar) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    overflow: visible !important;
}
.gf-login-brandbar {
    position: fixed;
    z-index: 1000;
    top: 0;
    left: 0;
    right: 0;
    min-height: 72px;
    box-sizing: border-box;
    padding: 12px clamp(18px, 2vw, 36px);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    background: linear-gradient(115deg, #102c4a, #173d61);
    border-bottom: 1px solid rgba(255,255,255,.12);
    color: #fff;
}
.gf-login-brand {
    display: flex;
    align-items: center;
    gap: 14px;
    min-width: 0;
}
.gf-login-brand-logo {
    width: 46px;
    height: 46px;
    flex: 0 0 46px;
    border-radius: 10px;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    gap: 4px;
    padding-bottom: 10px;
    box-sizing: border-box;
    background: linear-gradient(145deg, #14bdb1, #36cbbb);
}
.gf-login-brand-logo i {
    display: block;
    width: 6px;
    background: white;
    border-radius: 3px 3px 1px 1px;
}
.gf-login-brand-logo i:nth-child(1) { height: 11px; opacity: .85; }
.gf-login-brand-logo i:nth-child(2) { height: 19px; }
.gf-login-brand-logo i:nth-child(3) { height: 26px; }
.gf-login-brand-name {
    font: 800 clamp(15px, 1.3vw, 22px)/1.1 Inter, ui-sans-serif, system-ui, sans-serif;
    letter-spacing: -.025em;
    white-space: nowrap;
}
.gf-login-brand-subtitle {
    margin-top: 4px;
    font: 400 clamp(9px, .8vw, 12px)/1.2 Inter, ui-sans-serif, system-ui, sans-serif;
    color: #c4d6e7;
    white-space: nowrap;
}
.st-key-gf_login_card {
    position: relative;
    z-index: 1;
    box-sizing: border-box;
    width: min(100%, 600px) !important;
    max-width: 600px !important;
    padding: 24px 24px 22px !important;
    margin: 0 auto !important;
    background: #fff !important;
    border: 1px solid #d9e4ef !important;
    border-radius: 14px !important;
    box-shadow: 0 15px 40px rgba(17, 48, 80, .055) !important;
}
.st-key-gf_login_card [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
.gf-login-intro {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 0;
    padding-bottom: 20px;
}
.gf-login-shield {
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 68px;
    height: 68px;
    border-radius: 50%;
    background: #e4fbfb;
    color: #0b4265;
    margin-bottom: 14px;
}
.gf-login-shield svg { width: 40px; height: 40px; }
.gf-login-intro h1 {
    margin: 0;
    color: #14233b;
    font: 800 clamp(20px, 2vw, 30px)/1.1 Inter, ui-sans-serif, system-ui, sans-serif;
    letter-spacing: -.035em;
}
.gf-login-intro p {
    margin: 10px 0 0;
    color: #63748a;
    font: 400 clamp(12px, 1vw, 15px)/1.45 Inter, ui-sans-serif, system-ui, sans-serif;
    max-width: 470px;
}
.st-key-gf_login_card [data-testid="stForm"] {
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    width: 100% !important;
}
.st-key-gf_login_card [data-testid="stForm"] [data-testid="stVerticalBlock"] {
    gap: 12px !important;
}
.st-key-gf_login_card [data-testid="stWidgetLabel"] p {
    margin: 0 0 4px !important;
    color: #182b44 !important;
    font-size: 13px !important;
    font-weight: 750 !important;
}
.st-key-gf_login_card [data-baseweb="input"] {
    border: 1px solid #cddbea !important;
    border-radius: 9px !important;
    background: #fff !important;
    min-height: 46px !important;
    box-shadow: none !important;
}
.st-key-gf_login_card [data-baseweb="input"]:focus-within {
    border-color: #148c93 !important;
    box-shadow: 0 0 0 3px rgba(20, 183, 170, .12) !important;
}
.st-key-gf_login_card input {
    color: #182b44 !important;
    font-size: 14px !important;
    min-height: 46px !important;
    background: transparent !important;
}
.st-key-gf_login_card input::placeholder { color: #8492a3 !important; }
.st-key-gf_login_card [data-testid="stFormSubmitButton"] button {
    width: 100% !important;
    min-height: 46px !important;
    border: 0 !important;
    border-radius: 8px !important;
    background: #14385b !important;
    color: #fff !important;
    font-size: 15px !important;
    font-weight: 750 !important;
    box-shadow: 0 4px 8px rgba(12,45,76,.10) !important;
}
.st-key-gf_login_card [data-testid="stFormSubmitButton"] button:hover {
    background: #1b507c !important;
}
.st-key-gf_login_card [data-testid="stFormSubmitButton"] button:focus-visible {
    outline: 3px solid #16b9ad !important;
    outline-offset: 2px !important;
}
.gf-login-trust {
    margin-top: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: #6a7c91;
    text-align: center;
    font: 400 11px/1.4 Inter, ui-sans-serif, system-ui, sans-serif;
}
.gf-login-trust::before, .gf-login-trust::after {
    content: "";
    height: 1px;
    background: #d9e4ed;
    flex: 1;
}
.gf-login-trust span {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
}
.gf-login-trust svg { flex: 0 0 auto; }
@media (max-width: 650px) {
    .gf-login-brandbar { min-height: 74px; padding: 12px 16px; }
    .gf-login-brand { gap: 9px; }
    .gf-login-brand-logo { width: 42px; height: 42px; flex-basis: 42px; padding-bottom: 9px; gap: 4px; }
    .gf-login-brand-logo i { width: 5px; }
    .gf-login-brand-logo i:nth-child(1) { height: 10px; }
    .gf-login-brand-logo i:nth-child(2) { height: 17px; }
    .gf-login-brand-logo i:nth-child(3) { height: 24px; }
    .gf-login-brand-name { font-size: 16px; }
    .gf-login-brand-subtitle { font-size: 9px; }
    [data-testid="stMain"] .block-container { padding: 94px 12px 24px !important; }
    .st-key-gf_login_card { padding: 24px 20px !important; }
    .gf-login-shield { width: 62px; height: 62px; margin-bottom: 12px; }
    .gf-login-shield svg { width: 38px; height: 38px; }
    .gf-login-intro { padding-bottom: 18px; }
    .gf-login-intro p { margin-top: 12px; }
    .gf-login-trust { margin-top: 16px; font-size: 10px; gap: 7px; }
}
@media (prefers-reduced-motion: reduce) {
    .st-key-gf_login_card * { transition: none !important; }
}
</style>
"""


_HEADER = """
<div class="gf-login-brandbar" role="banner">
    <div class="gf-login-brand">
        <div class="gf-login-brand-logo" role="img" aria-label="Logo Gestão Financeira">
            <i></i><i></i><i></i>
        </div>
        <div>
            <div class="gf-login-brand-name">Gestão Financeira</div>
            <div class="gf-login-brand-subtitle">Controle, clareza e confiança.</div>
        </div>
    </div>
</div>
"""


_INTRO = """
<div class="gf-login-intro">
    <div class="gf-login-shield" aria-hidden="true">
        <svg viewBox="0 0 64 64" width="60" height="60" fill="none" aria-hidden="true">
            <path d="M32 4 54 13v17c0 16-9 25-22 31C19 55 10 46 10 30V13L32 4Z" fill="#2cc6bf" stroke="#103d61" stroke-width="3"/>
            <rect x="23" y="27" width="18" height="19" rx="2" fill="#f9ffff" stroke="#103d61" stroke-width="2.5"/>
            <path d="M27 27v-5a5 5 0 0 1 10 0v5" stroke="#103d61" stroke-width="2.5" stroke-linecap="round"/>
            <circle cx="32" cy="35" r="2" fill="#103d61"/>
            <path d="M32 37v3" stroke="#103d61" stroke-width="2"/>
        </svg>
    </div>
    <h1>Acesso à gestão financeira</h1>
    <p>Informe sua senha para acessar o sistema com segurança<br class="gf-login-break"/> e gerenciar suas finanças.</p>
</div>
"""


_TRUST = """
<div class="gf-login-trust">
    <span>
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#67809b" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 2 20 6v6c0 5-3 8-8 10-5-2-8-5-8-10V6l8-4Z"/>
            <path d="m9 12 2 2 4-4"/>
        </svg>
        Acesso protegido por senha e sessão segura.
    </span>
</div>
"""


def render_login() -> tuple[bool, str, str]:
    """Solicita nome de exibição e senha; autenticação continua no entrypoint."""
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    st.markdown(_HEADER, unsafe_allow_html=True)
    with st.container(key="gf_login_card"):
        st.markdown(_INTRO, unsafe_allow_html=True)
        with st.form("gf_private_login"):
            display_name = st.text_input(
                "Seu nome",
                placeholder="Como deseja ser chamado?",
                max_chars=40,
                autocomplete="name",
            )
            password = st.text_input(
                "Senha de acesso",
                type="password",
                placeholder="Digite sua senha",
            )
            submitted = st.form_submit_button(
                "Entrar   →",
                use_container_width=True,
            )
        if st.session_state.pop("_gf_login_name_error", False):
            st.error("Informe seu nome para continuar.")
        if st.session_state.pop("_gf_login_error", False):
            st.error("Senha incorreta.")
        st.markdown(_TRUST, unsafe_allow_html=True)
    return submitted, display_name, password
