"""Carteira de dívidas AXORA: sem importação automática da planilha pessoal.

O acordo é uma única RPC transacional: só o principal, com vínculo único à
Provisão. Nenhum registro financeiro ou saldo bancário é criado na renegociação.
"""
from decimal import Decimal, InvalidOperation
from fastapi import Depends, HTTPException

from axora_v2 import db, family_service

_M = Decimal("1000000000000")


def _currency(value, field):
    if isinstance(value, bool):
        raise HTTPException(422, field + " inválido.")
    try:
        v = Decimal(str(value))
        if not v.is_finite() or v <= 0 or v > _M or v != v.quantize(Decimal("0.01")):
            raise InvalidOperation
        return str(v.quantize(Decimal("0.01")))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(422, field + " deve ser positivo e ter até duas casas decimais.") from None


def _text(value, field, max_len=120):
    if not isinstance(value, str) or not (1 <= len(value.strip()) <= max_len):
        raise HTTPException(422, field + " inválido.")
    return value.strip()


def _count(value, label, *, minimum=0, maximum=360):
    if type(value) is not int or not (minimum <= value <= maximum):
        raise HTTPException(422, label + " inválida.")
    return value


def clean_debt(payload):
    if not isinstance(payload, dict) or set(payload) != {"description","total_value","category","responsible"}:
        raise HTTPException(422, "Campos inválidos para a dívida.")
    return {
        "description": _text(payload["description"], "Descrição", 240),
        "total_value": _currency(payload["total_value"], "Valor original"),
        "category": _text(payload["category"], "Categoria"),
        "responsible": _text(payload["responsible"], "Responsável"),
    }


def clean_agreement(payload):
    required = {"total_installments", "paid_installments", "installment_value",
                "first_due_date", "category", "responsible", "profile_id"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise HTTPException(422, "Informe os termos do acordo.")
    total = _count(payload["total_installments"], "Quantidade de parcelas", minimum=1)
    paid = _count(payload["paid_installments"], "Quantidade paga")
    if paid >= total:
        raise HTTPException(422, "Informe ao menos uma parcela ainda em aberto.")
    from datetime import date
    try:
        due = date.fromisoformat(str(payload["first_due_date"])).isoformat()
    except (TypeError,ValueError):
        raise HTTPException(422, "Data do próximo vencimento inválida.") from None
    profile = payload["profile_id"]
    if profile is not None and (type(profile) is not int or profile < 1):
        raise HTTPException(422, "Responsável da família inválido.")
    return {
        "p_total_installments": total, "p_paid_installments": paid,
        "p_installment_value": _currency(payload["installment_value"], "Parcela"),
        "p_first_due_date": due,
        "p_category": _text(payload["category"], "Categoria"),
        "p_responsible": _text(payload["responsible"], "Responsável"),
        "p_profile_id": profile,
    }


def _principal(user):
    ctx = user.get("_family")
    if ctx:
        if ctx["role"] != "principal":
            raise HTTPException(403, "Somente o titular principal pode visualizar ou renegociar dívidas.")
    elif not user.get("is_admin"):
        raise HTTPException(403, "Gestão de dívidas exclusiva do titular.")
    return ctx


def _match_owner(user, payload):
    ctx = user.get("_family")
    if not ctx:
        if payload.get("profile_id") is not None:
            raise HTTPException(422, "O responsável familiar não está disponível.")
        return
    profiles = family_service.profiles(user)
    linked = next((p for p in profiles if p.get("active") and
                   int(p["id"]) == payload.get("profile_id")), None)
    if linked is None or linked["display_name"] != payload.get("responsible"):
        raise HTTPException(422, "Selecione um responsável cadastrado da família.")


def install(app, auth, authorized, user_workspace):
    @app.get("/api/debts/portfolio")
    def portfolio(user=Depends(auth)):
        _principal(user)
        workspace=user_workspace(user)
        rows=db.call("GET", "finance_debts", params={
            "select":"id,description,total_value,status,total_installments,"
                     "paid_installments,installment_value,open_value,category,"
                     "responsible,linked_provision_rule_id,renegotiated_at",
            "workspace_id":"eq."+workspace,"order":"id.asc","limit":1000})
        members=[{"id":int(p["id"]),"name":p["display_name"]}
                 for p in family_service.profiles(user) if p.get("active")] if user.get("_family") else []
        return {"items":rows,"members":members}

    @app.post("/api/debts/portfolio")
    def create(payload: dict, user=Depends(authorized)):
        _principal(user)
        values=clean_debt(payload)
        # Nada é marcado como pago e nenhuma Provisão é criada pelo cadastro.
        result=db.call("POST","finance_debts",data={
            **values,"workspace_id":user_workspace(user),
            "open_value":values["total_value"],
            "status":"NÃO RENEGOCIADO",
            "total_installments":0,"paid_installments":0,"installment_value":"0.00",
        },prefer="return=representation")
        return {"item":result[0] if result else None}

    @app.patch("/api/debts/portfolio/{debt_id}")
    def update(debt_id:int,payload:dict,user=Depends(authorized)):
        _principal(user)
        if debt_id<1:raise HTTPException(422,"Dívida inválida.")
        values=clean_debt(payload)
        rows=db.call("PATCH","finance_debts",params={
            "id":"eq."+str(debt_id),"workspace_id":"eq."+user_workspace(user),
            "linked_provision_rule_id":"is.null","status":"eq.NÃO RENEGOCIADO"
        },data={**values,"open_value":values["total_value"]},prefer="return=representation")
        if not rows:
            raise HTTPException(409,"Dívida já renegociada ou não encontrada.")
        return {"item":rows[0]}

    @app.post("/api/debts/portfolio/{debt_id}/renegotiate")
    def renegotiate(debt_id:int,payload:dict,user=Depends(authorized)):
        _principal(user)
        if debt_id<1:raise HTTPException(422,"Dívida inválida.")
        values=clean_agreement(payload)
        _match_owner(user,{**payload})
        workspace=user_workspace(user)
        # Verificação informativa; o bloqueio e a proteção anti-duplicação
        # definitivos ocorrem dentro da transação PostgreSQL da RPC.
        exists=db.call("GET","finance_debts",params={
            "select":"id,linked_provision_rule_id,status",
            "id":"eq."+str(debt_id),"workspace_id":"eq."+workspace,"limit":1})
        if not exists:
            raise HTTPException(404,"Dívida não encontrada.")
        if exists[0].get("linked_provision_rule_id") or exists[0].get("status")=="RENEGOCIADO":
            raise HTTPException(409,"Esta dívida já foi renegociada.")
        result=db.call("POST","rpc/axora_debt_renegotiate",data={
            "p_workspace_id":workspace,"p_actor_id":int(user["id"]),
            "p_debt_id":debt_id,**values})
        return {"ok":True,"agreement":result}
