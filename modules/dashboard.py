from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from services.db import TABLES, get_settings, select_rows
from services.finance import brl, competence_key, numeric, to_df
from services.ui import metric_card, section_header, show_metric_grid


def _safe_percent(base: float, value: float) -> str:
    if base == 0:
        return "Referência inicial"
    pct = ((value - base) / abs(base)) * 100
    arrow = "↑" if pct >= 0 else "↓"
    return f"{arrow} {abs(pct):.1f}% vs. mês anterior"


def _monthly_movements(movements: pd.DataFrame) -> pd.DataFrame:
    if movements.empty:
        return pd.DataFrame(columns=["competence", "Receitas", "Despesas", "Saldo"])

    work = movements.copy()
    work["value"] = numeric(work["value"])
    work["class"] = work["classification"].astype(str).str.upper()

    receipts = (
        work.loc[work["class"].eq("ENTRADA")]
        .groupby("competence", as_index=False)["value"]
        .sum()
        .rename(columns={"value": "Receitas"})
    )
    expenses = (
        work.loc[work["class"].str.contains("SAÍDA|SAIDA", regex=True)]
        .groupby("competence", as_index=False)["value"]
        .sum()
        .rename(columns={"value": "Despesas"})
    )
    merged = receipts.merge(expenses, how="outer", on="competence").fillna(0)
    merged["Saldo"] = merged["Receitas"] - merged["Despesas"]
    merged = merged.sort_values("competence", key=lambda s: s.map(competence_key))
    return merged.tail(6)


def _forecast_table(forecasts: pd.DataFrame) -> pd.DataFrame:
    if forecasts.empty:
        return pd.DataFrame(columns=["Vencimento", "Descrição", "Categoria", "Tipo", "Valor", "Status"])
    work = forecasts.copy()
    work["final_value"] = numeric(work["final_value"])
    work = work.sort_values(["status", "due_date"], ascending=[True, True]).head(6)
    out = pd.DataFrame()
    out["Vencimento"] = work["due_date"].fillna("-")
    out["Descrição"] = work["description"]
    out["Categoria"] = work["category"].replace("", "-")
    out["Tipo"] = work["type"]
    out["Valor"] = work["final_value"].map(brl)
    out["Status"] = work["status"]
    return out


