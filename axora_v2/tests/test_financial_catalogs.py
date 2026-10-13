"""AXORA · Categorias e responsáveis padronizados, sem consultar banco real."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from axora_v2 import catalogs, db, security
from axora_v2.main import app


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OPTIONS = [
    {"id": 1, "kind": "category", "name": "Moradia", "active": True},
    {"id": 2, "kind": "category", "name": "Transporte", "active": True},
    {"id": 3, "kind": "responsible", "name": "Próprio", "active": True},
    {"id": 4, "kind": "responsible", "name": "Sérgio", "active": True},
]


def test_clean_options_and_prevent_unlisted_provisions():
    assert catalogs.clean_option({"kind": "category", "name": "  Educação   continuada "}) == {
        "kind": "category", "name": "Educação continuada"}
    for payload in ({"kind": "wrong", "name": "Teste"},
                    {"kind": "category", "name": " "},
                    {"kind": "responsible", "name": "a" * 121},
                    {"kind": "category", "name": "Moradia", "extra": 1}):
        with pytest.raises(HTTPException):
            catalogs.clean_option(payload)

    values = {"p_category": "moradia", "p_responsible": "sÉrgio"}
    assert catalogs.canonicalize_provision(values, OPTIONS) == {
        "p_category": "Moradia", "p_responsible": "Sérgio"}
    with pytest.raises(HTTPException):
        catalogs.canonicalize_provision({"p_category": "Livre", "p_responsible": "Próprio"}, OPTIONS)


def test_csv_export_supports_excel_and_escapes_formulas():
    content = catalogs.export_csv(OPTIONS + [{
        "id": 5, "kind": "responsible", "name": "=IMPORTXML('bad')", "active": False
    }])
    assert content.startswith("\ufeff")
    assert "Tipo;Nome padronizado;Situação;Orientação" in content
    assert "Categoria;Moradia;Ativo" in content
    assert "Responsável;Sérgio;Ativo" in content
    assert "'=IMPORTXML" in content


def test_catalog_api_is_workspace_scoped_and_requires_csrf(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "fake-key")
    monkeypatch.setenv("SESSION_SECRET", "a" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setattr(security, "current", lambda _request: {
        "id": 12, "is_admin": False, "display_name": "Teste", "csrf": "test-csrf"
    })

    def check_csrf(request, user):
        if request.headers.get("x-csrf-token") != "test-csrf":
            raise HTTPException(403, "CSRF obrigatório")

    monkeypatch.setattr(security, "require_csrf", check_csrf)
    state = [dict(row) for row in OPTIONS]
    calls = []

    def fake_call(method, table, *, params=None, data=None, prefer=None):
        calls.append((method, table, params, data))
        if table == "rpc/axora_user_workspace":
            assert data == {"p_user_id": 12}
            return WORKSPACE
        if table == "rpc/axora_ensure_catalog":
            assert data == {"p_workspace_id": WORKSPACE}
            return 0
        if table == "finance_catalog_options":
            if method == "GET":
                assert params["workspace_id"] == "eq." + WORKSPACE
                return [dict(item) for item in state]
            if method == "POST":
                assert data["workspace_id"] == WORKSPACE
                row = {"id": len(state) + 1, **data}
                state.append(row)
                return [row]
            if method == "PATCH":
                assert params["workspace_id"] == "eq." + WORKSPACE
                row_id = int(params["id"].replace("eq.", ""))
                for item in state:
                    if item["id"] == row_id:
                        item.update(data)
                        return [item]
                return []
        if table == "rpc/axora_create_provision":
            assert data["p_category"] == "Moradia"
            assert data["p_responsible"] == "Sérgio"
            assert data["p_workspace_id"] == WORKSPACE
            return 89
        raise AssertionError("Inesperado: " + table)

    monkeypatch.setattr(db, "call", fake_call)
    with TestClient(app) as client:
        result = client.get("/api/catalogs")
        assert result.status_code == 200
        assert len(result.json()["items"]) == 4
        exported = client.get("/api/catalogs/export")
        assert exported.status_code == 200
        assert exported.content.startswith(b"\xef\xbb\xbf")
        assert "attachment;" in exported.headers["content-disposition"]

        assert client.post("/api/catalogs", json={
            "kind": "category", "name": "Educação"
        }).status_code == 403
        auth = {"X-CSRF-Token": "test-csrf"}
        assert client.post("/api/catalogs", headers=auth, json={
            "kind": "category", "name": "moradia"
        }).status_code == 409
        new = client.post("/api/catalogs", headers=auth, json={
            "kind": "category", "name": "Educação"
        })
        assert new.status_code == 200
        assert new.json()["item"]["name"] == "Educação"
        assert client.patch("/api/catalogs/999", headers=auth, json={
            "active": False
        }).status_code == 404
        assert client.patch("/api/catalogs/2", headers=auth, json={
            "active": False
        }).status_code == 200
        assert client.patch("/api/catalogs/1", headers=auth, json={
            "active": False
        }).status_code == 200  # Categoria Educação permanece ativa.
        assert client.post("/api/provisions", headers=auth, json={
            "description": "Apartamento", "category": "moradia", "responsible": "Sérgio",
            "start_due_date": "2026-10-13", "planned_value": 350,
            "value_mode": "fixed", "recurrence": "unlimited", "frequency": "monthly"
        }).status_code == 422  # Categoria inativa não pode ser usada.
        assert client.patch("/api/catalogs/1", headers=auth, json={
            "active": True
        }).status_code == 200
        result = client.post("/api/provisions", headers=auth, json={
            "description": "Apartamento", "category": "moradia", "responsible": "sérgio",
            "start_due_date": "2026-10-13", "planned_value": 350,
            "value_mode": "fixed", "recurrence": "unlimited", "frequency": "monthly"
        })
        assert result.status_code == 200
        assert result.json()["id"] == 89


def test_frontend_uses_catalog_selects_and_settings_panel():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    main = (ROOT / "static/app.js").read_text(encoding="utf-8")
    provisions = (ROOT / "static/provisions.js").read_text(encoding="utf-8")
    client = (ROOT / "static/catalogs.js").read_text(encoding="utf-8")
    migration = (ROOT / "migrations/20261013_financial_catalogs.sql").read_text(encoding="utf-8")

    assert 'select id="pv-category" name="category"' in html
    assert 'select id="pv-responsible" name="responsible"' in html
    assert 'catalogs.js?v=axora-catalogs-r1' in html
    assert "financialCatalogPanel()" in main
    assert "loadFinanceCatalogs(true)" in provisions
    assert "Exportar listas (CSV)" in client
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "finance_provision_rules" in migration
    assert "DELETE FROM public.finance" not in migration
