from __future__ import annotations

import pandas as pd
import streamlit as st

from services.db import TABLES, insert_row, select_rows, update_row
from services.finance import brl, financial_table, numeric, to_df


def render():

    rows = select_rows(TABLES["debts"], order="id.asc")
    df = to_df(rows)

    with st.expander("Adicionar dívida", expanded=df.empty):
        with st.form("new_debt", clear_on_submit=True):
            c1, c2 = st.columns(2)
            description = c1.text_input("Descrição")
            total_value = c2.number_input("Valor original/total (R$)", min_value=0.0, step=10.0, format="%.2f")
            c1, c2, c3 = st.columns(3)
            status = c1.selectbox("Status", ["NÃO RENEGOCIADO", "RENEGOCIADO"])
            total_installments = c2.number_input("Parcelas totais", min_value=0, step=1)
            paid_installments = c3.number_input("Parcelas pagas", min_value=0, step=1)
            c1, c2 = st.columns(2)
            installment_value = c1.number_input("Valor da parcela (R$)", min_value=0.0, step=10.0, format="%.2f")
            open_value = c2.number_input("Valor em aberto (R$)", min_value=0.0, step=10.0, format="%.2f")
            submitted = st.form_submit_button("Salvar dívida", use_container_width=True)
        if submitted:
            if not description.strip():
                st.error("Informe a descrição.")
            else:
                insert_row(TABLES["debts"], {
                    "description": description.strip(), "total_value": total_value, "status": status,
                    "total_installments": int(total_installments), "paid_installments": int(paid_installments),
                    "installment_value": installment_value, "open_value": open_value,
                })
                st.success("Dívida registrada.")
                st.rerun()

    if df.empty:
        st.info("Nenhuma dívida cadastrada.")
        return

    df["open_value"] = numeric(df["open_value"])
    reneg = df.loc[df["status"].astype(str).str.upper().eq("RENEGOCIADO"), "open_value"].sum()
    non_reneg = df.loc[~df["status"].astype(str).str.upper().eq("RENEGOCIADO"), "open_value"].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total em aberto", brl(df["open_value"].sum()))
    c2.metric("Renegociado", brl(reneg))
    c3.metric("Não renegociado", brl(non_reneg))

    cols = [c for c in ["id", "description", "status", "total_value", "total_installments", "paid_installments", "installment_value", "open_value"] if c in df.columns]
    display_df = financial_table(df[cols])
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        row_height=30,
        height=min(360, max(110, (len(display_df) + 1) * 33)),
    )

    st.subheader("Atualizar pagamento")
    choices = {f"#{int(r['id'])} — {r.get('description','')}": int(r["id"]) for _, r in df.iterrows() if pd.notna(r.get("id"))}
    label = st.selectbox("Dívida", list(choices.keys()))
    selected = df.loc[df["id"].astype(int).eq(choices[label])].iloc[0]
    c1, c2, c3 = st.columns(3)
    paid = c1.number_input("Parcelas pagas", min_value=0, value=int(selected.get("paid_installments", 0) or 0), step=1)
    open_value = c2.number_input("Valor em aberto", min_value=0.0, value=float(selected.get("open_value", 0) or 0), step=10.0, format="%.2f")
    if c3.button("Atualizar dívida", use_container_width=True):
        update_row(TABLES["debts"], choices[label], {"paid_installments": int(paid), "open_value": open_value})
        st.success("Dívida atualizada.")
        st.rerun()
