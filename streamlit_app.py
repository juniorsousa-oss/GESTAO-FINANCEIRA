import hmac

import streamlit as st

from modules import configuracoes, dashboard, dividas, importacao, movimentacoes, previsoes, saldos
from services.db import _secret, is_configured, verify_database
from services.ui import inject_global_css, render_app_header, render_page_header, render_sidebar, render_sidebar_toggle, render_header_search


st.set_page_config(
    page_title="Gestão Financeira",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Segurança da V1: dados persistentes só ficam acessíveis com senha
# configurada nos secrets privados do Streamlit. Nenhuma senha no GitHub.
if is_configured():
    expected_password = _secret("APP_ACCESS_PASSWORD")
    if not expected_password:
        st.error(
            "Conexão financeira bloqueada: configure APP_ACCESS_PASSWORD "
            "nos Secrets do Streamlit antes de disponibilizar o banco."
        )
        st.stop()

    if not st.session_state.get("_gf_authenticated", False):
        st.title("Acesso à gestão financeira")
        with st.form("gf_private_login"):
            entered_password = st.text_input("Senha de acesso", type="password")
            submitted = st.form_submit_button("Entrar")
        if submitted:
            if hmac.compare_digest(entered_password, expected_password):
                st.session_state["_gf_authenticated"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
        st.stop()

    if not st.session_state.get("_gf_db_verified", False):
        ready, message = verify_database()
        if not ready:
            st.error(message)
            st.stop()
        st.session_state["_gf_db_verified"] = True

# O layout acompanha o tamanho da tela via CSS; não há modo manual.
st.session_state["view_mode"] = "Desktop"
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Dashboard"
if "gf_sidebar_open" not in st.session_state:
    st.session_state["gf_sidebar_open"] = True

PAGE_META = {
    "Dashboard": ("Visão Financeira", "Tudo o que você precisa para manter suas finanças sob controle."),
    "Movimentações": ("Movimentações", "Controle de tudo o que efetivamente entrou ou saiu do caixa."),
    "Contas e Previsões": ("Contas e Previsões", "Agenda financeira das entradas e saídas futuras, separada do realizado."),
    "Contas e Saldos": ("Contas e Saldos", "Concilie rapidamente onde o dinheiro está com o saldo do sistema."),
    "Dívidas": ("Dívidas", "Acompanhe renegociações, parcelas e saldos em aberto com mais clareza."),
    "Importar Excel": ("Importar Excel", "Leve a base atual do ACOMPANHAMENTOS.xlsx para dentro do aplicativo com segurança."),
    "Configurações": ("Configurações", "Defina metas, parâmetros financeiros e prepare a infraestrutura do sistema."),
}

inject_global_css(st.session_state["view_mode"])
render_app_header()
render_sidebar_toggle()
render_header_search()
page = render_sidebar(is_configured())
view_mode = st.session_state.get("view_mode", "Desktop")

page_title, subtitle = PAGE_META[page]
view_mode = render_page_header(page_title, subtitle)

if page == "Dashboard":
    dashboard.render(view_mode=view_mode)
elif page == "Movimentações":
    movimentacoes.render()
elif page == "Contas e Previsões":
    previsoes.render()
elif page == "Contas e Saldos":
    saldos.render()
elif page == "Dívidas":
    dividas.render()
elif page == "Importar Excel":
    importacao.render()
else:
    configuracoes.render()
