"""Rotas do AXORA Familiar V2 — todas baseadas na sessão HTTP-only."""
from datetime import date
from decimal import Decimal
import re

from fastapi import Depends, HTTPException

from axora_v2 import db, family_service, family_policy


def _context(user):
    ctx = user.get("_family")
    if not ctx:
        raise HTTPException(503, "Configure a base familiar deste ambiente antes de utilizar o recurso.")
    return ctx


def _actor(user):
    ctx = _context(user)
    return ctx["user_id"]


def _profile_set(ctx):
    profiles = family_service.profiles({"_family": ctx})
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


def install(app, auth, authorized):
    @app.get("/api/family")
    def get_family(user=Depends(auth)):
        ctx = _context(user)
        return {"enabled": True, "my_role": ctx["role"],
                "my_profile_id": ctx["profile_id"],
                "can_manage": ctx["role"] == "principal",
                "profiles": family_service.profiles(user)}

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

    @app.post("/api/family/profiles/{profile_id}/link")
    def link_existing_login(profile_id: int, payload: dict, user=Depends(authorized)):
        ctx = family_service.require_principal(user)
        if profile_id <= 0 or not isinstance(payload, dict) or set(payload) != {"user_id"}:
            raise HTTPException(422, "Identificador inválido.")
        uid = payload["user_id"]
        if type(uid) is not int or uid <= 0 or uid == ctx["owner_id"]:
            raise HTTPException(422, "Usuário inválido para vinculação.")
        current = family_service.table("finance_family_profiles", ctx["workspace_id"],
            filters={"id": "eq." + str(profile_id)}, limit=1)
        if not current or current[0].get("linked_user_id") is not None:
            raise HTTPException(409, "Perfil ausente ou já vinculado.")
        existing = db.select("users", fields="id,is_active,is_admin",
            params={"id": "eq." + str(uid), "limit": 1})
        if not existing or not existing[0]["is_active"] or existing[0]["is_admin"]:
            raise HTTPException(422, "Usuário precisa estar ativo e não ser administrador.")
        linked = db.call("GET", "finance_family_profiles", params={
            "linked_user_id": "eq." + str(uid), "select": "id", "limit": 1})
        if linked:
            raise HTTPException(409, "Usuário já vinculado a outra família.")
        previous = db.call("GET", "finance_workspace_members", params={
            "user_id": "eq." + str(uid), "select": "workspace_id", "limit": 30})
        if any(p["workspace_id"] != ctx["workspace_id"] for p in previous):
            raise HTTPException(409, "Este usuário possui espaço financeiro independente. Migração assistida necessária.")
        # Um RPC único impede perfil sem membership após erro de rede.
        return db.call("POST", "rpc/axora_family_link_user", data={
            "p_workspace_id": ctx["workspace_id"], "p_actor_id": ctx["user_id"],
            "p_profile_id": profile_id, "p_user_id": uid
        })

    @app.post("/api/family/visibility")
    def set_visibility(payload: dict, user=Depends(authorized)):
        ctx = _context(user)
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
        profiles = family_service.profiles(user)
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
        return {"people": result, "visible_movements":len(ledger),
            "unallocated_movements":sum(int(r["id"]) not in assigned for r in ledger),
            "note": "Itens antigos sem rateio permanecem não atribuídos. Valores não são duplicados."}
