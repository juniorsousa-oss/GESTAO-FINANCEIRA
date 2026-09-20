import time

import streamlit as st

from modules import configuracoes, dashboard, dividas, importacao, movimentacoes, previsoes, saldos
from services.db import is_configured, verify_database
from services.login import render_login
from services.users import identify_user, list_users
from services.ui import inject_global_css, render_app_header, render_page_header, render_sidebar, render_sidebar_toggle, render_header_search


st.set_page_config(
    page_title="Gestão Financeira",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# A tela pede apenas a senha. A conta (nome, papel e foto) é identificada
# no banco pelo hash correspondente, sem selecionar o nome manualmente.
if is_configured():
    # Sessões antigas usavam somente um booleano e não possuem identidade
    # comprovada. Pedir um novo login após a migração.
    if st.session_state.get("_gf_authenticated") and not st.session_state.get("_gf_user_id"):
        st.session_state["_gf_authenticated"] = False
        st.session_state.pop("_gf_display_name", None)
        st.session_state.pop("_gf_avatar_uri", None)

    if not st.session_state.get("_gf_authenticated", False):
        submitted, entered_password = render_login()
        if submitted:
            lock_until = float(st.session_state.get("_gf_lock_until", 0))
            if time.monotonic() < lock_until:
                st.error("Muitas tentativas. Aguarde um minuto e tente novamente.")
            else:
                try:
                    user = identify_user(entered_password)
                except Exception:
                    st.error(
                        "Não foi possível consultar as contas de acesso. "
                        "Verifique a conexão e a tabela finance_users."
                    )
                    st.stop()
                if user is not None:
                    st.session_state["_gf_authenticated"] = True
                    st.session_state["_gf_user_id"] = int(user["id"])
                    st.session_state["_gf_display_name"] = user["display_name"]
                    st.session_state["_gf_is_admin"] = bool(user.get("is_admin"))
                    st.session_state["_gf_avatar_uri"] = user.get("avatar_data_uri")
                    st.session_state["_gf_login_failures"] = 0
                    st.session_state.pop("_gf_lock_until", None)
                    st.session_state.pop("_gf_login_error", None)
                    st.rerun()
                else:
                    failures = int(st.session_state.get("_gf_login_failures", 0)) + 1
                    st.session_state["_gf_login_failures"] = failures
                    if failures >= 5:
                        st.session_state["_gf_lock_until"] = time.monotonic() + 60
                        st.error("Muitas tentativas. Aguarde um minuto e tente novamente.")
                    else:
                        st.session_state["_gf_login_error"] = True
                        st.rerun()
        st.stop()

    # Não manter acesso de um usuário removido/desativado durante a sessão.
    try:
        active_user = next(
            (u for u in list_users() if int(u["id"]) == st.session_state["_gf_user_id"]
             and u.get("is_active")),
            None,
        )
    except Exception:
        st.error("Não foi possível verificar sua sessão. Tente novamente mais tarde.")
        st.stop()
    if active_user is None:
        for key in (
            "_gf_authenticated", "_gf_user_id", "_gf_display_name",
            "_gf_is_admin", "_gf_avatar_uri",
        ):
            st.session_state.pop(key, None)
        st.rerun()

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
