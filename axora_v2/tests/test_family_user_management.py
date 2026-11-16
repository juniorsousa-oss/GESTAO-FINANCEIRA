"""Cadastramento familiar: principal sem privilégios globais e isolamento DEMO/Pessoal."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db, family_service, security
from axora_v2.main import app

W = "eeeeeeee-bbbb-cccc-dddd-aaaaaaaaaaaa"
OWNER = {"id":3,"display_name":"Responsável pessoal","is_admin":False,"is_active":True,"csrf":"csrf"}
CTX = {"workspace_id":W,"profile_id":9,"role":"principal","user_id":3,"owner_id":3}
EXISTING = security.hash_password("SenhaTesteExistente8877")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","falso-em-testes")
    monkeypatch.setenv("SESSION_SECRET","h"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setenv("AXORA_FAMILY_V2_ENABLED","1")
    monkeypatch.setenv("AXORA_ENV","")
    monkeypatch.setattr(security,"current",lambda _:dict(OWNER))
    monkeypatch.setattr(family_service,"context",lambda _:dict(CTX))
    monkeypatch.setattr(security,"require_csrf",
        lambda req,u: None if req.headers.get("x-csrf-token")=="csrf" else
        (_ for _ in ()).throw(HTTPException(403,"CSRF")))
    monkeypatch.setattr(security,"accounts",lambda:[
        {"id":1,"display_name":"Demo","password_hash":EXISTING,"is_admin":True,"is_active":True}
    ])
    recorded=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        if table=="rpc/axora_family_upsert_member":
            recorded.append(data)
            assert data["p_workspace_id"]==W
            assert data["p_actor_id"]==3
            assert data["p_relationship"] in ("conjuge","filho","outro")
            return {"id":50,"display_name":data["p_display_name"],"relationship":data["p_relationship"],
                    "linked_user_id":80 if data["p_password_hash"] else None,
                    "active":True,"access":"login" if data["p_password_hash"] else "perfil"}
        if table=="rpc/axora_family_change_relationship":
            recorded.append(data)
            assert data["p_workspace_id"]==W and data["p_actor_id"]==3
            return {"ok":True,"relationship":data["p_relationship"]}
        if table=="finance_family_profiles":
            assert params["workspace_id"]=="eq."+W
            return [{"id":50,"display_name":"Dependente","relationship":"filho",
                     "linked_user_id":None,"active":True}]
        raise AssertionError("Consulta fora do núcleo: "+table)
    monkeypatch.setattr(db,"call",fake_call)
    monkeypatch.setattr(family_service,"profiles",lambda user:[
        {"id":9,"display_name":"Responsável pessoal","relationship":"principal",
         "linked_user_id":3,"active":True},
        {"id":50,"display_name":"Dependente","relationship":"filho",
         "linked_user_id":None,"active":True}
    ])
    return recorded


def test_nonadmin_principal_creates_secondary_login_atomically(env):
    with TestClient(app) as client:
        data={"display_name":"Pessoa da família","relationship":"conjuge",
              "password":"NovaSenhaUnica2026!"}
        assert client.post("/api/family/members",json=data).status_code==403
        res=client.post("/api/family/members",json=data,
                        headers={"X-CSRF-Token":"csrf"})
        assert res.status_code==200
        assert res.json()["linked_user_id"]==80
        assert len(env)==1
        assert env[0]["p_password_hash"].startswith("pbkdf2_sha256$")
        assert "NovaSenhaUnica2026!" not in str(env[0])
        assert env[0]["p_profile_id"] is None


def test_principal_can_create_cost_profile_without_login(env):
    with TestClient(app) as client:
        res=client.post("/api/family/members",json={
            "display_name":"Criança","relationship":"filho","password":None
        },headers={"X-CSRF-Token":"csrf"})
        assert res.status_code==200
        assert res.json()["access"]=="perfil"
        assert env[0]["p_password_hash"] is None


def test_weak_or_duplicated_password_and_principal_role_rejected(env):
    with TestClient(app) as client:
        headers={"X-CSRF-Token":"csrf"}
        for value in [
            {"display_name":"Pessoa","relationship":"principal","password":None},
            {"display_name":"Pessoa","relationship":"conjuge","password":"curta"},
            {"display_name":"Pessoa","relationship":"conjuge","password":"SenhaTesteExistente8877"},
            {"display_name":"Pessoa","relationship":"viewer","password":None},
        ]:
            assert client.post("/api/family/members",json=value,headers=headers).status_code==422
        assert env==[]


def test_principal_can_enable_login_and_change_secondary_relationship(env):
    with TestClient(app) as client:
        h={"X-CSRF-Token":"csrf"}
        res=client.post("/api/family/profiles/50/enable-login",
            json={"password":"OutraSenhaSegura!2026"},headers=h)
        assert res.status_code==200
        assert env[0]["p_profile_id"]==50
        assert env[0]["p_password_hash"].startswith("pbkdf2_sha256$")
        changed=client.post("/api/family/profiles/50/relationship",
            json={"relationship":"outro"},headers=h)
        assert changed.status_code==200
        assert env[-1]["p_profile_id"]==50
        assert env[-1]["p_relationship"]=="outro"
        assert client.post("/api/family/profiles/50/relationship",
            json={"relationship":"principal"},headers=h).status_code==422
        assert client.post("/api/family/profiles/50/link",
            json={"user_id":1},headers=h).status_code==410


def test_secondary_cannot_create_users_or_enumerate_other_workspaces(env,monkeypatch):
    monkeypatch.setattr(family_service,"context",lambda _:{
        **CTX,"role":"conjuge","user_id":2,"profile_id":22
    })
    monkeypatch.setattr(security,"current",lambda _:{"id":2,"display_name":"Secundário","csrf":"csrf","is_admin":False})
    with TestClient(app) as client:
        h={"X-CSRF-Token":"csrf"}
        assert client.post("/api/family/members",json={
            "display_name":"Intruso","relationship":"filho","password":None},headers=h).status_code==403
        assert client.get("/api/users").status_code==403
        assert client.post("/api/family/profiles/50/relationship",
            json={"relationship":"conjuge"},headers=h).status_code==403
        assert env==[]


def test_nonadmin_principal_user_listing_only_own_family(env):
    with TestClient(app) as client:
        res=client.get("/api/users")
        assert res.status_code==200
        data=res.json()
        assert [p["display_name"] for p in data]==["Responsável pessoal"]
        assert "Demo" not in res.text
        assert client.post("/api/users",json={
            "display_name":"Outro principal","password":"Unique-Password-2026!"},
            headers={"X-CSRF-Token":"csrf"}).status_code==403


def test_family_ui_no_longer_fetches_global_user_directory():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/"static"
    js=(root/"family.js").read_text()
    appjs=(root/"app.js").read_text()
    html=(root/"index.html").read_text()
    assert 'api("/api/users")' not in js
    assert '/api/family/members' in js
    assert '/api/family/profiles/' in js
    assert 'name="password" type="password"' in js
    assert 'name="confirm_password" type="password"' in js
    assert "family-access-dialog" in html
    assert "Família e usuários" in html
    assert 'me.is_admin&&!me.family_enabled' in appjs
