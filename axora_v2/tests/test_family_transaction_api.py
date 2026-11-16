"""Fluxos de registro e rateio familiar com banco simulado, sem dados reais."""
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db,security,family_service
from axora_v2.main import app

W="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CTX={"workspace_id":W,"profile_id":9,"role":"principal","owner_id":7,"user_id":7}


def test_family_record_split_validated_before_atomic_rpc(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake")
    monkeypatch.setenv("SESSION_SECRET","a"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(security,"current",lambda _:{"id":7,"is_admin":True,"csrf":"csrf"})
    monkeypatch.setattr(family_service,"context",lambda _:dict(CTX))
    monkeypatch.setattr(security,"require_csrf",
        lambda req,user: None if req.headers.get("x-csrf-token")=="csrf" else (_ for _ in ()).throw(HTTPException(403,"CSRF")))
    calls=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        if table=="finance_family_profiles":
            return [
                {"id":9,"display_name":"Principal","relationship":"principal","active":True,
                 "linked_user_id":7},
                {"id":10,"display_name":"Cônjuge","relationship":"conjuge","active":True,
                 "linked_user_id":8},
                {"id":11,"display_name":"Dependente","relationship":"filho","active":True,
                 "linked_user_id":None}
            ]
        if table=="rpc/axora_family_record":
            calls.append(data)
            return {"ok":True,"movement_id":43}
        raise AssertionError(table)
    monkeypatch.setattr(db,"call",fake_call)
    valid={"date":"2026-11-16","description":"Despesa escolar","value":300,
           "classification":"SAÍDA","category":"ESCOLA","label":"casal",
           "costs":[{"profile_id":11,"percentage":100}],
           "payments":[{"profile_id":9,"amount":200},{"profile_id":10,"amount":100}]}
    with TestClient(app) as client:
        assert client.post("/api/family/transactions",json=valid).status_code==403
        ok=client.post("/api/family/transactions",json=valid,
                        headers={"X-CSRF-Token":"csrf"})
        assert ok.status_code==200 and ok.json()["movement_id"]==43
        assert calls[0]["p_workspace_id"]==W and calls[0]["p_actor_id"]==7
        assert calls[0]["p_costs"]==[{"profile_id":11,"amount":"300.00"}]
        assert calls[0]["p_payments"]==[
          {"profile_id":9,"amount":"200.00","source_account_id":None},
          {"profile_id":10,"amount":"100.00","source_account_id":None}]
        assert calls[0]["p_label"]=="casal"
        # Erros não podem criar linha ou rateio parcial.
        invalid=dict(valid,payments=[{"profile_id":9,"amount":200}])
        assert client.post("/api/family/transactions",json=invalid,
            headers={"X-CSRF-Token":"csrf"}).status_code==422
        invalid=dict(valid,costs=[{"profile_id":11,"percentage":90}])
        assert client.post("/api/family/transactions",json=invalid,
            headers={"X-CSRF-Token":"csrf"}).status_code==422
        invalid=dict(valid,costs=[{"profile_id":999,"percentage":100}])
        assert client.post("/api/family/transactions",json=invalid,
            headers={"X-CSRF-Token":"csrf"}).status_code==422
        assert len(calls)==1


def test_child_cannot_write_costs_or_change_visibility(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake")
    monkeypatch.setenv("SESSION_SECRET","a"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(security,"current",lambda _:{"id":12,"is_admin":False,"csrf":"csrf"})
    monkeypatch.setattr(family_service,"context",
        lambda _:{**CTX,"role":"filho","user_id":12,"profile_id":11})
    monkeypatch.setattr(security,"require_csrf",lambda req,user:None)
    monkeypatch.setattr(db,"call",lambda *a,**kw: (_ for _ in ()).throw(AssertionError("DB write attempted")))
    with TestClient(app) as client:
        body={"date":"2026-11-16","description":"teste","value":50,
           "classification":"SAÍDA","category":"OUTROS","label":"privado",
           "costs":[{"profile_id":11,"percentage":100}],
           "payments":[{"profile_id":11,"amount":50}]}
        assert client.post("/api/family/transactions",json=body,
            headers={"X-CSRF-Token":"csrf"}).status_code==403
        assert client.post("/api/family/visibility",json={
            "resource_type":"registro","resource_id":9,"label":"casal","viewers":[]
        },headers={"X-CSRF-Token":"csrf"}).status_code==403
