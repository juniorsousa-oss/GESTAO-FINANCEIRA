import os
from typing import Any

import requests
import streamlit as st


TABLES = {
    "movements": "finance_movements",
    "forecasts": "finance_forecasts",
    "accounts": "finance_accounts",
    "debts": "finance_debts",
    "settings": "finance_settings",
}


def _secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return value or os.getenv(name)


def is_configured() -> bool:
    return bool(_secret("SUPABASE_URL") and _secret("SUPABASE_KEY"))


def verify_database() -> tuple[bool, str]:
    """Testa em leitura as cinco tabelas exigidas antes de habilitar o app."""
    if not is_configured():
        return False, "Credenciais do Supabase ainda não configuradas."
    for table in TABLES.values():
        try:
            response = requests.get(
                _url(table),
                headers=_headers(),
                params={"select": "id", "limit": 1},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException:
            return False, (
                f"Não foi possível validar a tabela {table}. Confira o projeto, "
                "a chave e a aplicação do supabase_schema.sql."
            )
    return True, "Conexão validada com as cinco tabelas financeiras."


def _headers(prefer: str | None = None) -> dict[str, str]:
    key = _secret("SUPABASE_KEY") or ""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _url(table: str) -> str:
    base = (_secret("SUPABASE_URL") or "").rstrip("/")
    return f"{base}/rest/v1/{table}"


def _local_key(table: str) -> str:
    return f"local::{table}"


def _local_rows(table: str) -> list[dict[str, Any]]:
    key = _local_key(table)
    if key not in st.session_state:
        st.session_state[key] = []
    return st.session_state[key]


def select_rows(table: str, order: str | None = None) -> list[dict[str, Any]]:
    if not is_configured():
        rows = list(_local_rows(table))
        if order:
            col = order.split(".")[0]
            rows = sorted(rows, key=lambda r: (r.get(col) is None, r.get(col)))
        return rows

    params = {"select": "*"}
    if order:
        params["order"] = order
    response = requests.get(_url(table), headers=_headers(), params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def insert_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in row.items() if v is not None}
    if not is_configured():
        rows = _local_rows(table)
        existing_ids = [int(r.get("id", 0) or 0) for r in rows]
        payload["id"] = max(existing_ids, default=0) + 1
        rows.append(payload)
        return payload

    response = requests.post(
        _url(table),
        headers=_headers("return=representation"),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data[0] if data else payload


def insert_rows(table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cleaned = [{k: v for k, v in row.items() if v is not None and k != "id"} for row in rows]
    if not is_configured():
        target = _local_rows(table)
        next_id = max([int(r.get("id", 0) or 0) for r in target], default=0) + 1
        for row in cleaned:
            row = dict(row)
            row["id"] = next_id
            next_id += 1
            target.append(row)
        return

    response = requests.post(
        _url(table),
        headers=_headers("return=minimal"),
        json=cleaned,
        timeout=60,
    )
    response.raise_for_status()


def update_row(table: str, row_id: int, changes: dict[str, Any]) -> None:
    payload = {k: v for k, v in changes.items() if k != "id"}
    if not is_configured():
        rows = _local_rows(table)
        for idx, row in enumerate(rows):
            if int(row.get("id", -1)) == int(row_id):
                rows[idx] = {**row, **payload}
                return
        raise KeyError(f"Registro {row_id} não encontrado")

    response = requests.patch(
        _url(table),
        headers=_headers("return=minimal"),
        params={"id": f"eq.{row_id}"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()


def delete_row(table: str, row_id: int) -> None:
    if not is_configured():
        rows = _local_rows(table)
        st.session_state[_local_key(table)] = [r for r in rows if int(r.get("id", -1)) != int(row_id)]
        return

    response = requests.delete(
        _url(table),
        headers=_headers("return=minimal"),
        params={"id": f"eq.{row_id}"},
        timeout=30,
    )
    response.raise_for_status()


def replace_table(table: str, rows: list[dict[str, Any]]) -> None:
    if not is_configured():
        st.session_state[_local_key(table)] = []
        insert_rows(table, rows)
        return

    # Validação inicial: não apagar registros persistentes já existentes.
    # A importação completa deve ser transacional/ter backup antes de
    # permitir uma substituição de dados reais em produção.
    if select_rows(table):
        raise RuntimeError(
            f"A tabela {table} já contém dados no banco. "
            "A substituição está bloqueada para evitar perda irreversível. "
            "Exporte os registros existentes antes de uma nova carga."
        )
    insert_rows(table, rows)


def get_settings() -> dict[str, float]:
    defaults = {
        "gross_income": 0.0,
        "net_income": 0.0,
        "emergency_months": 6.0,
        "investment_pct": 20.0,
        "fixed_pct": 50.0,
        "leisure_pct": 30.0,
        "investment_multiple": 250.0,
    }
    rows = select_rows(TABLES["settings"])
    for row in rows:
        key = row.get("key")
        if key in defaults:
            try:
                defaults[key] = float(row.get("value") or 0)
            except (TypeError, ValueError):
                pass
    return defaults


def save_setting(key: str, value: float) -> None:
    table = TABLES["settings"]
    if not is_configured():
        rows = _local_rows(table)
        for row in rows:
            if row.get("key") == key:
                row["value"] = float(value)
                return
        rows.append({"id": len(rows) + 1, "key": key, "value": float(value)})
        return

    existing = requests.get(
        _url(table),
        headers=_headers(),
        params={"select": "id,key,value", "key": f"eq.{key}"},
        timeout=30,
    )
    existing.raise_for_status()
    data = existing.json()
    if data:
        update_row(table, int(data[0]["id"]), {"value": float(value)})
    else:
        insert_row(table, {"key": key, "value": float(value)})
