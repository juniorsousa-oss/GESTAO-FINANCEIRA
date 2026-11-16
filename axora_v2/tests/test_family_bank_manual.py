"""Modo bancário manual: sem sincronização concorrente, preservando histórico bancário."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from axora_v2 import banking, db, meu_pluggy, security
from axora_v2.main import app

W = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_manual_balance_uses_only_user_entries(monkeypatch):
    monkeypatch.setenv("AXORA_BANK_MODE", "manual")
    assert banking.manual_mode()
    holders=[{"id":1,"name":"Pessoa","relationship":"proprio"}]
    accounts=[{"id":4,"holder_id":1,"manual_balance":"80.00","pluggy_balance":"400.00",
               "pluggy_account_id":"old-connection"}]
    out=banking.balance_overview(holders,accounts,manual_only=banking.manual_mode())
    assert out["personal"]=="80.00"
    assert out["combined"]=="80.00"
    monkeypatch.delenv("AXORA_BANK_MODE")
    assert banking.balance_overview(holders,accounts)["personal"]=="400.00"


def test_manual_endpoints_pause_provider_and_preserve_links(monkeypatch):
    monkeypatch.setenv("AXORA_BANK_MODE", "manual")
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake")
    monkeypatch.setenv("SESSION_SECRET","session-test-key-longer-than-thirty-two-characters")
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(meu_pluggy,"configured",lambda:True)
    monkeypatch.setattr(security,"current",lambda _r:{"id":12,"is_admin":True,"csrf":"t"})
    def csrf(req,_user):
        if req.headers.get("x-csrf-token")!="t":
            raise HTTPException(403,"CSRF")
    monkeypatch.setattr(security,"require_csrf",csrf)
    accounts=[{"id":4,"workspace_id":W,"holder_id":1,"manual_balance":None,
               "pluggy_balance":"750.00","pluggy_account_id":"old","pluggy_item_id":"old-item"}]
    holders=[{"id":1,"workspace_id":W,"name":"Pessoa","relationship":"proprio"}]
    patches=[]
    def call(method,table,*,params=None,data=None,prefer=None):
        if table=="rpc/axora_user_workspace":
            return W
        if table=="finance_bank_holders":
            return holders
        if table=="finance_bank_transactions":
            return []
        if table=="finance_bank_accounts":
            if method=="GET":
                rows=[x for x in accounts if "id" not in (params or {}) or params["id"]==f"eq.{x['id']}"]
                return rows
            if method=="PATCH":
                assert "pluggy_account_id" not in params and "pluggy_item_id" not in params
                assert set(data)=={"manual_balance"}
                patches.append(data)
                accounts[0].update(data)
                return accounts
        raise AssertionError((method,table))
    monkeypatch.setattr(db,"call",call)
    with TestClient(app) as client:
        overview=client.get("/api/banking")
        assert overview.status_code==200
        assert overview.json()["mode"]=="manual"
        assert overview.json()["provider"]["configured"] is False
        assert overview.json()["balances"]["known_accounts"]==0
        assert client.get("/api/banking/meu-pluggy/accounts").status_code==410
        assert client.post("/api/banking/meu-pluggy/sync/4",headers={"x-csrf-token":"t"},json={}).status_code==410
        assert client.patch("/api/banking/accounts/4/balance",json={"balance":30}).status_code==403
        out=client.patch("/api/banking/accounts/4/balance",headers={"x-csrf-token":"t"},json={"balance":"123.45"})
        assert out.status_code==200
        assert accounts[0]["pluggy_account_id"]=="old" and accounts[0]["pluggy_item_id"]=="old-item"
        assert patches==[{"manual_balance":"123.45"}]
        assert client.get("/api/banking").json()["balances"]["personal"]=="123.45"


def test_family_ui_groups_cards_with_native_details():
    from pathlib import Path
    folder=Path(__file__).resolve().parents[1]
    code=(folder/"static/banking.js").read_text()
    assert '<details class="bank-person-card">' in code
    assert "bank-person-amount" in code
    assert "bankingData.mode" in code
    assert "Controle bancário manual." in code
