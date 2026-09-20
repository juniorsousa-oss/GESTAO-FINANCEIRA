from __future__ import annotations

import pandas as pd
import streamlit as st

from services.ui import render_financial_table

from services.finance import financial_table
from services.db import TABLES, is_configured, replace_table
from services.importer import parse_excel


def render():

    if is_configured():
        st.success("Banco Supabase conectado. Os dados importados poderão ser persistidos.")
    else:
        st.warning("Supabase ainda não está configurado. A importação funcionará em modo de teste e ficará apenas nesta sessão do Streamlit.")

    uploaded = st.file_uploader("Selecione o ACOMPANHAMENTOS.xlsx", type=["xlsx"])
    if uploaded is None:
        st.info("O arquivo é processado pelo aplicativo. Ele não precisa ser enviado ao repositório.")
        return

    try:
        parsed = parse_excel(uploaded)
    except Exception as exc:
        st.error(f"Não foi possível interpretar o arquivo: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Movimentações", len(parsed["movements"]))
    c2.metric("Previsões", len(parsed["forecasts"]))
    c3.metric("Contas/saldos", len(parsed["accounts"]))
    c4.metric("Dívidas", len(parsed["debts"]))

    with st.expander("Prévia da importação"):
        for title, key in (
            ("Movimentações", "movements"),
            ("Previsões", "forecasts"),
            ("Contas e saldos", "accounts"),
            ("Dívidas", "debts"),
        ):
            if not parsed[key]:
                st.caption(f"{title}: nenhum registro nesta base.")
                continue
            preview = financial_table(pd.DataFrame(parsed[key][:5]))
            render_financial_table(
                preview,
                key=f"import_{key}",
                title=title.upper(),
                height=min(225, (len(preview) + 1) * 33),
            )

    confirm = st.checkbox("Entendo que a importação substituirá os dados atuais dessas quatro bases")
    if st.button("Importar e substituir base", type="primary", disabled=not confirm, use_container_width=True):
        try:
            replace_table(TABLES["movements"], parsed["movements"])
            replace_table(TABLES["forecasts"], parsed["forecasts"])
            replace_table(TABLES["accounts"], parsed["accounts"])
            replace_table(TABLES["debts"], parsed["debts"])
        except Exception as exc:
            st.error(f"Falha durante a gravação: {exc}")
            return
        st.success("Importação concluída. O Dashboard já pode ser conferido contra o Excel.")
