from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.db import TABLES, insert_row, select_rows, update_row
from services.finance import brl, financial_table, current_competence, normalize_competence_options, numeric, to_df


def render():

    rows = select_rows(TABLES["forecasts"], order="due_date.asc")
    df = to_df(rows)

    with st.expander("Adicionar previsão", expanded=df.empty):
        with st.form("new_forecast", clear_on_submit=True):
            c1, c2 = st.columns(2)
            due_date = c1.date_input("Vencimento", value=date.today())
            description = c2.text_input("Descrição / conta")
            c1, c2, c3 = st.columns(3)
            category = c1.text_input("Categoria")
            value = c2.number_input("Valor base (R$)", min_value=0.0, step=10.0, format="%.2f")
            adjustment = c3.number_input("Desconto / juros (R$)", step=1.0, format="%.2f")
            c1, c2, c3 = st.columns(3)
            tx_type = c1.selectbox("Tipo", ["Saída", "Entrada"])
            status = c2.selectbox("Status", ["Não pago", "Pago"])
            competence = c3.text_input("Competência", value=current_competence())
            simulate = st.checkbox("Incluir em simulação de pagamento")
            submitted = st.form_submit_button("Salvar previsão", use_container_width=True)
        if submitted:
            if not description.strip() or value <= 0:
                st.error("Informe descrição e valor maior que zero.")
            else:
                insert_row(TABLES["forecasts"], {
                    "due_date": due_date.isoformat(), "description": description.strip(), "category": category.strip(),
                    "value": value, "adjustment": adjustment, "final_value": value + adjustment,
                    "type": tx_type, "status": status, "simulate_payment": simulate, "competence": competence.strip(),
                })
                st.success("Previsão registrada.")
                st.rerun()

    if df.empty:
        st.info("Nenhuma conta ou previsão cadastrada.")
        return

    df["final_value"] = numeric(df["final_value"])
    options = normalize_competence_options(df.get("competence", []))
    c1, c2, c3 = st.columns(3)
    competence_filter = c1.selectbox("Competência", ["Todas"] + options)
    type_filter = c2.selectbox("Tipo", ["Todos", "Entrada", "Saída"])
    status_filter = c3.selectbox("Status", ["Todos", "Não pago", "Pago"])

    filtered = df.copy()
    if competence_filter != "Todas":
        filtered = filtered[filtered["competence"].astype(str).eq(competence_filter)]
    if type_filter != "Todos":
        filtered = filtered[filtered["type"].astype(str).eq(type_filter)]
    if status_filter != "Todos":
        filtered = filtered[filtered["status"].astype(str).eq(status_filter)]

    pending = ~filtered["status"].astype(str).str.lower().isin(["pago", "recebido", "sim"])
    types = filtered["type"].astype(str).str.lower()
    receive = filtered.loc[pending & types.eq("entrada"), "final_value"].sum()
    pay = filtered.loc[pending & types.str.contains("saída|saida", regex=True), "final_value"].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("A receber", brl(receive))
    c2.metric("A pagar", brl(pay))
    c3.metric("Impacto líquido", brl(receive - pay))

    cols = [c for c in ["id", "due_date", "description", "category", "final_value", "type", "status", "simulate_payment", "competence"] if c in filtered.columns]
    display_df = financial_table(filtered[cols])
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        row_height=30,
        height=min(360, max(110, (len(display_df) + 1) * 33)),
    )

    st.subheader("Atualizar status")
    choices = {f"#{int(r['id'])} — {r.get('description','')} — {r.get('status','')}": int(r["id"]) for _, r in filtered.iterrows() if pd.notna(r.get("id"))}
    if choices:
        c1, c2, c3 = st.columns([2, 1, 1])
        label = c1.selectbox("Conta", list(choices.keys()))
        new_status = c2.selectbox("Novo status", ["Não pago", "Pago"])
        if c3.button("Atualizar", use_container_width=True):
            update_row(TABLES["forecasts"], choices[label], {"status": new_status})
            st.success("Status atualizado.")
            st.rerun()
