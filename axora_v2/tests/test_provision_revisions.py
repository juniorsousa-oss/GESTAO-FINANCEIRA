"""Regressões de revisão e cancelamento de Provisões, sem banco real."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db, provisions, security
from axora_v2.main import app

BASE = Path(__file__).resolve().parents[1]
WORKSPACE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
EDIT = {
    "scope": "single", "due_date": "2026-11-13", "description": "Seguro",
    "category": "Transporte", "responsible": "Próprio",
    "planned_value": 100.50, "value_mode": "fixed",
}


def test_term_with_quantity_and_legacy_end_date():
    term = provisions.clean_provision({
        "description": "Apartamento", "category": "Moradia", "responsible": "Próprio",
        "start_due_date": "2026-10-20", "planned_value": 732.74,
        "value_mode": "fixed", "recurrence": "until_date", "frequency": "monthly",
        "installment_count": 18,
    })
    assert term["p_installment_count"] == 18
    assert term["p_end_date"] is None
    old = provisions.clean_provision({
        "description": "Apartamento", "category": "Moradia", "responsible": "Próprio",
        "start_due_date": "2026-10-20", "planned_value": 732.74,
        "value_mode": "fixed", "recurrence": "until_date", "frequency": "monthly",
        "end_date": "2027-11-20",
    })
    assert old["p_end_date"] == "2027-11-20"
    for count in (0, 361, -1, "invalid"):
        with pytest.raises(HTTPException):
            provisions.clean_provision({
                "description": "Aluguel", "category": "Moradia", "responsible": "Próprio",
                "start_due_date": "2026-10-20", "planned_value": 120,
                "value_mode": "fixed", "recurrence": "until_date",
                "frequency": "monthly", "installment_count": count,
            })


def test_validate_scope_edit_and_money():
    assert provisions.clean_scope("future") == "future"
    assert provisions.clean_scope("single") == "single"
    assert provisions.clean_edit_provision(EDIT)["p_due_date"] == "2026-11-13"
    for scope in ("all", "prior", "", None):
        with pytest.raises(HTTPException):
            provisions.clean_scope(scope)
    for modification in (
        {"planned_value": 0}, {"planned_value": -10},
        {"description": ""}, {"due_date": "invalid"},
        {"value_mode": "wrong"}, {"scope": "all"}, {"category": ""},
    ):
        with pytest.raises(HTTPException):
            provisions.clean_edit_provision({**EDIT, **modification})


def test_edit_cancel_routes_scoped_and_csrf(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "fake-test-key")
    monkeypatch.setenv("SESSION_SECRET", "t" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setattr(security, "current", lambda _request: {
        "id": 5, "is_admin": True, "csrf": "secure-test",
    })
    def csrf(request, _user):
        if request.headers.get("x-csrf-token") != "secure-test":
            raise HTTPException(403, "CSRF ausente")
    monkeypatch.setattr(security, "require_csrf", csrf)
    calls = []

    def fake_call(method, table, *, params=None, data=None, prefer=None):
        calls.append((method, table, data))
        if table == "rpc/axora_user_workspace":
            return WORKSPACE
        if table == "rpc/axora_ensure_catalog":
            return 0
        if table == "finance_catalog_options":
            return [
                {"kind": "category", "name": "Transporte", "active": True},
                {"kind": "responsible", "name": "Próprio", "active": True},
            ]
        if table == "rpc/axora_edit_provision":
            return {"updated": 3, "scope": data["p_scope"]}
        if table == "rpc/axora_cancel_provision":
            return {"cancelled": 2, "scope": data["p_scope"]}
        raise AssertionError("Unexpected table " + table)

    monkeypatch.setattr(db, "call", fake_call)
    with TestClient(app) as client:
        assert client.patch("/api/provisions/19", json=EDIT).status_code == 403
        assert client.post("/api/provisions/19/cancel", json={"scope": "future"}).status_code == 403
        auth = {"X-CSRF-Token": "secure-test"}
        assert client.patch("/api/provisions/19", json=EDIT, headers=auth).json()["updated"] == 3
        assert client.patch("/api/provisions/19", json={**EDIT, "scope": "all"}, headers=auth).status_code == 422
        assert client.post("/api/provisions/19/cancel", json={"scope": "future"}, headers=auth).json()["cancelled"] == 2
        assert client.post("/api/provisions/19/cancel", json={"scope": "bad"}, headers=auth).status_code == 422

    assert ("POST", "rpc/axora_edit_provision", {
        "p_workspace_id": WORKSPACE, "p_occurrence_id": 19, "p_scope": "single",
        "p_due_date": "2026-11-13", "p_description": "Seguro",
        "p_category": "Transporte", "p_responsible": "Próprio",
        "p_planned_value": 100.5, "p_value_mode": "fixed"
    }) in calls
    assert ("POST", "rpc/axora_cancel_provision", {
        "p_workspace_id": WORKSPACE, "p_occurrence_id": 19, "p_scope": "future"
    }) in calls


def test_sql_keeps_paid_history_and_prevents_regeneration():
    sql = (BASE / "migrations/20261013_provisions_revisions.sql").read_text()
    assert "status='open'" in sql
    assert "status='cancelled'" in sql
    assert "stop_before_sequence" in sql
    assert "ON CONFLICT(rule_id,sequence_no) DO NOTHING" in sql
    assert "axora_due_at" in sql
    assert "finance_provision_revisions" in sql
    assert "p_scope='future'" in sql
    assert "coalesce(i.description_override,r.description)" in sql
    assert "finance_movements" in sql
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()


def test_frontend_shows_scopes_and_quantity():
    html = (BASE / "static/index.html").read_text()
    js = (BASE / "static/provisions.js").read_text()
    assert 'id="provision-edit-dialog"' in html
    assert 'id="provision-cancel-dialog"' in html
    assert 'id="pv-count-label"' in html
    assert 'id="provision-end-wrap"' not in html
    assert 'data-action="edit-provision"' in js
    assert 'data-action="cancel-provision"' in js
    assert "value=\"future\"" in html
    assert '"PATCH"' in js
    assert '"/cancel"' in js
