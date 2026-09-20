"""Contas individuais por senha para a V1 do Gestão Financeira.

O nome é obtido exclusivamente da conta cujo hash de senha foi verificado.
As contas financeiras ainda são compartilhadas: isolamento de movimentações
por usuário exigirá migração específica das demais tabelas.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

import requests

from services.db import _headers, _secret, _url, insert_row
from services.profile import clean_display_name

USERS_TABLE = "finance_users"
ROUNDS = 390_000


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ROUNDS)
    return f"pbkdf2_sha256${ROUNDS}${salt.hex()}${value.hex()}"


def matches_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = str(encoded).split("$", 3)
        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(rounds) <= 1_000_000:
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds)
        )
        return hmac.compare_digest(derived, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def list_users() -> list[dict]:
    response = requests.get(
        _url(USERS_TABLE),
        headers=_headers(),
        params={
            "select": "id,display_name,password_hash,is_admin,is_active,avatar_data_uri",
            "order": "id.asc",
            "limit": "250",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def identify_user(password: str) -> dict | None:
    """Senha correta identifica a conta, não um nome fornecido no login."""
    accounts = list_users()
    for account in accounts:
        if account.get("is_active") and matches_password(password, account["password_hash"]):
            return account

    # Migração única da senha já configurada no Streamlit: após criar o
    # primeiro usuário, a senha legada deixa de ser uma rota alternativa.
    if not accounts:
        legacy_password = _secret("APP_ACCESS_PASSWORD")
        if legacy_password and hmac.compare_digest(password, legacy_password):
            owner_name = clean_display_name(_secret("APP_OWNER_NAME") or "Júnior")
            created = insert_row(
                USERS_TABLE,
                {
                    "display_name": owner_name,
                    "password_hash": password_hash(password),
                    "is_admin": True,
                    "is_active": True,
                },
            )
            return created
    return None


def create_user(name: str, password: str) -> dict:
    normalized = clean_display_name(name)
    if not normalized:
        raise ValueError("Informe o nome do novo usuário.")
    if len(password) < 12:
        raise ValueError("A senha precisa ter pelo menos 12 caracteres.")
    accounts = list_users()
    if len(accounts) >= 250:
        raise ValueError("Limite de usuários alcançado.")
    if any(matches_password(password, account["password_hash"]) for account in accounts):
        raise ValueError("Essa senha já está vinculada a outro usuário.")
    if any(account["display_name"].casefold() == normalized.casefold() for account in accounts):
        raise ValueError("Já existe um usuário com esse nome.")
    return insert_row(
        USERS_TABLE,
        {
            "display_name": normalized,
            "password_hash": password_hash(password),
            "is_admin": False,
            "is_active": True,
        },
    )


def update_own_profile(user_id: int, changes: dict) -> None:
    allowed = {"display_name", "avatar_data_uri"}
    if set(changes) - allowed or not changes:
        raise ValueError("Alteração de perfil inválida.")
    response = requests.patch(
        _url(USERS_TABLE),
        headers=_headers("return=minimal"),
        params={"id": f"eq.{int(user_id)}", "is_active": "eq.true"},
        json=changes,
        timeout=20,
    )
    response.raise_for_status()
