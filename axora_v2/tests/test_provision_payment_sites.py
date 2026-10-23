"""Links para portais oficiais: validação, escopo, segurança e regressão."""
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import provisions, db, security
from axora_v2.main import app

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
URL="https://www.cemig.com.br/segunda-via"


def payload():
    return {
      "description":"Cemig", "category":"Moradia","responsible":"Próprio",
      "start_due_date":"2026-10-22","planned_value":91.57,
      "value_mode":"variable","recurrence":"unlimited","frequency":"monthly",
      "payment_url":URL,
    }


def test_payment_url_accepts_https_while_rejecting_unsafe_schemes_and_hosts():
    assert provisions.clean_payment_url(URL)==URL
    assert provisions.clean_payment_url("") is None
    assert provisions.clean_payment_url(None) is None
    for value in (
        "javascript:alert(1)", "http://www.cemig.com.br",
        "https://localhost/","https://127.0.0.1/login",
        "https://usuario:senha@empresa.com.br/",
        "https://empresa.com.br\\@site.com.br",
        "https://empresa.com.br <script>",
        "https://", "https://empresa.com.br:8443",
        "https://empresa.com.br/" + ("x"*2050),
    ):
        with pytest.raises(HTTPException) as err:
            provisions.clean_payment_url(value)
        assert err.value.status_code==422


def test_existing_clients_without_link_remain_compatible():
    data=payload()
    result=provisions.clean_provision(data)
    assert result["p_payment_url"]==URL
    del data["payment_url"]
    assert "p_payment_url" not in provisions.clean_provision(data)
    edit={"scope":"single","due_date":"2026-10-22","description":"Cemig",
          "category":"Moradia","responsible":"Próprio","planned_value":91.57,
          "value_mode":"variable"}
    assert "p_payment_url" not in provisions.clean_edit_provision(edit)
    assert provisions.clean_edit_provision({**edit,"payment_url":""})["p_payment_url"] is None
    with pytest.raises(HTTPException):
        provisions.clean_edit_provision({**edit,"payment_url":"data:text/html,evil"})


def test_url_routes_csrf_and_atomic_creation_edit(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","ci-test-key")
    monkeypatch.setenv("SESSION_SECRET","v"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(security,"current",lambda _:{"id":9,"csrf":"test-token","is_admin":True})
    def require_csrf(request,_user):
        if request.headers.get("x-csrf-token")!="test-token":
            raise HTTPException(403,"csrf")
    monkeypatch.setattr(security,"require_csrf",require_csrf)
    calls=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        calls.append((method,table,data,params))
        if table=="rpc/axora_user_workspace":return WORKSPACE
        if table=="rpc/axora_ensure_catalog":return 0
        if table=="finance_catalog_options":
            return [{"kind":"category","name":"Moradia","active":True},
                    {"kind":"responsible","name":"Próprio","active":True}]
        if table=="rpc/axora_create_provision_with_link":
            assert data["p_workspace_id"]==WORKSPACE
            assert data["p_payment_url"]==URL
            return 90
        if table=="rpc/axora_edit_provision_with_link":
            assert data["p_workspace_id"]==WORKSPACE
            assert data["p_payment_url"]==URL
            return {"updated":1,"scope":"single"}
        if table=="rpc/axora_ensure_provisions":return 0
        if table=="finance_provision_occurrences":
            return [{"id":101,"due_date":"2026-10-22","planned_value":91.57,
                     "status":"open","rule":{"payment_url":URL}}]
        raise AssertionError(table)
    monkeypatch.setattr(db,"call",fake_call)
    with TestClient(app) as client:
        assert client.post("/api/provisions",json=payload()).status_code==403
        h={"X-CSRF-Token":"test-token"}
        response=client.post("/api/provisions",json=payload(),headers=h)
        assert response.status_code==200 and response.json()["id"]==90
        bad=client.post("/api/provisions",json={**payload(),"payment_url":"javascript:alert(1)"},headers=h)
        assert bad.status_code==422
        edit={"scope":"single","due_date":"2026-10-22","description":"Cemig",
              "category":"Moradia","responsible":"Próprio","planned_value":91.57,
              "value_mode":"variable","payment_url":URL}
        assert client.patch("/api/provisions/101",json=edit).status_code==403
        response=client.patch("/api/provisions/101",json=edit,headers=h)
        assert response.status_code==200
        listed=client.get("/api/provisions")
        assert listed.status_code==200
        assert listed.json()["items"][0]["rule"]["payment_url"]==URL
    assert sum(table=="rpc/axora_create_provision_with_link" for _,table,_,_ in calls)==1


def test_ui_has_new_tab_shortcut_and_sql_atomic_update():
    js=(ROOT/"static/provisions.js").read_text()
    html=(ROOT/"static/index.html").read_text()
    sql=(ROOT/"migrations/20261023_provision_payment_sites.sql").read_text()
    assert 'name="payment_url"' in html
    assert 'id="pv-payment-url"' in html and 'id="pve-payment-url"' in html
    assert "Acessar site" in js
    assert 'target="_blank"' in js
    assert 'rel="noopener noreferrer"' in js
    assert 'new URL(String(value))' in js
    assert "finance_provision_rules" in sql
    assert "payment_url" in sql
    assert "axora_create_provision_with_link" in sql
    assert "axora_edit_provision_with_link" in sql
    assert "DELETE FROM" not in sql.upper() and "TRUNCATE" not in sql.upper()
