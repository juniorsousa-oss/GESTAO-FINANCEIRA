"""Pluggy piloto: autenticação segura, vinculação consentida, importação idempotente."""
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import pluggy, db, security
from axora_v2.main import app

W="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
INTENT="f77e5ef1-e109-4254-b94a-3395a9e83a17"
ITEM="73ca9d85-68ac-4aca-b8e0-5db7cf04f2fd"
ACCOUNT="a96c3400-5e9d-40e3-8e3a-9225293850cc"


def test_pluggy_off_by_default(monkeypatch):
    monkeypatch.delenv("PLUGGY_CLIENT_ID",raising=False)
    monkeypatch.delenv("PLUGGY_CLIENT_SECRET",raising=False)
    monkeypatch.delenv("PLUGGY_ENABLE_LIVE",raising=False)
    assert pluggy.ready() is False
    assert pluggy.live_enabled() is False
    with pytest.raises(HTTPException) as e:
        pluggy.key()
    assert e.value.status_code==503


def test_provider_signs_using_type_and_excludes_pending(monkeypatch):
    def fake(method,path,*,params=None,payload=None):
        assert method=="GET" and path=="/transactions"
        assert params["pageSize"]==100
        return {"results":[
            {"id":"26c2f788-5cb9-4d09-917d-ec5f879c119a","date":"2026-10-13T00:00:00Z",
             "description":"Mercado","type":"DEBIT","amount":150,"status":"POSTED","currencyCode":"BRL"},
            {"id":"25067a03-23fd-4967-bd45-d69634fa4d07","date":"2026-10-13T00:00:00Z",
             "description":"Salário","type":"CREDIT","amount":1000,"status":"POSTED","currencyCode":"BRL"},
            {"id":"b6a3f977-731e-49ea-92bc-51f6bd844868","date":"2026-10-13T00:00:00Z",
             "description":"Pendente","type":"DEBIT","amount":12,"status":"PENDING","currencyCode":"BRL"}
        ]}
    monkeypatch.setattr(pluggy,"request",fake)
    data=pluggy.postable_transactions(ACCOUNT)
    assert len(data)==2
    assert data[0]["amount"]==-150
    assert data[1]["amount"]==1000
    assert all(x["source"]=="import" and x["external_ref"].startswith("pluggy:") for x in data)


def test_item_must_match_intent_and_sandbox(monkeypatch):
    monkeypatch.delenv("PLUGGY_ENABLE_LIVE",raising=False)
    def fake(method,path,*,params=None,payload=None):
        return {"clientUserId":INTENT,"connector":{"isSandbox":True},"status":"UPDATED"}
    monkeypatch.setattr(pluggy,"request",fake)
    assert pluggy.item_details(ITEM,INTENT)["status"]=="UPDATED"
    with pytest.raises(HTTPException) as err:
        pluggy.item_details(ITEM,"other-intent")
    assert err.value.status_code==403
    monkeypatch.setattr(pluggy,"request",lambda *a,**kw:{
        "clientUserId":INTENT,"connector":{"isSandbox":False},"status":"UPDATED"})
    with pytest.raises(HTTPException) as err:
        pluggy.item_details(ITEM,INTENT)
    assert err.value.status_code==403


