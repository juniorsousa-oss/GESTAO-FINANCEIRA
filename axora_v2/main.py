"""AXORA 2.0: API privada e frontend web, sem bibliotecas Streamlit."""
import io
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
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

from axora_v2 import db, metrics, security, branding, provisions, catalogs, banking, meu_pluggy, meu_pluggy_sync
from services.importer import parse_excel
from services.profile import clean_display_name, avatar_data_uri

@asynccontextmanager
async def lifespan(_app):
    if not db.configured():
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_KEY antes de iniciar o AXORA.")
    security.signer()
    task = asyncio.create_task(meu_pluggy_sync.periodic_sync()) if meu_pluggy.configured() else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


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


def user_workspace(user):
    """Acesso financeiro por workspace derivado exclusivamente da sessão."""
    result = db.call("POST", "rpc/axora_user_workspace", data={"p_user_id": int(user["id"])})
    if not isinstance(result, str) or len(result) != 36:
        raise HTTPException(503, "Espaço financeiro indisponível.")
    return result


def kind_or_404(kind):
    if kind == "forecasts":
        raise HTTPException(410, "Previsões do Excel desativadas; utilize Provisões.")
    if kind in ("accounts", "debts"):
        raise HTTPException(410, "Este módulo será reconstruído na nova lógica financeira.")
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
    workspace = user_workspace(user)
    scope = {"workspace_id": "eq." + workspace}
    rows = {kind: db.select(kind, order=ORDERS[kind], params=scope)
            for kind in ("movements", "accounts", "debts")}
    db.call("POST", "rpc/axora_ensure_provisions", data={"p_workspace_id": workspace})
    # Agregação no banco: não corta em 1.000 linhas, nem ignora parcelas distantes.
    provision_totals = db.call("POST", "rpc/axora_provision_overview",
                               data={"p_workspace_id": workspace})
    rows["forecasts"] = []
    settings = db.get_settings(workspace)
    summary = metrics.compute(rows["movements"], [], rows["accounts"], rows["debts"],
                              settings, provision_overview=provision_totals)
    return {**rows, "settings": settings, "summary": summary}


@app.post("/api/rows/{kind}")
def add_row(kind: str, payload: dict, user=Depends(authorized)):
    kind_or_404(kind)
    row = sanitize(kind, payload, creating=True)
    row["workspace_id"] = user_workspace(user)
    return db.insert(kind, row)


@app.patch("/api/rows/{kind}/{pk}")
def change_row(kind: str, pk: int, payload: dict, user=Depends(authorized)):
    kind_or_404(kind)
    positive_id(pk)
    workspace = user_workspace(user)
    current = db.select(kind, params={
        "id": f"eq.{pk}", "workspace_id": "eq." + workspace, "limit": 1})
    if not current:
        raise HTTPException(404, "Registro não localizado.")
    row = sanitize(kind, payload)
    if kind == "movements":
        if current[0].get("provision_occurrence_id"):
            raise HTTPException(409, "Registro de quitação vinculado à provisão; edição isolada bloqueada.")
        bank_links=db.call("GET","finance_bank_transactions",params={
            "select":"id","workspace_id":"eq."+workspace,
            "movement_id":"eq."+str(pk),"limit":1})
        if bank_links:
            raise HTTPException(409, "Registro conciliado com banco. Use o procedimento de estorno auditado.")
    return db.update(kind, pk, row, workspace_id=workspace)


@app.delete("/api/rows/{kind}/{pk}")
def remove_row(kind: str, pk: int, user=Depends(authorized)):
    kind_or_404(kind)
    positive_id(pk)
    workspace = user_workspace(user)
    current = db.select(kind, params={
        "id": f"eq.{pk}", "workspace_id": "eq." + workspace, "limit": 1})
    if not current:
        raise HTTPException(404, "Registro não localizado.")
    if kind == "movements":
        if current[0].get("provision_occurrence_id"):
            raise HTTPException(409, "Registro vinculado à provisão; estorno controlado virá na próxima etapa.")
        bank_links=db.call("GET","finance_bank_transactions",params={
            "select":"id","workspace_id":"eq."+workspace,
            "movement_id":"eq."+str(pk),"limit":1})
        if bank_links:
            raise HTTPException(409, "Registro conciliado com banco. Exclusão isolada bloqueada.")
    db.delete(kind, pk, workspace_id=workspace)
    return {"ok": True}


