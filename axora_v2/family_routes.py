"""Rotas do AXORA Familiar V2 — todas baseadas na sessão HTTP-only."""
from datetime import date
from decimal import Decimal
import re

from fastapi import Depends, HTTPException

from axora_v2 import db, family_service, family_policy, security


def _context(user):
    ctx = user.get("_family")
    if not ctx:
        raise HTTPException(503, "Configure a base familiar deste ambiente antes de utilizar o recurso.")
    return ctx


def _actor(user):
    ctx = _context(user)
    return ctx["user_id"]


def _profile_set(ctx):
    profiles = family_service.accessible_profiles({"_family": ctx})
    return profiles, {int(p["id"]) for p in profiles if p.get("active")}


def _allocations(value, costs, payments, classification, ctx):
    if not isinstance(costs, list):
        raise HTTPException(422, "Informe beneficiários e porcentagens do valor.")
    alloc = family_policy.split_percentages(value, costs)
    profiles, allowed = _profile_set(ctx)
    if any(int(c["profile_id"]) not in allowed for c in alloc):
        raise HTTPException(422, "Beneficiário inexistente nesta família.")
    if classification == "SAÍDA":
        paid = family_policy.validate_payment_sources(value, payments, allowed_profile_ids=allowed)
    else:
        if payments not in ([], None):
            raise HTTPException(422, "Receita não possui pagador de despesa.")
        paid = []
    return (
        [{"profile_id": a["profile_id"], "amount": a["amount"]} for a in alloc],
        [{"profile_id": a["profile_id"], "amount": a["amount"],
          "source_account_id": None} for a in paid]
    )


def _record_fields(data):
    if not isinstance(data, dict):
        raise HTTPException(422, "Informe os dados financeiros.")
    keys = {"date", "description", "value", "classification", "category", "label",
            "costs", "payments"}
    if set(data) != keys:
        raise HTTPException(422, "Campos inválidos para o registro familiar.")
    try:
        when = date.fromisoformat(str(data["date"])).isoformat()
    except (ValueError, TypeError):
        raise HTTPException(422, "Data inválida.") from None
    desc = data["description"]
    category = data["category"]
    if not isinstance(desc, str) or not 1 <= len(desc.strip()) <= 240:
        raise HTTPException(422, "Descrição obrigatória, até 240 caracteres.")
    if not isinstance(category, str) or len(category) > 120:
        raise HTTPException(422, "Categoria inválida.")
    if data["classification"] not in ("SAÍDA", "ENTRADA"):
        raise HTTPException(422, "Classificação inválida.")
    if data["label"] not in ("privado", "casal", "familia"):
        raise HTTPException(422, "Visibilidade inválida.")
    return when, desc.strip(), category.strip() or "OUTROS"


def _password_hash(password):
    """Senha recebida só no backend. O cliente nunca envia hash ou papel."""
    if password is None:
        return None
    if not isinstance(password, str) or len(password) < 12 or len(password) > 500:
        raise HTTPException(422, "A senha deve ter entre 12 e 500 caracteres.")
    existing = security.accounts()
    if len(existing) >= 250:
        raise HTTPException(422, "Limite de acessos atingido.")
    if any(security.matches(password, account.get("password_hash", ""))
           for account in existing):
        raise HTTPException(422, "Escolha outra senha de acesso.")
    return security.hash_password(password)


def _role(value):
    if not isinstance(value, str) or value not in ("conjuge", "filho", "outro"):
        raise HTTPException(422, "Selecione um vínculo de cônjuge, filho ou outro.")
    return value