def test_routes_scope_and_manual_confirmation(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","test-key")
    monkeypatch.setenv("SESSION_SECRET","a"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setenv("PLUGGY_CLIENT_ID","fake-id")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET","fake-secret")
    monkeypatch.delenv("PLUGGY_ENABLE_LIVE",raising=False)
    monkeypatch.setattr(security,"current",lambda _:{"id":5,"csrf":"token","is_admin":True})
    def csrf(request,_user):
        if request.headers.get("x-csrf-token")!="token":raise HTTPException(403,"csrf")
    monkeypatch.setattr(security,"require_csrf",csrf)
    monkeypatch.setattr(pluggy,"allowed_sandbox_connector",lambda:999)
    monkeypatch.setattr(pluggy,"connect_token",lambda reference:"safe-short-term-token")
    monkeypatch.setattr(pluggy,"item_details",lambda *_:{
        "clientUserId":INTENT,"connector":{"isSandbox":True},"status":"UPDATED"})
    monkeypatch.setattr(pluggy,"bank_accounts",lambda item_id:[{
        "id":ACCOUNT,"type":"BANK","currencyCode":"BRL","balance":500.50,
        "number":"****0123","owner":"Titular do consentimento","name":"Conta digital",
    }])
    monkeypatch.setattr(pluggy,"request",lambda *args,**kwargs:{
        "status":"UPDATED","connector":{"isSandbox":True}})
    monkeypatch.setattr(pluggy,"postable_transactions",lambda *_:[
        {"posted_on":"2026-10-13","description":"Teste externo","amount":-50,
         "source":"import","external_ref":"pluggy:26c2f788-5cb9-4d09-917d-ec5f879c119a"}])
    from datetime import datetime,timedelta,timezone
    expires=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()
    axora_account={"id":2,"holder_id":1,"workspace_id":W,"nickname":"Nubank pessoal",
                   "bank_name":"Nubank","pluggy_account_id":None,
                   "pluggy_item_id":None,"pluggy_sandbox":None}
    intent={"id":INTENT,"workspace_id":W,"initiated_by":5,"account_id":2,
            "expires_at":expires,"completed_at":None}
    calls=[]
    def fake(method,table,*,params=None,data=None,prefer=None):
        calls.append((method,table,params,data,prefer))
        if table=="rpc/axora_user_workspace":
            return W
        if table=="finance_bank_accounts":
            assert params["workspace_id"]=="eq."+W
            if method=="GET":return [axora_account]
            if method=="PATCH":
                assert params["id"]=="eq.2"
                axora_account.update(data)
                return [axora_account] if prefer=="return=representation" else []
        if table=="finance_pluggy_intents":
            if method=="POST":return [intent]
            if method=="GET":return [intent]
            if method=="PATCH":
                intent.update(data)
                return []
        if table=="finance_bank_transactions":
            assert params["on_conflict"]=="account_id,source,external_ref"
            assert prefer.startswith("resolution=ignore-duplicates")
            assert len(data)==1
            assert data[0]["status"] if "status" in data[0] else True
            return []
        raise AssertionError((method,table))
    monkeypatch.setattr(db,"call",fake)
    with TestClient(app) as c:
        assert c.post("/api/banking/pluggy/start",json={
            "account_id":2,"consent_confirmed":True}).status_code==403
        headers={"X-CSRF-Token":"token"}
        assert c.post("/api/banking/pluggy/start",headers=headers,json={
            "account_id":2,"consent_confirmed":False}).status_code==422
        start=c.post("/api/banking/pluggy/start",headers=headers,json={
            "account_id":2,"consent_confirmed":True})
        assert start.status_code==200
        assert start.json()["sandbox_connector_id"]==999
        assert start.json()["connect_token"]=="safe-short-term-token"
        complete=c.post("/api/banking/pluggy/complete",headers=headers,json={
            "intent_id":INTENT,"item_id":ITEM})
        assert complete.status_code==200
        assert complete.json()["accounts"][0]["last_digits"]=="0123"
        linked=c.post("/api/banking/pluggy/link",headers=headers,json={
            "intent_id":INTENT,"item_id":ITEM,"provider_account_id":ACCOUNT,"confirm_account":True})
        assert linked.status_code==200
        assert axora_account["connection_status"]=="pluggy_sandbox"
        synced=c.post("/api/banking/pluggy/sync/2",headers=headers,json={})
        assert synced.status_code==200
        assert synced.json()["received"]==1
        assert not any(t in str(calls) for t in ["finance_movements","axora_pay_provision"])


def test_sources_ensure_no_banking_passwords():
    root=Path(__file__).resolve().parents[1]
    page=(root/"static/index.html").read_text()
    client=(root/"static/pluggy-connect.js").read_text()
    backend=(root/"main.py").read_text()
    schema=(root/"migrations/20261014_pluggy_readonly_pilot.sql").read_text()
    assert "bank-pluggy-dialog" in page
    assert "pluggy-connect.js" in page
    assert "connectToken" in client and "connectorIds" in client
    assert "clientSecret" not in client and "PLUGGY_CLIENT_SECRET" not in client
    assert "frame-src https://connect.pluggy.ai" in backend
    assert "finance_pluggy_intents" in schema
    assert "ENABLE ROW LEVEL SECURITY" in schema
    assert "TRUNCATE" not in schema.upper()
    assert "DELETE FROM" not in schema.upper()
