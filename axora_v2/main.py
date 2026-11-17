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

from axora_v2 import db, metrics, security, branding, provisions, catalogs, banking, meu_pluggy, meu_pluggy_sync, pix_payments, family_service, family_policy, family_routes
from services.importer import parse_excel
from services.profile import clean_display_name, avatar_data_uri

@asynccontextmanager
async def lifespan(_app):
    if not db.configured():
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_KEY antes de iniciar o AXORA.")
    security.signer()
    # O ambiente de homologação precisa falhar fechado: jamais acessar public
    # por engano e validar a REST API de todas as tabelas antes de ficar Live.
    if os.environ.get("AXORA_ENV", "").lower() == "beta":
        if db.selected_schema() != "axora_beta":
            raise RuntimeError("AXORA BETA exige SUPABASE_DB_SCHEMA=axora_beta.")
        if not banking.manual_mode():
            raise RuntimeError("AXORA BETA exige integração bancária manual.")
        db.verify()
    task = asyncio.create_task(meu_pluggy_sync.periodic_sync()) if meu_pluggy.configured() and not banking.manual_mode() else None
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
    user = security.current(request)
    user["_family"] = family_service.context(user)
    family_service.gate(user, request.method, request.url.path)
    return user


def authorized(request: Request, user=Depends(auth)):
    security.require_csrf(request, user)
    return user


def admin(user):
    if not user.get("is_admin"):
        raise HTTPException(403, "Esta ação exige permissão de administrador.")


def user_workspace(user):
    """Workspace derivado exclusivamente de sessão e perfil familiar autorizado."""
    shared_workspace = family_service.family_workspace(user)
    if shared_workspace is not None:
        return shared_workspace
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
    ctx = user.get("_family")
    return {"id": user["id"], "display_name": user["display_name"], "is_admin": user["is_admin"],
            "family_enabled": bool(ctx), "family_role": ctx["role"] if ctx else None,
            "family_available": family_service.enabled(),
            "avatar_data_uri": avatar_rows[0].get("avatar_data_uri") if avatar_rows else None, "csrf": user["csrf"]}


@app.post("/api/logout")
def logout(response: Response, user=Depends(authorized)):
    security.clear_session(response)
    return {"ok": True}


@app.get("/api/snapshot")
def snapshot(user=Depends(auth)):
    workspace = user_workspace(user)
    scope = {"workspace_id": "eq." + workspace}
    ctx = user.get("_family")
    restricted = bool(ctx and ctx["role"] != "principal")
    if restricted:
        # Nunca buscar contas, dívidas, configurações e agregados do principal.
        rows = {
            "movements": family_service.tagged_records(
                user, "registro", family_service.all_rows(
                    "finance_movements", workspace, order=ORDERS["movements"])),
            "accounts": [],
            "debts": [],
        }
        provision_totals = family_service.provision_overview(list_provisions(user)["items"])
        settings = {}
    else:
        rows = {kind: db.select(kind, order=ORDERS[kind], params=scope)
                for kind in ("movements", "accounts", "debts")}
        if ctx:
            rows["movements"] = family_service.all_rows(
                "finance_movements", workspace, order=ORDERS["movements"])
            rows["movements"] = family_service.tagged_records(
                user, "registro", rows["movements"])
        db.call("POST", "rpc/axora_ensure_provisions", data={"p_workspace_id": workspace})
        provision_totals = db.call("POST", "rpc/axora_provision_overview",
                                   data={"p_workspace_id": workspace})
        settings = db.get_settings(workspace)
    rows["forecasts"] = []
    summary = metrics.compute(rows["movements"], [], rows["accounts"], rows["debts"],
                              settings, provision_overview=provision_totals)
    if restricted:
        # Não incluir placeholders de patrimônio, conciliação, dívidas ou metas
        # na resposta: não fazem parte da experiência deste usuário.
        fields = ("receipts", "expenses", "realized", "to_pay", "pending_count",
                  "monthly", "categories", "next_forecasts")
        summary = {key: summary[key] for key in fields}
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


