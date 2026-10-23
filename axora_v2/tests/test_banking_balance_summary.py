"""Saldo bancário consolidado: mesma conta não pode ser somada duas vezes."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from axora_v2 import banking, db, security
from axora_v2.main import app

W = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
BASE = Path(__file__).resolve().parents[1]


def test_sum_only_available_balance_and_keep_owners_separate():
    holders = [
        {"id":1,"name":"Titular principal","relationship":"proprio"},
        {"id":2,"name":"Familiar A","relationship":"conjuge"},
        {"id":3,"name":"Familiar B","relationship":"pai"},
        {"id":4,"name":"Familiar C","relationship":"mae"},
    ]
    accounts = [
        {"id":11,"holder_id":1,"pluggy_account_id":"bank-uuid",
         "pluggy_balance":"125.20","manual_balance":"999999.99"},
        {"id":12,"holder_id":1,"pluggy_account_id":None,"manual_balance":"74.80"},
        {"id":13,"holder_id":1,"pluggy_account_id":None,"manual_balance":None},
        {"id":14,"holder_id":2,"pluggy_account_id":None,"manual_balance":"300.10"},
        {"id":15,"holder_id":3,"pluggy_account_id":None,"manual_balance":"-12.50"},
        {"id":16,"holder_id":4,"pluggy_account_id":None,"manual_balance":None},
    ]
    summary=banking.balance_overview(holders,accounts)
    assert summary["personal"]=="200.00"  # Jamais soma o manual da conta sincronizada.
    assert summary["family"]=="287.60"
    assert summary["combined"]=="487.60"
    assert summary["known_accounts"]==4
    assert summary["missing_accounts"]==2
    assert summary["personal_missing"]==1
    assert summary["family_missing"]==1
    assert next(h for h in summary["holders"] if h["name"]=="Familiar A")["total"]=="300.10"
    assert banking.balance_overview([holders[0]],[{"holder_id":1,"pluggy_account_id":"i",
               "pluggy_balance":None,"manual_balance":"5000"}])["missing_accounts"]==1


def test_manual_balance_validation_and_empty_clear():
    assert banking.clean_manual_balance({"balance":"125.50"})=="125.50"
    assert banking.clean_manual_balance({"balance":0})=="0.00"
    assert banking.clean_manual_balance({"balance":"-4.12"})=="-4.12"
    assert banking.clean_manual_balance({"balance":None}) is None
    for value in ("NaN","Infinity",True,"18.123","1e25",{}):
        with pytest.raises(HTTPException) as exc:
            banking.clean_manual_balance({"balance":value})
        assert exc.value.status_code==422
    with pytest.raises(HTTPException):
        banking.clean_manual_balance({"balance":100,"bank":"Outro"})


def test_balance_api_workspace_csrf_and_connected_read_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","test-service")
    monkeypatch.setenv("SESSION_SECRET","b"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(security,"current",lambda _req:{"id":8,"csrf":"token","is_admin":True})
    def csrf(req,_user):
        if req.headers.get("x-csrf-token")!="token":
            raise HTTPException(403,"CSRF")
    monkeypatch.setattr(security,"require_csrf",csrf)
    holders=[{"id":1,"name":"Próprio","relationship":"proprio","workspace_id":W},
             {"id":2,"name":"Mãe","relationship":"mae","workspace_id":W}]
    accounts=[
        {"id":10,"holder_id":1,"workspace_id":W,"bank_name":"Nubank",
         "pluggy_account_id":"connected","pluggy_item_id":"item",
         "pluggy_balance":"450.00","manual_balance":None},
        {"id":11,"holder_id":2,"workspace_id":W,"bank_name":"Caixa",
         "pluggy_account_id":None,"pluggy_item_id":None,
         "manual_balance":None},
    ]
    calls=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        calls.append((method,table,params,data))
        if table=="rpc/axora_user_workspace":return W
        if table=="finance_bank_holders":return holders
        if table=="finance_bank_transactions":return []
        if table=="finance_bank_accounts":
            if method=="GET":
                return [a for a in accounts
                        if params["workspace_id"]=="eq."+W and
                        ("id" not in params or a["id"]==int(params["id"].removeprefix("eq.")))]
            if method=="PATCH":
                assert params["workspace_id"]=="eq."+W
                assert params["pluggy_item_id"]=="is.null"
                assert params["pluggy_account_id"]=="is.null"
                assert set(data)=={"manual_balance"}
                dest=next(a for a in accounts if a["id"]==int(params["id"].removeprefix("eq.")))
                dest.update(data)
                return [dest]
        raise AssertionError((method,table,params,data))
    monkeypatch.setattr(db,"call",fake_call)
    auth={"X-CSRF-Token":"token"}
    with TestClient(app) as client:
        initial=client.get("/api/banking")
        assert initial.status_code==200
        assert initial.json()["balances"]["personal"]=="450.00"
        assert initial.json()["balances"]["family_missing"]==1
        assert client.patch("/api/banking/accounts/11/balance",json={"balance":"250.20"}).status_code==403
        assert client.patch("/api/banking/accounts/10/balance",json={"balance":25},headers=auth).status_code==409
        assert client.patch("/api/banking/accounts/999/balance",json={"balance":25},headers=auth).status_code==404
        assert client.patch("/api/banking/accounts/11/balance",json={"balance":"1.235"},headers=auth).status_code==422
        ok=client.patch("/api/banking/accounts/11/balance",json={"balance":"250.20"},headers=auth)
        assert ok.status_code==200 and ok.json()["item"]["manual_balance"]=="250.20"
        current=client.get("/api/banking").json()["balances"]
        assert current["personal"]=="450.00"
        assert current["family"]=="250.20"
        assert current["combined"]=="700.20"
        cleared=client.patch("/api/banking/accounts/11/balance",json={"balance":None},headers=auth)
        assert cleared.status_code==200
        assert client.get("/api/banking").json()["balances"]["missing_accounts"]==1
    assert not any(m=="PATCH" and d.get("manual_balance")=="25.00"
                   for m,t,p,d in calls if isinstance(d,dict))


def test_ui_balance_summary_and_manual_update():
    js=(BASE/"static/banking.js").read_text()
    html=(BASE/"static/index.html").read_text()
    css=(BASE/"static/banking.css").read_text()
    assert "Meu dinheiro" in js and "Outros titulares" in js
    assert "stats.personal" not in js or "b.personal" in js
    assert 'data-action="bank-update-balance"' in js
    assert 'id="bank-balance-form"' in html
    assert 'id="bank-manual-balance"' in html
    assert "banking.js?v=axora-balance-summary-r1" in html
    assert "bank-balance-grid" in css
    assert "banking.balance_overview" in (BASE/"main.py").read_text()
