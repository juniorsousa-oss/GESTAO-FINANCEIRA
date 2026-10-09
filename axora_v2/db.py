"""Gateway REST exclusivo do servidor para o Supabase já existente."""
import os
import requests
from fastapi import HTTPException

TABLES = {
    "movements": "finance_movements",
    "forecasts": "finance_forecasts",
    "accounts": "finance_accounts",
    "debts": "finance_debts",
    "settings": "finance_settings",
    "users": "finance_users",
    "branding": "finance_brand_assets",
}
DEFAULT_SETTINGS = {
    "gross_income": 0, "net_income": 0, "emergency_months": 6,
    "investment_pct": 20, "fixed_pct": 50, "leisure_pct": 30,
    "investment_multiple": 250,
}


def configured():
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))


def headers(prefer=None):
    key = os.environ.get("SUPABASE_KEY", "")
    result = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_secret_"):
        result["Authorization"] = "Bearer " + key
    if prefer:
        result["Prefer"] = prefer
    return result


def url(table):
    return os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + table


def call(method, table, *, params=None, data=None, prefer=None):
    if not configured():
        raise HTTPException(503, "A conexão privada com o banco não está configurada.")
    try:
        response = requests.request(
            method, url(table), headers=headers(prefer),
            params=params, json=data, timeout=25,
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return []
        return response.json()
    except requests.RequestException:
        # Não retornar chaves, URL com parâmetros ou corpo interno do Supabase.
        raise HTTPException(502, "Falha na comunicação com a base financeira.") from None


def select(kind, *, fields="*", order=None, params=None):
    args = {"select": fields}
    if order:
        args["order"] = order
    args.update(params or {})
    return call("GET", TABLES[kind], params=args)


def insert(kind, payload):
    rows = call("POST", TABLES[kind], data=payload, prefer="return=representation")
    return rows[0] if isinstance(payload, dict) and rows else rows


def update(kind, pk, payload):
    return call("PATCH", TABLES[kind], params={"id": "eq." + str(pk)}, data=payload, prefer="return=representation")


def delete(kind, pk):
    return call("DELETE", TABLES[kind], params={"id": "eq." + str(pk)}, prefer="return=minimal")


def get_settings():
    settings = dict(DEFAULT_SETTINGS)
    for item in select("settings"):
        if item.get("key") in settings:
            settings[item["key"]] = float(item.get("value") or 0)
    return settings


def save_settings(changes):
    current = {r["key"]: r for r in select("settings")}
    for key, value in changes.items():
        if key in current:
            update("settings", int(current[key]["id"]), {"value": value})
        else:
            insert("settings", {"key": key, "value": value})


def verify():
    for table in TABLES:
        select(table, fields="id", params={"limit": "1"})
    return True
