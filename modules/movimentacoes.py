from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.db import TABLES, delete_row, insert_row, select_rows
from services.finance import brl, current_competence, normalize_competence_options, numeric, to_df


DEFAULT_CATEGORIES = ["ENTRADAS", "CONTAS FIXAS", "LAZER", "INVESTIMENTOS", "ALIMENTAÇÃO", "TRANSPORTE", "SAÚDE", "OUTROS"]


def render():
    st.title("Movimentações")
    st.caption("Caixa realizado: tudo o que efetivamente entrou ou saiu.")

    rows = select_rows(TABLES["movements"], order="id.desc")
    df = to_df(rows)

    with st.expander("Adicionar movimentação", expanded=df.empty):
        with st.form("new_movement", clear_on_submit=True):
            c1, c2 = st.columns(2)
            description = c1.text_input("Descrição")
            value = c2.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")
            c1, c2, c3 = st.columns(3)
            classification = c1.selectbox("Classificação", ["SAÍDA", "ENTRADA"])
            category = c2.text_input("Categoria", value="CONTAS FIXAS" if classification == "SAÍDA" else "ENTRADAS")
            fixed_variable = c3.selectbox("Fixo ou variável", ["FIXO", "VARIÁVEL"])
            c1, c2, c3 = st.columns(3)
            competence = c1.text_input("Competência (MM/AAAA)", value=current_competence())
            movement_date = c2.date_input("Data da movimentação", value=date.today())
            allocation = c3.number_input("Valor do rateio", min_value=0.0, step=10.0, format="%.2f")
            submitted = st.form_submit_button("Salvar movimentação", use_container_width=True)
        if submitted:
            if not description.strip() or value <= 0:
                st.error("Informe descrição e um valor maior que zero.")
            else:
                insert_row(TABLES["movements"], {
                    "description": description.strip(), "value": value, "category": category.strip().upper(),
                    "competence": competence.strip(), "classification": classification,
                    "allocation_value": allocation, "fixed_variable": fixed_variable,
                    "movement_date": movement_date.isoformat(),
                })
                st.success("Movimentação registrada.")
                st.rerun()

    if df.empty:
        st.info("Nenhuma movimentação cadastrada.")
        return

    df["value"] = numeric(df["value"])
    options = normalize_competence_options(df.get("competence", []))
    c1, c2, c3 = st.columns(3)
    competence_filter = c1.selectbox("Competência", ["Todas"] + options, index=0)
    class_filter = c2.selectbox("Classificação", ["Todas", "ENTRADA", "SAÍDA"])
    categories = sorted({str(v) for v in df.get("category", []) if str(v) != "nan"})
    category_filter = c3.selectbox("Categoria", ["Todas"] + categories)

    filtered = df.copy()
    if competence_filter != "Todas":
        filtered = filtered[filtered["competence"].astype(str).eq(competence_filter)]
    if class_filter != "Todas":
        filtered = filtered[filtered["classification"].astype(str).str.upper().eq(class_filter)]
    if category_filter != "Todas":
        filtered = filtered[filtered["category"].astype(str).eq(category_filter)]

    entries = filtered.loc[filtered["classification"].astype(str).str.upper().eq("ENTRADA"), "value"].sum()
    exits = filtered.loc[filtered["classification"].astype(str).str.upper().str.contains("SAÍDA|SAIDA", regex=True), "value"].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Entradas", brl(entries))
    c2.metric("Saídas", brl(exits))
    c3.metric("Resultado", brl(entries - exits))

    show_cols = [c for c in ["id", "movement_date", "description", "value", "category", "competence", "classification", "allocation_value", "fixed_variable"] if c in filtered.columns]
    st.dataframe(filtered[show_cols], use_container_width=True, hide_index=True)

    with st.expander("Excluir movimentação"):
        choices = {f"#{int(r['id'])} — {r.get('description','')} — {brl(r.get('value',0))}": int(r["id"]) for _, r in filtered.iterrows() if pd.notna(r.get("id"))}
        if choices:
            label = st.selectbox("Registro", list(choices.keys()))
            if st.button("Excluir selecionado", type="secondary"):
                delete_row(TABLES["movements"], choices[label])
                st.success("Movimentação excluída.")
                st.rerun()
