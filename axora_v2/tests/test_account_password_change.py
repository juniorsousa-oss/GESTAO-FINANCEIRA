"""Troca de senha sem expor credenciais, com invalidação de cookies anteriores."""
from fastapi.testclient import TestClient
from axora_v2 import db,security
from axora_v2.main import app


def test_password_change_requires_csrf_and_invalidates_other_sessions(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake")
    monkeypatch.setenv("SESSION_SECRET","w"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setenv("AXORA_FAMILY_V2_ENABLED","0")
    monkeypatch.setenv("AXORA_ENV","")
    security.FAILURES.clear()
    security.PASSWORD_FAILURES.clear()
    own={"id":200,"display_name":"Titular","password_hash":security.hash_password("Senha-Inicial-ABCD-1234"),"is_active":True,"is_admin":True}
    other={"id":201,"display_name":"Outro","password_hash":security.hash_password("Outra-Senha-ABCD-1234"),"is_active":True,"is_admin":False}
    store=[own,other]

    def select(kind,*,fields="*",order=None,params=None):
        if kind!="users":raise AssertionError("Outra tabela consultada: "+kind)
        rows=store
        if params and "id" in params:
            uid=int(params["id"].removeprefix("eq."))
            rows=[r for r in rows if r["id"]==uid]
        return [{key:value for key,value in row.items() if fields=="*" or key in fields.split(",")} for row in rows]
    def update(kind,pk,payload,*,workspace_id=None):
        assert kind=="users" and pk==200 and set(payload)=={"password_hash"}
        own.update(payload)
        return [own]
    monkeypatch.setattr(db,"select",select)
    monkeypatch.setattr(db,"update",update)
    monkeypatch.setattr(security,"accounts",lambda:store)

    with TestClient(app) as client:
        assert client.post("/api/login",json={"password":"Senha-Inicial-ABCD-1234"}).status_code==200
        old_session=client.cookies.get(security.COOKIE)
        csrf=client.get("/api/me").json()["csrf"]
        payload={"current_password":"Senha-Inicial-ABCD-1234","new_password":"Nova-Senha-Segura-56789"}
        assert client.post("/api/profile/password",json=payload).status_code==403
        assert client.post("/api/profile/password",json={**payload,"current_password":"incorreta"},
            headers={"X-CSRF-Token":csrf}).status_code==401
        assert client.post("/api/profile/password",json={**payload,"new_password":"Outra-Senha-ABCD-1234"},
            headers={"X-CSRF-Token":csrf}).status_code==422
        response=client.post("/api/profile/password",json=payload,headers={"X-CSRF-Token":csrf})
        assert response.status_code==200 and response.json()["reauthenticate"] is True
        assert client.get("/api/me").status_code==401
        # Outro dispositivo logado antes da troca também perde a sessão.
        client.cookies.set(security.COOKIE,old_session)
        assert client.get("/api/me").status_code==401
        client.cookies.delete(security.COOKIE)
        assert client.post("/api/login",json={"password":"Senha-Inicial-ABCD-1234"}).status_code==401
        assert client.post("/api/login",json={"password":"Nova-Senha-Segura-56789"}).status_code==200
        assert client.get("/api/me").status_code==200


def test_password_form_is_present_for_all_roles():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/"static"/"app.js").read_text()
    assert "password-change-form" in source
    assert 'autocomplete="current-password"' in source
    assert 'autocomplete="new-password"' in source
    assert '"/api/profile/password"' in source
