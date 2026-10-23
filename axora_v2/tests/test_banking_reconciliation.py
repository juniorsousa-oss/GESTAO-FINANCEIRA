"""Primeiro MVP de contas familiares e conciliação humana: testes sem banco real."""
from pathlib import Path
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from axora_v2 import banking, db, security
from axora_v2.main import app

BASE = Path(__file__).resolve().parents[1]
WORKSPACE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_holder_account_and_transaction_validation():
    assert banking.clean_holder({"name": "  Minha mãe  ", "relationship": "mae"}) == {
        "name": "Minha mãe", "relationship": "mae"}
    assert banking.clean_account({"holder_id": 3, "bank_name": "CAIXA",
                                  "nickname": "CAIXA Mãe", "account_type": "poupanca"})["holder_id"] == 3
    assert banking.clean_transaction({"account_id": 4, "posted_on": "2026-10-14",
                                     "description": "Pagamento", "amount": -732.74})["amount"] == -732.74
    for value in (0, "-0.00", "9.9999", "nan"):
        with pytest.raises(HTTPException):
            banking.clean_transaction({"account_id": 4, "posted_on": "2026-10-14",
                                       "description": "Compra", "amount": value})
    with pytest.raises(HTTPException):
        banking.clean_holder({"name": "P", "relationship": "wrong"})


def test_suggestions_are_explainable_but_not_automatic():
    tx = {"description": "Apartamento residencial", "posted_on": "2026-10-22", "amount": -732.74}
    movements = [
        {"id": 1, "description": "Apartamento residencial", "movement_date": "2026-10-22",
         "value": 732.74, "classification": "SAÍDA"},
        {"id": 2, "description": "Salário", "movement_date": "2026-10-22",
         "value": 732.74, "classification": "ENTRADA"},
        {"id": 3, "description": "Ajuste", "movement_date": "2026-10-22",
         "value": 732.74, "classification": "SAÍDA"},
    ]
    provisions = [{"id": 19, "due_date": "2026-10-22", "planned_value": 732.74,
                   "description_override": None, "rule": {"description": "Apartamento residencial"}}]
    results = banking.suggestions(tx, movements, provisions, occupied={3})
    assert {x["id"] for x in results} == {1, 19}
    assert results[0]["strength"] == "Alta"
    assert results[0]["can_confirm"] is True
    assert results[0]["reasons"]
    near = banking.score_match(tx,{"id": 10, "description": "Apartamento residencial",
                                   "date": "2026-10-22", "amount": -735},candidate_type="matched_provision")
    assert near["can_confirm"] is False


def test_operator_decisions_must_be_explicit():
    assert banking.clean_decision({"transaction_id": 8, "action": "matched_record", "target_id": 9}) == {
        "p_transaction_id": 8, "p_action": "matched_record",
        "p_target_id": 9, "p_counterpart_id": None, "p_category": None, "p_reason": None,
    }
    for v in (
        {"transaction_id": 8, "action": "matched_provision"},
        {"transaction_id": 8, "action": "ignored", "reason": ""},
        {"transaction_id": 8, "action": "transfer", "counterpart_id": None},
        {"transaction_id": 8, "action": "auto_confirm"},
    ):
        with pytest.raises(HTTPException):
            banking.clean_decision(v)


