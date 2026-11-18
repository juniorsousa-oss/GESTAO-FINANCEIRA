"""Segurança multitenant: dados privados não chegam a nenhum endpoint restrito."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from axora_v2 import db, security, family_service
from axora_v2.main import app

W="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CONJ={"id":2,"display_name":"Conta B","csrf":"csrf","is_admin":False}
CTX={"workspace_id":W,"profile_id":22,"role":"conjuge","owner_id":1,"user_id":2}
MOVEMENTS=[
    {"id":11,"workspace_id":W,"value":"1999.00","classification":"SAÍDA",
     "description":"Dado estritamente privado","category":"PRIVADO","movement_date":"2026-11-10","competence":"11/2026"},
    {"id":12,"workspace_id":W,"value":"180.00","classification":"SAÍDA",
     "description":"Gasto autorizado","category":"MERCADO","movement_date":"2026-11-10","competence":"11/2026"}
]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","ci-fake")
    monkeypatch.setenv("SESSION_SECRET","a"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setenv("AXORA_FAMILY_V2_ENABLED","1")
    monkeypatch.setattr(security,"current",lambda _:dict(CONJ))
    monkeypatch.setattr(family_service,"context",lambda _:dict(CTX))
    def csrf(request,_user):
        if request.headers.get("x-csrf-token")!="csrf":
            raise HTTPException(403, "CSRF")
    monkeypatch.setattr(security,"require_csrf",csrf)

    tags={
        ("registro",12):{"id":1,"resource_id":12,"creator_user_id":1,"label":"casal"},
        ("provisao",22):{"id":2,"resource_id":22,"creator_user_id":1,"label":"casal"},
        ("conta",32):{"id":3,"resource_id":32,"creator_user_id":1,"label":"casal"},
        ("perfil",44):{"id":4,"resource_id":44,"creator_user_id":1,"label":"casal"},
    }
    def select(kind,*,fields="*",order=None,params=None):
        if kind=="users":return [{"avatar_data_uri":None}]
        if kind=="movements":return list(MOVEMENTS)
        if kind=="accounts":return [{"id":50,"balance":"999999.00"}]
        if kind=="debts":return [{"id":60,"open_value":"999999.00"}]
        raise AssertionError(("select",kind))
    monkeypatch.setattr(db,"select",select)
    def call(method,table,*,params=None,data=None,prefer=None):
        if table=="rpc/axora_ensure_provisions":return []
        if table=="rpc/axora_provision_overview":
            raise AssertionError("Métrica global do principal nunca pode ser consultada")
        if table=="finance_provision_occurrences":
            return [
                {"id":111,"rule_id":21,"status":"open","planned_value":"9999.00",
                 "description_override":None,"due_date":"2026-12-10",
                 "rule":{"description":"Provisão PRIVADA"}},
                {"id":112,"rule_id":22,"status":"open","planned_value":"150.00",
                 "description_override":None,"due_date":"2026-12-11",
                 "rule":{"description":"Provisão compartilhada"}}
            ]
        if table=="finance_family_visibility":
            kind=params["resource_type"].removeprefix("eq.")
            allowed=params["resource_id"].removeprefix("in.(").removesuffix(")").split(",")
            return [{**row,"workspace_id":W} for (tag_kind,tag_id),row in tags.items()
                    if tag_kind==kind and str(tag_id) in allowed]
        if table=="finance_family_visibility_grants":return []
        if table=="finance_bank_holders":return [
            {"id":1,"name":"Titular principal","relationship":"proprio"},
            {"id":2,"name":"Titular autorizado","relationship":"conjuge"}]
        if table=="finance_bank_accounts":return [
            {"id":31,"holder_id":1,"bank_name":"Privado","nickname":"Conta pessoal sigilosa",
             "manual_balance":"9999.00","pluggy_account_id":None},
            {"id":32,"holder_id":2,"bank_name":"Casal","nickname":"Conta permitida",
             "manual_balance":"75.00","account_type":"corrente",
             "pluggy_account_id":"external-private-reference","pluggy_item_id":"private-item"}]
        if table=="finance_bank_transactions":return [
            {"id":51,"account_id":31,"status":"pending","amount":"999.00"},
            {"id":52,"account_id":32,"status":"pending","amount":"-75.00",
             "description":"Transação sem permissão separada"}]
        if table=="finance_family_profiles":return [
            {"id":1,"display_name":"Principal","relationship":"principal","linked_user_id":1,"active":True},
            {"id":22,"display_name":"Cônjuge","relationship":"conjuge","linked_user_id":2,"active":True},
            {"id":33,"display_name":"Dependente privado","relationship":"filho","linked_user_id":None,"active":True},
            {"id":44,"display_name":"Dependente relacionado ao gasto","relationship":"filho","linked_user_id":None,"active":True}]
        if table=="finance_movements":return list(MOVEMENTS)
        if table=="finance_family_cost_allocations":
            return [{"movement_id":12,"profile_id":44,"amount":"180.00"}]
        if table=="finance_family_payment_allocations":
            return [{"movement_id":12,"payer_profile_id":22,"amount":"180.00"}]
        raise AssertionError((method,table,params,data))
    monkeypatch.setattr(db,"call",call)
    with TestClient(app) as c:
        yield c


def test_private_rows_and_totals_never_leak_in_snapshot(client):
    response=client.get("/api/snapshot")
    assert response.status_code==200
    data=response.json()
    assert [r["id"] for r in data["movements"]]==[12]
    assert data["accounts"]==[]
    assert data["debts"]==[]
    assert data["summary"]["expenses"]==180
    assert data["summary"]["to_pay"]==150
    assert "located" not in data["summary"]
    assert "discrepancy" not in data["summary"]
    assert "debt_open" not in data["summary"]
    assert "conciliation" not in data["summary"]
    assert "goals" not in data["summary"]
    serialized=response.text
    assert "1999.00" not in serialized
    assert "9999" not in serialized
    assert "Provisão PRIVADA" not in serialized


def test_bank_and_provisions_are_filtered_at_backend(client):
    bank=client.get("/api/banking")
    assert bank.status_code==200
    body=bank.json()
    assert [a["id"] for a in body["accounts"]]==[32]
    assert [h["id"] for h in body["holders"]]==[2]
    assert body["pending"]==[]
    assert body["balances"]["combined"]=="75.00"
    assert body["mode"]=="manual"
    assert "provider" not in body and "bank_connected" not in body
    assert "pluggy_account_id" not in bank.text
    assert "private-item" not in bank.text
    assert "external-private-reference" not in bank.text
    assert "pessoal sigilosa" not in bank.text
    prov=client.get("/api/provisions")
    assert prov.status_code==200
    assert [x["id"] for x in prov.json()["items"]]==[112]
    assert "PRIVADA" not in prov.text


def test_unscreened_routes_are_denied_before_financial_queries(client):
    assert client.get("/api/export").status_code==403
    assert client.get("/api/banking/history").status_code==403
    assert client.get("/api/catalogs").status_code==403
    assert client.post("/api/rows/movements",headers={"X-CSRF-Token":"csrf"},json={
        "description":"Invasão","value":10,"classification":"SAÍDA"}).status_code==403
    assert client.post("/api/settings",headers={"X-CSRF-Token":"csrf"},json={"net_income":1}).status_code==403
    assert client.post("/api/family/profiles",headers={"X-CSRF-Token":"csrf"},json={
        "display_name":"Outro","relationship":"filho"}).status_code==403



def test_member_directory_is_independent_of_shared_transactions(client,monkeypatch):
    original=family_service.visibility_map
    def no_identity_grants(ctx, kind, ids):
        return {} if kind=="perfil" else original(ctx, kind, ids)
    monkeypatch.setattr(family_service,"visibility_map",no_identity_grants)
    family=client.get("/api/family")
    assert family.status_code==200
    # Mesmo participando de uma despesa compartilhada, o dependente 44
    # não deve ser revelado sem autorização EXPLÍCITA do diretório.
    assert {p["id"] for p in family.json()["profiles"]}=={22}
    assert "Dependente relacionado ao gasto" not in family.text
    summary=client.get("/api/family/summary")
    assert summary.status_code==200
    assert {p["id"] for p in summary.json()["people"]}=={22}


def test_secondary_cannot_authorize_member_directory(client):
    result=client.post("/api/family/visibility",headers={"X-CSRF-Token":"csrf"},json={
        "resource_type":"perfil","resource_id":44,
        "label":"familia","viewers":[]})
    assert result.status_code==403

def test_member_may_only_read_family_records_allocated_to_own_view(client):
    family=client.get("/api/family")
    assert family.status_code==200 and family.json()["my_role"]=="conjuge"
    summary=client.get("/api/family/summary")
    assert summary.status_code==200
    assert "visible_movements" not in summary.json()
    assert "unallocated_movements" not in summary.json()
    assert "note" not in summary.json()
    assert {p["id"] for p in summary.json()["people"]}=={22}  # Dados de terceiros, mesmo em despesa comum, não viram relatório pessoal.
    assert {p["id"] for p in family.json()["profiles"]}=={22,44}
    assert "linked_user_id" not in family.text
    assert "Dependente privado" not in family.text
    assert "Dependente privado" not in summary.text
    assert "Principal" not in family.text
    me=client.get("/api/me")
    assert me.status_code==200 and me.json()["family_role"]=="conjuge"
