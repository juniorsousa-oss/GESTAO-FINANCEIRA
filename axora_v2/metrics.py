"""Consolidação financeira compatível com a V1, sem dependência do Streamlit."""
from collections import defaultdict
from datetime import date
from calendar import monthrange


def number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def income(row):
    return str(row.get("classification", "")).upper() == "ENTRADA"


def outgoing(row):
    return str(row.get("classification", "")).upper() in ("SAÍDA", "SAIDA")


def pending(row):
    return str(row.get("status", "")).casefold() not in ("pago", "recebido", "sim")


def forecast_income(row):
    return str(row.get("type", "")).casefold() == "entrada"


def month_key(value):
    try:
        month, year = (int(x) for x in str(value).split("/"))
        if 1 <= month <= 12 and 2000 <= year < 2200:
            return year, month
    except (TypeError, ValueError):
        pass
    return 0, 0


def compute(movements, forecasts, accounts, debts, settings):
    receipts = sum(number(x.get("value")) for x in movements if income(x))
    expenses = sum(number(x.get("value")) for x in movements if outgoing(x))
    realized = receipts - expenses
    located = sum(number(x.get("balance")) for x in accounts)
    to_receive = sum(number(x.get("final_value")) for x in forecasts if pending(x) and forecast_income(x))
    to_pay = sum(number(x.get("final_value")) for x in forecasts if pending(x) and not forecast_income(x))
    debt_open = sum(number(x.get("open_value")) for x in debts)
    discrepancy = located - realized

    current = date.today()
    start = max((2026, 7), (current.year + (current.month - 6) // 12, ((current.month - 6) % 12) + 1))
    months = []
    yy, mm = start
    while (yy, mm) <= (current.year, current.month):
        label = f"{mm:02d}/{yy}"
        entradas = sum(number(r.get("value")) for r in movements if month_key(r.get("competence")) == (yy, mm) and income(r))
        saidas = sum(number(r.get("value")) for r in movements if month_key(r.get("competence")) == (yy, mm) and outgoing(r))
        months.append({"competence": label, "receipts": round(entradas, 2), "expenses": round(saidas, 2), "balance": round(entradas - saidas, 2)})
        yy, mm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)

    categories = defaultdict(float)
    for row in movements:
        if outgoing(row) and month_key(row.get("competence")) >= (2026, 7):
            categories[str(row.get("category") or "Sem categoria")] += number(row.get("value"))
    categories_sorted = [
        {"name": k, "value": round(v, 2)}
        for k, v in sorted(categories.items(), key=lambda kv: -kv[1]) if v > 0
    ][:7]

    if not any((movements, forecasts, accounts, debts)):
        conciliation = 0
    elif abs(discrepancy) < .01:
        conciliation = 100
    else:
        conciliation = max(0.0, 100 - abs(discrepancy) / max(abs(realized), 1) * 100)

    settings = settings or {}
    net = number(settings.get("net_income"))
    return {
        "receipts": round(receipts, 2),
        "expenses": round(expenses, 2),
        "realized": round(realized, 2),
        "located": round(located, 2),
        "discrepancy": round(discrepancy, 2),
        "to_receive": round(to_receive, 2),
        "to_pay": round(to_pay, 2),
        "projected": round(realized + to_receive - to_pay, 2),
        "debt_open": round(debt_open, 2),
        "conciliation": round(conciliation, 1),
        "monthly": months,
        "categories": categories_sorted,
        "next_forecasts": sorted(forecasts, key=lambda r: (str(r.get("status", "")), str(r.get("due_date") or "")))[:5],
        "goals": {
            "emergency": round(net * number(settings.get("emergency_months", 6)), 2),
            "investment": round(net * number(settings.get("investment_pct", 20)) / 100, 2),
            "fixed": round(net * number(settings.get("fixed_pct", 50)) / 100, 2),
            "leisure": round(net * number(settings.get("leisure_pct", 30)) / 100, 2),
        },
    }