def finance_provision_options(workspace, values):
    """Aceita titulares do cadastro único sem duplicar responsáveis legados.

    Usa primeiro os catálogos históricos. Busca titulares deste workspace
    somente quando o nome escolhido não está no catálogo, mantendo a
    compatibilidade e evitando uma consulta adicional desnecessária.
    """
    options = finance_catalog_items(workspace)
    selected = str(values.get("p_responsible", "")).strip().casefold()
    if any(entry.get("kind") == "responsible" and entry.get("active")
           and str(entry.get("name", "")).casefold() == selected
           for entry in options):
        return options
    holders = db.call("GET", "finance_bank_holders", params={
        "workspace_id": "eq." + workspace,
        "select": "name",
        "order": "name.asc",
        "limit": 500,
    })
    seen = {str(entry.get("name", "")).casefold() for entry in options
            if entry.get("kind") == "responsible" and entry.get("active")}
    for holder in holders:
        name = str(holder.get("name") or "").strip()
        if name and name.casefold() not in seen:
            options.append({"kind": "responsible", "name": name, "active": True})
            seen.add(name.casefold())
    return options


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
            "select": "id,rule_id,sequence_no,due_date,planned_value,status,description_override,category_override,responsible_override,value_mode_override,rule:finance_provision_rules(description,category,responsible,value_mode,recurrence,frequency,planned_value,last_paid_value,last_paid_at,end_date,installment_count,payment_url,payment_method,pix_kind,pix_value,pix_receiver_name,pix_receiver_city)",
            "workspace_id": "eq." + workspace,
            "status": "eq.open", "order": "due_date.asc,id.asc",
            "limit": page_size, "offset": len(items),
        })
        items.extend(rows)
        if len(rows) < page_size:
            break
        if len(items) >= 10000:
            raise HTTPException(503, "Muitas provisões abertas. Use filtros por período.")
    ctx = user.get("_family")
    if ctx:
        if ctx["role"] != "principal":
            items = family_service.filter_rows(user, "provisao", items, id_key="rule_id")
        tags = family_service.visibility_map(ctx, "provisao", [x["rule_id"] for x in items])
        if ctx["role"] == "principal":
            items = [{**x, "visibility_label": tags.get(int(x["rule_id"]), {}).get("label", "privado")} for x in items]
    return {"items": items}


@app.post("/api/provisions")
def add_provision(payload: dict, user=Depends(authorized)):
    workspace = user_workspace(user)
    values = provisions.clean_provision(payload)
    catalogs.canonicalize_provision(values, finance_provision_options(workspace, values))
    values["p_workspace_id"] = workspace
    endpoint = ("rpc/axora_create_provision_with_method" if "p_payment_method" in values
                else ("rpc/axora_create_provision_with_link" if "p_payment_url" in values
                      else "rpc/axora_create_provision"))
    new_id = db.call("POST", endpoint, data=values)
    return {"id": new_id, "ok": True}


@app.patch("/api/provisions/{pk}")
def edit_provision(pk: int, payload: dict, user=Depends(authorized)):
    positive_id(pk)
    workspace = user_workspace(user)
    values = provisions.clean_edit_provision(payload)
    catalogs.canonicalize_provision(values, finance_provision_options(workspace, values))
    endpoint = ("rpc/axora_edit_provision_with_method" if "p_payment_method" in values
                else ("rpc/axora_edit_provision_with_link" if "p_payment_url" in values
                      else "rpc/axora_edit_provision"))
    return db.call("POST", endpoint,
                   data={"p_workspace_id": workspace, "p_occurrence_id": pk, **values})


