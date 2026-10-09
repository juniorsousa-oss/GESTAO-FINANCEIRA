"""AXORA 2.0: API privada e frontend web, sem bibliotecas Streamlit."""
import io
import math
import os
import re
from datetime import date
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File, Depends
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from axora_v2 import db, metrics, security
from services.importer import parse_excel
from services.profile import clean_display_name, avatar_data_uri

@asynccontextmanager
async def lifespan(_app):
    if not db.configured():
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_KEY antes de iniciar o AXORA.")
    security.signer()
    yield


app = FastAPI(title="AXORA API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
DATA_KINDS = ("movements", "forecasts", "accounts", "debts")
COLUMNS = {
    "movements": {"movement_date", "description", "value", "category", "competence", "classification", "allocation_value", "fixed_variable"},
    "forecasts": {"due_date", "description", "category", "value", "adjustment", "final_value", "type", "status", "simulate_payment", "competence"},
    "accounts": {"name", "balance"},
    "debts": {"description", "total_value", "status", "total_installments", "paid_installments", "installment_value", "open_value"},
}
MONEY_FIELDS = {
    "value", "allocation_value", "adjustment", "final_value", "balance",
    "total_value", "installment_value", "open_value",
}
INT_FIELDS = {"total_installments", "paid_installments"}
SETTINGS_KEYS = set(db.DEFAULT_SETTINGS)
ORDERS = {"movements": "id.desc", "forecasts": "due_date.asc", "accounts": "name.asc", "debts": "id.asc"}


@app.middleware("http")
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


class Login(BaseModel):
    password: str = Field(min_length=1, max_length=500)


class UserCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=500)
    share_ack: bool = False


def auth(request: Request):
    return security.current(request)


def authorized(request: Request, user=Depends(auth)):
    security.require_csrf(request, user)
    return user


def admin(user):
    if not user.get("is_admin"):
        raise HTTPException(403, "Esta ação exige permissão de administrador.")


def kind_or_404(kind):
    if kind not in DATA_KINDS:
        raise HTTPException(404, "Módulo não encontrado.")


def positive_id(pk):
    if pk < 1:
        raise HTTPException(422, "Identificador inválido.")


def sanitize(kind, fields, *, creating=False):
    if not isinstance(fields, dict) or not fields or set(fields) - COLUMNS[kind]:
        raise HTTPException(422, "Campos inválidos para este módulo.")
    row = dict(fields)
    row.pop("final_value", None)  # sempre calculado pelo servidor
    for key, value in list(row.items()):
        if key in MONEY_FIELDS:
            try:
                v = float(value)
                if not math.isfinite(v) or abs(v) > 1e12:
                    raise ValueError
                row[key] = round(v, 2)
            except (TypeError, ValueError):
                raise HTTPException(422, "Valor numérico inválido: " + key) from None
        elif key in INT_FIELDS:
            if isinstance(value, bool) or not str(value).isdigit() or int(value) > 100000:
                raise HTTPException(422, "Número de parcelas inválido.")
            row[key] = int(value)
        elif key == "simulate_payment":
            if not isinstance(value, bool):
                raise HTTPException(422, "Simulação inválida.")
        elif key in ("due_date", "movement_date"):
            if value not in (None, ""):
                try:
                    date.fromisoformat(str(value))
                except (ValueError, TypeError):
                    raise HTTPException(422, "Data inválida.") from None
            row[key] = value or None
        else:
            if not isinstance(value, str) or len(value) > 240:
                raise HTTPException(422, "Texto inválido: " + key)
            row[key] = value.strip()

    label = row.get("description") if kind != "accounts" else row.get("name")
    if creating and not label:
        raise HTTPException(422, "Informe o nome ou descrição.")
    if "description" in row and not row["description"]:
        raise HTTPException(422, "Descrição obrigatória.")
    if "name" in row and not row["name"]:
        raise HTTPException(422, "Nome obrigatório.")
    if "name" in row:
        row["name"] = row["name"].upper()
    if "classification" in row and row["classification"] not in ("ENTRADA", "SAÍDA"):
        raise HTTPException(422, "Classificação inválida.")
    if "type" in row and row["type"] not in ("Entrada", "Saída"):
        raise HTTPException(422, "Tipo inválido.")
    if "competence" in row and row["competence"] and not re.fullmatch(r"(0[1-9]|1[0-2])/20\d{2}", row["competence"]):
        raise HTTPException(422, "Competência deve ser MM/AAAA.")
    if kind in ("movements", "forecasts") and "value" in row and row["value"] <= 0:
        raise HTTPException(422, "O valor deve ser maior que zero.")
    for field in ("allocation_value", "total_value", "installment_value", "open_value"):
        if field in row and row[field] < 0:
            raise HTTPException(422, "Valor não pode ser negativo: " + field)
    if creating and kind in ("movements", "forecasts") and "value" not in row:
        raise HTTPException(422, "Informe o valor.")
    if creating and kind == "movements" and "classification" not in row:
        raise HTTPException(422, "Informe a classificação.")
    if creating and kind == "forecasts" and "type" not in row:
        raise HTTPException(422, "Informe o tipo.")
    return row