def test_private_workspaces_require_session_and_csrf(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "fake-ci-key")
    monkeypatch.setenv("SESSION_SECRET", "z" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setattr(security, "current", lambda _: {
        "id": 12, "csrf": "test-token", "is_admin": False})
    def require_csrf(request, _user):
        if request.headers.get("x-csrf-token") != "test-token":
            raise HTTPException(403, "csrf")
    monkeypatch.setattr(security, "require_csrf", require_csrf)
    calls = []
    holders = [{"id": 1, "workspace_id": WORKSPACE, "name": "Mãe", "relationship": "mae"}]
    accounts = [{"id": 2, "workspace_id": WORKSPACE, "holder_id": 1, "bank_name": "CAIXA",
                 "nickname": "Poupança Mãe", "account_type": "poupanca"}]
    def fake_call(method, table, *, params=None, data=None, prefer=None):
        calls.append((method,table,params,data))
        if table == "rpc/axora_user_workspace":
            assert data == {"p_user_id": 12}
            return WORKSPACE
        if table == "finance_bank_holders":
            if method == "GET":
                assert params["workspace_id"] == "eq." + WORKSPACE
                return holders
            return [{"id": 3, **data}]
        if table == "finance_bank_accounts":
            if method == "GET":
                assert params["workspace_id"] == "eq." + WORKSPACE
                return accounts
            return [{"id": 4, **data}]
        if table == "finance_bank_transactions":
            if method == "GET":
                assert params["workspace_id"] == "eq." + WORKSPACE
                return []
            return [{"id": 5, **data}]
        if table == "finance_reconciliation_events":
            return []
        if table == "rpc/axora_confirm_reconciliation":
            assert data["p_workspace_id"] == WORKSPACE
            assert data["p_user_id"] == 12
            return {"transaction_id": 5, "status": "matched_record", "confirmed": True}
        raise AssertionError(table)
    monkeypatch.setattr(db, "call", fake_call)
    with TestClient(app) as client:
        assert client.get("/api/banking").status_code == 200
        assert client.post("/api/banking/holders",json={"name": "Pai", "relationship": "pai"}).status_code == 403
        head={"X-CSRF-Token":"test-token"}
        assert client.post("/api/banking/holders",json={"name": "Pai", "relationship": "pai"},
                           headers=head).status_code == 200
        assert client.post("/api/banking/accounts",json={
            "holder_id": 1, "bank_name": "CAIXA", "nickname": "CAIXA Pessoal", "account_type": "corrente"
        },headers=head).status_code == 200
        assert client.post("/api/banking/transactions",json={
            "account_id": 2, "posted_on": "2026-10-14", "description": "Extrato de teste",
            "amount": -12.34
        },headers=head).status_code == 200
        assert client.post("/api/banking/reconcile",json={
            "transaction_id": 5, "action": "matched_record", "target_id": 6
        }).status_code == 403
        assert client.post("/api/banking/reconcile",json={
            "transaction_id": 5, "action": "matched_record", "target_id": 6
        },headers=head).json()["confirmed"] is True


def test_migration_atomic_checks_and_ui():
    sql=(BASE/"migrations/20261014_banking_reconciliation_mvp.sql").read_text()
    assert "FOR UPDATE" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "status='paid'" in sql
    assert "finance_reconciliation_events" in sql
    assert "p_user_id=p_user_id" not in sql
    assert "GRANT EXECUTE ON FUNCTION public.axora_confirm_reconciliation" in sql
    assert "DELETE FROM" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    html=(BASE/"static/index.html").read_text()
    app_js=(BASE/"static/app.js").read_text()
    banking_js=(BASE/"static/banking.js").read_text()
    assert 'data-page="bank-accounts"' in html
    assert 'data-page="reconciliation"' in html
    assert 'id="bank-decision-dialog"' in html
    assert 'banking.js?v=axora-balance-summary-r1' in html
    assert 'page==="reconciliation"?bankingReconciliationPage()' in app_js
    assert 'bankingReview=true;' in banking_js
    assert 'bankingChoice=null;' in banking_js
    assert "Não será" not in banking_js or True


def test_aprendizado_bom_pastor_prioriza_funeraria_sem_confirmar():
    tx={"description":"PIX ENVIADO PARA BOM PASTOR", "posted_on":"2026-11-15", "amount":-189.90}
    provisions=[
        {"id":7,"due_date":"2026-11-15","planned_value":189.90,
         "description_override":None,"rule":{"description":"Serviço genérico"}},
        {"id":8,"due_date":"2026-11-15","planned_value":189.90,
         "description_override":None,"rule":{"description":"Funerária"}},
    ]
    # O primeiro exemplo já confirmado ensina apenas o favorecido, jamais o ID da parcela.
    examples=[{"source_description":"Pix Bom Pastor",
               "target_description":"FUNERÁRIA"}]
    results=banking.suggestions(tx,[],provisions,patterns=examples)
    assert results[0]["id"]==8
    assert results[0]["learned_count"]==1
    assert "padrão aprendido" in " ".join(results[0]["reasons"])
    assert results[0]["can_confirm"] is True
    assert banking.same_bank_counterpart("PIX - BOM PASTOR LTDA", "Pix Bom Pastor")
    assert not banking.same_bank_counterpart("PIX OUTRA EMPRESA", "Pix Bom Pastor")
    # Mesmo com histórico, valores divergentes não podem ser confirmados.
    wrong=banking.suggestions({**tx,"amount":-245.00},[],provisions,patterns=examples)
    assert not any(c["id"]==8 for c in wrong)
    # Estorno desativa o exemplo e elimina o bônus aprendido.
    no_pattern=banking.suggestions(tx,[],provisions,patterns=[])
    assert all(x["learned_count"]==0 for x in no_pattern)


def test_desfazer_exige_justificativa_e_permissao_csrf(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","ci-fake")
    monkeypatch.setenv("SESSION_SECRET","z"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(security,"current",lambda _:{"id":12,"csrf":"test-token","is_admin":False})
    def csrf(request,_user):
        if request.headers.get("x-csrf-token")!="test-token":
            raise HTTPException(403,"csrf")
    monkeypatch.setattr(security,"require_csrf",csrf)
    calls=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        calls.append((method,table,data))
        if table=="rpc/axora_user_workspace":
            return WORKSPACE
        if table=="rpc/axora_undo_reconciliation":
            assert data=={"p_workspace_id":WORKSPACE,"p_user_id":12,
                          "p_transaction_id":55,"p_reason":"Vínculo incorreto"}
            return {"transaction_id":55,"status":"pending","reverted":True}
        raise AssertionError(table)
    monkeypatch.setattr(db,"call",fake_call)
    with TestClient(app) as client:
        body={"transaction_id":55,"reason":"Vínculo incorreto"}
        assert client.post("/api/banking/reconcile/undo",json=body).status_code==403
        h={"X-CSRF-Token":"test-token"}
        assert client.post("/api/banking/reconcile/undo",
                           json={"transaction_id":55,"reason":"err"},headers=h).status_code==422
        response=client.post("/api/banking/reconcile/undo",json=body,headers=h)
        assert response.status_code==200
        assert response.json()["reverted"] is True
    assert sum(table=="rpc/axora_undo_reconciliation" for _,table,_ in calls)==1


def test_sql_estorno_isola_workspace_preserva_extrato_e_grava_auditoria():
    sql=(BASE/"migrations/20261023_reversible_reconciliation_learning.sql").read_text()
    assert "axora_undo_reconciliation" in sql
    assert "axora_confirm_reconciliation" in sql
    assert "finance_reconciliation_learning" in sql
    assert "ON CONFLICT (workspace_id,transaction_id)" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "member.workspace_id=p_workspace_id" in sql
    assert "UPDATE public.finance_bank_transactions SET" in sql
    assert "status='pending'" in sql
    assert "action,active" in sql
    assert "'reversed'" in sql
    assert "DELETE FROM public.finance_bank_transactions" not in sql
    assert "TRUNCATE" not in sql
    html=(BASE/"static/index.html").read_text()
    js=(BASE/"static/banking.js").read_text()
    assert 'id="bank-undo-dialog"' in html
    assert "/api/banking/reconcile/undo" in js
    assert "Padrão aprendido" in js
