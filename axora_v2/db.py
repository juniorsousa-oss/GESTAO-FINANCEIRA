"""Gateway REST exclusivo do servidor para o Supabase já existente."""
import logging
import os
import requests
from fastapi import HTTPException

log = logging.getLogger("axora.database")

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


def selected_schema():
    schema = os.environ.get("SUPABASE_DB_SCHEMA", "public").strip()
    if schema not in {"public", "axora_beta"}:
        raise HTTPException(503, "Esquema financeiro indisponível.")
    return schema


def headers(prefer=None, *, method="GET"):
    key = os.environ.get("SUPABASE_KEY", "")
    schema = selected_schema()
    result = {"apikey": key, "Content-Type": "application/json"}
    # PostgREST seleciona explicitamente o schema da mesma base Supabase.
    # Não cair silenciosamente em public quando o beta não está disponível.
    if method.upper() in {"GET", "HEAD"}:
        result["Accept-Profile"] = schema
    else:
        result["Content-Profile"] = schema
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
            method, url(table), headers=headers(prefer, method=method),
            params=params, json=data, timeout=25,
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return []
        return response.json()
    except requests.HTTPError as exc:
        # Diagnóstico seguro: somente código de status, sem URL, resposta, chave ou dados.
        status = exc.response.status_code if exc.response is not None else "unknown"
        log.warning("Falha de resposta do Supabase: HTTP %s", status)
        raise HTTPException(502, "Falha na comunicação com a base financeira.") from None
    except requests.RequestException as exc:
        # Não exibir host, parâmetros, credenciais ou conteúdo financeiro nos logs.
        log.warning("Falha de transporte do Supabase: %s", type(exc).__name__)
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


def update(kind, pk, payload, *, workspace_id=None):
    params = {"id": "eq." + str(pk)}
    if workspace_id is not None:
        params["workspace_id"] = "eq." + str(workspace_id)
    return call("PATCH", TABLES[kind], params=params, data=payload, prefer="return=representation")


def delete(kind, pk, *, workspace_id=None):
    params = {"id": "eq." + str(pk)}
    if workspace_id is not None:
        params["workspace_id"] = "eq." + str(workspace_id)
    return call("DELETE", TABLES[kind], params=params, prefer="return=minimal")


def get_settings(workspace_id):
    settings = dict(DEFAULT_SETTINGS)
    for item in select("settings", params={"workspace_id": "eq." + str(workspace_id)}):
        if item.get("key") in settings:
            settings[item["key"]] = float(item.get("value") or 0)
    return settings


def save_settings(changes, workspace_id):
    current = {r["key"]: r for r in select("settings", params={"workspace_id": "eq." + str(workspace_id)})}
    for key, value in changes.items():
        if key in current:
            update("settings", int(current[key]["id"]), {"value": value}, workspace_id=workspace_id)
        else:
            insert("settings", {"key": key, "value": value, "workspace_id": str(workspace_id)})


def verify():
    # Branding utiliza 'key' como identificador, não 'id'.
    # Verificação somente de leitura; não altera dados em nenhum schema.
    for kind in TABLES:
        identifier = "key" if kind == "branding" else "id"
        select(kind, fields=identifier, params={"limit": "1"})
    if selected_schema() == "axora_beta":
        # Novo BETA deve falhar fechado caso qualquer tabela recém-criada
        # esteja fora do Data API. Evita o aplicativo Live com funções quebradas.
        for table in ("finance_bank_accounts", "finance_bank_account_types",
                      "finance_balance_transfers"):
            call("GET", table, params={"select": "id", "limit": 1})
    return True