def finance_catalog_items(workspace):
    db.call("POST", "rpc/axora_ensure_catalog", data={"p_workspace_id": workspace})
    return db.call("GET", "finance_catalog_options", params={
        "select": "id,kind,name,active", "workspace_id": "eq." + workspace,
        "order": "kind.asc,name.asc",
    })


@app.get("/api/catalogs")
def list_finance_catalogs(user=Depends(auth)):
    return {"items": finance_catalog_items(user_workspace(user))}


@app.get("/api/catalogs/export")
def export_finance_catalogs(user=Depends(auth)):
    records = finance_catalog_items(user_workspace(user))
    return Response(
        content=catalogs.export_csv(records).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="axora_categorias_responsaveis.csv"'},
    )


@app.post("/api/catalogs")
def add_finance_catalog(payload: dict, user=Depends(authorized)):
    workspace = user_workspace(user)
    option = catalogs.clean_option(payload)
    options = finance_catalog_items(workspace)
    if any(it["kind"] == option["kind"] and
           it["name"].casefold() == option["name"].casefold() for it in options):
        raise HTTPException(409, "Essa opção já existe. Reative-a se estiver inativa.")
    inserted = db.call("POST", "finance_catalog_options",
        data={"workspace_id": workspace, **option, "active": True},
        prefer="return=representation",
    )
    return {"item": inserted[0]}


@app.patch("/api/catalogs/{pk}")
def change_finance_catalog(pk: int, payload: dict, user=Depends(authorized)):
    positive_id(pk)
    if not isinstance(payload, dict) or set(payload) != {"active"} or not isinstance(payload["active"], bool):
        raise HTTPException(422, "Informe se a opção está ativa.")
    workspace = user_workspace(user)
    rows = finance_catalog_items(workspace)
    selected = next((it for it in rows if int(it["id"]) == pk), None)
    if selected is None:
        raise HTTPException(404, "Opção não localizada neste espaço financeiro.")
    if not payload["active"] and selected["active"]:
        remaining = [it for it in rows if it["kind"] == selected["kind"] and
                     it["active"] and int(it["id"]) != pk]
        if not remaining:
            raise HTTPException(409, "Mantenha pelo menos uma opção ativa desse tipo.")
    changed = db.call("PATCH", "finance_catalog_options", params={
        "id": "eq." + str(pk), "workspace_id": "eq." + workspace,
    }, data={"active": payload["active"]}, prefer="return=representation")
    if not changed:
        raise HTTPException(404, "Opção não localizada.")
    return {"item": changed[0]}


@app.get("/api/provisions")
def list_provisions(user=Depends(auth)):
    workspace = user_workspace(user)
    db.call("POST", "rpc/axora_ensure_provisions", data={"p_workspace_id": workspace})
    # Paginação explícita: o Supabase costuma limitar GET a 1.000 registros.
    items = []
    page_size = 500
    while True:
        rows = db.call("GET", "finance_provision_occurrences", params={
            "select": "id,rule_id,sequence_no,due_date,planned_value,status,description_override,category_override,responsible_override,value_mode_override,rule:finance_provision_rules(description,category,responsible,value_mode,recurrence,frequency,planned_value,end_date,installment_count)",
            "workspace_id": "eq." + workspace,
            "status": "eq.open", "order": "due_date.asc,id.asc",
            "limit": page_size, "offset": len(items),
        })
        items.extend(rows)
        if len(rows) < page_size:
            break
        if len(items) >= 10000:
            raise HTTPException(503, "Muitas provisões abertas. Use filtros por período.")
    return {"items": items}


@app.post("/api/provisions")
def add_provision(payload: dict, user=Depends(authorized)):
    workspace = user_workspace(user)
    values = provisions.clean_provision(payload)
    catalogs.canonicalize_provision(values, finance_catalog_items(workspace))
    values["p_workspace_id"] = workspace
    new_id = db.call("POST", "rpc/axora_create_provision", data=values)
    return {"id": new_id, "ok": True}


