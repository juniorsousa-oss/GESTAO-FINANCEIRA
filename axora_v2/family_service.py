"""AXORA Familiar: contexto de sessão e visibilidade por recurso, deny-by-default.

A integração financeira continua no servidor. NUNCA confiar em IDs, papéis ou
rótulos enviados pelo navegador para conceder acesso. Ativado somente depois
da migração em banco BETA independente.
"""
import os
import re
from decimal import Decimal

from fastapi import HTTPException

from axora_v2 import db, family_policy


def enabled():
    return os.environ.get("AXORA_FAMILY_V2_ENABLED", "0").strip().lower() in {"1", "true", "yes"}


def table(name, workspace, *, filters=None, fields="*", limit=1000, order=None):
    data = {"select": fields, "workspace_id": "eq." + workspace, "limit": limit}
    if filters:
        data.update(filters)
    if order:
        data["order"] = order
    return db.call("GET", name, params=data)


def all_rows(name, workspace, *, fields="*", order=None, filters=None, maximum=30000):
    """Paginação para relatórios e visões consolidadas sem truncamento de 1.000 linhas."""
    result = []
    page_size = 500
    while len(result) < maximum:
        rows = table(name, workspace, fields=fields, order=order,
                     filters={**(filters or {}), "offset": len(result)}, limit=page_size)
        result.extend(rows)
        if len(rows) < page_size:
            return result
    raise HTTPException(503, "O histórico é maior que o limite de consulta. Refine o período.")


def context(user):
    if not enabled():
        return None
    matches = db.call("GET", "finance_family_profiles", params={
        "select": "id,workspace_id,relationship,linked_user_id,active,display_name",
        "linked_user_id": "eq." + str(int(user["id"])), "active": "eq.true", "limit": 2,
    })
    if not matches:
        return None
    if len(matches) != 1:
        raise HTTPException(403, "Vínculo familiar duplicado; acesso bloqueado.")
    profile = matches[0]
    workspaces = db.call("GET", "finance_workspaces", params={
        "select": "id,created_by,is_active", "id": "eq." + profile["workspace_id"], "limit": 1
    })
    if not workspaces or not workspaces[0].get("is_active", True):
        raise HTTPException(403, "Espaço familiar indisponível.")
    owner_id = workspaces[0].get("created_by")
    if owner_id is None:
        raise HTTPException(403, "Espaço sem proprietário definido.")
    if profile["relationship"] == "principal" and int(user["id"]) != int(owner_id):
        raise HTTPException(403, "Proprietário inválido.")
    if profile["relationship"] != "principal" and int(user["id"]) == int(owner_id):
        raise HTTPException(403, "Configuração familiar inconsistente.")
    return {"workspace_id": str(profile["workspace_id"]), "profile_id": int(profile["id"]),
            "role": profile["relationship"], "owner_id": int(owner_id),
            "user_id": int(user["id"])}


def is_owner(user):
    ctx = user.get("_family")
    return not ctx or ctx["role"] == "principal"


def require_principal(user):
    ctx = user.get("_family")
    if ctx is None or ctx["role"] != "principal" or ctx["user_id"] != ctx["owner_id"]:
        raise HTTPException(403, "Somente o usuário principal pode administrar a família.")
    return ctx


def family_workspace(user):
    ctx = user.get("_family")
    return ctx["workspace_id"] if ctx else None


def restricted_route(method, path):
    """Allowlist para TODOS os endpoints antes de cada operação real.

    Em modo familiar nenhum endpoint não auditado fica acessível ao cônjuge.
    """
    if method == "GET" and path in {
        "/api/me", "/api/snapshot", "/api/provisions", "/api/banking",
        "/api/family", "/api/family/summary", "/api/branding/institutional",
        "/api/brand-kit", "/api/multiuser/status"
    }:
        return True
    if method == "POST" and path in {"/api/logout", "/api/family/transactions"}:
        return True
    if method == "POST" and re.fullmatch(r"/api/family/provisions/[1-9]\d*/pay", path):
        return True
    if method == "GET" and re.fullmatch(r"/api/provisions/[1-9]\d*/pix", path):
        return True
    return False


def gate(user, method, path):
    ctx = user.get("_family")
    if ctx and ctx["role"] != "principal" and not restricted_route(method, path):
        raise HTTPException(403, "Esta operação não foi autorizada para seu perfil familiar.")


def visibility_map(ctx, resource_type, ids):
    valid_ids = sorted({int(v) for v in ids if v is not None and int(v) > 0})
    if not valid_ids:
        return {}
    result = {}
    for offset in range(0, len(valid_ids), 250):
        keys = valid_ids[offset:offset + 250]
        rows = table("finance_family_visibility", ctx["workspace_id"], filters={
            "resource_type": "eq." + resource_type,
            "resource_id": "in.(" + ",".join(map(str, keys)) + ")",
        }, limit=250)
        for row in rows:
            result[int(row["resource_id"])] = {**row, "granted_user_ids": []}
    if not result:
        return result
    visibility_ids = [int(x["id"]) for x in result.values()]
    grants = []
    for offset in range(0, len(visibility_ids), 250):
        keys = visibility_ids[offset:offset + 250]
        grants.extend(table("finance_family_visibility_grants", ctx["workspace_id"], filters={
            "visibility_id": "in.(" + ",".join(map(str, keys)) + ")"
        }, fields="visibility_id,user_id", limit=500))
    by_id = {int(row["id"]): row for row in result.values()}
    for grant in grants:
        existing = by_id.get(int(grant["visibility_id"]))
        if existing is not None:
            existing["granted_user_ids"].append(int(grant["user_id"]))
    return result