@app.get("/api/provisions/{pk}/pix")
def provision_pix_qr(pk: int, response: Response, user=Depends(auth)):
    """Renderiza o QR Code localmente; nunca envia chave nem copia-e-cola a terceiros."""
    response.headers["Cache-Control"]="private, no-store"
    positive_id(pk)
    workspace = user_workspace(user)
    records=db.call("GET","finance_provision_occurrences",params={
        "workspace_id":"eq."+workspace,"id":"eq."+str(pk),
        "status":"eq.open","limit":1,
        "select":"id,rule_id,rule:finance_provision_rules(description,payment_method,pix_kind,pix_value,pix_receiver_name,pix_receiver_city)"
    })
    if not records or not records[0].get("rule"):
        raise HTTPException(404,"Previsão não encontrada ou já quitada.")
    if user.get("_family") and user["_family"]["role"] != "principal":
        family_service.assert_visible(user, "provisao", records[0].get("rule_id") or 0)
    rule=records[0]["rule"]
    if rule.get("payment_method")!="pix" or not rule.get("pix_value"):
        raise HTTPException(409,"Esta previsão não possui Pix configurado.")
    qr=pix_payments.pix_qr(rule["pix_kind"],rule["pix_value"],
        rule.get("pix_receiver_name"),rule.get("pix_receiver_city"))
    return {**qr,"description":rule.get("description") or "",
            "receiver":rule.get("pix_receiver_name") or None,
            "notice":("Confira o beneficiário e o valor no aplicativo do banco antes de confirmar. "
                      "Este QR Code não registra nem confirma pagamento.")}


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


@app.get("/api/provisions/{pk}/matches")
def provision_payment_matches(pk: int, payment_date: str, amount: float, user=Depends(auth)):
    """Somente sugere transações já importadas e Registros já existentes."""
    positive_id(pk)
    workspace = user_workspace(user)
    checked = provisions.clean_payment({"payment_date": payment_date, "amount": amount})
    rows = db.call("GET", "finance_provision_occurrences", params={
        "workspace_id": "eq." + workspace, "id": "eq." + str(pk),
        "status": "eq.open", "limit": 1,
        "select": "id,planned_value,description_override,rule:finance_provision_rules(description)",
    })
    if not rows:
        raise HTTPException(404, "Previsão em aberto não localizada.")
    item = rows[0]
    reference = item.get("description_override") or (item.get("rule") or {}).get("description", "")
    if abs(float(item["planned_value"]) - checked["p_amount"]) > 0.01:
        return {"items": [], "message": "O valor difere da previsão. Revise antes de conciliar."}

    bank = db.call("GET", "finance_bank_transactions", params={
        "workspace_id": "eq." + workspace, "status": "eq.pending",
        "amount": "lt.0", "order": "posted_on.desc,id.desc", "limit": 800,
        "select": "id,account_id,description,posted_on,amount,status",
    })
    movements = db.select("movements", order="movement_date.desc,id.desc", params={
        "workspace_id": "eq." + workspace, "limit": 800,
    })
    learned = db.call("GET", "finance_reconciliation_learning", params={
        "workspace_id": "eq." + workspace, "active": "eq.true",
        "select": "source_description,target_description",
        "order": "updated_at.desc,id.desc", "limit": 1000,
    })
    items = provisions.payment_matches(
        {"description": reference},
        checked["p_payment_date"], checked["p_amount"], bank, movements, learned)
    accounts = db.call("GET", "finance_bank_accounts", params={
        "workspace_id": "eq." + workspace, "limit": 500,
        "select": "id,bank_name,nickname,holder:finance_bank_holders(name)",
    })
    account_names = {
        int(a["id"]): " · ".join(filter(None, [
            a.get("bank_name"), a.get("nickname"),
            (a.get("holder") or {}).get("name"),
        ])) for a in accounts
    }
    for candidate in items:
        if candidate["kind"] == "bank":
            candidate["account_label"] = account_names.get(candidate["account_id"], "Conta bancária")
    return {"items": items, "message": "Sugestões exigem confirmação. Nenhum registro foi criado."}


@app.post("/api/provisions/{pk}/match")
def provision_confirm_match(pk: int, payload: dict, user=Depends(authorized)):
    """Um único vínculo por operação, resolvido em transação SQL atômica."""
    positive_id(pk)
    values = provisions.clean_match(payload)
    workspace = user_workspace(user)
    if values["kind"] == "bank":
        return db.call("POST", "rpc/axora_confirm_reconciliation", data={
            "p_workspace_id": workspace, "p_user_id": int(user["id"]),
            "p_transaction_id": values["source_id"],
            "p_action": "matched_provision", "p_target_id": pk,
            "p_counterpart_id": None, "p_category": None, "p_reason": None,
        })
    return db.call("POST", "rpc/axora_link_record_to_provision", data={
        "p_workspace_id": workspace, "p_user_id": int(user["id"]),
        "p_occurrence_id": pk, "p_movement_id": values["source_id"],
    })


