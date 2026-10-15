"""Conector pessoal MeuPluggy: somente leitura, restrito a um único usuário.

A API Key nunca sai do backend. Não cria conexões bancárias ou consente em
nome de terceiros; lê somente o item previamente autorizado no MeuPluggy.
"""
import os
import threading
import time
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, parse_qs
from uuid import UUID

import requests
from fastapi import HTTPException

API = "https://api.pluggy.ai"
_lock = threading.Lock()
_cache = {"token": None, "valid_until": 0}


def uuid_text(value):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(422, "Identificador bancário inválido.") from None


def owner_id():
    raw = os.environ.get("PLUGGY_PERSONAL_USER_ID", "")
    if not raw.isdecimal() or int(raw) <= 0:
        return None
    return int(raw)


def configured():
    return bool(os.environ.get("PLUGGY_CLIENT_ID")
                and os.environ.get("PLUGGY_CLIENT_SECRET")
                and os.environ.get("PLUGGY_ITEM_ID")
                and owner_id() is not None)


def personal_item():
    if not configured():
        raise HTTPException(503, "MeuPluggy pessoal ainda não está configurado na Hostinger.")
    return uuid_text(os.environ["PLUGGY_ITEM_ID"])


def require_owner(user):
    if not configured() or str(user.get("id")) != str(owner_id()):
        raise HTTPException(403, "Conexão pessoal não disponível para este usuário.")


def _auth_token():
    if not configured():
        raise HTTPException(503, "Credenciais pessoais Pluggy ausentes.")
    with _lock:
        if _cache["token"] and time.monotonic() < _cache["valid_until"]:
            return _cache["token"]
        try:
            result = requests.post(API + "/auth", json={
                "clientId": os.environ["PLUGGY_CLIENT_ID"],
                "clientSecret": os.environ["PLUGGY_CLIENT_SECRET"],
            }, timeout=20)
            result.raise_for_status()
            token = result.json()["apiKey"]
            if not isinstance(token, str) or not token:
                raise ValueError("API Key vazia")
        except (requests.RequestException, ValueError, KeyError, TypeError):
            raise HTTPException(502, "Não foi possível autenticar na Pluggy. Confira a configuração privada.") from None
        _cache["token"] = token
        _cache["valid_until"] = time.monotonic() + 6600  # Chave expira em 2 h.
        return token


def _get(path, *, params):
    # Caminhos fixos, sem URLs fornecidas por usuários e sem redirecionamentos.
    if path not in ("/accounts", "/v2/transactions"):
        raise HTTPException(422, "Recurso de leitura bancária inválido.")
    try:
        response = requests.get(API + path, params=params,
                                headers={"X-API-KEY": _auth_token()},
                                timeout=25, allow_redirects=False)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Resposta inesperada")
        return result
    except (requests.RequestException, ValueError, TypeError):
        raise HTTPException(502, "Não foi possível consultar dados bancários na Pluggy.") from None


def bank_accounts():
    """Somente contas BANK, excluindo cartões de crédito do piloto inicial."""
    item_id = personal_item()
    result = _get("/accounts", params={"itemId": item_id})
    rows = result.get("results", [])
    if not isinstance(rows, list):
        raise HTTPException(502, "Resposta inesperada de contas bancárias.")
    accounts = []
    for account in rows:
        if not isinstance(account, dict) or account.get("type") != "BANK":
            continue
        if account.get("currencyCode") != "BRL":
            continue
        try:
            account_id = uuid_text(account["id"])
        except (KeyError, HTTPException):
            continue
        raw_balance = account.get("balance")
        try:
            balance = str(Decimal(str(raw_balance))) if raw_balance is not None else None
        except (TypeError, InvalidOperation):
            balance = None
        number = str(account.get("number") or "")
        accounts.append({
            "id": account_id,
            "name": str(account.get("name") or "Conta bancária")[:100],
            "last_digits": number[-4:] if len(number) >= 4 else "",
            "balance": balance,
            "institution": str((account.get("institution") or {}).get("name") or "")[:80],
        })
    return accounts


def normalize_transaction(tx):
    if not isinstance(tx, dict):
        return None
    if tx.get("status") != "POSTED" or tx.get("currencyCode") != "BRL":
        return None
    if tx.get("type") not in ("DEBIT", "CREDIT"):
        return None
    try:
        raw = Decimal(str(tx["amount"]))
        if not raw.is_finite() or raw == 0 or abs(raw) > Decimal("99999999999999.99"):
            return None
        amount = abs(raw) * (-1 if tx["type"] == "DEBIT" else 1)
        amount = amount.quantize(Decimal("0.01"))
        if amount == 0:
            return None
        when = date.fromisoformat(str(tx["date"])[:10]).isoformat()
        description = str(tx.get("descriptionRaw") or tx.get("description") or "").strip()[:240]
        if not description:
            return None
        return {
            "posted_on": when, "description": description, "amount": str(amount),
            "source": "import", "external_ref": "pluggy:" + uuid_text(tx["id"]),
        }
    except (KeyError, ValueError, TypeError, InvalidOperation, HTTPException):
        return None


def recent_transactions(provider_account_id, days=90, max_pages=20):
    """Cursor de v2, com limite de segurança e sem retornar páginas parciais."""
    account_id = uuid_text(provider_account_id)
    since = (date.today() - timedelta(days=days)).isoformat()
    params = {"accountId": account_id, "dateFrom": since}
    entries, pages, visited = [], 0, set()
    while True:
        response = _get("/v2/transactions", params=params)
        rows = response.get("results")
        if not isinstance(rows, list):
            raise HTTPException(502, "Extrato bancário retornou um formato inesperado.")
        for row in rows:
            entry = normalize_transaction(row)
            if entry:
                entries.append(entry)
        pages += 1
        next_page = response.get("next")
        if not next_page:
            break
        if pages >= max_pages:
            raise HTTPException(409, "Extrato maior que o limite de segurança. Solicite paginação adicional.")
        # 'next' é apenas uma query string. Nunca seguir domínios externos.
        part = urlsplit(next_page)
        if part.scheme or part.netloc or part.path not in ("", "/"):
            raise HTTPException(502, "Cursor do extrato inválido.")
        parsed = parse_qs(part.query)
        cursor = parsed.get("after", [None])[0]
        if not cursor or cursor in visited:
            raise HTTPException(502, "Paginação bancária inconsistente.")
        visited.add(cursor)
        params = {"accountId": account_id, "dateFrom": since, "after": cursor}
    return entries
