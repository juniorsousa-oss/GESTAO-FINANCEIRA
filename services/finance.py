from __future__ import annotations

from datetime import date, datetime

import pandas as pd


def brl(value: float) -> str:
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0.0
    sign = "-" if value < 0 else ""
    value = abs(value)
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}R$ {formatted}"


def to_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def competence_key(value: str) -> tuple[int, int]:
    try:
        month, year = str(value).split("/")
        return int(year), int(month)
    except Exception:
        return 9999, 99


def current_competence() -> str:
    return datetime.now().strftime("%m/%Y")


def normalize_competence_options(values) -> list[str]:
    items = sorted({str(v) for v in values if str(v).strip() and str(v) != "nan"}, key=competence_key)
    return items


# Formatação exclusiva da interface: nunca alterar os valores gravados ou
# as colunas numéricas que alimentam saldos, filtros e outros cálculos.
TABLE_LABELS = {
    "id": "ID",
    "movement_date": "Data",
    "due_date": "Vencimento",
    "description": "Descrição",
    "value": "Valor",
    "allocation_value": "Valor do rateio",
    "adjustment": "Ajuste",
    "final_value": "Valor final",
    "balance": "Saldo",
    "total_value": "Valor total",
    "installment_value": "Valor da parcela",
    "open_value": "Valor em aberto",
    "name": "Conta / local",
    "category": "Categoria",
    "competence": "Competência",
    "classification": "Classificação",
    "fixed_variable": "Fixo / variável",
    "type": "Tipo",
    "status": "Status",
    "simulate_payment": "Simular pagamento",
    "total_installments": "Parcelas totais",
    "paid_installments": "Parcelas pagas",
}
MONEY_COLUMNS = frozenset({
    "value", "allocation_value", "adjustment", "final_value", "balance",
    "total_value", "installment_value", "open_value",
})
DATE_COLUMNS = frozenset({"movement_date", "due_date"})


def date_br(value: object) -> str:
    """Formata data conhecida sem interpretar competência MM/AAAA como dia."""
    if value is None:
        return "—"
    if isinstance(value, (date, datetime, pd.Timestamp)):
        if pd.isna(value):
            return "—"
        return value.strftime("%d/%m/%Y")
    raw = str(value).strip()
    if not raw or raw.lower() in {"none", "nan", "nat"}:
        return "—"
    for candidate, pattern in (
        (raw[:10], "%Y-%m-%d"),
        (raw, "%d/%m/%Y"),
        (raw, "%d/%m/%y"),
    ):
        try:
            return datetime.strptime(candidate, pattern).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return raw


def financial_table(df: pd.DataFrame, *, hide_id: bool = True) -> pd.DataFrame:
    """Cópia apenas para exibição; números do banco continuam numéricos.

    As competências MM/AAAA e contagens de parcelas não são valores
    monetários nem datas e, portanto, permanecem com seu formato original.
    """
    shown = df.copy(deep=True)
    if hide_id:
        shown = shown.drop(columns=["id"], errors="ignore")
    for column in MONEY_COLUMNS.intersection(shown.columns):
        shown[column] = shown[column].map(
            lambda value: "—" if pd.isna(value) or str(value).strip() == "" else brl(value)
        )
    for column in DATE_COLUMNS.intersection(shown.columns):
        shown[column] = shown[column].map(date_br)
    if "simulate_payment" in shown.columns:
        shown["simulate_payment"] = shown["simulate_payment"].map(
            lambda value: "Sim" if value is True or str(value).lower() in {"true", "sim", "1"} else "Não"
        )
    return shown.rename(columns={key: label for key, label in TABLE_LABELS.items() if key in shown.columns})


# Paleta compartilhada com o aplicativo e inspirada na planilha original.
# O Streamlit aplica cor de fundo/texto do pandas Styler sem perder
# ordenação, seleção de células ou rolagem do st.dataframe.
_CATEGORY_TONES = {
    "ENTRADAS": ("#e1f4d5", "#205b38"),
    "CONTAS FIXAS": ("#eee1fb", "#603a82"),
    "LAZER": ("#ffe3d4", "#874521"),
    "ALIMENTAÇÃO": ("#fff0c8", "#795319"),
    "TRANSPORTE": ("#dceafa", "#255584"),
    "SAÚDE": ("#daf1ec", "#205d51"),
    "INVESTIMENTOS": ("#d5eceb", "#235f5b"),
    "HABITAÇÃO": ("#e9e5df", "#544d43"),
    "HABITACAO": ("#e9e5df", "#544d43"),
    "FILHOS": ("#ffe2e2", "#833e3e"),
}
_MONEY_LABELS = frozenset(TABLE_LABELS[name] for name in MONEY_COLUMNS)


def _cell_tone(value: object, column: str) -> str:
    text = str(value).strip()
    upper = text.upper()
    if column == "Categoria":
        background, foreground = _CATEGORY_TONES.get(upper, ("#edf2f6", "#42586f"))
        return f"background-color: {background}; color: {foreground};"
    if column in {"Classificação", "Tipo"}:
        if upper in {"SAÍDA", "SAIDA"}:
            return "background-color: #fde3e3; color: #a12d35; font-weight: 700;"
        if upper in {"ENTRADA"}:
            return "background-color: #e3f5e7; color: #246b3e; font-weight: 700;"
    if column == "Status":
        if upper in {"PAGO", "SIM", "RECEBIDO", "RENEGOCIADO"}:
            return "background-color: #e3f5de; color: #246a35; font-weight: 650;"
        if upper in {"NÃO PAGO", "NAO PAGO", "NÃO RENEGOCIADO", "NAO RENEGOCIADO"}:
            return "background-color: #ffe1db; color: #8b382d; font-weight: 650;"
    if column == "Fixo / variável":
        return (
            "background-color: #e5f0ff; color: #245c91;"
            if upper == "VARIÁVEL"
            else "background-color: #e9f4e5; color: #39633a;"
        )
    if column in _MONEY_LABELS:
        return (
            "color: #ad3441; font-weight: 650;"
            if text.startswith("-")
            else "color: #19364a; font-weight: 600;"
        )
    return ""


def styled_financial_table(shown: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Adiciona cores de leitura sem alterar nenhuma célula ou cálculo."""
    styler = shown.style
    for column in shown.columns:
        if column in _MONEY_LABELS or column in {
            "Categoria", "Classificação", "Tipo", "Status", "Fixo / variável"
        }:
            styler = styler.map(lambda value, col=column: _cell_tone(value, col), subset=[column])
    return styler
