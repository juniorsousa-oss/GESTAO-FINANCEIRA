"""AXORA banking upgrades: fixtures only; production financial balances remain untouched."""
import uuid
from decimal import Decimal
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import banking, main, db, security, family_service

BASE=Path(__file__).resolve().parents[1]
WORKSPACE="aaaabbbb-cccc-dddd-eeee-ffffffffffff"
REQUEST="ccccdddd-1111-2222-3333-444455556666"


def test_transfer_input_and_investments_validation():
    valid={"from_account_id":1,"to_account_id":2,"amount":"75.45",
           "note":"Entre contas","request_id":REQUEST}
    obj=banking.clean_transfer(valid)
    assert obj["p_amount"]=="75.45" and obj["p_from_account_id"]==1
    for change in ({"from_account_id":2},{"amount":"0"},{"amount":"-1"},
                   {"amount":"10.123"},{"to_account_id":0},
                   {"request_id":"not-uuid"}):
        with pytest.raises(HTTPException):
            banking.clean_transfer({**valid,**change})
    assert banking.clean_investment_balance({"investment_balance":"250.50"})=="250.50"
    assert banking.clean_investment_balance({"investment_balance":None}) is None
    with pytest.raises(HTTPException):
        banking.clean_investment_balance({"investment_balance":"-2"})
    assert banking.clean_account_type({"label":"  Corretora   digital "})["label"]=="Corretora digital"


def test_overview_cash_and_investments_are_counted_once():
    holders=[{"id":1,"name":"Principal","relationship":"proprio"},
             {"id":2,"name":"Conjugue","relationship":"conjuge"}]
    accounts=[
      {"holder_id":1,"manual_balance":"100.25","investment_balance":"40.00"},
      {"holder_id":1,"manual_balance":"10.00","investment_balance":None},
      {"holder_id":2,"manual_balance":"250.00","investment_balance":"50.00"},
      {"holder_id":2,"manual_balance":None,"investment_balance":None},
    ]
    b=banking.balance_overview(holders,accounts,manual_only=True)
    assert b["personal"]=="150.25"
    assert b["family"]=="300.00"
    assert b["cash_total"]=="360.25"
    assert b["investment_total"]=="90.00"
    assert b["combined"]=="450.25"
    assert b["missing_accounts"]==1
    assert b["known_accounts"]==3


def test_principal_transfer_calls_atomic_rpc_and_investment_update(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fixture-key")
    monkeypatch.setenv("SESSION_SECRET","x"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setenv("AXORA_BANK_MODE","manual")
    monkeypatch.setattr(security,"current",lambda _:{"id":44,"csrf":"csrf-test",
                                                     "is_admin":True,"display_name":"Principal"})
    monkeypatch.setattr(security,"require_csrf",
                        lambda request,user:None if request.headers.get("x-csrf-token")=="csrf-test"
                        else (_ for _ in ()).throw(HTTPException(403,"CSRF")))
    monkeypatch.setattr(family_service,"context",lambda _:None)
    monkeypatch.setattr(family_service,"gate",lambda *_:None)
    calls=[]
    def fake(method,table,*,params=None,data=None,prefer=None):
        calls.append((method,table,params,data))
        if table=="rpc/axora_user_workspace":return WORKSPACE
        if table=="rpc/axora_ensure_bank_account_types":return 0
        if table=="finance_bank_account_types":
            return [{"id":1,"code":"corrente","label":"Conta corrente","active":True}]
        if table=="finance_bank_accounts":
            if method=="GET":
                return [{"id":1,"holder_id":1,"manual_balance":"200.00"},
                        {"id":2,"holder_id":1,"manual_balance":"0.00"}]
            if method=="PATCH":
                assert data=={"investment_balance":"50.50"}
                assert params["workspace_id"]=="eq."+WORKSPACE
                return [{"id":1,**data}]
        if table=="rpc/axora_transfer_manual_balance":
            assert data["p_workspace_id"]==WORKSPACE
            assert data["p_actor_user_id"]==44
            assert data["p_request_id"]==REQUEST
            return {"id":80,"already_applied":False,
                    "from_balance":"124.55","to_balance":"75.45"}
        if table=="finance_balance_transfers":
            assert params["workspace_id"]=="eq."+WORKSPACE
            return [{"id":80,"from_account_id":1,"to_account_id":2,"amount":"75.45"}]
        raise AssertionError((method,table))
    monkeypatch.setattr(db,"call",fake)
    auth={"X-CSRF-Token":"csrf-test"}
    with TestClient(main.app) as client:
        result=client.get("/api/banking/account-types")
        assert result.status_code==200 and result.json()["items"][0]["code"]=="corrente"
        transfer=client.post("/api/banking/transfers",json={
            "from_account_id":1,"to_account_id":2,"amount":"75.45",
            "note":"Entre contas","request_id":REQUEST
        },headers=auth)
        assert transfer.status_code==200 and transfer.json()["transfer"]["id"]==80
        invested=client.patch("/api/banking/accounts/1/investments",
             json={"investment_balance":"50.50"},headers=auth)
        assert invested.status_code==200
        history=client.get("/api/banking/transfers")
        assert history.status_code==200 and len(history.json()["items"])==1
        invalid=client.post("/api/banking/transfers",json={
            "from_account_id":1,"to_account_id":1,"amount":"12",
            "note":None,"request_id":REQUEST
        },headers=auth)
        assert invalid.status_code==422
    assert sum(t=="rpc/axora_transfer_manual_balance" for _,t,_,_ in calls)==1


def test_privileged_operations_reject_secondary_profiles():
    user={"_family":{"role":"conjuge"}}
    with pytest.raises(HTTPException) as err:main.require_bank_principal(user)
    assert err.value.status_code==403


def test_frontend_contract_and_migration_scope():
    js=(BASE/"static/banking.js").read_text()
    advanced=(BASE/"static/banking-advanced.js").read_text()
    family=(BASE/"static/family.js").read_text()
    app=(BASE/"static/app.js").read_text()
    css=(BASE/"static/banking-advanced.css").read_text()
    migration=(BASE/"migrations/20261116_bank_transfers_investments_and_types.sql").read_text()
    html=(BASE/"static/index.html").read_text()
    assert 'class="bank-account-menu axora-action-menu"' in js
    assert '"bank-transfer-open"' in js+app+advanced
    assert '"bank-open-investments"' in js
    assert 'bankingHolderCatalogPanel' in app
    assert 'Membros cadastrados' in js
    assert 'bankOnlyMembers()' in family
    assert 'bank-account-menu>summary' in css
    for key in ('bank-transfer-form','bank-investment-form','bank-type-form'):
        assert 'id="'+key+'"' in html
    assert 'CREATE TABLE IF NOT EXISTS axora_beta.finance_balance_transfers' in migration
    assert 'FOR UPDATE' in migration
    assert 'request_id uuid NOT NULL' in migration
    assert 'ENABLE ROW LEVEL SECURITY' in migration
    assert 'axora_beta.' in migration and 'public.finance_bank' not in migration