@app.patch("/api/provisions/{pk}")
def edit_provision(pk: int, payload: dict, user=Depends(authorized)):
    positive_id(pk)
    workspace = user_workspace(user)
    values = provisions.clean_edit_provision(payload)
    catalogs.canonicalize_provision(values, finance_catalog_items(workspace))
    return db.call("POST", "rpc/axora_edit_provision",
                   data={"p_workspace_id": workspace, "p_occurrence_id": pk, **values})


@app.post("/api/provisions/{pk}/cancel")
def cancel_provision(pk: int, payload: dict, user=Depends(authorized)):
    positive_id(pk)
    if not isinstance(payload, dict) or set(payload) != {"scope"}:
        raise HTTPException(422, "Selecione como excluir a provisão.")
    scope = provisions.clean_scope(payload["scope"])
    return db.call("POST", "rpc/axora_cancel_provision",
                   data={"p_workspace_id": user_workspace(user),
                         "p_occurrence_id": pk, "p_scope": scope})


@app.post("/api/provisions/{pk}/pay")
def pay_provision(pk: int, payload: dict, user=Depends(authorized)):
    positive_id(pk)
    values = provisions.clean_payment(payload)
    return db.call("POST", "rpc/axora_pay_provision",
                   data={"p_workspace_id": user_workspace(user), "p_occurrence_id": pk, **values})


# Banco manual e Central de Conciliação: nenhuma integração Open Finance ativa.
def banking_rows(workspace, name, *, filters=None, select="*", order=None, limit=500):
    params={"select":select,"workspace_id":"eq."+workspace,"limit":limit}
    if filters: params.update(filters)
    if order:params["order"]=order
    return db.call("GET",name,params=params)


@app.get("/api/banking")
def banking_overview(user=Depends(auth)):
    workspace=user_workspace(user)
    holders=banking_rows(workspace,"finance_bank_holders",order="name.asc")
    accounts=banking_rows(workspace,"finance_bank_accounts",order="nickname.asc")
    transactions=banking_rows(workspace,"finance_bank_transactions",
       filters={"status":"eq.pending"},order="posted_on.desc,id.desc",limit=500)
    is_owner = meu_pluggy.configured() and int(user["id"]) == meu_pluggy.owner_id()
    return {"holders":holders,"accounts":accounts,"pending":transactions,
            "mode":"read_only" if is_owner else "manual",
            "bank_connected":any(a.get("pluggy_account_id") for a in accounts),
            "provider":{"configured":bool(is_owner),
                        "type":"meu_pluggy_personal" if is_owner else "none",
                        "read_only":True}}


@app.post("/api/banking/holders")
def banking_add_holder(payload:dict,user=Depends(authorized)):
    workspace=user_workspace(user)
    cleaned=banking.clean_holder(payload)
    created=db.call("POST","finance_bank_holders",data={"workspace_id":workspace,**cleaned},
                    prefer="return=representation")
    return {"item":created[0]}


@app.post("/api/banking/accounts")
def banking_add_account(payload:dict,user=Depends(authorized)):
    workspace=user_workspace(user)
    cleaned=banking.clean_account(payload)
    holders=banking_rows(workspace,"finance_bank_holders",
                          filters={"id":"eq."+str(cleaned["holder_id"])},limit=1)
    if not holders:raise HTTPException(404,"Titular não encontrado neste espaço.")
    created=db.call("POST","finance_bank_accounts",
      data={"workspace_id":workspace,**cleaned},prefer="return=representation")
    return {"item":created[0]}


@app.patch("/api/banking/holders/{holder_id}")
def banking_edit_holder(holder_id:int,payload:dict,user=Depends(authorized)):
    holder_id=banking.positive_id(holder_id)
    workspace=user_workspace(user)
    existing=banking_rows(workspace,"finance_bank_holders",
        filters={"id":"eq."+str(holder_id)},limit=1)
    if not existing:
        raise HTTPException(404,"Titular não encontrado neste espaço.")
    details=banking.clean_holder(payload)
    updated=db.call("PATCH","finance_bank_holders",
        params={"id":"eq."+str(holder_id),"workspace_id":"eq."+workspace},
        data=details,prefer="return=representation")
    if not updated:
        raise HTTPException(404,"Titular não encontrado.")
    return {"item":updated[0]}