# Banco manual e Central de Conciliação: nenhuma integração Open Finance ativa.
def banking_rows(workspace, name, *, filters=None, select="*", order=None, limit=500):
    params={"select":select,"workspace_id":"eq."+workspace,"limit":limit}
    if filters: params.update(filters)
    if order:params["order"]=order
    return db.call("GET",name,params=params)


def require_bank_principal(user):
    """Secondary profiles cannot access balance mutations, types or transfer history."""
    ctx = user.get("_family")
    if ctx and ctx["role"] != "principal":
        raise HTTPException(403, "Somente a conta principal gerencia saldos e tipos.")


def bank_types(workspace):
    db.call("POST", "rpc/axora_ensure_bank_account_types",
            data={"p_workspace_id": workspace})
    return banking_rows(workspace, "finance_bank_account_types",
                        order="label.asc", limit=150)


def validate_bank_type(workspace, code, *, existing=None):
    # Default codes remain valid for legacy installations; custom types must
    # be registered and ACTIVE in the current workspace.
    if code in {"corrente", "poupanca", "pagamento", "outro"}:
        return
    if existing is not None and code == existing:
        return
    types = banking_rows(workspace, "finance_bank_account_types",
                         filters={"code": "eq." + code, "active": "eq.true"}, limit=1)
    if not types:
        raise HTTPException(422, "Tipo de conta não cadastrado ou inativo neste espaço.")


@app.get("/api/banking/account-types")
def banking_account_types(user=Depends(auth)):
    require_bank_principal(user)
    return {"items": bank_types(user_workspace(user))}


@app.post("/api/banking/account-types")
def banking_add_type(payload: dict, user=Depends(authorized)):
    require_bank_principal(user)
    workspace = user_workspace(user)
    details = banking.clean_account_type(payload)
    rows = bank_types(workspace)
    if any(r["label"].casefold() == details["label"].casefold() for r in rows):
        raise HTTPException(409, "Já existe um tipo com esse nome.")
    from uuid import uuid4
    code = "custom_" + uuid4().hex
    created = db.call("POST", "finance_bank_account_types",
        data={"workspace_id": workspace, "code": code, **details},
        prefer="return=representation")
    return {"item": created[0]}


@app.patch("/api/banking/account-types/{pk}")
def banking_edit_type(pk: int, payload: dict, user=Depends(authorized)):
    require_bank_principal(user)
    banking.positive_id(pk)
    workspace = user_workspace(user)
    details = banking.clean_account_type(payload, editing=True)
    rows = bank_types(workspace)
    selected = next((r for r in rows if int(r["id"]) == pk), None)
    if not selected:
        raise HTTPException(404, "Tipo não encontrado.")
    if any(int(r["id"]) != pk and r["label"].casefold() == details["label"].casefold()
           for r in rows):
        raise HTTPException(409, "Já existe um tipo com esse nome.")
    updated = db.call("PATCH", "finance_bank_account_types",
        params={"id": "eq." + str(pk), "workspace_id": "eq." + workspace},
        data=details, prefer="return=representation")
    return {"item": updated[0]}


