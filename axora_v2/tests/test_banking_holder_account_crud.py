"""Titulares e contas bancárias: corrigir ou excluir com segurança por workspace."""
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db, security
from axora_v2.main import app

WORKSPACE="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def client_and_calls(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake-test")
    monkeypatch.setenv("SESSION_SECRET","s"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(security,"current",lambda _req:{"id":12,"is_admin":True,"csrf":"test-token"})
    def csrf(req,_user):
        if req.headers.get("x-csrf-token")!="test-token":
            raise HTTPException(403,"CSRF")
    monkeypatch.setattr(security,"require_csrf",csrf)
    holders=[
        {"id":1,"workspace_id":WORKSPACE,"name":"Mãe","relationship":"mae","linked_user_id":None},
        {"id":3,"workspace_id":WORKSPACE,"name":"Pai","relationship":"pai","linked_user_id":None}
    ]
    accounts=[{"id":2,"workspace_id":WORKSPACE,"holder_id":1,"bank_name":"CAIXA",
               "nickname":"Poupança Mãe","account_type":"poupanca"},
              {"id":4,"workspace_id":WORKSPACE,"holder_id":3,"bank_name":"Nubank",
               "nickname":"Nubank pai","account_type":"corrente"}]
    transactions=[]
    calls=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        calls.append((method,table,params,data))
        if table=="rpc/axora_user_workspace":
            assert data=={"p_user_id":12}
            return WORKSPACE
        if table in ("finance_bank_holders","finance_bank_accounts","finance_bank_transactions"):
            rows={"finance_bank_holders":holders,"finance_bank_accounts":accounts,
                  "finance_bank_transactions":transactions}[table]
            assert params["workspace_id"]=="eq."+WORKSPACE
            if method=="GET":
                filtered=list(rows)
                for key,value in params.items():
                    if key in ("id","holder_id","account_id") and value.startswith("eq."):
                        filtered=[item for item in filtered if str(item.get(key))==value[3:]]
                return filtered[:int(params.get("limit",500))]
            if method=="PATCH":
                filtered=[r for r in rows if str(r["id"])==params["id"][3:]]
                for item in filtered:item.update(data)
                return filtered
            if method=="DELETE":
                rows[:]=[r for r in rows if str(r["id"])!=params["id"][3:]]
                return []
        raise AssertionError((method,table,params,data))
    monkeypatch.setattr(db,"call",fake_call)
    with TestClient(app) as client:
        yield client,holders,accounts,transactions,calls


def test_edit_both_and_block_holder_with_account(client_and_calls):
    client,holders,accounts,transactions,calls=client_and_calls
    auth={"X-CSRF-Token":"test-token"}
    assert client.patch("/api/banking/holders/1",json={
        "name":"Maria corrigida","relationship":"mae"
    }).status_code==403
    edited=client.patch("/api/banking/holders/1",headers=auth,json={
        "name":"Maria corrigida","relationship":"mae"
    })
    assert edited.status_code==200
    assert edited.json()["item"]["name"]=="Maria corrigida"
    result=client.delete("/api/banking/holders/1",headers=auth)
    assert result.status_code==409
    assert "contas vinculadas" in result.json()["detail"]
    assert client.delete("/api/banking/holders/999",headers=auth).status_code==404
    assert client.patch("/api/banking/holders/1",json={"name":"Sem vínculo"},headers=auth).status_code==422
    assert not any(c[0]=="DELETE" for c in calls)


def test_edit_and_delete_accounts_and_empty_holders(client_and_calls):
    client,holders,accounts,transactions,calls=client_and_calls
    auth={"X-CSRF-Token":"test-token"}
    edited=client.patch("/api/banking/accounts/2",headers=auth,json={
        "holder_id":1,"bank_name":"CAIXA","nickname":"CAIXA Mãe corrigida",
        "account_type":"poupanca"
    })
    assert edited.status_code==200
    assert edited.json()["item"]["nickname"]=="CAIXA Mãe corrigida"
    assert client.patch("/api/banking/accounts/2",headers=auth,json={
        "holder_id":888,"bank_name":"CAIXA","nickname":"Outra",
        "account_type":"poupanca"
    }).status_code==404
    assert client.delete("/api/banking/accounts/2").status_code==403
    transactions.append({"id":8,"workspace_id":WORKSPACE,"account_id":2})
    assert client.delete("/api/banking/accounts/2",headers=auth).status_code==409
    assert client.patch("/api/banking/accounts/2",headers=auth,json={
        "holder_id":3,"bank_name":"CAIXA","nickname":"Outra",
        "account_type":"poupanca"
    }).status_code==409
    assert client.patch("/api/banking/accounts/2",headers=auth,json={
        "holder_id":1,"bank_name":"CAIXA","nickname":"Apelido atualizado",
        "account_type":"poupanca"
    }).status_code==200
    transactions.clear()
    assert client.delete("/api/banking/accounts/2",headers=auth).json()["deleted"] is True
    assert client.delete("/api/banking/holders/1",headers=auth).json()["deleted"] is True
    assert client.delete("/api/banking/holders/1",headers=auth).status_code==404
    assert any(x[0]=="DELETE" and x[2]["workspace_id"]=="eq."+WORKSPACE for x in calls)


def test_ui_both_sections_have_actions_and_confirmation():
    base=Path(__file__).resolve().parents[1]
    js=(base/"static/banking.js").read_text(encoding="utf-8")
    html=(base/"static/index.html").read_text(encoding="utf-8")
    css=(base/"static/banking.css").read_text(encoding="utf-8")
    sql=(base/"migrations/20261014_holder_account_permissions.sql").read_text(encoding="utf-8")
    for name in ("bank-edit-holder","bank-delete-holder",
                 "bank-edit-account","bank-delete-account"):
        assert 'data-action="'+name+'"' in js
    assert "bankDelete(type,id)" in js
    assert "if(!confirm(" in js
    assert "method:id?\"PATCH\":\"POST\"" in js
    assert 'id="bank-holder-title"' in html
    assert 'id="bank-account-title"' in html
    assert "banking.js?v=axora-pluggy-pilot-r1" in html
    assert ".bank-account-actions" in css
    assert "GRANT UPDATE, DELETE" in sql
