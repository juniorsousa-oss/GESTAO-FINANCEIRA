from __future__ import annotations

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from services.db import TABLES, get_settings, select_rows
from services.finance import brl, competence_key, numeric, to_df
from services.ui import metric_card, section_header, show_metric_grid


def _safe_percent(base: float, value: float) -> str | None:
    if base == 0:
        return None
    pct = ((value - base) / abs(base)) * 100
    arrow = "↑" if pct >= 0 else "↓"
    return f"{arrow} {abs(pct):.1f}%"


def _recent_competences(n: int = 6) -> list[str]:
    now = pd.Timestamp(datetime.now().date())
    periods = pd.period_range(end=now.to_period("M"), periods=n, freq="M")
    return [f"{p.month:02d}/{p.year}" for p in periods]


def _monthly_movements(movements: pd.DataFrame) -> pd.DataFrame:
    base = pd.DataFrame({"competence": _recent_competences(6)})

    if movements.empty:
        base["Receitas"] = 0.0
        base["Despesas"] = 0.0
        base["Saldo"] = 0.0
        return base

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
    merged = base.merge(merged, how="left", on="competence").fillna(0)
    merged["Saldo"] = merged["Receitas"] - merged["Despesas"]

    return merged.sort_values("competence", key=lambda s: s.map(competence_key))


def _forecast_table(forecasts: pd.DataFrame) -> pd.DataFrame:
    columns = ["Vencimento", "Descrição", "Categoria", "Tipo", "Valor", "Status"]

    if forecasts.empty:
        return pd.DataFrame(columns=columns)

    work = forecasts.copy()
    work["final_value"] = numeric(work["final_value"])
    work = work.sort_values(["status", "due_date"], ascending=[True, True]).head(5)

    out = pd.DataFrame()
    out["Vencimento"] = work["due_date"].fillna("-")
    out["Descrição"] = work["description"]
    out["Categoria"] = work["category"].replace("", "-")
    out["Tipo"] = work["type"]
    out["Valor"] = work["final_value"].map(brl)
    out["Status"] = work["status"]

    return out


def _finance_chart(monthly: pd.DataFrame) -> alt.Chart:
    chart_data = monthly.rename(columns={"competence": "Competência"})
    bars_df = chart_data.melt(
        id_vars=["Competência"],
        value_vars=["Receitas", "Despesas"],
        var_name="Série",
        value_name="Valor",
    )

    bars = (
        alt.Chart(bars_df)
        .mark_bar(size=22, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X(
                "Competência:N",
                sort=list(chart_data["Competência"]),
                axis=alt.Axis(labelAngle=0, title=None, labelFontSize=9, labelColor="#73859a"),
            ),
            y=alt.Y(
                "Valor:Q",
                title=None,
                axis=alt.Axis(gridColor="#eef3f7", labelColor="#73859a", labelFontSize=9),
            ),
            color=alt.Color(
                "Série:N",
                scale=alt.Scale(domain=["Receitas", "Despesas"], range=["#4fbd8d", "#294f76"]),
                legend=alt.Legend(orient="top", title=None, labelFontSize=9, symbolSize=65),
            ),
            xOffset="Série:N",
            tooltip=["Competência", "Série", alt.Tooltip("Valor:Q", format=",.2f")],
        )
    )

    line = (
        alt.Chart(chart_data)
        .mark_line(point=True, strokeWidth=2.2, color="#19a99e")
        .encode(
            x=alt.X("Competência:N", sort=list(chart_data["Competência"])),
            y=alt.Y("Saldo:Q"),
            tooltip=["Competência", alt.Tooltip("Saldo:Q", format=",.2f")],
        )
    )

    return (bars + line).properties(height=215)