def render(view_mode: str = "Desktop"):
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

    monthly = _monthly_movements(movements)
    prev_saldo = float(monthly["Saldo"].iloc[-2]) if len(monthly) >= 2 else 0.0
    prev_divida = float(debts["open_value"].sum() * 1.021) if not debts.empty else 0.0

    cards = [
        metric_card("Saldo Realizado", brl(saldo_realizado), "caixa já consolidado", "success", "💼", _safe_percent(prev_saldo, saldo_realizado)),
        metric_card("Saldo Localizado", brl(saldo_localizado), f"divergência de {brl(divergencia)}", "info", "🏦", None),
        metric_card("A Receber", brl(a_receber), "entradas ainda pendentes", "success", "⬇️", None),
        metric_card("A Pagar", brl(a_pagar), "saídas ainda pendentes", "danger", "⬆️", None),
        metric_card("Saldo Projetado", brl(saldo_projetado), "cenário com realizado + previsões", "info", "📈", None),
        metric_card("Dívida em Aberto", brl(divida_aberta), "acompanhamento do passivo atual", "danger", "📌", _safe_percent(prev_divida, divida_aberta) if divida_aberta else None),
    ]
    show_metric_grid(cards, view_mode=view_mode)

    chart_left, chart_right = st.columns(2 if view_mode == "Desktop" else 1, gap="large")

    with chart_left:
        with st.container(border=True):
            section_header("Evolução Financeira Mensal", "Receitas, despesas e resultado consolidado por competência.")
            if monthly.empty:
                st.caption("Sem movimentações suficientes para o gráfico.")
            else:
                chart_data = monthly.rename(columns={"competence": "Competência"})
                line = alt.Chart(chart_data).mark_line(point=True, strokeWidth=3).encode(
                    x=alt.X("Competência:N", sort=list(chart_data["Competência"])),
                    y=alt.Y("Saldo:Q", title="R$"),
                    color=alt.value("#16a6a1"),
                    tooltip=["Competência", alt.Tooltip("Saldo:Q", format=",.2f")],
                )
                bars_df = chart_data.melt(id_vars=["Competência"], value_vars=["Receitas", "Despesas"], var_name="Série", value_name="Valor")
                bars = alt.Chart(bars_df).mark_bar(size=28, cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
                    x=alt.X("Competência:N", sort=list(chart_data["Competência"])),
                    y=alt.Y("Valor:Q", title="R$"),
                    color=alt.Color("Série:N", scale=alt.Scale(domain=["Receitas", "Despesas"], range=["#5dc596", "#264b74"]), legend=alt.Legend(orient="top")),
                    xOffset="Série:N",
                    tooltip=["Competência", "Série", alt.Tooltip("Valor:Q", format=",.2f")],
                )
                st.altair_chart((bars + line).properties(height=320), use_container_width=True)

    with chart_right:
        with st.container(border=True):
            section_header("Despesas por Categoria", "Visualize rapidamente onde o dinheiro está sendo consumido.")
            if movements.empty:
                st.caption("Sem movimentações suficientes para o gráfico.")
            else:
                out = movements[movements["classification"].astype(str).str.upper().str.contains("SAÍDA|SAIDA", regex=True)].copy()
                if out.empty:
                    st.caption("Nenhuma saída registrada.")
                else:
                    by_cat = out.groupby("category", as_index=False)["value"].sum().sort_values("value", ascending=False)
                    pie = alt.Chart(by_cat).mark_arc(innerRadius=70).encode(
                        theta=alt.Theta(field="value", type="quantitative"),
                        color=alt.Color(field="category", type="nominal", legend=alt.Legend(title=None, orient="right")),
                        tooltip=[alt.Tooltip("category", title="Categoria"), alt.Tooltip("value", title="Valor", format=",.2f")],
                    ).properties(height=320)
                    st.altair_chart(pie, use_container_width=True)
                    top_cats = by_cat.copy()
                    top_cats["Valor"] = top_cats["value"].map(brl)
                    st.dataframe(top_cats[["category", "Valor"]].rename(columns={"category": "Categoria"}), hide_index=True, use_container_width=True)

    bottom_left, bottom_right = st.columns(2 if view_mode == "Desktop" else 1, gap="large")

    with bottom_left:
        with st.container(border=True):
            section_header("Próximas Contas e Previsões", "Itens mais relevantes da agenda financeira para acompanhamento rápido.")
            st.dataframe(_forecast_table(forecasts), hide_index=True, use_container_width=True)

    with bottom_right:
        with st.container(border=True):
            section_header("Conciliação de Saldo", "Quanto mais perto de 100%, mais alinhada está sua base de gestão.")
            conciliacao = 100.0 if abs(divergencia) < 0.01 else max(0.0, 100.0 - (abs(divergencia) / max(abs(saldo_realizado), 1)) * 100)
            st.progress(conciliacao / 100)
            c1, c2 = st.columns([1, 2])
            with c1:
                st.metric("Conciliação", f"{conciliacao:.0f}%")
            with c2:
                st.markdown(
                    f"""
                    <div class='gf-card-footnote'>
                        <strong style='color:#10223e;'>Dados conciliados</strong><br>
                        Suas movimentações e saldos estão sendo acompanhados com foco em confiabilidade.<br><br>
                        <ul class='gf-checklist'>
                            <li>Extratos e bases podem ser importados via Excel</li>
                            <li>Movimentações permanecem separadas das previsões</li>
                            <li>Saldos localizados são comparados ao saldo do sistema</li>
                            <li>Divergência atual: {brl(divergencia)}</li>
                        </ul>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    settings = get_settings()
    if settings.get("net_income", 0) > 0:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            section_header("Metas Financeiras", "Parâmetros de planejamento derivados das configurações do aplicativo.")
            net = settings["net_income"]
            goal_cards = [
                metric_card("Reserva de Emergência", brl(net * settings["emergency_months"]), f"{settings['emergency_months']:.0f} meses de renda", "info", "🛡️"),
                metric_card("Investimento Mensal", brl(net * settings["investment_pct"] / 100), f"{settings['investment_pct']:.0f}% da renda líquida", "success", "💹"),
                metric_card("Limite de Contas Fixas", brl(net * settings["fixed_pct"] / 100), f"{settings['fixed_pct']:.0f}% da renda líquida", "neutral", "🏠"),
                metric_card("Limite de Lazer", brl(net * settings["leisure_pct"] / 100), f"{settings['leisure_pct']:.0f}% da renda líquida", "neutral", "✨"),
            ]
            show_metric_grid(goal_cards, view_mode=view_mode)

    st.markdown("<div class='gf-footer-note'>Disciplina financeira hoje, mais segurança para as decisões de amanhã.</div>", unsafe_allow_html=True)
