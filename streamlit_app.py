import streamlit as st

from modules import configuracoes, dashboard, dividas, importacao, movimentacoes, previsoes, saldos
from services.db import is_configured


st.set_page_config(
    page_title="Gestão Financeira",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stApp { background: #f8fafc; }
        [data-testid="stSidebar"] { background: #0f172a; }
        [data-testid="stSidebar"] * { color: #e2e8f0; }
        [data-testid="stSidebar"] .stRadio label { padding: .15rem 0; }
        .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1500px; }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 14px 16px;
            box-shadow: 0 1px 2px rgba(15,23,42,.04);
        }
        div[data-testid="stMetric"] label { color: #475569 !important; }
        h1, h2, h3 { color: #0f172a; }
        .status-pill {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 999px;
            font-size: .78rem;
            font-weight: 700;
            margin-top: 2px;
        }
        .status-ok { background:#dcfce7; color:#166534; }
        .status-test { background:#fef3c7; color:#92400e; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## Gestão Financeira")
    st.caption("Controle pessoal • V1")
    if is_configured():
        st.markdown('<span class="status-pill status-ok">● Banco conectado</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-pill status-test">● Modo de teste</span>', unsafe_allow_html=True)
    st.divider()
    page = st.radio(
        "Navegação",
        [
            "Dashboard",
            "Movimentações",
            "Contas e Previsões",
            "Contas e Saldos",
            "Dívidas",
            "Importar Excel",
            "Configurações",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Base inicial: ACOMPANHAMENTOS.xlsx")

if page == "Dashboard":
    dashboard.render()
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
