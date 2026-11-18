"""Dívidas AXORA: isolamento, valores exatos, vínculo único a Provisões."""
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db, security, family_service, debts
from axora_v2.main import app

ROOT=Path(__file__).resolve().parents[1]
W="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
DEBT={"description":"Cartão fictício","total_value":1500,"category":"Dívidas",
      "responsible":"Titular teste"}
AGREEMENT={"total_installments":12,"paid_installments":2,"installment_value":65.50,
           "first_due_date":"2026-12-15","category":"Dívidas",
           "responsible":"Titular teste","profile_id":11}


def test_debt_values_and_installments_validation():
    assert debts.clean_debt(DEBT)["total_value"]=="1500.00"
    assert debts.clean_agreement(AGREEMENT)["p_paid_installments"]==2
    for invalid in [dict(DEBT,total_value=-1),dict(DEBT,total_value="10.123"),
                    dict(DEBT,description=""),dict(DEBT,extra="imprevisto")]:
        with pytest.raises(HTTPException) as e: debts.clean_debt(invalid)
        assert e.value.status_code==422
    for invalid in [
        dict(AGREEMENT,total_installments=0),
        dict(AGREEMENT,total_installments=361),
        dict(AGREEMENT,total_installments=2,paid_installments=2),
        dict(AGREEMENT,paid_installments=-1),
        dict(AGREEMENT,paid_installments=2.3),
        dict(AGREEMENT,installment_value="20.009"),
        dict(AGREEMENT,first_due_date="amanhã"),
        dict(AGREEMENT,profile_id="11"),
    ]:
        with pytest.raises(HTTPException) as e: debts.clean_agreement(invalid)
        assert e.value.status_code==422


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake")
    monkeypatch.setenv("SESSION_SECRET","a"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setenv("AXORA_FAMILY_V2_ENABLED","1")
    member={"id":1,"display_name":"Titular teste","relationship":"principal","active":True}
    ctx={"workspace_id":W,"profile_id":11,"role":"principal","owner_id":1,"user_id":1}
    user={"id":1,"display_name":"Titular teste","is_admin":True,"csrf":"csrf"}
    monkeypatch.setattr(security,"current",lambda _:dict(user))
    monkeypatch.setattr(family_service,"context",lambda _:dict(ctx))
    monkeypatch.setattr(family_service,"profiles",lambda _: [
        dict(member,id=11),{"id":12,"display_name":"Outro membro","active":True,"relationship":"conjuge"}
    ])
    def csrf(request,user):
        if request.headers.get("X-CSRF-Token")!="csrf":raise HTTPException(403,"CSRF")
    monkeypatch.setattr(security,"require_csrf",csrf)
    calls=[]
    current=[{"id":55,"description":"Cartão fictício","status":"NÃO RENEGOCIADO",
              "total_value":"1500.00","open_value":"1500.00",
              "linked_provision_rule_id":None}]
    def call(method,table,*,params=None,data=None,prefer=None):
        calls.append((method,table,params,data))
        if table=="finance_debts":
            if method=="GET":return list(current)
            if method=="POST":return [{"id":56,**data}]
            if method=="PATCH":return [{"id":55,**data}]
        if table=="rpc/axora_debt_renegotiate":
            return {"debt_id":55,"provision_rule_id":101,"remaining_installments":10,"open_value":"655.00"}
        raise AssertionError(("Unexpected DB query",table))
    monkeypatch.setattr(db,"call",call)
    with TestClient(app) as c: yield c,ctx,current,calls


def test_owner_create_update_renegotiate_and_read(client):
    c,ctx,current,calls=client
    read=c.get("/api/debts/portfolio")
    assert read.status_code==200
    assert read.json()["members"][0]["name"]=="Titular teste"
    created=c.post("/api/debts/portfolio",headers={"X-CSRF-Token":"csrf"},json=DEBT)
    assert created.status_code==200
    posted=next(x for x in calls if x[0]=="POST" and x[1]=="finance_debts")[3]
    assert posted["open_value"]=="1500.00" and posted["workspace_id"]==W
    assert posted["status"]=="NÃO RENEGOCIADO"
    updated=c.patch("/api/debts/portfolio/55",headers={"X-CSRF-Token":"csrf"},json=DEBT)
    assert updated.status_code==200
    agreement=c.post("/api/debts/portfolio/55/renegotiate",headers={"X-CSRF-Token":"csrf"},json=AGREEMENT)
    assert agreement.status_code==200
    args=next(x for x in calls if x[1]=="rpc/axora_debt_renegotiate")[3]
    assert args["p_debt_id"]==55 and args["p_workspace_id"]==W
    assert args["p_profile_id"]==11 and args["p_paid_installments"]==2
    assert args["p_installment_value"]=="65.50"
    current[0]["linked_provision_rule_id"]=101
    again=c.post("/api/debts/portfolio/55/renegotiate",headers={"X-CSRF-Token":"csrf"},json=AGREEMENT)
    assert again.status_code==409
    assert len([x for x in calls if x[1]=="rpc/axora_debt_renegotiate"])==1


def test_secondary_denied_before_query(client):
    c,ctx,current,calls=client
    ctx["role"]="conjuge"
    baseline=len(calls)
    assert c.get("/api/debts/portfolio").status_code==403
    assert c.post("/api/debts/portfolio",headers={"X-CSRF-Token":"csrf"},json=DEBT).status_code==403
    assert c.post("/api/debts/portfolio/55/renegotiate",
        headers={"X-CSRF-Token":"csrf"},json=AGREEMENT).status_code==403
    assert len(calls)==baseline


def test_missing_csrf_and_cross_workspace_denied(client):
    c,ctx,current,calls=client
    assert c.post("/api/debts/portfolio",json=DEBT).status_code==403
    assert c.post("/api/debts/portfolio/55/renegotiate",
        headers={"X-CSRF-Token":"csrf"},json=dict(AGREEMENT,profile_id=999)).status_code==422
    assert len([x for x in calls if x[1]=="rpc/axora_debt_renegotiate"])==0


def test_sql_atomic_link_and_balances_contract():
    sql=(ROOT/"migrations/20261118_debt_portfolio_renegotiation.sql").read_text()
    assert "BEGIN;" in sql and sql.rstrip().endswith("COMMIT;")
    assert "FOR UPDATE" in sql and "v_debt.linked_provision_rule_id IS NOT NULL" in sql
    assert "axora_beta.axora_create_provision(" in sql
    assert "v_remaining:=p_total_installments-p_paid_installments" in sql
    assert "p_first_due_date,p_installment_value,'fixed','installments','monthly'" in sql
    assert "finance_provision_cost_shares" in sql
    assert "AFTER UPDATE OF status" in sql
    assert "d.linked_provision_rule_id=NEW.rule_id" in sql
    assert "REVOKE ALL ON FUNCTION axora_beta.axora_debt_renegotiate" in sql
    assert "GRANT EXECUTE" in sql
    assert "TRUNCATE" not in sql and "DELETE FROM" not in sql
    assert "finance_bank_accounts" not in sql
    assert "public.finance_debts" not in sql


def test_visibility_filters_and_income_single_recipient():
    app=(ROOT/"static/app.js").read_text()
    prov=(ROOT/"static/provisions.js").read_text()
    family=(ROOT/"static/family.js").read_text()
    family_ui=(ROOT/"static/index.html").read_text()
    api=(ROOT/"family_routes.py").read_text()
    assert 'filters.visibility' not in app or 'f.visibility' in app
    assert 'optionFilter("visibility","Todos os acessos"' in app
    assert 'provision-visibility-filter' in prov
    assert 'provisionFilters.visibility' in prov
    assert 'me.family_role==="principal"' in prov
    assert 'id="family-income-recipient-wrap"' in family_ui
    assert 'id="family-cost-fieldset"' in family_ui
    assert 'income.hidden=expense' in family
    assert 'split.hidden=!expense' in family
    assert 'const costs=classification==="ENTRADA"?' in family
    assert 'percentage:100' in family
    assert 'len(alloc) != 1' in api
    assert 'if(kind==="movements"&&data.classification==="ENTRADA")' in app
