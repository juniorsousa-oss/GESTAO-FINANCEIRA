"""Regressões da primeira etapa de Provisões; não usa Supabase real."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from axora_v2 import db, provisions, security
from axora_v2.main import app


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def valid_rule(**overrides):
    return {
        "description": "Internet", "category": "Moradia",
        "responsible": "Próprio", "start_due_date": "2026-10-20",
        "planned_value": 130, "value_mode": "variable",
        "recurrence": "unlimited", "frequency": "monthly",
        **overrides,
    }


def test_recurring_provision_validation_and_deadlines():
    monthly = provisions.clean_provision(valid_rule())
    assert monthly["p_recurrence"] == "unlimited"
    assert monthly["p_end_date"] is None
    assert monthly["p_installment_count"] is None
    fixed = provisions.clean_provision(valid_rule(
        recurrence="installments", installment_count=10, frequency="monthly"
    ))
    assert fixed["p_installment_count"] == 10
    temporary = provisions.clean_provision(valid_rule(
        recurrence="until_date", end_date="2027-10-20"
    ))
    assert temporary["p_end_date"] == "2027-10-20"
    once = provisions.clean_provision(valid_rule(recurrence="once"))
    assert once["p_recurrence"] == "once"
    with pytest.raises(HTTPException):
        provisions.clean_provision(valid_rule(recurrence="until_date", end_date="2026-10-01"))
    with pytest.raises(HTTPException):
        provisions.clean_provision(valid_rule(recurrence="installments", installment_count=0))
    with pytest.raises(HTTPException):
        provisions.clean_provision(valid_rule(planned_value=0))
    with pytest.raises(HTTPException):
        provisions.clean_provision(valid_rule(planned_value="-50"))
    with pytest.raises(HTTPException):
        provisions.clean_provision(valid_rule(planned_value="10.123"))
    with pytest.raises(HTTPException):
        provisions.clean_provision(valid_rule(description=" "))


def test_payment_requires_full_positive_valid_request():
    assert provisions.clean_payment({"payment_date": "2026-10-13", "amount": 130})["p_amount"] == 130
    for payment in (
        {"payment_date": "2026-10-13", "amount": 0},
        {"payment_date": "nao-e-data", "amount": 130},
        {"payment_date": "2026-10-13", "amount": -30},
        {"payment_date": "2026-10-13", "amount": 130, "other": "invalid"},
    ):
        with pytest.raises(HTTPException):
            provisions.clean_payment(payment)


def test_provision_endpoints_and_csrf_without_real_database(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "service-test-key")
    monkeypatch.setenv("SESSION_SECRET", "a" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setattr(security, "current", lambda _request: {
        "id": 1, "display_name": "Validador", "is_admin": True, "csrf": "test-csrf"
    })
    def check_csrf(request, _user):
        if request.headers.get("x-csrf-token") != "test-csrf":
            raise HTTPException(403, "CSRF inválido")
    monkeypatch.setattr(security, "require_csrf", check_csrf)
    calls = []

    def fake_call(method, table, *, params=None, data=None, prefer=None):
        calls.append((method, table, data))
        if table == "rpc/axora_user_workspace":
            return WORKSPACE
        if table == "rpc/axora_ensure_catalog":
            return 0
        if table == "finance_catalog_options":
            return [{"id": 1, "kind": "category", "name": "Moradia", "active": True},
                    {"id": 2, "kind": "responsible", "name": "Próprio", "active": True}]
        if table == "rpc/axora_ensure_provisions":
            return 1
        if table == "finance_provision_occurrences":
            return [{"id": 5, "due_date": "2026-10-20", "status": "open",
                     "planned_value": 130, "rule": {"description": "Internet"}}]
        if table == "rpc/axora_create_provision":
            return 7
        if table == "rpc/axora_pay_provision":
            return {"status": "paid", "occurrence_id": 5, "movement_id": 100}
        raise AssertionError("Unexpected table: " + table)

    monkeypatch.setattr(db, "call", fake_call)
    with TestClient(app) as client:
        assert client.get("/api/provisions").status_code == 200
        assert client.get("/api/provisions").json()["items"][0]["status"] == "open"
        assert client.post("/api/provisions", json=valid_rule()).status_code == 403
        assert client.post("/api/provisions", json=valid_rule(),
                           headers={"X-CSRF-Token": "test-csrf"}).json()["id"] == 7
        assert client.post("/api/provisions/5/pay", json={
            "payment_date": "2026-10-13", "amount": 128
        }).status_code == 403
        paid = client.post("/api/provisions/5/pay", json={
            "payment_date": "2026-10-13", "amount": 128
        }, headers={"X-CSRF-Token": "test-csrf"})
        assert paid.status_code == 200
        assert paid.json()["movement_id"] == 100
    assert ("POST", "rpc/axora_pay_provision",
            {"p_workspace_id": WORKSPACE, "p_occurrence_id": 5, "p_payment_date": "2026-10-13", "p_amount": 128.0}) in calls


def test_paid_movement_cannot_be_edited_separately(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "service-test-key")
    monkeypatch.setenv("SESSION_SECRET", "a" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setattr(security, "current", lambda _request: {
        "id": 1, "is_admin": True, "csrf": "test-csrf"
    })
    monkeypatch.setattr(security, "require_csrf", lambda request, user: None)
    monkeypatch.setattr(db, "call", lambda *args, **kwargs: WORKSPACE)
    monkeypatch.setattr(db, "select", lambda *args, **kwargs:
                        [{"id": 100, "provision_occurrence_id": 5, "workspace_id": WORKSPACE}])
    monkeypatch.setattr(db, "update", lambda *args, **kwargs:
                        pytest.fail("Never update a payment-linked movement directly"))
    monkeypatch.setattr(db, "delete", lambda *args, **kwargs:
                        pytest.fail("Never delete a payment-linked movement directly"))
    with TestClient(app) as client:
        assert client.patch("/api/rows/movements/100", json={"description": "Alterada"}).status_code == 409
        assert client.delete("/api/rows/movements/100").status_code == 409


def test_migration_has_atomic_payment_and_no_data_erasure():
    sql = (ROOT / "migrations/20261013_provisoes_mvp.sql").read_text(encoding="utf-8")
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "FOR UPDATE OF i" in sql
    assert "ON CONFLICT (rule_id,sequence_no) DO NOTHING" in sql
    assert "INSERT INTO public.finance_movements(" in sql
    assert "UPDATE public.finance_provision_occurrences" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS finance_movements_provision_once" in sql
    assert "REVOKE ALL ON FUNCTION public.axora_pay_provision" in sql
    assert "TRUNCATE" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    isolation = (ROOT / "migrations/20261013_finance_workspace_isolation.sql").read_text(encoding="utf-8")
    assert "axora_user_workspace" in isolation
    assert "finance_movements ADD COLUMN IF NOT EXISTS workspace_id" in isolation
    assert "p_workspace_id uuid" in isolation
    assert "AND i.workspace_id=p_workspace_id" in isolation
    assert "DROP FUNCTION IF EXISTS public.axora_pay_provision(bigint,date,numeric)" in isolation


def test_ui_exposes_provisions_and_keeps_existing_data():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/app.js").read_text(encoding="utf-8")
    screen = (ROOT / "static/provisions.js").read_text(encoding="utf-8")
    assert 'data-page="provisions"' in html
    assert 'id="provision-dialog"' in html and 'id="provision-payment-dialog"' in html
    assert 'page==="provisions"?provisionsPage()' in js
    assert 'loadProvisions().catch' in js
    assert 'data-action="pay-provision"' in screen
    assert "await refresh();await loadProvisions();" in screen