def visible(ctx, kind, record_id, *, tag=None):
    if ctx is None or ctx["role"] == "principal":
        return True
    if not tag:
        return False  # registros anteriores não ganham visibilidade por inferência
    return family_policy.can_view(
        viewer_id=ctx["user_id"], principal_id=ctx["owner_id"],
        creator_id=int(tag["creator_user_id"]), viewer_role=ctx["role"],
        label=tag["label"], same_workspace=True,
        allowed_user_ids=tag.get("granted_user_ids", ())
    )


def filter_rows(user, kind, rows, *, id_key="id"):
    ctx = user.get("_family")
    if not ctx or ctx["role"] == "principal":
        return rows
    mapped = visibility_map(ctx, kind, [row.get(id_key) for row in rows])
    return [row for row in rows if visible(ctx, kind, row.get(id_key), tag=mapped.get(int(row[id_key])))]


def assert_visible(user, kind, record_id):
    ctx = user.get("_family")
    if not ctx or ctx["role"] == "principal":
        return
    tag = visibility_map(ctx, kind, [record_id]).get(int(record_id))
    if not visible(ctx, kind, record_id, tag=tag):
        raise HTTPException(404, "Registro não localizado.")


def provision_overview(items):
    # Resumo construído APENAS com registros já filtrados, sem RPC global.
    pending = [x for x in items if x.get("status") == "open"]
    total = sum(Decimal(str(x.get("planned_value") or "0")) for x in pending)
    first = sorted(pending, key=lambda x: (x.get("due_date") or "", int(x["id"])))[:5]
    return {
        "to_pay": float(total), "pending_count": len(pending),
        "next_forecasts": [{"due_date": x["due_date"],
             "description": x.get("description_override") or (x.get("rule") or {}).get("description", ""),
             "type": "Saída", "status": "Não pago",
             "final_value": x.get("planned_value")} for x in first]
    }


def profiles(user):
    ctx = user.get("_family")
    if not ctx:
        raise HTTPException(503, "A gestão familiar ainda não foi ativada neste ambiente.")
    # Nomes e vínculos são informações cadastrais, não saldos financeiros.
    return table("finance_family_profiles", ctx["workspace_id"],
                 fields="id,display_name,relationship,linked_user_id,active",
                 order="id.asc")


def accessible_profiles(user):
    """Exibe só a pessoa logada e participantes de lançamentos a que tem acesso.

    A presença de um dependente ou outro usuário não é revelada por
    contadores, listagens de perfis ou busca de IDs não autorizados.
    """
    ctx = user.get("_family")
    available = profiles(user)
    if ctx["role"] == "principal":
        return available
    allowed_ids = {int(ctx["profile_id"])}
    all_ids = all_rows("finance_movements", ctx["workspace_id"],
                       fields="id", order="id.asc")
    visible_movements = filter_rows(user, "registro", all_ids)
    movement_ids = [int(row["id"]) for row in visible_movements]
    for start in range(0, len(movement_ids), 200):
        chunk = movement_ids[start:start + 200]
        condition = {"movement_id": "in.(" + ",".join(map(str, chunk)) + ")"}
        costs = table("finance_family_cost_allocations", ctx["workspace_id"],
                      fields="profile_id", filters=condition, limit=500)
        payers = table("finance_family_payment_allocations", ctx["workspace_id"],
                       fields="payer_profile_id", filters=condition, limit=500)
        allowed_ids.update(int(x["profile_id"]) for x in costs)
        allowed_ids.update(int(x["payer_profile_id"]) for x in payers)
    return [
        {"id": p["id"], "display_name": p["display_name"],
         "relationship": p["relationship"], "active": p["active"]}
        for p in available if int(p["id"]) in allowed_ids and p.get("active")
    ]


def check_profile_ids(ctx, profile_ids):
    listed = profiles({"_family": ctx})
    known = {int(p["id"]) for p in listed if p.get("active")}
    if set(map(int, profile_ids)) - known:
        raise HTTPException(422, "Participante não pertence a esta família.")


def check_resource(ctx, kind, resource_id):
    tables = {"registro": "finance_movements", "provisao": "finance_provision_rules",
              "conta": "finance_bank_accounts", "transacao": "finance_bank_transactions"}
    name = tables.get(kind)
    if not name:
        raise HTTPException(422, "Tipo de recurso inválido.")
    rows = table(name, ctx["workspace_id"], filters={"id": "eq." + str(int(resource_id))},
                 fields="id", limit=1)
    if not rows:
        raise HTTPException(404, "Registro não localizado neste espaço financeiro.")
    return True


def tagged_records(user, kind, rows):
    """Acrescenta o rótulo autorizado, sem expor tags de recursos privados."""
    ctx = user.get("_family")
    if not ctx:
        return rows
    tags = visibility_map(ctx, kind, [x.get("id") for x in rows])
    output = []
    for row in rows:
        tag = tags.get(int(row["id"]))
        if visible(ctx, kind, row["id"], tag=tag):
            output.append({**row, "visibility_label": tag["label"] if tag else "privado"}
                          if ctx["role"] == "principal" else row)
    return output
