"""Regressões: filtros e sugestão/vinculação sem lançar duas vezes."""
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db, security, provisions
from axora_v2.main import app

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_payment_candidates_require_equal_amount_and_matching_description():
    occurrence={"description":"FUNERÁRIA"}
    bank=[
        {"id":8,"description":"Transferência enviada pelo Pix BOM PASTOR",
         "amount":-189.90,"posted_on":"2026-10-23","status":"pending","account_id":3},
        {"id":9,"description":"BOM PASTOR","amount":-190.10,
         "posted_on":"2026-10-23","status":"pending"},
        {"id":10,"description":"CEMIG","amount":-189.90,
         "posted_on":"2026-10-23","status":"matched_provision"},
    ]
    records=[
        {"id":7,"description":"Funerária","value":189.90,
         "movement_date":"2026-10-22","classification":"SAÍDA","provision_occurrence_id":None},
        {"id":11,"description":"Funerária","value":189.90,
         "movement_date":"2026-10-22","classification":"SAÍDA","provision_occurrence_id":5},
    ]
    history=[{"source_description":"Pix BOM PASTOR","target_description":"Funerária"}]
    found=provisions.payment_matches(occurrence,"2026-10-23",189.90,bank,records,history)
    assert {(x["kind"],x["id"]) for x in found}=={("bank",8),("movement",7)}
    assert found[0]["kind"]=="bank"
    assert found[0]["learned"] is True
    assert all(x["amount"]==189.90 for x in found)
    assert provisions.payment_matches(occurrence,"2026-10-23",200,bank,records,history)==[]
    utility=provisions.payment_matches(
       {"description":"CEMIG"},"2026-10-23",91.57,
       [{"id":40,"description":"Transferência enviada pelo Pix CEMIG DISTRIBUIÇÃO",
         "amount":-91.57,"posted_on":"2026-10-22",
         "status":"pending","account_id":3}],[],[])
    assert utility and utility[0]["id"]==40
    assert "favorecido identificado" in " ".join(utility[0]["reasons"])


def test_payment_match_payload_validation():
    assert provisions.clean_match({"kind":"bank","source_id":5})=={"kind":"bank","source_id":5}
    assert provisions.clean_match({"kind":"movement","source_id":"7"})=={"kind":"movement","source_id":7}
    for item in ({},{"kind":"other","source_id":5},
                 {"kind":"bank","source_id":0},
                 {"kind":"bank","source_id":5,"extra":True}):
        with pytest.raises(HTTPException):
            provisions.clean_match(item)


def test_payment_routes_require_auth_and_confirm_only_with_csrf(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","integration-tests")
    monkeypatch.setenv("SESSION_SECRET","b"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(security,"current",lambda _:{"id":12,"csrf":"test-token","is_admin":True})
    def guard(request,_user):
        if request.headers.get("x-csrf-token")!="test-token":
            raise HTTPException(403,"csrf")
    monkeypatch.setattr(security,"require_csrf",guard)
    calls=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        calls.append((table,data))
        if table=="rpc/axora_user_workspace":
            return WORKSPACE
        if table=="finance_provision_occurrences":
            assert params["workspace_id"]=="eq."+WORKSPACE
            return [{"id":2,"planned_value":189.90,"status":"open",
                     "description_override":None,"rule":{"description":"Funerária"}}]
        if table=="finance_bank_transactions":
            assert params["workspace_id"]=="eq."+WORKSPACE
            return [{"id":8,"description":"Pix BOM PASTOR","amount":-189.90,
                     "status":"pending","posted_on":"2026-10-23","account_id":3}]
        if table=="finance_reconciliation_learning":
            return [{"source_description":"Pix BOM PASTOR","target_description":"Funerária"}]
        if table=="finance_bank_accounts":
            return [{"id":3,"bank_name":"Nubank","nickname":"Principal",
                     "holder":{"name":"Titular"}}]
        if table=="rpc/axora_confirm_reconciliation":
            assert data["p_workspace_id"]==WORKSPACE
            assert data["p_user_id"]==12
            assert data["p_action"]=="matched_provision"
            assert data["p_target_id"]==2
            assert data["p_transaction_id"]==8
            return {"confirmed":True}
        if table=="rpc/axora_link_record_to_provision":
            assert data=={"p_workspace_id":WORKSPACE,"p_user_id":12,
                          "p_occurrence_id":2,"p_movement_id":7}
            return {"linked_existing_record":True}
        raise AssertionError(table)
    monkeypatch.setattr(db,"call",fake_call)
    monkeypatch.setattr(db,"select",lambda *args,**kwargs: [])
    with TestClient(app) as client:
        result=client.get("/api/provisions/2/matches",
          params={"payment_date":"2026-10-23","amount":189.90})
        assert result.status_code==200
        assert result.json()["items"][0]["kind"]=="bank"
        assert "Nubank" in result.json()["items"][0]["account_label"]
        assert client.post("/api/provisions/2/match",
            json={"kind":"bank","source_id":8}).status_code==403
        head={"X-CSRF-Token":"test-token"}
        ok=client.post("/api/provisions/2/match",
            json={"kind":"bank","source_id":8},headers=head)
        assert ok.status_code==200 and ok.json()["confirmed"]
        ok=client.post("/api/provisions/2/match",
            json={"kind":"movement","source_id":7},headers=head)
        assert ok.status_code==200 and ok.json()["linked_existing_record"]
    assert sum(x[0]=="rpc/axora_confirm_reconciliation" for x in calls)==1


def test_ui_filters_and_atomic_link_contract():
    js=(ROOT/"static/provisions.js").read_text()
    html=(ROOT/"static/index.html").read_text()
    sql=(ROOT/"migrations/20261023_provision_payment_existing_record_link.sql").read_text()
    for selector in ("provision-search-filter","provision-category-filter",
                     "provision-responsible-filter","provision-from-filter",
                     "provision-to-filter"):
        assert selector in js
    assert "Reserva · 6 meses" in js
    assert "janela móvel de 18 meses" in js
    assert "provisionSixMonthEnd" in js
    assert 'id="provision-match-options"' in html
    assert "/api/provisions/"+"" in js
    assert "/match" in js
    assert "pg_advisory_xact_lock" in sql
    assert "member.workspace_id=p_workspace_id" in sql
    assert "m.provision_occurrence_id IS NOT NULL" in sql
    assert "status='paid'" in sql
    assert "CREATE OR REPLACE FUNCTION public.axora_link_record_to_provision" in sql
    assert "DELETE FROM" not in sql.upper()