@app.get("/health")
def health():
    return {"status": "ok", "app": "AXORA", "engine": "FastAPI"}


@app.post("/api/login")
def login(payload: Login, request: Request, response: Response):
    user = security.login(payload.password, request.client.host if request.client else "unknown")
    security.create_session(response, user)
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(auth)):
    avatar_rows = db.select("users", fields="avatar_data_uri", params={"id": f"eq.{user['id']}", "limit": 1})
    return {"id": user["id"], "display_name": user["display_name"], "is_admin": user["is_admin"],
            "avatar_data_uri": avatar_rows[0].get("avatar_data_uri") if avatar_rows else None, "csrf": user["csrf"]}


@app.post("/api/logout")
def logout(response: Response, user=Depends(authorized)):
    security.clear_session(response)
    return {"ok": True}


@app.get("/api/snapshot")
def snapshot(user=Depends(auth)):
    rows = {k: db.select(k, order=ORDERS[k]) for k in DATA_KINDS}
    settings = db.get_settings()
    summary = metrics.compute(rows["movements"], rows["forecasts"], rows["accounts"], rows["debts"], settings)
    return {**rows, "settings": settings, "summary": summary}


@app.post("/api/rows/{kind}")
def add_row(kind: str, payload: dict, user=Depends(authorized)):
    kind_or_404(kind)
    row = sanitize(kind, payload, creating=True)
    if kind == "forecasts":
        row["final_value"] = round(row["value"] + row.get("adjustment", 0), 2)
    return db.insert(kind, row)


@app.patch("/api/rows/{kind}/{pk}")
def change_row(kind: str, pk: int, payload: dict, user=Depends(authorized)):
    kind_or_404(kind)
    positive_id(pk)
    current = db.select(kind, params={"id": f"eq.{pk}", "limit": 1})
    if not current:
        raise HTTPException(404, "Registro não localizado.")
    row = sanitize(kind, payload)
    if kind == "forecasts" and ("value" in row or "adjustment" in row):
        row["final_value"] = round(float(row.get("value", current[0].get("value") or 0)) + float(row.get("adjustment", current[0].get("adjustment") or 0)), 2)
    return db.update(kind, pk, row)


@app.delete("/api/rows/{kind}/{pk}")
def remove_row(kind: str, pk: int, user=Depends(authorized)):
    kind_or_404(kind)
    positive_id(pk)
    db.delete(kind, pk)
    return {"ok": True}


@app.post("/api/settings")
def settings(payload: dict, user=Depends(authorized)):
    if not payload or set(payload) - SETTINGS_KEYS:
        raise HTTPException(422, "Configurações inválidas.")
    parsed = {}
    for key, value in payload.items():
        try:
            v = float(value)
        except (ValueError, TypeError):
            raise HTTPException(422, "Valor de configuração inválido.") from None
        if not math.isfinite(v) or v < 0 or v > 1e10:
            raise HTTPException(422, "Valor de configuração inválido.")
        if key in ("investment_pct", "fixed_pct", "leisure_pct") and v > 100:
            raise HTTPException(422, "O percentual não pode ultrapassar 100.")
        if key == "emergency_months" and v < 1:
            raise HTTPException(422, "Informe pelo menos um mês.")
        parsed[key] = v
    db.save_settings(parsed)
    return {"ok": True}


