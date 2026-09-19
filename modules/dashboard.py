from __future__ import annotations

import pandas as pd
import streamlit as st

from services.db import TABLES, get_settings, select_rows
from services.finance import brl, numeric, to_df


def render():
    st.title("Dashboard Financeiro")
    st.caption("Realizado, previsto, saldo localizado e endividamento em uma única visão.")

    movements = to_df(select_rows(TABLES["movements"], order="id.asc"))
    forecasts = to_df(select_rows(TABLES["forecasts"], order="due_date.asc"))
    accounts = to_df(select_rows(TABLES["accounts"], order="name.asc"))
    debts = to_df(select_rows(TABLES["debts"], order="id.asc"))

    if movements.empty and forecasts.empty and accounts.empty and debts.empty:
        st.info("Ainda não há dados. Use **Importar Excel** para carregar o ACOMPANHAMENTOS.xlsx ou cadastre registros manualmente.")
        return

    entradas = saidas = 0.0
    if not movements.empty:
        movements["value"] = numeric(movements["value"])
        classif = movements["classification"].astype(str).str.upper()
        entradas = movements.loc[classif.eq("ENTRADA"), "value"].sum()
        saidas = movements.loc[classif.str.contains("SAÍDA|SAIDA", regex=True), "value"].sum()
    saldo_realizado = entradas - saidas

    saldo_localizado = 0.0
    if not accounts.empty:
        accounts["balance"] = numeric(accounts["balance"])
        saldo_localizado = accounts["balance"].sum()

    a_receber = a_pagar = 0.0
    if not forecasts.empty:
        forecasts["final_value"] = numeric(forecasts["final_value"])
        status = forecasts["status"].astype(str).str.lower()
        pending = ~status.isin(["pago", "sim", "recebido"])
        types = forecasts["type"].astype(str).str.lower()
        a_receber = forecasts.loc[pending & types.eq("entrada"), "final_value"].sum()
        a_pagar = forecasts.loc[pending & types.str.contains("saída|saida", regex=True), "final_value"].sum()

    divida_aberta = 0.0
    if not debts.empty:
        debts["open_value"] = numeric(debts["open_value"])
        divida_aberta = debts["open_value"].sum()

    saldo_projetado = saldo_realizado + a_receber - a_pagar
    divergencia = saldo_localizado - saldo_realizado

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saldo realizado", brl(saldo_realizado))
    c2.metric("Saldo localizado", brl(saldo_localizado), delta=brl(divergencia))
    c3.metric("A receber", brl(a_receber))
    c4.metric("A pagar", brl(a_pagar))

    c1, c2, c3 = st.columns(3)
    c1.metric("Saldo projetado", brl(saldo_projetado))
    c2.metric("Dívida em aberto", brl(divida_aberta))
    c3.metric("Resultado realizado", brl(entradas - saidas))

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Realizado por competência")
        if movements.empty or "competence" not in movements.columns:
            st.caption("Sem movimentações suficientes para o gráfico.")
        else:
            chart = movements.copy()
            chart["signed"] = chart["value"]
            chart.loc[chart["classification"].astype(str).str.upper().str.contains("SAÍDA|SAIDA", regex=True), "signed"] *= -1
            monthly = chart.groupby("competence", as_index=False)["signed"].sum().set_index("competence")
            st.bar_chart(monthly, y="signed")

    with right:
        st.subheader("Saídas por categoria")
        if movements.empty:
            st.caption("Sem movimentações suficientes para o gráfico.")
        else:
            out = movements[movements["classification"].astype(str).str.upper().str.contains("SAÍDA|SAIDA", regex=True)].copy()
            if out.empty:
                st.caption("Nenhuma saída registrada.")
            else:
                by_cat = out.groupby("category", as_index=False)["value"].sum().sort_values("value", ascending=False).head(10).set_index("category")
                st.bar_chart(by_cat, y="value")

    settings = get_settings()
    if settings.get("net_income", 0) > 0:
        st.divider()
        st.subheader("Metas financeiras")
        net = settings["net_income"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Reserva de emergência", brl(net * settings["emergency_months"]))
        m2.metric("Investimento mensal", brl(net * settings["investment_pct"] / 100))
        m3.metric("Limite contas fixas", brl(net * settings["fixed_pct"] / 100))
        m4.metric("Limite lazer", brl(net * settings["leisure_pct"] / 100))