@app.delete("/api/banking/holders/{holder_id}")
def banking_delete_holder(holder_id:int,user=Depends(authorized)):
    holder_id=banking.positive_id(holder_id)
    workspace=user_workspace(user)
    existing=banking_rows(workspace,"finance_bank_holders",
        filters={"id":"eq."+str(holder_id)},limit=1)
    if not existing:
        raise HTTPException(404,"Titular não encontrado neste espaço.")
    accounts=banking_rows(workspace,"finance_bank_accounts",
        filters={"holder_id":"eq."+str(holder_id)},select="id",limit=1)
    if accounts:
        raise HTTPException(409,"Este titular possui contas vinculadas. Remova primeiro as contas sem movimentações.")
    if existing[0].get("linked_user_id") is not None:
        raise HTTPException(409,"Titular vinculado a um usuário. Desfaça a vinculação antes de excluir.")
    db.call("DELETE","finance_bank_holders",
        params={"id":"eq."+str(holder_id),"workspace_id":"eq."+workspace},
        prefer="return=minimal")
    return {"deleted":True,"id":holder_id}


@app.patch("/api/banking/accounts/{account_id}")
def banking_edit_account(account_id:int,payload:dict,user=Depends(authorized)):
    account_id=banking.positive_id(account_id)
    workspace=user_workspace(user)
    original=banking_rows(workspace,"finance_bank_accounts",
        filters={"id":"eq."+str(account_id)},limit=1)
    if not original:
        raise HTTPException(404,"Conta não encontrada neste espaço.")
    details=banking.clean_account(payload)
    holders=banking_rows(workspace,"finance_bank_holders",
        filters={"id":"eq."+str(details["holder_id"])},select="id",limit=1)
    if not holders:
        raise HTTPException(404,"Novo titular não encontrado neste espaço.")
    transactions=banking_rows(workspace,"finance_bank_transactions",
        filters={"account_id":"eq."+str(account_id)},select="id",limit=1)
    if transactions and any(
        str(details[key])!=str(original[0][key])
        for key in ("holder_id","bank_name","account_type")
    ):
        raise HTTPException(409,"Conta com transações: apenas o apelido pode ser corrigido. Titular, banco e tipo devem preservar o histórico.")
    updated=db.call("PATCH","finance_bank_accounts",
        params={"id":"eq."+str(account_id),"workspace_id":"eq."+workspace},
        data=details,prefer="return=representation")
    if not updated:
        raise HTTPException(404,"Conta não encontrada.")
    return {"item":updated[0]}


@app.delete("/api/banking/accounts/{account_id}")
def banking_delete_account(account_id:int,user=Depends(authorized)):
    account_id=banking.positive_id(account_id)
    workspace=user_workspace(user)
    existing=banking_rows(workspace,"finance_bank_accounts",
        filters={"id":"eq."+str(account_id)},select="id",limit=1)
    if not existing:
        raise HTTPException(404,"Conta não encontrada neste espaço.")
    transactions=banking_rows(workspace,"finance_bank_transactions",
        filters={"account_id":"eq."+str(account_id)},select="id",limit=1)
    if transactions:
        raise HTTPException(409,"Esta conta possui movimentações bancárias. A exclusão está bloqueada para preservar o histórico.")
    db.call("DELETE","finance_bank_accounts",
        params={"id":"eq."+str(account_id),"workspace_id":"eq."+workspace},
        prefer="return=minimal")
    return {"deleted":True,"id":account_id}


@app.post("/api/banking/transactions")
def banking_add_transaction(payload:dict,user=Depends(authorized)):
    workspace=user_workspace(user)
    cleaned=banking.clean_transaction(payload)
    accounts=banking_rows(workspace,"finance_bank_accounts",
                           filters={"id":"eq."+str(cleaned["account_id"])},limit=1)
    if not accounts:raise HTTPException(404,"Conta não localizada neste espaço.")
    created=db.call("POST","finance_bank_transactions",
      data={"workspace_id":workspace,**cleaned},prefer="return=representation")
    return {"item":created[0]}


