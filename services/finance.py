from __future__ import annotations

from datetime import datetime

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
