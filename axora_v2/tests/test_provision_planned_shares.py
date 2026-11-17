"""Rateio planejado, tipos enxutos e segurança do AXORA BETA."""
from pathlib import Path
import importlib
from fastapi import HTTPException
from fastapi.testclient import TestClient
from axora_v2 import db, security, family_service

main = importlib.import_module("axora_v2.main")
app = main.app
W="11111111-2222-3333-4444-555555555555"
BASE=Path(__file__).resolve().parents[1]
PRINCIPAL={"id":17,"display_name":"Responsável principal","is_admin":False,"csrf":"tok"}
CTX={"workspace_id":W,"profile_id":10,"role":"principal","owner_id":17,"user_id":17}
MEMBERS=[
    {"id":10,"display_name":"Responsável principal","relationship":"principal","active":True},
    {"id":11,"display_name":"Cônjuge","relationship":"conjuge","active":True},
    {"id":12,"display_name":"Dependente","relationship":"filho","active":True},
]


def test_atomic_provision_split_endpoint_and_rejects_invalid_participants(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake")
    monkeypatch.setenv("SESSION_SECRET","a"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    monkeypatch.setattr(security,"current",lambda _request:dict(PRINCIPAL))
    monkeypatch.setattr(family_service,"context",lambda _user:dict(CTX))
    monkeypatch.setattr(family_service,"profiles",lambda _user:list(MEMBERS))
    monkeypatch.setattr(main,"user_workspace",lambda _user:W)
    monkeypatch.setattr(security,"require_csrf",
        lambda request,user:None if request.headers.get("x-csrf-token")=="tok"
        else (_ for _ in ()).throw(HTTPException(403,"CSRF")))
    created=[]
    def fake_call(method,table,*,params=None,data=None,prefer=None):
        if table=="rpc/axora_ensure_catalog":return 0
        if table=="finance_catalog_options":
            return [{"kind":"category","name":"Moradia","active":True},
                    {"kind":"responsible","name":"Próprio","active":True}]
        if table=="finance_bank_holders":return []
        if table=="rpc/axora_family_create_provision_with_shares":
            created.append(data)
            return 400
        raise AssertionError("Unexpected DB call "+table)
    monkeypatch.setattr(db,"call",fake_call)
    payload={"description":"Energia","category":"Moradia",
      "responsible":"Responsável principal","start_due_date":"2026-11-17",
      "planned_value":150,"value_mode":"fixed","recurrence":"unlimited",
      "frequency":"monthly","payment_method":"none",
      "cost_shares":[{"profile_id":10,"percentage":60},
                     {"profile_id":11,"percentage":40}]}
    h={"X-CSRF-Token":"tok"}
    with TestClient(app) as client:
        assert client.post("/api/provisions",json=payload).status_code==403
        r=client.post("/api/provisions",json=payload,headers=h)
        assert r.status_code==200, r.text
        assert r.json()["id"]==400
        assert created[0]["p_actor_id"]==17
        assert created[0]["p_workspace_id"]==W
        assert created[0]["p_shares"]==payload["cost_shares"] or all(
          str(a["percentage"])==str(b["percentage"]) for a,b in zip(created[0]["p_shares"],payload["cost_shares"]))
        for bad in [
            [{"profile_id":10,"percentage":90}],
            [{"profile_id":10,"percentage":50},{"profile_id":10,"percentage":50}],
            [{"profile_id":999,"percentage":100}],
            [{"profile_id":10,"percentage":100.001}],
        ]:
            assert client.post("/api/provisions",json={**payload,"cost_shares":bad},
                headers=h).status_code==422
    assert len(created)==1


def test_planned_share_lookup_owner_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY","fake")
    monkeypatch.setenv("SESSION_SECRET","a"*64)
    monkeypatch.setenv("COOKIE_SECURE","0")
    role={"value":"principal"}
    monkeypatch.setattr(security,"current",lambda _request:dict(PRINCIPAL))
    monkeypatch.setattr(family_service,"context",lambda _:{**CTX,"role":role["value"]})
    called=[]
    def fake_table(name,workspace,*,fields="*",filters=None,limit=1000,order=None):
        called.append(name)
        assert workspace==W and filters=={"id":"eq.8"} if name=="finance_provision_rules" else filters=={"rule_id":"eq.8"}
        if name=="finance_provision_rules":return [{"id":8}]
        return [{"profile_id":10,"percentage":60},{"profile_id":11,"percentage":40}]
    monkeypatch.setattr(family_service,"table",fake_table)
    with TestClient(app) as client:
        r=client.get("/api/family/provisions/8/shares")
        assert r.status_code==200, r.text
        assert len(r.json()["shares"])==2
        role["value"]="conjuge"
        assert client.get("/api/family/provisions/8/shares").status_code==403
    assert called==["finance_provision_rules","finance_provision_cost_shares"]


def test_ui_split_modes_and_single_responsible_source():
    html=(BASE/"static/index.html").read_text()
    js=(BASE/"static/provisions.js").read_text()
    cat=(BASE/"static/catalogs.js").read_text()
    family=(BASE/"static/family.js").read_text()
    sql=(BASE/"migrations/20261117_provision_planned_shares.sql").read_text()
    assert 'id="provision-split-fieldset"' in html
    assert 'id="pv-limit-recurring"' in html
    assert '<option value="until_date">' not in html
    assert '<option value="once">Único</option>' in html
    assert '<option value="unlimited" selected>Recorrente</option>' in html
    assert '<option value="installments">Parcelado</option>' in html
    assert 'values.recurrence="until_date"' in js
    assert 'values.cost_shares=shares' in js
    assert 'provisionSplitEqual()' in js
    assert 'items=members.filter(p=>p.active).map(p=>p.display_name)' in cat
    assert 'function entryRows(type,predefined=null,shares=[])' in family
    assert '/api/family/provisions/' in family
    assert 'CREATE TABLE axora_beta.finance_provision_cost_shares' in sql
    assert 'axora_family_create_provision_with_shares' in sql
    assert 'axora_create_provision_with_method(' in sql
    assert 'ALTER TABLE public.' not in sql
    assert 'finance_movements' not in sql


def test_provision_scrollbar_stays_inside_rounded_modal_on_desktop():
    """Scrollbar must not overlap the upper/lower rounded modal edges."""
    css=(BASE/"static/provisions.css").read_text()
    html=(BASE/"static/index.html").read_text()
    assert '@media (min-width:851px)' in css
    assert 'dialog.provision-dialog:not(.provision-pix-dialog){' in css
    assert 'overflow:hidden;' in css.split('dialog.provision-dialog:not(.provision-pix-dialog){',1)[1].split('}',1)[0]
    content=css.split('dialog.provision-dialog:not(.provision-pix-dialog)>form{',1)[1].split('}',1)[0]
    for expected in ('max-height:calc(min(92dvh,840px) - 24px)',
                     'margin:10px 10px 10px 0',
                     'overflow-y:auto',
                     'overscroll-behavior-y:contain',
                     'scrollbar-width:thin'):
        assert expected in content
    assert 'provisions.css?v=modal-scroll-inset-r1' in html
    assert '.provision-split-participants{display:grid;' in css  # internal scrolling remains independent
    assert '@media(max-width:850px)' in (BASE/"static/ios-pwa-finish.css").read_text()
