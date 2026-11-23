"""AXORA BETA: reversao de provisoes e autorizacao do principal."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db, family_service, security
from axora_v2.main import app

WORKSPACE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ROOT = Path(__file__).resolve().parents[1]


def _setup(monkeypatch, role="principal"):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "dummy")
    monkeypatch.setenv("SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setattr(security, "current", lambda _: {
        "id": 12, "display_name": "Titular", "is_admin": False,
        "csrf": "test-csrf",
    })
    monkeypatch.setattr(security, "require_csrf", lambda req, user:
        None if req.headers.get("x-csrf-token") == "test-csrf"
        else (_ for _ in ()).throw(HTTPException(403, "CSRF")))
    monkeypatch.setattr(family_service, "context", lambda _:
        {"workspace_id": WORKSPACE, "profile_id": 1,
         "owner_id": 12, "role": role, "user_id": 12})
    monkeypatch.setattr(family_service, "require_principal",
        family_service.require_principal)


def test_preview_and_undo_use_only_server_derived_workspace(monkeypatch):
    _setup(monkeypatch)
    calls = []

    def fake_call(method, table, *, data=None, params=None, prefer=None):
        calls.append((method, table, data))
        if table.endswith("_preview"):
            return {"occurrence_id": 9, "paid_amount": 120,
                    "linked_existing_record": False,
                    "needs_reference": False, "restored_wallet_amount": 120}
        if table.endswith("_payment"):
            return {"ok": True, "status": "open", "occurrence_id": 9,
                    "restored_wallet_amount": 120}
        raise AssertionError(table)

    monkeypatch.setattr(db, "call", fake_call)
    with TestClient(app) as client:
        preview = client.get("/api/family/provisions/9/reversal-preview")
        assert preview.status_code == 200, preview.text
        assert preview.json()["restored_wallet_amount"] == 120
        assert client.post("/api/family/provisions/9/undo",
            json={"confirm": True}).status_code == 403
        result = client.post("/api/family/provisions/9/undo",
            headers={"X-CSRF-Token": "test-csrf"},
            json={"confirm": True})
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "open"
        assert calls[-1] == ("POST", "rpc/axora_family_reverse_provision_payment", {
            "p_workspace_id": WORKSPACE, "p_actor_id": 12,
            "p_occurrence_id": 9, "p_reference_value": None,
        })
        assert client.post("/api/family/provisions/9/undo",
            headers={"X-CSRF-Token": "test-csrf"},
            json={"confirm": True, "reference_value": "73.25"}).status_code == 200
        assert calls[-1][2]["p_reference_value"] == "73.25"


def test_invalid_payload_and_secondary_access_rejected(monkeypatch):
    _setup(monkeypatch)
    calls = []
    monkeypatch.setattr(db, "call", lambda *a, **k: calls.append(a))
    headers = {"X-CSRF-Token": "test-csrf"}
    with TestClient(app) as client:
        for body in (
            {}, {"confirm": False}, {"confirm": "true"},
            {"confirm": True, "unknown": 9},
            {"confirm": True, "reference_value": -10},
            {"confirm": True, "reference_value": "90.001"},
        ):
            assert client.post("/api/family/provisions/3/undo",
                headers=headers, json=body).status_code == 422
        assert client.post("/api/family/provisions/0/undo",
            headers=headers, json={"confirm": True}).status_code == 422
    assert not calls
    _setup(monkeypatch, role="conjuge")
    with TestClient(app) as client:
        assert client.get("/api/family/provisions/3/reversal-preview").status_code == 403
        assert client.post("/api/family/provisions/3/undo",
            headers=headers, json={"confirm": True}).status_code == 403
    assert not calls


def test_sql_undo_is_isolated_atomic_and_audited():
    migration = (ROOT / "migrations" / "20261123_reverse_provision_payments.sql").read_text()
    assert "axora_beta.finance_provision_payment_reversals" in migration
    assert "SECURITY INVOKER" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FROM PUBLIC,anon,authenticated" in migration
    assert "pg_advisory_xact_lock" in migration
    assert "FOR UPDATE OF o" in migration
    assert "FOR UPDATE OF a" in migration
    assert "finance_bank_transactions" in migration
    assert "Desfaca primeiro a conciliacao" in migration
    assert "v_restore_amount:=coalesce(v_debit_total,0)" in migration
    assert "manual_balance=a.manual_balance+v_row.amount" in migration
    assert "DELETE FROM finance_family_balance_debit_sources" in migration
    assert "DELETE FROM finance_family_balance_debits" in migration
    assert "UPDATE finance_provision_occurrences" in migration
    assert "SET status='open',payment_date=NULL,paid_value=NULL" in migration
    assert "INSERT INTO finance_provision_payment_reversals" in migration
    assert "v_is_linked" in migration
    assert "UPDATE finance_movements SET provision_occurrence_id=NULL" in migration
    assert "last_paid_value=v_ref_paid_value" in migration
    assert "CREATE OR REPLACE FUNCTION axora_beta.axora_family_reverse_payment_preview" in migration
    assert "ALTER TABLE public." not in migration
    assert "DROP TABLE" not in migration and "TRUNCATE" not in migration


def test_ui_renders_undo_only_for_principal():
    app_js = (ROOT / "static" / "app.js").read_text()
    family_js = (ROOT / "static" / "family.js").read_text()
    assert 'data-family-action="undo-provision-payment"' in app_js
    assert 'me?.family_enabled&&me?.family_role==="principal"' in app_js
    assert "if(!own())throw Error" in family_js
    assert "reversal-preview" in family_js
    assert '"confirm":true' not in family_js  # request uses object semantics
    assert "const body={confirm:true}" in family_js
    assert '"/undo"' in family_js