# MeuPluggy pessoal: a conexão já foi autorizada no dashboard do provedor.
# Não abrir um widget de nova autorização bancária e não usar contas de terceiros.
def require_meu_pluggy(user):
    meu_pluggy.require_owner(user)
    return user_workspace(user)


@app.get("/api/banking/meu-pluggy/accounts")
def personal_bank_preview(user=Depends(auth)):
    require_meu_pluggy(user)
    return {"accounts":meu_pluggy.bank_accounts(),
            "read_only":True, "personal_use":True,
            "message":"Somente contas bancárias em BRL; cartão de crédito virá em etapa separada."}


@app.post("/api/banking/meu-pluggy/link")
def personal_bank_link(payload:dict,user=Depends(authorized)):
    workspace=require_meu_pluggy(user)
    if not isinstance(payload,dict) or set(payload)!={"account_id","provider_account_id","confirm_owner"}:
        raise HTTPException(422,"Escolha a conta do AXORA, a conta do provedor e confirme a titularidade.")
    if payload["confirm_owner"] is not True:
        raise HTTPException(422,"Confirme a titularidade antes de vincular.")
    local_id=banking.positive_id(payload["account_id"])
    provider_id=meu_pluggy.uuid_text(payload["provider_account_id"])
    own=banking_rows(workspace,"finance_bank_accounts",
                     filters={"id":"eq."+str(local_id)},limit=1)
    if not own:
        raise HTTPException(404,"Conta AXORA não localizada neste espaço.")
    if own[0].get("pluggy_account_id"):
        raise HTTPException(409,"A conta já possui conexão bancária.")
    if not any(a["id"]==provider_id for a in meu_pluggy.bank_accounts()):
        raise HTTPException(404,"A conta não pertence ao item MeuPluggy autorizado.")
    updated=db.call("PATCH","finance_bank_accounts",params={
        "workspace_id":"eq."+workspace,"id":"eq."+str(local_id),
        "pluggy_account_id":"is.null"
    },data={"pluggy_item_id":meu_pluggy.personal_item(),
            "pluggy_account_id":provider_id},prefer="return=representation")
    if not updated:
        raise HTTPException(409,"Conta já vinculada por outra sessão.")
    # A primeira sincronização pode ser iniciada manualmente após conferir o vínculo.
    return {"linked":True,"account_id":local_id,"read_only":True}


@app.post("/api/banking/meu-pluggy/sync/{account_id}")
def personal_bank_sync(account_id:int,user=Depends(authorized)):
    workspace=require_meu_pluggy(user)
    return meu_pluggy_sync.sync_account(workspace,banking.positive_id(account_id))


@app.get("/api/banking/transactions/{transaction_id}/suggestions")
def banking_suggestions(transaction_id:int,user=Depends(auth)):
    banking.positive_id(transaction_id)
    workspace=user_workspace(user)
    transactions=banking_rows(workspace,"finance_bank_transactions",
      filters={"id":"eq."+str(transaction_id),"status":"eq.pending"},limit=1)
    if not transactions:raise HTTPException(404,"Transação pendente não encontrada.")
    transaction=transactions[0]
    movements=db.select("movements",order="movement_date.desc,id.desc",
      params={"workspace_id":"eq."+workspace,"limit":500})
    provision_rows=banking_rows(workspace,"finance_provision_occurrences",
      filters={"status":"eq.open"},
      select="id,due_date,planned_value,description_override,rule:finance_provision_rules(description)",
      order="due_date.asc,id.asc",limit=1000)
    linked=banking_rows(workspace,"finance_bank_transactions",
      filters={"movement_id":"not.is.null"},select="movement_id",limit=1000)
    occupied=[row["movement_id"] for row in linked if row.get("movement_id")]
    return {"transaction_id":transaction_id,
            "candidates":banking.suggestions(transaction,movements,provision_rows,occupied)}


