"""Regressões do piloto MeuPluggy: privacidade, leitura e ausência de baixa automática."""
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from axora_v2 import db, meu_pluggy, meu_pluggy_sync, security
from axora_v2.main import app

BASE=Path(__file__).resolve().parents[1]
W="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ITEM="11111111-2222-4333-8444-555555555555"
ACCOUNT="22222222-3333-4444-8555-666666666666"
TXID="33333333-4444-4555-8666-777777777777"


def enable(monkeypatch):
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "test-id")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("PLUGGY_ITEM_ID", ITEM)
    monkeypatch.setenv("PLUGGY_PERSONAL_USER_ID", "12")
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "fake")
    monkeypatch.setenv("SESSION_SECRET", "a"*64)
    monkeypatch.setenv("COOKIE_SECURE", "0")


def test_personal_credentials_only_on_server(monkeypatch):
    enable(monkeypatch)
    assert meu_pluggy.configured()
    assert meu_pluggy.personal_item()==ITEM
    meu_pluggy.require_owner({"id": 12})
    with pytest.raises(HTTPException) as exc:
        meu_pluggy.require_owner({"id": 13})
    assert exc.value.status_code==403
    monkeypatch.delenv("PLUGGY_CLIENT_SECRET")
    assert not meu_pluggy.configured()


def test_only_bank_accounts_are_listed(monkeypatch):
    enable(monkeypatch)
    def api(path, *, params):
        assert path=="/accounts"
        assert params["itemId"]==ITEM
        return {"results":[
            {"id":ACCOUNT,"type":"BANK","currencyCode":"BRL",
             "name":"Nubank corrente","number":"12345-6","balance":1234.55},
            {"id":"44444444-5555-4666-8777-888888888888","type":"CREDIT",
             "currencyCode":"BRL","name":"Cartão Nubank","balance":900},
        ]}
    monkeypatch.setattr(meu_pluggy, "_get", api)
    accounts=meu_pluggy.bank_accounts()
    assert len(accounts)==1
    assert accounts[0]["id"]==ACCOUNT
    assert accounts[0]["last_digits"]=="45-6"
    assert all(a["name"]!="Cartão Nubank" for a in accounts)


def test_normalize_only_posted_transactions():
    row={"id":TXID,"date":"2026-10-14T12:00:00.000Z","type":"DEBIT",
         "status":"POSTED","currencyCode":"BRL","amount":99.99,
         "description":"Pagamento mercado"}
    cleaned=meu_pluggy.normalize_transaction(row)
    assert cleaned["amount"]=="-99.99"
    assert cleaned["source"]=="import"
    assert cleaned["external_ref"]=="pluggy:"+TXID
    assert cleaned["posted_on"]=="2026-10-14"
    for patch in ({"status":"PENDING"},{"currencyCode":"USD"},{"amount":0},
                  {"type":"UNKNOWN"}):
        assert meu_pluggy.normalize_transaction({**row,**patch}) is None


def test_transactions_use_cursor_and_not_deprecated_endpoint(monkeypatch):
    pages=[]
    def api(path, *, params):
        assert path=="/v2/transactions"
        pages.append(dict(params))
        tx={"id":TXID,"date":"2026-10-14T10:00:00Z","type":"CREDIT",
            "status":"POSTED","currencyCode":"BRL","amount":100,
            "description":"Transferencia"}
        if len(pages)==1:
            return {"results":[tx], "next":"?after=cursorABC"}
        return {"results":[], "next":None}
    monkeypatch.setattr(meu_pluggy, "_get", api)
    rows=meu_pluggy.recent_transactions(ACCOUNT)
    assert len(rows)==1
    assert rows[0]["amount"]=="100.00"
    assert pages[1]["after"]=="cursorABC"


def test_import_is_idempotent_and_never_modifies_movements(monkeypatch):
    enable(monkeypatch)
    recorded=[]
    def fake_call(method, table, *, params=None, data=None, prefer=None):
        recorded.append((method,table,params,data,prefer))
        if table=="finance_bank_accounts":
            return [{"id":4,"workspace_id":W,"pluggy_item_id":ITEM,
                     "pluggy_account_id":ACCOUNT}] if method=="GET" else []
        if table=="finance_bank_transactions":
            assert params["on_conflict"]=="account_id,source,external_ref"
            assert prefer=="resolution=ignore-duplicates,return=minimal"
            assert data[0]["status"] if "status" in data[0] else True
            return []
        raise AssertionError((method,table))
    monkeypatch.setattr(db,"call",fake_call)
    monkeypatch.setattr(meu_pluggy,"bank_accounts",lambda:[{
        "id":ACCOUNT,"balance":"200.00","name":"Nubank"
    }])
    monkeypatch.setattr(meu_pluggy,"recent_transactions",lambda _id:[{
        "posted_on":"2026-10-14","description":"Pix recebido","amount":"20.00",
        "source":"import","external_ref":"pluggy:"+TXID,
    }])
    output=meu_pluggy_sync.sync_account(W,4)
    assert output["reconciled"]==0
    assert output["checked"]==1
    assert not any("finance_movements" in x[1] or "finance_provision" in x[1] for x in recorded)


def test_personal_api_prevents_other_users_and_checks_explicit_consent(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(security,"current",lambda _:{"id":13,"is_admin":True,"csrf":"csrf"})
    monkeypatch.setattr(security,"require_csrf",lambda req,_user:
        None if req.headers.get("x-csrf-token")=="csrf" else (_ for _ in ()).throw(HTTPException(403,"CSRF")))
    monkeypatch.setattr(db,"call",lambda method,table,*,params=None,data=None,prefer=None:
        W if table=="rpc/axora_user_workspace" else [])
    with TestClient(app) as client:
        assert client.get("/api/banking/meu-pluggy/accounts").status_code==403
        assert client.post("/api/banking/meu-pluggy/link",headers={"X-CSRF-Token":"csrf"},
            json={"account_id":4,"provider_account_id":ACCOUNT,"confirm_owner":True}).status_code==403


def test_no_secrets_in_frontend_and_limited_scope():
    js=(BASE/"static/banking.js").read_text()
    html=(BASE/"static/index.html").read_text()
    main=(BASE/"main.py").read_text()
    sql=(BASE/"migrations/20261015_meu_pluggy_personal_sync.sql").read_text()
    worker=(BASE/"meu_pluggy_sync.py").read_text()
    for phrase in ("PLUGGY_CLIENT_SECRET","PLUGGY_CLIENT_ID","X-API-KEY"):
        assert phrase not in js
        assert phrase not in html
    assert "periodic_sync" in main
    assert "await asyncio.sleep(3600)" in worker
    assert "ON CONFLICT" not in worker or "on_conflict" in worker
    assert "DELETE FROM" not in sql.upper()
    assert 'id="meu-pluggy-link-dialog"' in html
    assert "bankSyncMeuPluggy" in js
