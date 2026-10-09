"""Teste de integração HTTP com Supabase substituído por memória: sem dados reais."""
from fastapi.testclient import TestClient

from axora_v2.main import app
from axora_v2 import db, security


def test_login_csrf_and_forecast_edit(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-ci-test-key")
    monkeypatch.setenv("SESSION_SECRET", "s" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    user = {"id": 3, "display_name": "Teste", "is_active": True, "is_admin": True,
            "password_hash": security.hash_password("uma-senha-forte-123")}
    store = {"forecasts": [], "users": [user], "movements": [], "accounts": [], "debts": []}

    def fake_select(kind, *, fields="*", order=None, params=None):
        rows = store.get(kind, [])
        if params and "id" in params:
            pk = int(params["id"].removeprefix("eq."))
            rows = [r for r in rows if int(r["id"]) == pk]
        return [{k: v for k, v in row.items() if fields == "*" or k in fields.split(",")} for row in rows]

    def fake_insert(kind, payload):
        item = {"id": len(store[kind]) + 1, **payload}
        store[kind].append(item)
        return item

    def fake_update(kind, pk, payload):
        for row in store[kind]:
            if row["id"] == pk:
                row.update(payload)
                return [row]
        return []

    monkeypatch.setattr(db, "select", fake_select)
    monkeypatch.setattr(db, "insert", fake_insert)
    monkeypatch.setattr(db, "update", fake_update)
    monkeypatch.setattr(security, "accounts", lambda: [user])

    with TestClient(app) as client:
        assert client.post("/api/login", json={"password":"incorreta"}).status_code == 401
        assert client.post("/api/login", json={"password":"uma-senha-forte-123"}).status_code == 200
        profile = client.get("/api/me").json()
        assert profile["display_name"] == "Teste"
        assert "csrf" in profile
        row = {"description":"Aluguel","value": 1000,"adjustment":-100,"type":"Saída","status":"Não pago"}
        assert client.post("/api/rows/forecasts", json=row).status_code == 403
        csrf = {"X-CSRF-Token": profile["csrf"]}
        response = client.post("/api/rows/forecasts", json=row, headers=csrf)
        assert response.status_code == 200
        assert response.json()["final_value"] == 900
        changed = client.patch("/api/rows/forecasts/1", json={"status":"Pago"}, headers=csrf)
        assert changed.status_code == 200
        assert store["forecasts"][0]["status"] == "Pago"
        assert client.post("/api/logout", headers=csrf).status_code == 200
        assert client.get("/api/me").status_code == 401