def _category_chart(movements: pd.DataFrame) -> alt.Chart:
    if movements.empty:
        data = pd.DataFrame({"category": ["Sem dados"], "value": [1.0]})
        colors = ["#dce6f0"]
    else:
        out = movements[
            movements["classification"]
            .astype(str)
            .str.upper()
            .str.contains("SAÍDA|SAIDA", regex=True)
        ].copy()

        data = (
            out.groupby("category", as_index=False)["value"]
            .sum()
            .sort_values("value", ascending=False)
            .head(7)
        )

        if data.empty:
            data = pd.DataFrame({"category": ["Sem dados"], "value": [1.0]})
            colors = ["#dce6f0"]
        else:
            colors = [
                "#2f76c7",
                "#2f9fc5",
                "#1aab9f",
                "#6c8dd4",
                "#92aac7",
                "#8bcdbf",
                "#c5d1df",
            ]

    return (
        alt.Chart(data)
        .mark_arc(innerRadius=48, outerRadius=75)
        .encode(
            theta=alt.Theta(field="value", type="quantitative"),
            color=alt.Color(
                field="category",
                type="nominal",
                scale=alt.Scale(range=colors),
                legend=alt.Legend(
                    title=None,
                    orient="bottom",
                    columns=2,
                    labelFontSize=8,
                    symbolSize=48,
                ),
            ),
            tooltip=[
                alt.Tooltip("category", title="Categoria"),
                alt.Tooltip("value", title="Valor", format=",.2f"),
            ],
        )
        .properties(height=215)
    )


