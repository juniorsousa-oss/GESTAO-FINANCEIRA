from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any

import pandas as pd


SHEET_MOVEMENTS = "REGISTRO DE MOVIMENTAÇÕES"
SHEET_FORECASTS = "CONTROLE DE ENTSAÍDAS"
SHEET_ACCOUNTS = "DINHEIRO"
SHEET_DEBTS = "DEMAIS DÍVIDAS"


def _text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _number(value: Any) -> float:
    if pd.isna(value) or value == "":
        return 0.0
    if isinstance(value, str):
        value = value.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _date(value: Any) -> str | None:
    if pd.isna(value) or value == "":
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date().isoformat()
        except Exception:
            return None
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    return None if pd.isna(parsed) else parsed.date().isoformat()


def _competence(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    if "/" in text:
        parts = text.split("/")
        if len(parts) == 2:
            mm, yy = parts
            if len(yy) == 2:
                yy = f"20{yy}"
            return f"{mm.zfill(2)}/{yy}"
    return text


def parse_excel(uploaded_file) -> dict[str, list[dict[str, Any]]]:
    content = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    excel = pd.ExcelFile(BytesIO(content), engine="openpyxl")
    missing = [s for s in [SHEET_MOVEMENTS, SHEET_FORECASTS, SHEET_ACCOUNTS, SHEET_DEBTS] if s not in excel.sheet_names]
    if missing:
        raise ValueError("Abas obrigatórias não encontradas: " + ", ".join(missing))

    result: dict[str, list[dict[str, Any]]] = {}

    mov = pd.read_excel(excel, sheet_name=SHEET_MOVEMENTS, header=None, engine="openpyxl")
    rows = []
    for _, r in mov.iloc[5:].iterrows():
        description = _text(r.iloc[0] if len(r) > 0 else "")
        if not description:
            continue
        classification = _text(r.iloc[4] if len(r) > 4 else "").upper()
        if classification not in {"ENTRADA", "SAÍDA", "SAIDA"}:
            continue
        rows.append({
            "description": description,
            "value": _number(r.iloc[1]),
            "category": _text(r.iloc[2]),
            "competence": _competence(r.iloc[3]),
            "classification": "SAÍDA" if classification == "SAIDA" else classification,
            "allocation_value": _number(r.iloc[5] if len(r) > 5 else 0),
            "fixed_variable": _text(r.iloc[6] if len(r) > 6 else "").upper(),
            "movement_date": None,
        })
    result["movements"] = rows

    fc = pd.read_excel(excel, sheet_name=SHEET_FORECASTS, header=None, engine="openpyxl")
    rows = []
    for _, r in fc.iloc[5:].iterrows():
        description = _text(r.iloc[1] if len(r) > 1 else "")
        if not description:
            continue
        tx_type = _text(r.iloc[6] if len(r) > 6 else "")
        if tx_type.upper() not in {"ENTRADA", "SAÍDA", "SAIDA"}:
            continue
        rows.append({
            "due_date": _date(r.iloc[0]),
            "description": description,
            "category": _text(r.iloc[2]),
            "value": _number(r.iloc[3]),
            "adjustment": _number(r.iloc[4]),
            "final_value": _number(r.iloc[5]),
            "type": "Saída" if tx_type.upper() in {"SAÍDA", "SAIDA"} else "Entrada",
            "status": "Pago" if _text(r.iloc[7]).lower() in {"sim", "pago"} else "Não pago",
            "simulate_payment": _text(r.iloc[8]).lower() == "sim",
            "competence": _competence(r.iloc[9]),
        })
    result["forecasts"] = rows

    acc = pd.read_excel(excel, sheet_name=SHEET_ACCOUNTS, header=None, engine="openpyxl")
    rows = []
    for _, r in acc.iloc[4:].iterrows():
        name = _text(r.iloc[0] if len(r) > 0 else "")
        if not name:
            continue
        rows.append({"name": name, "balance": _number(r.iloc[1])})
    result["accounts"] = rows

    debt = pd.read_excel(excel, sheet_name=SHEET_DEBTS, header=None, engine="openpyxl")
    rows = []
    for _, r in debt.iloc[3:].iterrows():
        description = _text(r.iloc[0] if len(r) > 0 else "")
        if not description:
            continue
        rows.append({
            "description": description,
            "total_value": _number(r.iloc[1]),
            "status": _text(r.iloc[2]).upper(),
            "total_installments": int(_number(r.iloc[3])),
            "paid_installments": int(_number(r.iloc[4])),
            "installment_value": _number(r.iloc[5]),
            "open_value": _number(r.iloc[6]),
        })
    result["debts"] = rows

    return result
