"""Onboarding: novo login cria seu próprio workspace e perfil principal."""
from fastapi.testclient import TestClient
from axora_v2 import db,security,family_service
from axora_v2.main import app

W="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeef"

def test_principal_onboarding_does_not_attach_demo_workspace(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake")
    monkeypatch.setenv("SESSION_SECRET","z"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setenv("AXORA_FAMILY_V2_ENABLED","1")
    monkeypatch.setenv("AXORA_ENV","")
    person={"id":100,"display_name":"Conta pessoal","is_admin":False,"is_active":True,"csrf":"csrf"}
    profiles=[]
    monkeypatch.setattr(security,"current",lambda _:dict(person))
    monkeypatch.setattr(security,"require_csrf",
        lambda req,user: None if req.headers.get("X-CSRF-Token")=="csrf" else (_ for _ in ()).throw(__import__("fastapi").HTTPException(403,"CSRF")))
    monkeypatch.setattr(family_service,"context",lambda _:None)
    def call(method,table,*,params=None,data=None,prefer=None):
        if table=="rpc/axora_user_workspace":
            assert data=={"p_user_id":100}
            return W
        if table=="finance_workspaces":
            return [{"id":W,"created_by":100,"is_active":True}]
        if table=="finance_family_profiles":
            if method=="GET":return list(profiles)
            if method=="POST":
                assert data["workspace_id"]==W
                assert data["relationship"]=="principal" and data["linked_user_id"]==100
                profiles.append({"id":9,**data})
                return list(profiles)
        raise AssertionError((method,table,params,data))
    monkeypatch.setattr(db,"call",call)
    with TestClient(app) as client:
        assert client.post("/api/family/onboard").status_code==403
        assert client.post("/api/family/onboard",headers={"X-CSRF-Token":"csrf"}).status_code==200
        assert len(profiles)==1
        response=client.post("/api/family/onboard",headers={"X-CSRF-Token":"csrf"})
        assert response.status_code==200 and response.json()["created"] is False
        assert len(profiles)==1


def test_onboarding_rejects_workspace_belonging_to_other_principal(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake")
    monkeypatch.setenv("SESSION_SECRET","z"*64)
    monkeypatch.setenv("AXORA_FAMILY_V2_ENABLED","1")
    monkeypatch.setenv("AXORA_ENV","")
    person={"id":101,"display_name":"Não autorizado","is_admin":False,"is_active":True,"csrf":"csrf"}
    monkeypatch.setattr(security,"current",lambda _:dict(person))
    monkeypatch.setattr(security,"require_csrf",lambda *_:None)
    monkeypatch.setattr(family_service,"context",lambda _:None)
    def call(method,table,*,params=None,data=None,prefer=None):
        if table=="rpc/axora_user_workspace":return W
        if table=="finance_workspaces":return [{"id":W,"created_by":200,"is_active":True}]
        raise AssertionError("Onboarding não pode escrever em workspace de terceiros.")
    monkeypatch.setattr(db,"call",call)
    with TestClient(app) as client:
        assert client.post("/api/family/onboard",headers={"X-CSRF-Token":"csrf"}).status_code==403