@app.get("/api/banking/history")
def banking_history(user=Depends(auth)):
    workspace=user_workspace(user)
    rows=banking_rows(workspace,"finance_reconciliation_events",
      select="id,transaction_id,actor_id,action,movement_id,provision_occurrence_id,counterpart_id,notes,created_at",
      order="created_at.desc,id.desc",limit=100)
    return {"items":rows}


@app.post("/api/banking/reconcile")
def banking_reconcile(payload:dict,user=Depends(authorized)):
    workspace=user_workspace(user)
    data=banking.clean_decision(payload)
    return db.call("POST","rpc/axora_confirm_reconciliation",
      data={"p_workspace_id":workspace,"p_user_id":int(user["id"]),**data})


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
    db.save_settings(parsed, user_workspace(user))
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



# A mesma assinatura institucional e lida no login publico e no rodape interno.
# Apenas o administrador pode altera-la; o arquivo e armazenado no Supabase.
def institutional_row(fields="key,updated_at"):
    items = db.select(
        "branding",
        fields=fields,
        params={"key": "eq.institutional_signature", "limit": 1},
    )
    return items[0] if items else None


@app.get("/api/branding/institutional")
def get_institutional_brand():
    row = institutional_row()
    return {
        "has_logo": bool(row),
        "updated_at": row.get("updated_at") if row else None,
    }


