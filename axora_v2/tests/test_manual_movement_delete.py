"""Regressão: excluir lançamento manual com controle de saldo e auditoria."""
from pathlib import Path
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db, family_service, security
from axora_v2.main import app

ROOT = Path(__file__).resolve().parents[1]
WS = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def setup(monkeypatch, role="principal"):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "dummy")
    monkeypatch.setenv("SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setattr(security, "current", lambda _: {
        "id": 12, "display_name": "Principal teste",
        "is_admin": False, "csrf": "csrf-test",
    })
    monkeypatch.setattr(security, "require_csrf", lambda req, user:
        None if req.headers.get("x-csrf-token") == "csrf-test"
        else (_ for _ in ()).throw(HTTPException(403, "CSRF")))
    monkeypatch.setattr(family_service, "context", lambda _:{
        "workspace_id": WS, "profile_id":1, "owner_id":12,
        "role":role, "user_id":12,
    })


def test_manual_delete_preview_and_rpc_with_csrf(monkeypatch):
    setup(monkeypatch)
    calls = []
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        calls.append((method,table,params,data))
        if table == "rpc/axora_manual_delete_preview":
            return {"id": 7, "description": "Entrada de teste", "amount": 864,
                    "wallet_delta": -750, "credited_reversed": 750,
                    "debited_restored": 0}
        if table == "rpc/axora_manual_delete_movement":
            return {"ok":True, "deleted_id": 7, "wallet_delta": -750}
        if table == "finance_bank_transactions": return []
        raise AssertionError(table)
    monkeypatch.setattr(db,"call",fake_call)
    monkeypatch.setattr(db,"select",lambda *args,**kwargs:
        [{"id":7,"provision_occurrence_id":None}])
    with TestClient(app) as client:
        preview = client.get("/api/family/movements/7/delete-preview")
        assert preview.status_code == 200,preview.text
        assert preview.json()["wallet_delta"] == -750
        assert client.delete("/api/rows/movements/7").status_code == 403
        result = client.delete("/api/rows/movements/7",
                               headers={"X-CSRF-Token":"csrf-test"})
        assert result.status_code == 200,result.text
        assert result.json()["deleted_id"] == 7
        assert calls[-1] == ("POST","rpc/axora_manual_delete_movement",None,
              {"p_workspace_id":WS,"p_actor_id":12,"p_movement_id":7})


def test_linked_provision_never_uses_manual_delete_rpc(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(db,"select",lambda *a,**k:[
        {"id":7,"provision_occurrence_id":9}])
    calls=[]
    monkeypatch.setattr(db,"call",lambda *a,**k:calls.append(a))
    with TestClient(app) as client:
        result=client.delete("/api/rows/movements/7",
                             headers={"X-CSRF-Token":"csrf-test"})
    assert result.status_code==409
    assert "Desfazer pagamento" in result.json()["detail"]
    assert not calls


def test_nonprincipal_denied_before_database(monkeypatch):
    setup(monkeypatch,role="conjuge")
    calls=[]
    monkeypatch.setattr(db,"call",lambda *a,**k:calls.append(a))
    with TestClient(app) as client:
        assert client.get("/api/family/movements/7/delete-preview").status_code==403
        assert client.delete("/api/rows/movements/7",
            headers={"X-CSRF-Token":"csrf-test"}).status_code==403
    assert not calls


def test_manual_delete_sql_contract_and_ui():
    sql=(ROOT/"migrations"/"20261123_manual_movement_delete.sql").read_text()
    assert "SECURITY INVOKER" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FROM PUBLIC,anon,authenticated" in sql
    assert "axora_manual_delete_preview" in sql
    assert "axora_manual_delete_movement" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "FOR UPDATE OF a" in sql
    assert "credited_reversed" in sql
    assert "finance_provision_record_links" in sql
    assert "finance_bank_transactions" in sql
    assert "finance_manual_movement_deletions" in sql
    assert "finance_family_balance_credit_sources" in sql
    assert "finance_family_balance_debit_sources" in sql
    assert "DELETE FROM finance_family_cost_allocations" in sql
    assert "DELETE FROM finance_family_payment_allocations" in sql
    assert "DELETE FROM finance_movements" in sql
    assert "ALTER TABLE public." not in sql and "TRUNCATE" not in sql
    html=(ROOT/"static"/"index.html").read_text()
    js=(ROOT/"static"/"family.js").read_text()
    appjs=(ROOT/"static"/"app.js").read_text()
    assert 'id="family-manual-delete-dialog"' in html
    assert 'id="family-manual-delete-wallet"' in html
    assert 'id="family-manual-delete-error" role="alert" hidden' in html
    assert 'openManualDeletion' in js
    assert '"/delete-preview"' in js
    assert '"DELETE"' in js
    assert 'window.AxoraFamily.openManualDeletion' in appjs
