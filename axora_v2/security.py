"""Sessões HTTP-only e autenticação compatível com os hashes PBKDF2 da V1."""
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from axora_v2 import db

COOKIE = "axora_session"
MAX_AGE = 8 * 60 * 60
FAILURES = defaultdict(list)
ROUNDS = 390_000


def signer():
    key = os.environ.get("SESSION_SECRET", "")
    if len(key) < 32:
        raise RuntimeError("SESSION_SECRET precisa ter pelo menos 32 caracteres aleatórios.")
    return URLSafeTimedSerializer(key, salt="axora-session-v2")


def hash_password(password):
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ROUNDS)
    return f"pbkdf2_sha256${ROUNDS}${salt.hex()}${derived.hex()}"


def matches(password, encoded):
    try:
        algorithm, rounds, salt, digest = str(encoded).split("$", 3)
        work = int(rounds)
        if algorithm != "pbkdf2_sha256" or not 100000 <= work <= 1000000:
            return False
        derived = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), work)
        return hmac.compare_digest(derived, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def accounts():
    return db.select("users", fields="id,display_name,password_hash,is_admin,is_active", order="id.asc", params={"limit": 250})


def login(password, remote):
    now = time.monotonic()
    failures = [t for t in FAILURES[remote] if now - t < 300]
    FAILURES[remote] = failures
    if len(failures) >= 8:
        raise HTTPException(429, "Muitas tentativas. Aguarde cinco minutos.")
    users = accounts()
    found = None
    for user in users:
        if user.get("is_active") and matches(password, user.get("password_hash", "")):
            found = user
            break
    if found is None and not users:
        legacy = os.environ.get("APP_ACCESS_PASSWORD", "")
        if legacy and hmac.compare_digest(password, legacy):
            found = db.insert("users", {
                "display_name": (os.getenv("APP_OWNER_NAME") or "Júnior")[:40],
                "password_hash": hash_password(password),
                "is_admin": True, "is_active": True,
            })
    if not found:
        failures.append(now)
        raise HTTPException(401, "Senha incorreta.")
    FAILURES.pop(remote, None)
    return found


def current(request: Request):
    token = request.cookies.get(COOKIE, "")
    try:
        data = signer().loads(token, max_age=MAX_AGE)
        uid = int(data["uid"])
        if not (data.get("csrf") and isinstance(data["csrf"], str)):
            raise ValueError
    except (BadSignature, SignatureExpired, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Sua sessão expirou. Faça login novamente.") from None
    users = db.select(
        "users",
        fields="id,display_name,is_admin,is_active,avatar_data_uri",
        params={"id": "eq." + str(uid), "limit": 1},
    )
    if not users or not users[0].get("is_active"):
        raise HTTPException(401, "Usuário desativado ou sessão inválida.")
    user = users[0]
    user["csrf"] = data["csrf"]
    return user


def require_csrf(request: Request, user):
    candidate = request.headers.get("X-CSRF-Token", "")
    if not candidate or not hmac.compare_digest(candidate, user["csrf"]):
        raise HTTPException(403, "Verificação de segurança da sessão falhou.")


def create_session(response, user):
    token = signer().dumps({"uid": int(user["id"]), "csrf": secrets.token_urlsafe(32)})
    response.set_cookie(
        COOKIE, token, max_age=MAX_AGE, path="/",
        httponly=True, secure=os.getenv("COOKIE_SECURE", "1") != "0",
        samesite="lax",
    )


def clear_session(response):
    response.delete_cookie(COOKIE, path="/", secure=os.getenv("COOKIE_SECURE", "1") != "0", samesite="lax")
