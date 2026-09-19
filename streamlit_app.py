import streamlit as st

from modules import configuracoes, dashboard, dividas, importacao, movimentacoes, previsoes, saldos
from services.db import is_configured
from services.ui import inject_global_css, render_app_header, render_page_header, render_sidebar, render_sidebar_toggle


st.set_page_config(
    page_title="Gestão Financeira",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "view_mode" not in st.session_state:
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