@app.post("/api/profile")
def change_profile(payload: dict, user=Depends(authorized)):
    if set(payload) != {"display_name"}:
        raise HTTPException(422, "Dados de perfil inválidos.")
    name = clean_display_name(payload["display_name"])
    if not name:
        raise HTTPException(422, "Informe seu nome.")
    db.update("users", user["id"], {"display_name": name})
    return {"ok": True}


@app.post("/api/profile/avatar")
async def avatar(request: Request, file: UploadFile = File(...), user=Depends(authorized)):
    if file.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(422, "Use uma foto PNG ou JPEG.")
    raw = await file.read(15 * 1024 * 1024 + 1)
    class Wrapped:
        size = len(raw)
        def getvalue(self):
            return raw
    try:
        uri = avatar_data_uri(Wrapped())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    db.update("users", user["id"], {"avatar_data_uri": uri})
    return {"ok": True}


@app.delete("/api/profile/avatar")
def remove_avatar(user=Depends(authorized)):
    db.update("users", user["id"], {"avatar_data_uri": None})
    return {"ok": True}


@app.get("/api/users")
def users(user=Depends(auth)):
    admin(user)
    return [{"id": x["id"], "display_name": x["display_name"], "is_admin": x["is_admin"], "is_active": x["is_active"]} for x in security.accounts()]


@app.post("/api/users")
def create_user(payload: UserCreate, user=Depends(authorized)):
    admin(user)
    if not payload.share_ack:
        raise HTTPException(422, "Confirme que os usuários compartilharão a base financeira.")
    name = clean_display_name(payload.display_name)
    if not name:
        raise HTTPException(422, "Nome obrigatório.")
    users = security.accounts()
    if len(users) >= 250:
        raise HTTPException(422, "Limite de usuários atingido.")
    if any(x["display_name"].casefold() == name.casefold() for x in users):
        raise HTTPException(422, "Já existe usuário com esse nome.")
    if any(security.matches(payload.password, x["password_hash"]) for x in users):
        raise HTTPException(422, "Esta senha já pertence a outra pessoa.")
    new_user = db.insert("users", {"display_name": name, "password_hash": security.hash_password(payload.password),
                                   "is_active": True, "is_admin": False})
    return {"id": new_user["id"], "display_name": name}


async def read_excel(file):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(422, "Envie um arquivo .xlsx válido.")
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Arquivo Excel deve ter até 10 MB.")
    try:
        return parse_excel(io.BytesIO(content))
    except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(422, "A planilha não segue o modelo das quatro abas: " + str(exc)[:240]) from None


@app.post("/api/import/preview")
async def preview(file: UploadFile = File(...), user=Depends(authorized)):
    parsed = await read_excel(file)
    return {"counts": {name: len(parsed[name]) for name in DATA_KINDS},
            "warning": "A importação só será permitida se todas as quatro tabelas estiverem vazias."}


@app.post("/api/import/commit")
async def import_commit(file: UploadFile = File(...), user=Depends(authorized)):
    parsed = await read_excel(file)
    # Nunca substituir dados persistentes na V1/V2.
    existing = [name for name in DATA_KINDS if db.select(name, fields="id", params={"limit": 1})]
    if existing:
        raise HTTPException(409, "Importação bloqueada: já existem registros em " + ", ".join(existing) + ".")
    written = []
    try:
        for name in DATA_KINDS:
            rows = parsed[name]
            if rows:
                db.insert(name, rows)
            written.append(name)
    except HTTPException:
        raise HTTPException(502, "Importação interrompida. Confira o banco e faça backup antes de nova tentativa.") from None
    return {"ok": True, "counts": {k: len(parsed[k]) for k in DATA_KINDS}}


@app.get("/api/export")
def export_excel(user=Depends(auth)):
    data = {kind: db.select(kind, order=ORDERS[kind]) for kind in DATA_KINDS}
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for kind, rows in data.items():
            pd.DataFrame(rows).drop(columns=["created_at", "updated_at"], errors="ignore").to_excel(
                writer, sheet_name={"movements":"Movimentacoes","forecasts":"Previsoes","accounts":"Contas","debts":"Dividas"}[kind], index=False
            )
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="axora_export.xlsx"'})


ASSETS = os.path.join(os.path.dirname(__file__), "static")
app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")


@app.get("/")
def index():
    return FileResponse(os.path.join(ASSETS, "index.html"), media_type="text/html")