@app.get("/api/banking")
def banking_overview(user=Depends(auth)):
    workspace = user_workspace(user)
    ctx = user.get("_family")
    restricted = bool(ctx and ctx["role"] != "principal")
    accounts = banking_rows(workspace, "finance_bank_accounts", order="nickname.asc")
    manual = banking.manual_mode()
    if restricted:
        # Pegar apenas contas rotuladas para este perfil. Nunca devolver
        # vínculos Pluggy, identificadores de terceiros, flags de integração
        # ou transações que não integram a página deste usuário.
        accounts = family_service.filter_rows(user, "conta", accounts)
        holder_ids = {int(a["holder_id"]) for a in accounts}
        holders = banking_rows(workspace, "finance_bank_holders", order="name.asc") if holder_ids else []
        holders = [
            {"id": h["id"], "name": h["name"], "relationship": h["relationship"]}
            for h in holders if int(h["id"]) in holder_ids
        ]
        accounts = [
            {"id": a["id"], "holder_id": a["holder_id"],
             "bank_name": a["bank_name"], "nickname": a["nickname"],
             "account_type": a.get("account_type") or "conta",
             "manual_balance": a.get("manual_balance"),
             "investment_balance": a.get("investment_balance")}
            for a in accounts
        ]
        return {
            "holders": holders, "accounts": accounts, "pending": [],
            "balances": banking.balance_overview(holders, accounts, manual_only=True),
            "mode": "manual",
        }

    holders = banking_rows(workspace, "finance_bank_holders", order="name.asc")
    transactions = banking_rows(workspace, "finance_bank_transactions",
        filters={"status": "eq.pending"}, order="posted_on.desc,id.desc", limit=500)
    if ctx:
        accounts = family_service.tagged_records(user, "conta", accounts)
    is_owner = not manual and meu_pluggy.configured() and int(user["id"]) == meu_pluggy.owner_id()
    return {
        "holders": holders, "accounts": accounts, "pending": transactions,
        "balances": banking.balance_overview(holders, accounts, manual_only=manual),
        "mode": "manual" if manual else ("read_only" if is_owner else "manual"),
        "bank_connected": any(a.get("pluggy_account_id") for a in accounts),
        "provider": {"configured": bool(is_owner),
                     "type": "meu_pluggy_personal" if is_owner else "none",
                     "paused": manual, "read_only": True},
    }


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
    validate_bank_type(workspace, cleaned["account_type"])
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
    validate_bank_type(workspace, details["account_type"], existing=original[0]["account_type"])
    transactions=banking_rows(workspace,"finance_bank_transactions",
        filters={"account_id":"eq."+str(account_id)},select="id",limit=1)
    if (transactions or original[0].get("pluggy_account_id")) and any(
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


@app.patch("/api/banking/accounts/{account_id}/balance")
def banking_update_manual_balance(account_id: int, payload: dict, user=Depends(authorized)):
    """Atualiza só o saldo informado de conta manual, preservando extrato e saldos Pluggy."""
    account_id=banking.positive_id(account_id)
    value=banking.clean_manual_balance(payload)
    workspace=user_workspace(user)
    current=banking_rows(workspace,"finance_bank_accounts",
                         filters={"id":"eq."+str(account_id)},limit=1)
    if not current:
        raise HTTPException(404,"Conta não encontrada neste espaço.")
    manual = banking.manual_mode()
    if (current[0].get("pluggy_account_id") or current[0].get("pluggy_item_id")) and not manual:
        raise HTTPException(409,"Esta conta está conectada ao banco. Seu saldo é atualizado pela integração.")
    filters={"id":"eq."+str(account_id),"workspace_id":"eq."+workspace}
    if not manual:
        filters.update({"pluggy_account_id":"is.null","pluggy_item_id":"is.null"})
    # Em modo manual, mantém o vínculo histórico e altera SOMENTE o saldo informado.
    updated=db.call("PATCH","finance_bank_accounts",
        params=filters, data={"manual_balance":value},prefer="return=representation")
    if not updated:
        raise HTTPException(409,"Conta modificada por outra sessão. Recarregue e tente novamente.")
    return {"item":updated[0], "source":"manual"}


@app.patch("/api/banking/accounts/{account_id}/investments")
def banking_update_investments(account_id: int, payload: dict, user=Depends(authorized)):
    require_bank_principal(user)
    account_id = banking.positive_id(account_id)
    amount = banking.clean_investment_balance(payload)
    workspace = user_workspace(user)
    current = banking_rows(workspace, "finance_bank_accounts",
        filters={"id": "eq." + str(account_id)}, limit=1)
    if not current:
        raise HTTPException(404, "Conta não encontrada.")
    updated = db.call("PATCH", "finance_bank_accounts",
        params={"id": "eq." + str(account_id), "workspace_id": "eq." + workspace},
        data={"investment_balance": amount}, prefer="return=representation")
    if not updated:
        raise HTTPException(409, "Conta alterada por outra sessão.")
    return {"item": updated[0]}


@app.post("/api/banking/transfers")
def banking_transfer_manual(payload: dict, user=Depends(authorized)):
    require_bank_principal(user)
    values = banking.clean_transfer(payload)
    workspace = user_workspace(user)
    from_id, to_id = values["p_from_account_id"], values["p_to_account_id"]
    accounts = banking_rows(workspace, "finance_bank_accounts",
        filters={"id": "in.(" + str(from_id) + "," + str(to_id) + ")"}, limit=2)
    if len(accounts) != 2:
        raise HTTPException(404, "Origem ou destino não encontrado neste espaço.")
    if not banking.manual_mode() and any(
        a.get("pluggy_account_id") or a.get("pluggy_item_id") for a in accounts):
        raise HTTPException(409, "Transferências manuais estão disponíveis apenas entre contas manuais.")
    # Uma RPC transacional bloqueia ambas as contas, evita saldos inconsistentes
    # e registra uma única transferência com chave idempotente.
    result = db.call("POST", "rpc/axora_transfer_manual_balance", data={
        "p_workspace_id": workspace, "p_actor_user_id": int(user["id"]), **values
    })
    return {"transfer": result, "ok": True}


@app.get("/api/banking/transfers")
def banking_transfer_history(user=Depends(auth)):
    require_bank_principal(user)
    workspace = user_workspace(user)
    records = banking_rows(workspace, "finance_balance_transfers",
        select="id,from_account_id,to_account_id,amount,note,created_at",
        order="created_at.desc,id.desc", limit=25)
    return {"items": records}


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
    transfers=banking_rows(workspace,"finance_balance_transfers",
        filters={"or":"(from_account_id.eq."+str(account_id)+",to_account_id.eq."+str(account_id)+")"},
        select="id",limit=1)
    if transfers:
        raise HTTPException(409,"Esta conta possui transferências internas; a exclusão está bloqueada para preservar o histórico.")
    account=banking_rows(workspace,"finance_bank_accounts",filters={"id":"eq."+str(account_id)},limit=1)
    if account and account[0].get("pluggy_account_id"):
        raise HTTPException(409,"Conta conectada ao MeuPluggy. Desvincule-a antes de excluir.")
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
    if banking.manual_mode():
        raise HTTPException(410, "Integração bancária pausada. Atualize os saldos manualmente.")
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
    holder=banking_rows(workspace,"finance_bank_holders",
                        filters={"id":"eq."+str(own[0]["holder_id"])},limit=1)
    if not holder or holder[0].get("relationship")!="proprio":
        raise HTTPException(403,"O MeuPluggy pessoal só pode ser vinculado à própria conta.")
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
    history_patterns=banking_rows(workspace,"finance_reconciliation_learning",
       filters={"active":"eq.true"},
       select="source_description,target_description",
       order="updated_at.desc,id.desc",limit=3000)
    return {"transaction_id":transaction_id,
            "candidates":banking.suggestions(
                transaction,movements,provision_rows,occupied,history_patterns)}


@app.get("/api/banking/history")
def banking_history(user=Depends(auth)):
    workspace=user_workspace(user)
    rows=banking_rows(workspace,"finance_reconciliation_events",
      select="id,transaction_id,actor_id,action,movement_id,provision_occurrence_id,counterpart_id,notes,created_at",
      order="created_at.desc,id.desc",limit=100)
    # Somente a decisão ativa mais recente pode ser revertida.
    active=banking_rows(workspace,"finance_bank_transactions",
       filters={"status":"neq.pending"},
       select="id,status,description,amount,posted_on",
       order="decided_at.desc,id.desc",limit=1000)
    active_by_id={int(item["id"]):item for item in active}
    seen=set()
    for event in rows:
        txid=int(event["transaction_id"])
        tx=active_by_id.get(txid)
        event["bank_description"]=tx["description"] if tx else ""
        event["can_undo"]=bool(
            tx and txid not in seen
            and tx["status"]==event["action"]
            and event["action"] in banking.UNDOABLE_ACTIONS
        )
        seen.add(txid)
    return {"items":rows}


@app.post("/api/banking/reconcile/undo")
def banking_undo(payload:dict,user=Depends(authorized)):
    workspace=user_workspace(user)
    data=banking.clean_undo(payload)
    return db.call("POST","rpc/axora_undo_reconciliation",
       data={"p_workspace_id":workspace,"p_user_id":int(user["id"]),**data})


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


@app.post("/api/profile/password")
def change_password(payload: dict, response: Response, user=Depends(authorized)):
    """Troca protegida por sessão e CSRF; invalida outras sessões ativas."""
    if not isinstance(payload, dict) or set(payload) != {"current_password", "new_password"}:
        raise HTTPException(422, "Informe sua senha atual e a nova senha.")
    current, new = payload["current_password"], payload["new_password"]
    if not isinstance(current, str) or not isinstance(new, str):
        raise HTTPException(422, "Senha inválida.")
    if not (12 <= len(new) <= 500):
        raise HTTPException(422, "A senha deve ter entre 12 e 500 caracteres.")
    previous = db.select("users", fields="password_hash",
                         params={"id": "eq." + str(user["id"]), "limit": 1})
    if not previous:
        raise HTTPException(401, "Sessão inválida.")
    security.verify_current_password(int(user["id"]), current, previous[0]["password_hash"])
    if security.matches(new, previous[0]["password_hash"]):
        raise HTTPException(422, "Escolha uma senha diferente da anterior.")
    # No login atual a senha identifica o usuário, portanto deve ser única.
    if any(security.matches(new, x["password_hash"]) for x in security.accounts()
           if int(x["id"]) != int(user["id"])):
        raise HTTPException(422, "Escolha outra senha.")
    db.update("users", user["id"], {"password_hash": security.hash_password(new)})
    security.clear_session(response)
    return {"ok": True, "reauthenticate": True}


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
    try:
        rows = db.select(
            "branding",
            fields="key,image_data_uri",
            params={"key": "in.(axora_favicon,axora_icon)"},
        )
    except HTTPException as error:
        # O ícone do navegador deve funcionar mesmo quando o banco estiver indisponível.
        # A falha de conectividade não substitui a marca AXORA por um ícone genérico.
        if error.status_code not in (502, 503, 504):
            raise
        rows = []
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
    ctx = user.get("_family")
    return {
        "phase": "family_v2" if ctx else "native_finance",
        "isolation_enabled": True,
        "legacy_shared_data": False,
        "workspace_id": user_workspace(user),
        "workspace_roles": ["principal", "conjuge", "filho", "outro"] if ctx else ["owner", "admin", "editor", "viewer"],
        "next_step": "Compartilhamento individual exige rótulos explícitos." if ctx else "Compartilhamento familiar ainda não ativado.",
    }


@app.get("/api/users")
def users(user=Depends(auth)):
    ctx = user.get("_family")
    if ctx:
        family_service.require_principal(user)
        # Não devolver a lista global de contas ao principal de uma família.
        return [
            {"id": p["linked_user_id"], "display_name": p["display_name"],
             "is_admin": p["relationship"] == "principal", "is_active": p["active"]}
            for p in family_service.profiles(user) if p.get("linked_user_id")
        ]
    admin(user)
    return [
        {"id": x["id"], "display_name": x["display_name"],
         "is_admin": x["is_admin"], "is_active": x["is_active"]}
        for x in security.accounts()
    ]


@app.post("/api/users")
def create_user(payload: UserCreate, user=Depends(authorized)):
    # Administrador de um núcleo não cria outros usuários principais globais.
    if user.get("_family"):
        raise HTTPException(403, "Cadastre pessoas na seção Família e usuários.")
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


@app.get("/service-worker.js", include_in_schema=False)
def pwa_service_worker():
    """Service worker sem cache de respostas financeiras, autenticação ou páginas."""
    return FileResponse(
        os.path.join(ASSETS, "pwa", "service-worker.js"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-store", "Service-Worker-Allowed": "/"},
    )


# As rotas familiares são inertes sem AXORA_FAMILY_V2_ENABLED=1.
# Nenhuma versão deve ativá-las antes da migração e homologação de permissões.
family_routes.install(app, auth, authorized)
