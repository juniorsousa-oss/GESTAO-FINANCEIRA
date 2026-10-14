"""Cliente Pluggy somente leitura do AXORA.

Credenciais apenas no servidor; nenhum fluxo de pagamento/Pix.
Integração fica desabilitada até configuração explícita da VPS.
"""
import os
import threading
import time
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

import requests
from fastapi import HTTPException

BASE = "https://api.pluggy.ai"
_lock = threading.Lock()
_session = {"key": None, "expires": 0}


def ready():
    return bool(os.environ.get("PLUGGY_CLIENT_ID") and os.environ.get("PLUGGY_CLIENT_SECRET"))


def live_enabled():
    return os.environ.get("PLUGGY_ENABLE_LIVE", "").strip().lower() == "true"


def key():
    if not ready():
        raise HTTPException(503, "Pluggy ainda não configurada na Hostinger.")
    with _lock:
        if _session["key"] and time.monotonic() < _session["expires"]:
            return _session["key"]
        try:
            r = requests.post(BASE + "/auth", json={
                "clientId": os.environ["PLUGGY_CLIENT_ID"],
                "clientSecret": os.environ["PLUGGY_CLIENT_SECRET"],
            }, timeout=15)
            r.raise_for_status()
            token = r.json()["apiKey"]
            if not isinstance(token, str) or not token:
                raise ValueError("Resposta de autenticação inválida")
        except (requests.RequestException, ValueError, KeyError, TypeError):
            raise HTTPException(502, "Não foi possível autenticar no provedor bancário.") from None
        _session["key"] = token
        _session["expires"] = time.monotonic() + 6600
        return token


def request(method, path, *, params=None, payload=None):
    # Caminhos são constantes ou UUIDs validados antes da chamada, nunca URLs arbitrárias.
    if not path.startswith("/") or "://" in path:
        raise HTTPException(422, "Caminho bancário inválido.")
    try:
        r = requests.request(method, BASE + path, params=params, json=payload,
                             headers={"X-API-KEY": key(), "Accept": "application/json",
                                      "Content-Type": "application/json"}, timeout=20)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        raise HTTPException(502, "Falha na comunicação com o provedor bancário. Verifique a autorização e tente novamente.") from None


def checked_uuid(value):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(422, "Identificador de conexão inválido.") from None


def allowed_sandbox_connector():
    data = request("GET", "/connectors", params={"sandbox": "true"})
    choices = data.get("results", []) if isinstance(data, dict) else []
    candidates = [x for x in choices if x.get("isSandbox") is True]
    if not candidates:
        raise HTTPException(503, "Conector de teste Pluggy indisponível.")
    preferred = next((x for x in candidates if "Pluggy Bank" in x.get("name", "")), candidates[0])
    return int(preferred["id"])


def connect_token(reference):
    payload = {"options": {"clientUserId": str(reference), "avoidDuplicates": True}}
    result = request("POST", "/connect_token", payload=payload)
    token = result.get("accessToken")
    if not isinstance(token, str) or not token:
        raise HTTPException(502, "Token de conexão indisponível.")
    return token


def item_details(item_id, intent_id):
    item = request("GET", "/items/" + checked_uuid(item_id))
    if item.get("clientUserId") != str(intent_id):
        raise HTTPException(403, "Esta conexão não foi iniciada por esta autorização AXORA.")
    connector = item.get("connector") or {}
    if not live_enabled() and connector.get("isSandbox") is not True:
        raise HTTPException(403, "O piloto permite somente conectores de teste.")
    if item.get("status") != "UPDATED":
        raise HTTPException(409, "A conexão ainda está sendo autorizada. Confira o banco e tente novamente.")
    return item


def bank_accounts(item_id):
    obj = request("GET", "/accounts", params={"itemId": checked_uuid(item_id), "type": "BANK"})
    rows = obj.get("results", []) if isinstance(obj, dict) else []
    return [x for x in rows if x.get("type") == "BANK" and x.get("currencyCode") == "BRL"]


def public_bank_account(a):
    number = str(a.get("number") or "")
    return {
        "id": checked_uuid(a["id"]),
        "label": str(a.get("name") or a.get("marketingName") or "Conta bancária")[:100],
        "owner": str(a.get("owner") or "Titular informado pelo banco")[:100],
        "last_digits": number[-4:] if len(number) >= 4 else "",
        "balance": a.get("balance"),
        "type": a.get("subtype"),
    }


def postable_transactions(provider_account_id, *, max_records=100):
    """Retorna no máximo 100 transações POSTED recentes, sem conciliar nenhuma."""
    account_id = checked_uuid(provider_account_id)
    start = (date.today() - timedelta(days=90)).isoformat()
    payload = request("GET", "/transactions", params={
        "accountId": account_id, "from": start, "pageSize": min(max_records, 100),
        "page": 1,
    })
    records = payload.get("results", []) if isinstance(payload, dict) else []
    output = []
    for tx in records:
        if tx.get("status") != "POSTED" or tx.get("currencyCode") != "BRL":
            continue
        if tx.get("type") not in {"DEBIT", "CREDIT"}:
            continue
        try:
            amount = Decimal(str(tx.get("amount")))
            if not amount.is_finite() or amount == 0 or abs(amount) > Decimal("99999999999999.99"):
                continue
            amount = abs(amount) * (-1 if tx["type"] == "DEBIT" else 1)
            text = str(tx.get("descriptionRaw") or tx.get("description") or "").strip()[:240]
            on = str(tx["date"])[:10]
            date.fromisoformat(on)
            identifier = checked_uuid(tx["id"])
            if not text:
                continue
        except (TypeError, KeyError, ValueError, InvalidOperation, HTTPException):
            continue
        output.append({"posted_on": on, "description": text,
                       "amount": float(amount), "source": "import",
                       "external_ref": "pluggy:" + identifier})
    return output
