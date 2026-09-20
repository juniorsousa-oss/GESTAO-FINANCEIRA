from __future__ import annotations

import pandas as pd
import streamlit as st

from services.ui import render_financial_table

from services.db import TABLES, insert_row, select_rows, update_row
from services.finance import brl, financial_table, numeric, to_df


def render():

    accounts = to_df(select_rows(TABLES["accounts"], order="name.asc"))
    movements = to_df(select_rows(TABLES["movements"]))

    saldo_realizado = 0.0
    if not movements.empty:
        movements["value"] = numeric(movements["value"])
        classif = movements["classification"].astype(str).str.upper()
        saldo_realizado = movements.loc[classif.eq("ENTRADA"), "value"].sum() - movements.loc[classif.str.contains("SAÍDA|SAIDA", regex=True), "value"].sum()

    saldo_localizado = 0.0
    if not accounts.empty:
        accounts["balance"] = numeric(accounts["balance"])
        saldo_localizado = accounts["balance"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Saldo do sistema", brl(saldo_realizado))
    c2.metric("Saldo informado", brl(saldo_localizado))
    c3.metric("Divergência", brl(saldo_localizado - saldo_realizado))

    with st.expander("Adicionar conta/local", expanded=accounts.empty):
        with st.form("new_account", clear_on_submit=True):
            name = st.text_input("Nome da conta / local")
            balance = st.number_input("Saldo atual (R$)", step=10.0, format="%.2f")
            submitted = st.form_submit_button("Adicionar")
        if submitted:
            if not name.strip():
                st.error("Informe o nome da conta.")
            else:
                insert_row(TABLES["accounts"], {"name": name.strip().upper(), "balance": balance})
                st.success("Conta adicionada.")
                st.rerun()

    if accounts.empty:
        st.info("Nenhuma conta/local cadastrado.")
        return

    display_df = financial_table(accounts[[c for c in ["id", "name", "balance"] if c in accounts.columns]])
    render_financial_table(
        display_df,
        key="accounts",
        title="CONTAS E SALDOS",
        height=min(360, max(110, (len(display_df) + 1) * 33)),
    )

    st.subheader("Atualizar saldo")
    choices = {f"{r.get('name','')} — {brl(r.get('balance',0))}": int(r["id"]) for _, r in accounts.iterrows() if pd.notna(r.get("id"))}
    c1, c2, c3 = st.columns([2, 1, 1])
    label = c1.selectbox("Conta", list(choices.keys()))
    current = accounts.loc[accounts["id"].astype(int).eq(choices[label]), "balance"].iloc[0]
    new_balance = c2.number_input("Novo saldo", value=float(current), step=10.0, format="%.2f")
    if c3.button("Salvar saldo", use_container_width=True):
        update_row(TABLES["accounts"], choices[label], {"balance": new_balance})
        st.success("Saldo atualizado.")
        st.rerun()