def render(view_mode: str = "Desktop") -> None:
    movements = to_df(select_rows(TABLES["movements"], order="id.asc"))
    forecasts = to_df(select_rows(TABLES["forecasts"], order="due_date.asc"))
    accounts = to_df(select_rows(TABLES["accounts"], order="name.asc"))
    debts = to_df(select_rows(TABLES["debts"], order="id.asc"))

    has_data = not (movements.empty and forecasts.empty and accounts.empty and debts.empty)

    entradas = 0.0
    saidas = 0.0

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

    a_receber = 0.0
    a_pagar = 0.0

    if not forecasts.empty:
        forecasts["final_value"] = numeric(forecasts["final_value"])
        status = forecasts["status"].astype(str).str.lower()
        pending = ~status.isin(["pago", "sim", "recebido"])
        types = forecasts["type"].astype(str).str.lower()

        a_receber = forecasts.loc[pending & types.eq("entrada"), "final_value"].sum()
        a_pagar = forecasts.loc[
            pending & types.str.contains("saída|saida", regex=True),
            "final_value",
        ].sum()

    divida_aberta = 0.0
    if not debts.empty:
        debts["open_value"] = numeric(debts["open_value"])
        divida_aberta = debts["open_value"].sum()

    saldo_projetado = saldo_realizado + a_receber - a_pagar
    divergencia = saldo_localizado - saldo_realizado

    monthly = _monthly_movements(movements)
    prev_saldo = float(monthly["Saldo"].iloc[-2]) if len(monthly) >= 2 else 0.0

    cards = [
        metric_card(
            "Saldo Realizado",
            brl(saldo_realizado),
            "caixa consolidado",
            "success",
            "▣",
            _safe_percent(prev_saldo, saldo_realizado),
        ),
        metric_card(
            "Saldo Localizado",
            brl(saldo_localizado),
            f"diferença {brl(divergencia)}",
            "info",
            "▦",
        ),
        metric_card(
            "A Receber",
            brl(a_receber),
            "próximos compromissos",
            "success",
            "↓",
        ),
        metric_card(
            "A Pagar",
            brl(a_pagar),
            "próximos compromissos",
            "danger",
            "↑",
        ),
        metric_card(
            "Saldo Projetado",
            brl(saldo_projetado),
            "realizado + previsões",
            "info",
            "↗",
        ),
        metric_card(
            "Dívida em Aberto",
            brl(divida_aberta),
            "passivo atual",
            "danger",
            "▧",
        ),
    ]

    show_metric_grid(cards, view_mode=view_mode)
    st.markdown("<div class='gf-gap'></div>", unsafe_allow_html=True)

    if view_mode == "Desktop":
        chart_left, chart_right = st.columns([1.55, .75], gap="small")
    else:
        chart_left = st.container()
        chart_right = st.container()

    with chart_left:
        with st.container(border=True):
            section_header(
                "▥  Evolução Financeira Mensal",
                "Receitas, despesas e saldo nos últimos seis meses.",
            )
            st.altair_chart(_finance_chart(monthly), use_container_width=True)

    with chart_right:
        with st.container(border=True):
            section_header(
                "◉  Despesas por Categoria",
                "Distribuição das saídas registradas.",
            )
            st.altair_chart(_category_chart(movements), use_container_width=True)

    st.markdown("<div class='gf-gap'></div>", unsafe_allow_html=True)

    if view_mode == "Desktop":
        bottom_left, bottom_right = st.columns([1.55, .75], gap="small")
    else:
        bottom_left = st.container()
        bottom_right = st.container()

    with bottom_left:
        with st.container(border=True):
            section_header(
                "▣  Próximas Contas e Previsões",
                "Agenda financeira para acompanhamento imediato.",
            )

            table = _forecast_table(forecasts)
            if table.empty:
                st.caption("Nenhuma previsão carregada ainda.")

            st.dataframe(
                table,
                hide_index=True,
                use_container_width=True,
                height=150,
            )

    with bottom_right:
        with st.container(border=True):
            section_header(
                "▰  Conciliação de Saldo",
                "Conferência entre saldo calculado e saldo localizado.",
            )

            if not has_data:
                conciliacao = 0.0
            elif abs(divergencia) < 0.01:
                conciliacao = 100.0
            else:
                conciliacao = max(
                    0.0,
                    100.0
                    - (abs(divergencia) / max(abs(saldo_realizado), 1)) * 100,
                )

            st.progress(conciliacao / 100)

            st.markdown(
                f"""
                <div style="font-size:1.35rem;font-weight:850;color:#10233f;margin:.30rem 0 .05rem;">
                    {conciliacao:.0f}%
                </div>
                <div style="font-size:.72rem;font-weight:800;color:#36506b;margin-bottom:6px;">
                    Dados conciliados
                </div>
                <ul class="gf-checklist">
                    <li>Movimentações separadas das previsões</li>
                    <li>Saldos localizados comparados ao sistema</li>
                    <li>Divergência atual: {brl(divergencia)}</li>
                    <li>{"Base pronta para conferência" if has_data else "Aguardando importação da base"}</li>
                </ul>
                """,
                unsafe_allow_html=True,
            )

    settings = get_settings()

    if settings.get("net_income", 0) > 0:
        with st.expander("Metas financeiras", expanded=False):
            net = settings["net_income"]

            goal_cards = [
                metric_card(
                    "Reserva de Emergência",
                    brl(net * settings["emergency_months"]),
                    f"{settings['emergency_months']:.0f} meses",
                    "info",
                    "▣",
                ),
                metric_card(
                    "Investimento Mensal",
                    brl(net * settings["investment_pct"] / 100),
                    f"{settings['investment_pct']:.0f}% da renda",
                    "success",
                    "↗",
                ),
                metric_card(
                    "Contas Fixas",
                    brl(net * settings["fixed_pct"] / 100),
                    f"{settings['fixed_pct']:.0f}% da renda",
                    "neutral",
                    "▤",
                ),
                metric_card(
                    "Lazer",
                    brl(net * settings["leisure_pct"] / 100),
                    f"{settings['leisure_pct']:.0f}% da renda",
                    "neutral",
                    "◇",
                ),
            ]

            show_metric_grid(goal_cards, view_mode=view_mode)

    st.markdown(
        "<div class='gf-footer-note'>Mais controle para decisões melhores.</div>",
        unsafe_allow_html=True,
    )
