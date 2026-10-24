"""Pix em Previsões: BR Code completo, chave, segurança e não quitação."""
from pathlib import Path
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from axora_v2 import pix_payments, provisions, db, security
from axora_v2.main import app

BASE=Path(__file__).resolve().parents[1]
W="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
KEY="recebedor.exemplo@empresa.com.br"


def draft(method, **other):
    data={
        "description":"Contribuição mensal","category":"Moradia",
        "responsible":"Responsável","start_due_date":"2026-10-23",
        "planned_value":None,"value_mode":"variable",
        "recurrence":"unlimited","frequency":"monthly",
        "payment_method":method,
        "payment_url":"","pix_kind":"key","pix_value":"",
        "pix_receiver_name":"","pix_receiver_city":"",
    }
    data.update(other)
    return data


def test_static_qr_from_key_is_standard_brcode_without_preset_amount():
    code=pix_payments.brcode_from_key(KEY,"Recebedor Exemplo","Patos de Minas")
    assert code.startswith("000201")
    assert "br.gov.bcb.pix" in code
    assert "RECEBEDOR EXEMPLO" in code
    assert "PATOS DE MINAS" in code
    assert code.endswith(pix_payments._crc16(code[:-4]))
    parsed=pix_payments._fields(code)
    assert parsed["53"]=="986"
    assert parsed["58"]=="BR"
    assert "54" not in parsed
    assert pix_payments.validate_brcode(code)==code
    qr=pix_payments.pix_qr("key",KEY,"Recebedor Exemplo","Patos de Minas")
    assert qr["copy_paste"]==code
    assert qr["image_data"].startswith("data:image/png;base64,")
    import base64
    assert base64.b64decode(qr["image_data"].split(",",1)[1])[:8]==b"\x89PNG\r\n\x1a\n"


def test_paste_pix_is_not_modified_and_crc_and_format_are_checked():
    code=pix_payments.brcode_from_key(KEY,"Recebedor Exemplo","Patos de Minas")
    assert pix_payments.clean_pix("brcode",code)=={
        "kind":"brcode","value":code,"receiver_name":None,"receiver_city":None}
    assert pix_payments.pix_qr("brcode",code)["copy_paste"]==code
    for malformed in (
        code[:-1]+("0" if code[-1]!="0" else "1"),
        "0002015604010263040000",
        "https://golpe.example/pix",
        "abc", "A"*1300,
        code+" ",
    ):
        with pytest.raises(HTTPException):
            pix_payments.validate_brcode(malformed)


def test_invalid_keys_or_receiver_fail_closed():
    valid=["123e4567-e89b-12d3-a456-426614174000","123.456.789-09",
           "+5534999999999",KEY]
    assert pix_payments.normalize_key(valid[0])==valid[0]
    assert pix_payments.normalize_key(valid[1])=="12345678909"
    assert pix_payments.normalize_key(valid[2])==valid[2]
    for key in ("", "123.456.789-00", "00000000000",
                "+55 34 999999999", "www.minha-chave", "123456", "<script>"):
        with pytest.raises(HTTPException):pix_payments.normalize_key(key)
    with pytest.raises(HTTPException):pix_payments.clean_pix("key",KEY,"","Patos de Minas")
    with pytest.raises(HTTPException):pix_payments.clean_pix("key",KEY,"Recebedor Exemplo","")


def test_payment_method_exclusive_and_legacy_links():
    new=provisions.clean_provision(draft("pix",pix_value=KEY,
         pix_receiver_name="Recebedor Exemplo",pix_receiver_city="Patos de Minas"))
    assert new["p_payment_method"]=="pix"
    assert new["p_payment_url"] is None
    assert new["p_pix_kind"]=="key"
    assert new["p_pix_value"]==KEY
    link=provisions.clean_provision(draft("link",payment_url="https://www.site-oficial.com.br/contas"))
    assert link["p_payment_method"]=="link" and link["p_pix_value"] is None
    none=provisions.clean_provision(draft("none"))
    assert none["p_payment_method"]=="none"
    with pytest.raises(HTTPException):
        provisions.clean_provision(draft("link"))
    with pytest.raises(HTTPException):
        provisions.clean_provision(draft("pix",pix_value="1234"))
    legacy=draft("link",payment_url="https://www.site-oficial.com.br")
    for x in ("payment_method","pix_kind","pix_value","pix_receiver_name","pix_receiver_city"):
        legacy.pop(x)
    assert "p_payment_method" not in provisions.clean_provision(legacy)
    assert provisions.clean_provision(legacy)["p_payment_url"] is not None


def test_pix_read_protected_by_login_workspace_and_no_payment(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","ci-only")
    monkeypatch.setenv("SESSION_SECRET","a"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    auth_enabled=[True]
    def current(req):
        return {"id":9,"csrf":"csrf","is_admin":True} if auth_enabled[0] else None
    monkeypatch.setattr(security,"current",current)
    def csrf(req,_user):
        if req.headers.get("x-csrf-token")!="csrf":raise HTTPException(403,"CSRF")
    monkeypatch.setattr(security,"require_csrf",csrf)
    queries=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        queries.append((method,table,params,data))
        if table=="rpc/axora_user_workspace":return W
        if table=="finance_provision_occurrences":
            assert params["workspace_id"]=="eq."+W
            assert params["status"]=="eq.open"
            if params["id"]=="eq.1":
                return [{"id":1,"rule":{"description":"Aluguel",
                   "payment_method":"pix","pix_kind":"key","pix_value":KEY,
                   "pix_receiver_name":"Recebedor Exemplo","pix_receiver_city":"Patos de Minas"}}]
            if params["id"]=="eq.2":
                return [{"id":2,"rule":{"description":"Aluguel","payment_method":"link"}}]
            return []
        raise AssertionError((method,table))
    monkeypatch.setattr(db,"call",fake_call)
    with TestClient(app) as client:
        response=client.get("/api/provisions/1/pix")
        assert response.status_code==200
        data=response.json()
        assert data["copy_paste"].startswith("000201")
        assert data["image_data"].startswith("data:image/png;base64,")
        assert "não registra" in data["notice"]
        assert client.get("/api/provisions/2/pix").status_code==409
        assert client.get("/api/provisions/3/pix").status_code==404
        auth_enabled[0]=False
        assert client.get("/api/provisions/1/pix").status_code in (401,403)
    assert not any(method!="GET" and table!="rpc/axora_user_workspace" for method,table,_,_ in queries)


def test_ui_and_sql_methods_and_qr_are_local():
    js=(BASE/"static/provisions.js").read_text()
    html=(BASE/"static/index.html").read_text()
    py=(BASE/"main.py").read_text()
    migration=(BASE/"migrations/20261023_provision_pix_methods.sql").read_text()
    for item in ("payment_method","pix_kind","pix_value",
                 "pix_receiver_name","pix_receiver_city"):
        assert 'name="'+item+'"' in html
    assert "Gerar QR Code Pix" in js
    assert 'id="provision-pix-dialog"' in html
    assert "navigator.clipboard.writeText" in js
    assert 'data-action="open-provision-pix"' in js
    assert 'v=axora-pix-methods-r1' in html
    assert "pix_payments.pix_qr" in py
    assert "axora_create_provision_with_method" in migration
    assert "axora_edit_provision_with_method" in migration
    assert "DROP TABLE" not in migration.upper()
    assert "TRUNCATE" not in migration.upper()
