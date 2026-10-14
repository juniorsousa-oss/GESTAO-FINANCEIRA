"""Regressão: 180 parcelas completas, total global e atualização automática."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db, security
from axora_v2.main import app
from axora_v2.metrics import compute

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_metrics_uses_complete_obligations_from_database():
    full_total = 180 * 732.74
    summary = compute([], [], [], [], {},
                      provision_overview={
                          "to_pay": full_total,
                          "pending_count": 180,
                          "next_forecasts": [{
                              "due_date": "2026-05-22", "description": "Apartamento",
                              "type": "Saída", "status": "Não pago", "final_value": 732.74,
                          }],
                      })
    assert summary["to_pay"] == pytest.approx(full_total)
    assert summary["projected"] == pytest.approx(-full_total)
    assert summary["pending_count"] == 180
    assert len(summary["next_forecasts"]) == 1
    assert compute([], [{"type": "Saída", "status": "Não pago", "final_value": 15}], [], [], {})["to_pay"] == 15


def test_snapshot_uses_rpc_aggregate_and_not_row_limited_list(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "fake-ci-test-key")
    monkeypatch.setenv("SESSION_SECRET", "a" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setattr(security, "current", lambda _request: {"id": 2, "is_admin": True, "csrf": "csrf"})
    called = []
    monkeypatch.setattr(db, "select", lambda *args, **kwargs: [])
    monkeypatch.setattr(db, "get_settings", lambda w: {})
    def fake_call(method, table, *, params=None, data=None, prefer=None):
        called.append((table, data))
        if table == "rpc/axora_user_workspace":
            return WORKSPACE
        if table == "rpc/axora_ensure_provisions":
            assert data == {"p_workspace_id": WORKSPACE}
            return 157
        if table == "rpc/axora_provision_overview":
            assert data == {"p_workspace_id": WORKSPACE}
            return {"to_pay": "131893.20", "pending_count": 180,
                    "next_forecasts": [{"due_date": "2026-05-22", "description": "Apartamento",
                                        "type": "Saída", "status": "Não pago",
                                        "final_value": 732.74}]}
        raise AssertionError(table)
    monkeypatch.setattr(db, "call", fake_call)
    with TestClient(app) as client:
        response = client.get("/api/snapshot")
        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary["pending_count"] == 180
        assert summary["to_pay"] == pytest.approx(131893.20)
        assert summary["projected"] == pytest.approx(-131893.20)
    assert not any("finance_provision_occurrences" in table for table, _ in called)


def test_list_provisions_paginates_until_every_due_date_is_returned(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "fake-ci-test-key")
    monkeypatch.setenv("SESSION_SECRET", "a" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setattr(security, "current", lambda _request: {"id": 2, "is_admin": True, "csrf": "csrf"})
    all_items = [{"id": n, "due_date": "2026-10-22", "planned_value": 1}
                 for n in range(1, 1102)]
    pages = []
    def fake_call(method, table, *, params=None, data=None, prefer=None):
        if table == "rpc/axora_user_workspace":
            return WORKSPACE
        if table == "rpc/axora_ensure_provisions":
            return 0
        if table == "finance_provision_occurrences":
            assert params["workspace_id"] == "eq." + WORKSPACE
            assert params["status"] == "eq.open"
            start = int(params["offset"])
            size = int(params["limit"])
            pages.append(start)
            return all_items[start:start + size]
        raise AssertionError(table)
    monkeypatch.setattr(db, "call", fake_call)
    with TestClient(app) as client:
        response = client.get("/api/provisions")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1101
    assert pages == [0, 500, 1000]


def test_sql_finite_vs_unlimited_and_no_existing_record_replacement():
    sql = (ROOT / "migrations/20261014_full_term_and_summary.sql").read_text(encoding="utf-8")
    assert "r.recurrence IN ('installments','until_date')" in sql
    assert "THEN least(360,r.installment_count)" in sql
    assert "r.recurrence='until_date' AND r.end_date IS NOT NULL" in sql
    assert "s.recurrence IN ('once','installments','until_date')" in sql
    assert "ON CONFLICT(rule_id,sequence_no) DO NOTHING" in sql
    assert "axora_provision_overview" in sql
    assert "sum(planned_value)" in sql
    assert "WHERE i.workspace_id=p_workspace_id AND i.status='open'" in sql
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()


def test_autosync_is_enabled_and_form_safe():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/auto-sync.js").read_text(encoding="utf-8")
    appjs = (ROOT / "static/app.js").read_text(encoding="utf-8")
    assert "auto-sync.js?v=axora-complete-obligations-r1" in html
    assert "AXORA_SYNC_INTERVAL=45000" in js
    assert 'document.querySelector("dialog[open]")' in js
    assert "visibilitychange" in js
    assert 'window.addEventListener("focus"' in js
    assert "refresh({silent:true})" in js
    assert "loadProvisions({silent:true})" in js
    assert 'refresh({silent=false}' in appjs
    assert "previousPosition" in appjs
