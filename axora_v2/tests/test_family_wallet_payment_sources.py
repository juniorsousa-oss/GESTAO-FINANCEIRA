"""Pagadores, múltiplas contas e lançamentos históricos sem mutação de saldos."""
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import family_policy, db, family_service, security
from axora_v2.main import app

W="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CTX={"workspace_id":W,"profile_id":7,"role":"principal","owner_id":12,"user_id":12}
HEADERS={"X-CSRF-Token":"test-csrf"}
ROOT=Path(__file__).resolve().parents[1]

def payments():
    return [{"profile_id":7,"amount":"60.00","source_account_id":None},
            {"profile_id":8,"amount":"40.00","source_account_id":None}]

def sources():
    return [{"profile_id":7,"account_id":101,"amount":"35.00"},
            {"profile_id":7,"account_id":102,"amount":"25.00"},
            {"profile_id":8,"account_id":103,"amount":"40.00"}]

def setup_family(monkeypatch, role="principal"):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","dummy")
    monkeypatch.setenv("SESSION_SECRET","x"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(security,"current",lambda _:{ "id":12, "display_name":"Principal",
        "is_admin":False,"csrf":"test-csrf"})
    monkeypatch.setattr(security,"require_csrf",lambda req,user:None if
        req.headers.get("x-csrf-token")=="test-csrf"
        else (_ for _ in ()).throw(HTTPException(403,"CSRF")))
    monkeypatch.setattr(family_service,"context",lambda _:dict(CTX,role=role))
    monkeypatch.setattr(family_service,"accessible_profiles",lambda user:[
        {"id":7,"display_name":"Principal","active":True},
        {"id":8,"display_name":"Cônjuge","active":True},
    ])
    monkeypatch.setattr(family_service,"assert_visible",lambda *_:None)

def payload(balance=False):
    body={"date":"2026-11-17","description":"Conta familiar","value":100,
          "classification":"SAÍDA","category":"Moradia","label":"privado",
          "costs":[{"profile_id":7,"percentage":50},{"profile_id":8,"percentage":50}],
          "payments":[{"profile_id":7,"amount":60},{"profile_id":8,"amount":40}]}
    if balance:
        body.update(balance_mode="wallet",request_id=str(uuid4()),
                    account_sources=[{"profile_id":7,"account_id":101,"amount":35},
                                     {"profile_id":7,"account_id":102,"amount":25},
                                     {"profile_id":8,"account_id":103,"amount":40}])
    return body

def test_wallet_amounts_multiple_accounts_per_payer_and_duplicate_rejected():
    assert family_policy.validate_wallet_sources(100,payments(),sources())==sources()
    bad=[
        sources()[:-1],
        [*sources(),sources()[0]],
        [dict(sources()[0],amount=35.001),*sources()[1:]],
        [dict(sources()[0],profile_id=999),*sources()[1:]],
        [dict(sources()[0],account_id=102),*sources()[1:]],
        "not-list",
    ]
    for src in bad:
        with pytest.raises(HTTPException) as error:
            family_policy.validate_wallet_sources(100,payments(),src)
        assert error.value.status_code==422

def test_wallet_route_uses_atomic_rpc_and_legacy_no_balance_is_unchanged(monkeypatch):
    setup_family(monkeypatch)
    calls=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        calls.append((table,data))
        if table=="rpc/axora_family_record_from_wallet":
            return {"ok":True,"movement_id":95,"balance_debited":True}
        if table=="rpc/axora_family_record":
            return {"ok":True,"movement_id":96}
        raise AssertionError(table)
    monkeypatch.setattr(db,"call",fake_call)
    with TestClient(app) as client:
        p=payload(True)
        assert client.post("/api/family/transactions",json=p).status_code==403
        r=client.post("/api/family/transactions",headers=HEADERS,json=p)
        assert r.status_code==200,r.text
        assert r.json()["balance_debited"] is True
        assert calls[-1][0]=="rpc/axora_family_record_from_wallet"
        assert calls[-1][1]["p_sources"]==[{"profile_id":7,"account_id":101,"amount":"35.00"},
          {"profile_id":7,"account_id":102,"amount":"25.00"},
          {"profile_id":8,"account_id":103,"amount":"40.00"}]
        assert calls[-1][1]["p_request_id"]==p["request_id"]
        older=client.post("/api/family/transactions",headers=HEADERS,json=payload())
        assert older.status_code==200,older.text
        assert calls[-1][0]=="rpc/axora_family_record"
        assert "p_sources" not in calls[-1][1]

def test_unbalanced_wallet_and_secondary_user_cannot_debit(monkeypatch):
    setup_family(monkeypatch)
    calls=[]
    monkeypatch.setattr(db,"call",lambda *a,**k:calls.append(a))
    with TestClient(app) as client:
        invalid=payload(True)
        invalid["account_sources"][0]["amount"]=30
        assert client.post("/api/family/transactions",headers=HEADERS,json=invalid).status_code==422
        invalid=payload(True)
        invalid["request_id"]="not-a-uuid"
        assert client.post("/api/family/transactions",headers=HEADERS,json=invalid).status_code==422
    assert calls==[]
    setup_family(monkeypatch,role="conjuge")
    with TestClient(app) as client:
        assert client.post("/api/family/transactions",headers=HEADERS,
            json=payload(True)).status_code==403
    assert calls==[]

def test_provision_payment_wallet_uses_same_account_sources(monkeypatch):
    setup_family(monkeypatch)
    calls=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        calls.append((table,data))
        if table=="rpc/axora_family_pay_provision_from_wallet":
            return {"ok":True,"movement_id":125,"balance_debited":True}
        raise AssertionError(table)
    monkeypatch.setattr(db,"call",fake_call)
    monkeypatch.setattr(family_service,"table",lambda name,workspace,*,filters=None,
        fields="*",limit=1000,order=None:[{"id":33,"rule_id":8}])
    p=payload(True)
    pay={"payment_date":"2026-11-17","amount":100,
         "label":"privado","costs":p["costs"],"payments":p["payments"],
         "balance_mode":p["balance_mode"],"account_sources":p["account_sources"],
         "request_id":p["request_id"]}
    with TestClient(app) as client:
        result=client.post("/api/family/provisions/33/pay",headers=HEADERS,json=pay)
        assert result.status_code==200,result.text
        assert calls[0][0]=="rpc/axora_family_pay_provision_from_wallet"
        assert calls[0][1]["p_occurrence_id"]==33
        assert len(calls[0][1]["p_sources"])==3

def test_ui_account_selection_and_no_balance_are_explicit():
    js=(ROOT/"static/family.js").read_text()
    html=(ROOT/"static/index.html").read_text()
    css=(ROOT/"static/family.css").read_text()
    sql=(ROOT/"migrations/20261117_family_wallet_payment_sources.sql").read_text()
    assert 'name="balance_mode" value="none" checked' in html
    assert 'name="balance_mode" value="wallet"' in html
    assert 'id="family-wallet-source-list"' in html
    assert 'data-wallet-account' in js and 'data-wallet-payer' in js
    assert 'walletPaymentSources(form)' in js
    assert 'body.account_sources=accountSources' in js
    assert 'form.dataset.walletRequestId=crypto.randomUUID()' in js
    assert "walletAvailableAccounts()" in js
    assert 'family.css?v=family-hidden-payment-20261123-r1' in html
    assert '.family-wallet-source{' in css
    assert 'axora_family_record_from_wallet' in sql
    assert 'axora_family_pay_provision_from_wallet' in sql
    assert 'pg_advisory_xact_lock' in sql
    assert 'manual_balance=manual_balance-v_row.amount' in sql
    assert 'a.manual_balance>=s.amount' in sql
    assert 'ALTER TABLE public.' not in sql
    assert 'DROP TABLE' not in sql and 'TRUNCATE' not in sql


def income_payload(balance=False, *, recipient=7):
    body={"date":"2026-11-19","description":"Salário histórico",
          "value":120,"classification":"ENTRADA","category":"Salário",
          "label":"privado","costs":[{"profile_id":recipient,"percentage":100}],
          "payments":[]}
    if balance:
        body.update(balance_mode="wallet",request_id=str(uuid4()),
                    account_sources=[{"profile_id":recipient,"account_id":101,"amount":65},
                                     {"profile_id":recipient,"account_id":102,"amount":55}])
    return body


def test_income_credit_amounts_validate_recipient_ownership_duplicates_and_exact_cents():
    sources=income_payload(True)["account_sources"]
    assert family_policy.validate_income_wallet_sources(120,7,sources)==[
        {"profile_id":7,"account_id":101,"amount":"65.00"},
        {"profile_id":7,"account_id":102,"amount":"55.00"}]
    invalid=[
        sources[:1],[sources[0],dict(sources[1],account_id=101)],
        [dict(sources[0],profile_id=8),sources[1]],
        [dict(sources[0],amount=65.001),sources[1]],
        [dict(sources[0],account_id=0),sources[1]],
        "bad",
    ]
    for entry in invalid:
        with pytest.raises(HTTPException) as err:
            family_policy.validate_income_wallet_sources(120,7,entry)
        assert err.value.status_code==422


def test_income_history_is_record_only_and_wallet_increases_balance_via_atomic_rpc(monkeypatch):
    setup_family(monkeypatch)
    calls=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        calls.append((table,data))
        if table=="rpc/axora_family_record":return {"ok":True,"movement_id":21}
        if table=="rpc/axora_family_record_income_to_wallet":
            return {"ok":True,"movement_id":22,"balance_credited":True}
        raise AssertionError(table)
    monkeypatch.setattr(db,"call",fake_call)
    with TestClient(app) as client:
        history=client.post("/api/family/transactions",headers=HEADERS,json=income_payload())
        assert history.status_code==200,history.text
        assert calls[-1][0]=="rpc/axora_family_record"
        assert "p_sources" not in calls[-1][1]
        current=income_payload(True)
        credited=client.post("/api/family/transactions",headers=HEADERS,json=current)
        assert credited.status_code==200,credited.text
        assert credited.json()["balance_credited"] is True
        assert calls[-1][0]=="rpc/axora_family_record_income_to_wallet"
        assert calls[-1][1]["p_payments"]==[]
        assert calls[-1][1]["p_sources"]==[
          {"profile_id":7,"account_id":101,"amount":"65.00"},
          {"profile_id":7,"account_id":102,"amount":"55.00"}]
        assert calls[-1][1]["p_request_id"]==current["request_id"]


def test_income_credit_rejected_for_secondary_and_invalid_splits(monkeypatch):
    setup_family(monkeypatch)
    calls=[]
    monkeypatch.setattr(db,"call",lambda *a,**k:calls.append((a,k)))
    with TestClient(app) as client:
        invalid=income_payload(True)
        invalid["account_sources"][0]["amount"]=60
        assert client.post("/api/family/transactions",headers=HEADERS,json=invalid).status_code==422
        invalid=income_payload(True)
        invalid["account_sources"][0]["profile_id"]=8
        assert client.post("/api/family/transactions",headers=HEADERS,json=invalid).status_code==422
        invalid=income_payload(True)
        invalid["request_id"]="bad"
        assert client.post("/api/family/transactions",headers=HEADERS,json=invalid).status_code==422
        invalid=income_payload(True)
        invalid["costs"]=[{"profile_id":7,"percentage":50},{"profile_id":8,"percentage":50}]
        assert client.post("/api/family/transactions",headers=HEADERS,json=invalid).status_code==422
        assert client.post("/api/family/transactions",json=income_payload(True)).status_code==403
    assert calls==[]
    setup_family(monkeypatch,role="conjuge")
    with TestClient(app) as client:
        assert client.post("/api/family/transactions",headers=HEADERS,json=income_payload(True)).status_code==403
    assert calls==[]


def test_income_wallet_ui_migration_and_record_button_contract():
    index=(ROOT/"static/index.html").read_text()
    js=(ROOT/"static/family.js").read_text()
    app=(ROOT/"static/app.js").read_text()
    sql=(ROOT/"migrations/20261119_income_wallet_credits.sql").read_text()
    assert '<span>Adicionar registro</span>' in app
    assert 'name="income_balance_mode" value="none" checked' in index
    assert 'name="income_balance_mode" value="wallet"' in index
    assert 'id="family-income-wallet-source-list"' in index
    assert 'data-income-wallet-account' in js
    assert 'incomeWalletSources(form)' in js
    assert 'accountSources=classification==="ENTRADA"?incomeWalletSources(form)' in js
    assert "axora_family_record_income_to_wallet" in sql
    assert "manual_balance=manual_balance+v_row.amount" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "FOR UPDATE OF a" in sql
    assert "SELECT movement_id INTO v_prior" in sql
    assert "p_payments" in sql
    assert "h.family_profile_id=v_profile" in sql
    assert "pluggy_account_id IS NULL" in sql
    assert "finance_family_balance_credits" in sql
    assert "finance_family_balance_credit_sources" in sql
    assert "public.finance_movements" not in sql
    assert "TRUNCATE" not in sql and "DELETE FROM" not in sql