def install(app, auth, authorized):
    @app.post("/api/family/onboard")
    def activate_my_family(user=Depends(authorized)):
        """Cria espaço familiar do próprio usuário sem tocar nos testes."""
        if not family_service.enabled():
            raise HTTPException(404, "Recurso familiar indisponível.")
        if user.get("_family"):
            raise HTTPException(409, "Sua família já está configurada.")
        uid=int(user["id"])
        workspace=db.call("POST", "rpc/axora_user_workspace", data={"p_user_id":uid})
        own=db.call("GET", "finance_workspaces", params={
            "select":"id,created_by,is_active","id":"eq."+str(workspace),"limit":1})
        if not own or int(own[0].get("created_by") or 0)!=uid or not own[0].get("is_active"):
            raise HTTPException(403, "O espaço financeiro não pertence à sua conta.")
        existing=db.call("GET", "finance_family_profiles", params={
            "select":"id,relationship,linked_user_id","workspace_id":"eq."+str(workspace),
            "limit":2})
        if existing:
            if len(existing)==1 and existing[0]["relationship"]=="principal" and existing[0].get("linked_user_id")==uid:
                return {"ok":True,"created":False}
            raise HTTPException(409, "Espaço já possui cadastro familiar.")
        db.call("POST", "finance_family_profiles", data={
            "workspace_id":str(workspace),"display_name":user["display_name"][:80],
            "relationship":"principal","linked_user_id":uid,"active":True
        }, prefer="return=representation")
        return {"ok":True,"created":True}

    @app.get("/api/family")
    def get_family(user=Depends(auth)):
        ctx = _context(user)
        result = {"enabled": True, "my_role": ctx["role"],
                  "my_profile_id": ctx["profile_id"],
                  "can_manage": ctx["role"] == "principal",
                  "profiles": family_service.accessible_profiles(user)}
        if ctx["role"] == "principal":
            workspace = db.call("GET", "finance_workspaces", params={
                "select":"name", "id":"eq."+ctx["workspace_id"], "limit":1})
            result["workspace_name"] = workspace[0]["name"] if workspace else "Meu espaço financeiro"
        return result

    @app.post("/api/family/profiles")
    def add_family_profile(payload: dict, user=Depends(authorized)):
        ctx = family_service.require_principal(user)
        if not isinstance(payload, dict) or set(payload) != {"display_name", "relationship"}:
            raise HTTPException(422, "Informe nome e vínculo familiar.")
        name, role = payload["display_name"], payload["relationship"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise HTTPException(422, "Nome inválido.")
        if role not in ("conjuge", "filho", "outro"):
            raise HTTPException(422, "Vínculo inválido.")
        current = family_service.profiles(user)
        if len(current) >= 50:
            raise HTTPException(422, "Limite de perfis familiares atingido.")
        if any(x["display_name"].casefold() == name.strip().casefold() for x in current):
            raise HTTPException(409, "Pessoa já cadastrada.")
        added = db.call("POST", "finance_family_profiles", data={
            "workspace_id": ctx["workspace_id"], "display_name": name.strip(),
            "relationship": role, "active": True}, prefer="return=representation")
        return {"profile": added[0]}

    @app.post("/api/family/members")
    def create_member(payload: dict, user=Depends(authorized)):
        """Principal cria perfil e, opcionalmente, login dentro do próprio workspace."""
        ctx = family_service.require_principal(user)
        if not isinstance(payload, dict) or set(payload) != {"display_name", "relationship", "password"}:
            raise HTTPException(422, "Cadastro de membro inválido.")
        name = payload["display_name"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise HTTPException(422, "Informe um nome de até 80 caracteres.")
        name = name.strip()
        role = _role(payload["relationship"])
        hashed = _password_hash(payload["password"])
        if hashed is not None and len(name) > 40:
            raise HTTPException(422, "Para criar um login, use um nome de até 40 caracteres.")
        return db.call("POST", "rpc/axora_family_upsert_member", data={
            "p_workspace_id": ctx["workspace_id"], "p_actor_id": ctx["user_id"],
            "p_display_name": name, "p_relationship": role,
            "p_password_hash": hashed, "p_profile_id": None
        })


    @app.post("/api/family/profiles/{profile_id}/enable-login")
    def enable_member_login(profile_id: int, payload: dict, user=Depends(authorized)):
        ctx = family_service.require_principal(user)
        if profile_id < 1 or not isinstance(payload, dict) or set(payload) != {"password"}:
            raise HTTPException(422, "Acesso inválido.")
        profile = family_service.table("finance_family_profiles", ctx["workspace_id"],
            fields="id,display_name,relationship,linked_user_id,active",
            filters={"id":"eq."+str(profile_id)},limit=1)
        if not profile or not profile[0]["active"] or profile[0]["relationship"]=="principal" or profile[0].get("linked_user_id"):
            raise HTTPException(404, "Perfil disponível para acesso não encontrado.")
        hash_value = _password_hash(payload["password"])
        if hash_value is None:
            raise HTTPException(422, "Informe a senha deste usuário.")
        return db.call("POST", "rpc/axora_family_upsert_member", data={
            "p_workspace_id": ctx["workspace_id"], "p_actor_id": ctx["user_id"],
            "p_display_name": profile[0]["display_name"], "p_relationship": profile[0]["relationship"],
            "p_password_hash": hash_value, "p_profile_id": profile_id
        })


    @app.post("/api/family/profiles/{profile_id}/relationship")
    def change_member_relationship(profile_id: int, payload: dict, user=Depends(authorized)):
        ctx = family_service.require_principal(user)
        if profile_id < 1 or not isinstance(payload, dict) or set(payload) != {"relationship"}:
            raise HTTPException(422, "Vínculo inválido.")
        return db.call("POST", "rpc/axora_family_change_relationship", data={
            "p_workspace_id": ctx["workspace_id"], "p_actor_id": ctx["user_id"],
            "p_profile_id": profile_id, "p_relationship": _role(payload["relationship"])
        })


    @app.post("/api/family/profiles/{profile_id}/link")
    def legacy_link_disabled(profile_id: int, user=Depends(authorized)):
        family_service.require_principal(user)
        raise HTTPException(410, "Vincular outra conta existente requer consentimento e migração assistida.")

    @app.post("/api/family/visibility")
    def set_visibility(payload: dict, user=Depends(authorized)):
        # A conta principal autoriza alterações em dados já existentes.
        ctx = family_service.require_principal(user)
        if not isinstance(payload, dict) or set(payload) != {"resource_type", "resource_id", "label", "viewers"}:
            raise HTTPException(422, "Visibilidade inválida.")
        kind, rid, label, viewers = (payload[x] for x in
            ("resource_type", "resource_id", "label", "viewers"))
        if kind not in family_policy.RESOURCE_KINDS or type(rid) is not int or rid < 1:
            raise HTTPException(422, "Recurso inválido.")
        if label not in family_policy.LABELS or not isinstance(viewers, list) or len(viewers)>50:
            raise HTTPException(422, "Rótulo ou lista inválida.")
        if any(type(v) is not int or v <= 0 for v in viewers) or len(set(viewers))!=len(viewers):
            raise HTTPException(422, "Permissões duplicadas ou inválidas.")
        if label == "selecionados" and not viewers:
            raise HTTPException(422, "Selecione as pessoas autorizadas.")
        if label != "selecionados" and viewers:
            raise HTTPException(422, "Use seleção apenas com rótulo Selecionados.")
        family_service.check_resource(ctx, kind, rid)
        return db.call("POST", "rpc/axora_family_set_visibility", data={
            "p_workspace_id": ctx["workspace_id"], "p_actor_id": ctx["user_id"],
            "p_resource_type": kind, "p_resource_id": rid,
            "p_label": label, "p_viewers": viewers})

    @app.post("/api/family/transactions")
    def create_financial_entry(payload: dict, user=Depends(authorized)):
        ctx = _context(user)
        if ctx["role"] not in ("principal","conjuge"):
            raise HTTPException(403, "Somente adultos autorizados podem registrar movimentações.")
        when, description, category = _record_fields(payload)
        value = payload["value"]
        family_policy.amount_cents(value)
        costs, payments = _allocations(value, payload["costs"], payload["payments"],
                                        payload["classification"], ctx)
        return db.call("POST", "rpc/axora_family_record", data={
            "p_workspace_id": ctx["workspace_id"], "p_actor_id": ctx["user_id"],
            "p_movement_date": when, "p_description": description,
            "p_value": str(value), "p_classification": payload["classification"],
            "p_category": category, "p_label": payload["label"],
            "p_costs": costs, "p_payments": payments})

    @app.post("/api/family/provisions/{occurrence_id}/pay")
    def pay_family_provision(occurrence_id: int, payload: dict, user=Depends(authorized)):
        ctx = _context(user)
        if ctx["role"] not in ("principal","conjuge"):
            raise HTTPException(403, "Este perfil não pode registrar pagamentos.")
        if occurrence_id <= 0 or not isinstance(payload, dict) or set(payload) != {
            "payment_date", "amount", "label", "costs", "payments"
        }:
            raise HTTPException(422, "Pagamento familiar inválido.")
        try:
            payment_date = date.fromisoformat(str(payload["payment_date"])).isoformat()
        except (ValueError, TypeError):
            raise HTTPException(422, "Data inválida.") from None
        family_policy.amount_cents(payload["amount"])
        if payload["label"] not in ("privado", "casal", "familia"):
            raise HTTPException(422, "Visibilidade inválida.")
        existing = family_service.table("finance_provision_occurrences",ctx["workspace_id"],
            filters={"id": "eq." + str(occurrence_id), "status": "eq.open"},
            fields="id,rule_id",limit=1)
        if not existing:
            raise HTTPException(404, "Provisão pendente não encontrada.")
        family_service.assert_visible(user, "provisao", existing[0]["rule_id"])
        costs, payments = _allocations(payload["amount"], payload["costs"],
                                        payload["payments"], "SAÍDA", ctx)
        return db.call("POST", "rpc/axora_family_pay_provision", data={
            "p_workspace_id": ctx["workspace_id"], "p_actor_id": ctx["user_id"],
            "p_occurrence_id": occurrence_id, "p_payment_date": payment_date,
            "p_amount": str(payload["amount"]), "p_label": payload["label"],
            "p_costs": costs, "p_payments": payments})

    @app.get("/api/family/summary")
    def family_summary(user=Depends(auth)):
        ctx = _context(user)
        profiles = family_service.accessible_profiles(user)
        ledger = family_service.all_rows("finance_movements",ctx["workspace_id"],
            fields="id,value,classification,movement_date",order="id.asc")
        ledger = family_service.filter_rows(user, "registro", ledger)
        movement_ids = [int(row["id"]) for row in ledger]
        people = {int(p["id"]): {"id": int(p["id"]), "name": p["display_name"],
            "role": p["relationship"], "entradas": Decimal("0"),
            "despesas": Decimal("0"), "pagamentos": Decimal("0")} for p in profiles}
        costs, payments = [], []
        for start in range(0, len(movement_ids), 200):
            ids = movement_ids[start:start + 200]
            query = {"movement_id": "in.(" + ",".join(map(str,ids)) + ")"}
            costs.extend(family_service.table("finance_family_cost_allocations",
                ctx["workspace_id"], filters=query, limit=1000))
            payments.extend(family_service.table("finance_family_payment_allocations",
                ctx["workspace_id"], filters=query, limit=1000))
        movement_by_id = {int(item["id"]): item for item in ledger}
        for row in costs:
            person = people.get(int(row["profile_id"]))
            movement = movement_by_id.get(int(row["movement_id"]))
            if person is None or movement is None:
                continue
            key = "entradas" if movement["classification"] == "ENTRADA" else "despesas"
            person[key] += Decimal(str(row["amount"]))
        for row in payments:
            person = people.get(int(row["payer_profile_id"]))
            if person is not None:
                person["pagamentos"] += Decimal(str(row["amount"]))
        assigned = {int(x["movement_id"]) for x in costs}
        result = []
        for person in people.values():
            result.append({**{k:v for k,v in person.items() if k not in
                {"entradas","despesas","pagamentos"}},
                "entradas":str(person["entradas"].quantize(Decimal(".01"))),
                "despesas":str(person["despesas"].quantize(Decimal(".01"))),
                "pagamentos":str(person["pagamentos"].quantize(Decimal(".01"))),
                "saldo":str((person["entradas"]-person["despesas"]).quantize(Decimal(".01")))})
        response = {"people": result}
        if ctx["role"] == "principal":
            response["unallocated_movements"] = sum(
                int(r["id"]) not in assigned for r in ledger)
        return response