@app.get("/api/branding/institutional/image")
def get_institutional_image():
    row = institutional_row(fields="content_type,image_data_uri")
    if not row:
        raise HTTPException(404, "Assinatura ainda não configurada.")
    raw = branding.render_logo_image(row["image_data_uri"])
    return Response(
        raw, media_type=row["content_type"],
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.post("/api/branding/institutional")
async def upload_institutional_brand(file: UploadFile = File(...), user=Depends(authorized)):
    admin(user)
    raw = await file.read(branding.MAX_UPLOAD + 1)
    mime, data_uri = branding.prepare_logo(raw, file.content_type or "")
    timestamp = datetime.now(timezone.utc).isoformat()
    db.call(
        "POST",
        db.TABLES["branding"],
        params={"on_conflict": "key"},
        data={
            "key": "institutional_signature",
            "content_type": mime,
            "image_data_uri": data_uri,
            "updated_at": timestamp,
        },
        prefer="resolution=merge-duplicates,return=representation",
    )
    return {"ok": True, "has_logo": True, "updated_at": timestamp}


@app.delete("/api/branding/institutional")
def remove_institutional_brand(user=Depends(authorized)):
    admin(user)
    db.call(
        "DELETE",
        db.TABLES["branding"],
        params={"key": "eq.institutional_signature"},
        prefer="return=minimal",
    )
    return {"ok": True, "has_logo": False, "updated_at": None}


# Kit visual AXORA: quatro aplicações independentes de uma mesma identidade.
# Os arquivos são privados para escrita, públicos para exibição no login/favicon.
BRAND_KIT_SLOTS = {
    "primary": ("axora_primary", "Principal · login e apresentações", (1400, 420)),
    "secondary": ("axora_secondary", "Horizontal compacta · menu lateral", (1100, 340)),
    "icon": ("axora_icon", "Ícone do aplicativo · 1024 px", (1024, 1024)),
    "favicon": ("axora_favicon", "Favicon · 256 px", (256, 256)),
}


def brand_slot(slot: str):
    if slot not in BRAND_KIT_SLOTS:
        raise HTTPException(404, "Layout de logo não encontrado.")
    return BRAND_KIT_SLOTS[slot][0]


@app.get("/api/brand-kit")
def get_brand_kit():
    rows = db.select(
        "branding",
        fields="key,updated_at",
        params={"key": "in.(" + ",".join(s[0] for s in BRAND_KIT_SLOTS.values()) + ")"},
    )
    modified = {row["key"]: row.get("updated_at") for row in rows}
    return {
        slot: {
            "label": data[1],
            "width": data[2][0],
            "height": data[2][1],
            "configured": data[0] in modified,
            "updated_at": modified.get(data[0]),
        }
        for slot, data in BRAND_KIT_SLOTS.items()
    }


@app.get("/api/brand-kit/square-icon")
def get_square_brand_icon(prefer: str = "favicon"):
    """Fonte única para favicon e menu compacto; nunca distorce a marca."""
    if prefer not in ("favicon", "icon"):
        raise HTTPException(422, "Tipo de ícone inválido.")
    keys = ("axora_favicon", "axora_icon") if prefer == "favicon" else ("axora_icon", "axora_favicon")
    rows = db.select(
        "branding",
        fields="key,image_data_uri",
        params={"key": "in.(axora_favicon,axora_icon)"},
    )
    by_key = {r["key"]: r["image_data_uri"] for r in rows}
    for key in keys:
        if key not in by_key:
            continue
        try:
            icon_data = branding.render_square_icon(by_key[key])
            return Response(
                icon_data, media_type="image/png",
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )
        except HTTPException as error:
            if error.status_code != 422:
                raise
    # Fallback oficial, sem tentar reduzir a logo horizontal a um favicon.
    static_path = os.path.join(os.path.dirname(__file__), "static", "axora-mark.svg")
    return FileResponse(static_path, media_type="image/svg+xml")


@app.get("/api/brand-kit/{slot}/image")
def get_brand_kit_image(slot: str):
    key = brand_slot(slot)
    rows = db.select(
        "branding",
        fields="content_type,image_data_uri",
        params={"key": "eq." + key, "limit": 1},
    )
    if not rows:
        raise HTTPException(404, "A logo deste layout ainda não foi enviada.")
    return Response(
        branding.render_logo_image(rows[0]["image_data_uri"]),
        media_type=rows[0]["content_type"],
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.post("/api/brand-kit/{slot}")
async def update_brand_kit(slot: str, file: UploadFile = File(...), user=Depends(authorized)):
    admin(user)
    key = brand_slot(slot)
    raw = await file.read(branding.MAX_UPLOAD + 1)
    if slot in ("icon", "favicon"):
        branding.validate_square_upload(raw)
    mime, uri = branding.prepare_logo(raw, file.content_type or "")
    timestamp = datetime.now(timezone.utc).isoformat()
    db.call(
        "POST", db.TABLES["branding"],
        params={"on_conflict": "key"},
        data={"key": key, "content_type": mime, "image_data_uri": uri, "updated_at": timestamp},
        prefer="resolution=merge-duplicates,return=representation",
    )
    return {"ok": True, "updated_at": timestamp}


@app.delete("/api/brand-kit/{slot}")
def remove_brand_kit(slot: str, user=Depends(authorized)):
    admin(user)
    key = brand_slot(slot)
    db.call("DELETE", db.TABLES["branding"],
            params={"key": "eq." + key}, prefer="return=minimal")
    return {"ok": True}


@app.get("/api/multiuser/status")
def multiuser_status(user=Depends(auth)):
    return {
        "phase": "native_finance",
        "isolation_enabled": True,
        "legacy_shared_data": False,
        "workspace_id": user_workspace(user),
        "workspace_roles": ["owner", "admin", "editor", "viewer"],
        "next_step": "Compartilhamento entre usuarios e equipes somente com autorizacao explicita.",
    }


@app.get("/api/users")
def users(user=Depends(auth)):
    admin(user)
    return [{"id": x["id"], "display_name": x["display_name"], "is_admin": x["is_admin"], "is_active": x["is_active"]} for x in security.accounts()]


@app.post("/api/users")
def create_user(payload: UserCreate, user=Depends(authorized)):
    admin(user)
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
    return {"id": new_user["id"], "display_name": name, "financial_isolation": True}


# Não aceitar a antiga planilha de quatro abas: dados financeiros agora são nativos.
@app.post("/api/import/preview")
async def preview(user=Depends(authorized)):
    raise HTTPException(410, "Importação do Excel legado desativada. Use Provisões e Registros.")


@app.post("/api/import/commit")
async def import_commit(user=Depends(authorized)):
    raise HTTPException(410, "Importação do Excel legado desativada. Use Provisões e Registros.")


@app.get("/api/export")
def export_excel(user=Depends(auth)):
    scope = {"workspace_id": "eq." + user_workspace(user)}
    data = {kind: db.select(kind, order=ORDERS[kind], params=scope) for kind in DATA_KINDS}
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
