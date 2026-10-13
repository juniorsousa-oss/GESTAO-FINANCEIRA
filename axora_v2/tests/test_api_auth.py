"""AXORA nativo: autenticação, workspace e desativação do legado Excel."""
from fastapi.testclient import TestClient

from axora_v2.main import app
from axora_v2 import db, security


WORKSPACE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_login_csrf_and_new_records_are_private(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-ci-test-key")
    monkeypatch.setenv("SESSION_SECRET", "s" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    user = {"id": 3, "display_name": "Teste", "is_active": True, "is_admin": True,
            "password_hash": security.hash_password("uma-senha-forte-123")}
    store = {"users": [user], "movements": []}

    def fake_select(kind, *, fields="*", order=None, params=None):
        rows = store.get(kind, [])
        if params and "workspace_id" in params:
            workspace = params["workspace_id"].removeprefix("eq.")
            rows = [r for r in rows if r.get("workspace_id") == workspace]
        if params and "id" in params:
            pk = int(params["id"].removeprefix("eq."))
            rows = [r for r in rows if int(r["id"]) == pk]
        return [{k: v for k, v in row.items() if fields == "*" or k in fields.split(",")} for row in rows]

    def fake_insert(kind, payload):
        row = {"id": len(store[kind]) + 1, **payload}
        store[kind].append(row)
        return row

    def fake_call(method, table, *, params=None, data=None, prefer=None):
        if table == "rpc/axora_user_workspace":
            assert data == {"p_user_id": 3}
            return WORKSPACE
        raise AssertionError("RPC unexpectedly accessed: " + table)

    monkeypatch.setattr(db, "select", fake_select)
    monkeypatch.setattr(db, "insert", fake_insert)
    monkeypatch.setattr(db, "call", fake_call)
    monkeypatch.setattr(security, "accounts", lambda: [user])

    with TestClient(app) as client:
        assert client.post("/api/login", json={"password":"incorreta"}).status_code == 401
        assert client.post("/api/login", json={"password":"uma-senha-forte-123"}).status_code == 200
        profile = client.get("/api/me").json()
        csrf = {"X-CSRF-Token": profile["csrf"]}
        row = {"description": "Salário", "value": 3000, "classification": "ENTRADA"}
        assert client.post("/api/rows/movements", json=row).status_code == 403
        created = client.post("/api/rows/movements", json=row, headers=csrf)
        assert created.status_code == 200
        assert created.json()["workspace_id"] == WORKSPACE
        assert len(store["movements"]) == 1
        assert client.post("/api/rows/forecasts", json={
            "description": "Conta", "value": 20, "type": "Saída"
        }, headers=csrf).status_code == 410
        assert client.post("/api/import/commit", headers=csrf).status_code == 410
        assert client.post("/api/logout", headers=csrf).status_code == 200
        assert client.get("/api/me").status_code == 401
