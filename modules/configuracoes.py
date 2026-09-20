from __future__ import annotations

import streamlit as st

from services.db import get_settings, is_configured, save_setting


def render():
    if is_configured():
        st.success("Banco financeiro validado em leitura. Acesso persistente protegido pela senha da sessão.")
    else:
        st.warning(
            "Modo de teste — sem banco persistente. Os registros desta sessão "
            "não migram automaticamente quando o Supabase for habilitado."
        )
        st.info(
            "Para conectar um projeto financeiro privado, prepare as cinco tabelas "
            "do supabase_schema.sql e defina SUPABASE_URL, SUPABASE_KEY e "
            "APP_ACCESS_PASSWORD nos Secrets do Streamlit Cloud. "
            "Nunca compartilhe essas credenciais no chat ou no GitHub."
        )

    settings = get_settings()
    st.subheader("Metas")
    with st.form("financial_settings"):
        c1, c2 = st.columns(2)
        gross = c1.number_input("Renda bruta mensal (R$)", min_value=0.0, value=float(settings["gross_income"]), step=100.0)
        net = c2.number_input("Renda líquida mensal (R$)", min_value=0.0, value=float(settings["net_income"]), step=100.0)
        c1, c2, c3 = st.columns(3)
        emergency = c1.number_input("Reserva: meses de renda", min_value=1.0, value=float(settings["emergency_months"]), step=1.0)
        investment = c2.number_input("Investimento mensal (%)", min_value=0.0, max_value=100.0, value=float(settings["investment_pct"]), step=1.0)
        fixed = c3.number_input("Contas fixas (%)", min_value=0.0, max_value=100.0, value=float(settings["fixed_pct"]), step=1.0)
        c1, c2 = st.columns(2)
        leisure = c1.number_input("Lazer (%)", min_value=0.0, max_value=100.0, value=float(settings["leisure_pct"]), step=1.0)
        multiple = c2.number_input("Meta patrimônio (x renda líquida)", min_value=0.0, value=float(settings["investment_multiple"]), step=10.0)
        submitted = st.form_submit_button("Salvar configurações", use_container_width=True)
    if submitted:
        values = {
            "gross_income": gross, "net_income": net, "emergency_months": emergency,
            "investment_pct": investment, "fixed_pct": fixed, "leisure_pct": leisure,
            "investment_multiple": multiple,
        }
        try:
            for key, value in values.items():
                save_setting(key, float(value))
            st.success("Configurações salvas.")
            st.rerun()
        except Exception as exc:
            st.error(f"Não foi possível salvar: {exc}")

    st.divider()
    st.subheader("Escopo da V1")
    st.markdown("""
- Dashboard consolidado do realizado, previsto, saldos e dívidas.
- Cadastro de movimentações realizadas.
- Agenda de contas/entradas previstas e atualização de status.
- Conferência de contas e saldos.
- Controle de dívidas.
- Importação das quatro bases financeiras principais do Excel.
- Supermercado, Unimed e demais módulos auxiliares ficam preparados para as próximas versões.
""")
