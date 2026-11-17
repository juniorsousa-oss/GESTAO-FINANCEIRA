"""Cadastro central AXORA: um único conjunto de titulares sem duplicar responsáveis."""
from pathlib import Path
import pytest
from fastapi import HTTPException
from axora_v2 import catalogs, main

BASE = Path(__file__).resolve().parents[1] / "static"
WORKSPACE = "feea46b5-a1e2-420d-aa2c-01da398d4bc9"


def test_provision_uses_bank_holder_master_without_cross_workspace(monkeypatch):
    seen = []

    monkeypatch.setattr(main, "finance_catalog_items", lambda workspace: [
        {"kind": "category", "name": "Saúde", "active": True},
        {"kind": "responsible", "name": "Responsável histórico", "active": True},
        {"kind": "responsible", "name": "Bianca", "active": True},
    ] if workspace == WORKSPACE else pytest.fail("Outro workspace consultado"))

    def fake_call(method, table, *, params=None, **kwargs):
        assert method == "GET" and table == "finance_bank_holders"
        assert params["workspace_id"] == "eq." + WORKSPACE
        assert params["select"] == "name"
        seen.append(params)
        return [{"name": "Bianca"}, {"name": "Sérgio"}, {"name": "Maria José"}]

    monkeypatch.setattr(main.db, "call", fake_call)
    options = main.finance_provision_options(WORKSPACE, {"p_responsible": "Maria José"})
    assert len([x for x in options if x["kind"] == "responsible" and x["name"] == "Bianca"]) == 1
    assert set(x["name"] for x in options if x["kind"] == "responsible") == {
        "Responsável histórico", "Bianca", "Sérgio", "Maria José"
    }
    assert seen and len(seen) == 1
    values = {"p_category": "saúde", "p_responsible": "maria josé"}
    assert catalogs.canonicalize_provision(values, options)["p_responsible"] == "Maria José"
    with pytest.raises(HTTPException):
        catalogs.canonicalize_provision({"p_category": "Saúde", "p_responsible": "Intruso"}, options)


def test_ui_registry_is_only_in_settings_and_account_selections_reuse_it():
    banking = (BASE / "banking.js").read_text(encoding="utf-8")
    app = (BASE / "app.js").read_text(encoding="utf-8")
    styles = (BASE / "banking.css").read_text(encoding="utf-8")
    catalogs_js = (BASE / "catalogs.js").read_text(encoding="utf-8")
    provisions = (BASE / "provisions.js").read_text(encoding="utf-8")
    html = (BASE / "index.html").read_text(encoding="utf-8")

    assert "function bankingHolderCatalogPanel()" in banking
    assert "function bankingHolderOptions()" in banking
    assert "bankingHolderOptions().map(h=>({id:h.id,label:h.name}))" in banking
    assert 'id="bank-holder-settings"' in banking
    assert "bankingHolderCatalogPanel()" in app
    assert 'if(page==="bank-accounts")return' in app
    assert 'Novo titular' not in app[app.index("function actionButtons()"):app.index("function render(){")]
    page_part = banking[banking.index("function bankingAccountsPage()"):banking.index("function bankTransactionRow(")]
    assert "bankingHolderCatalogPanel()" not in page_part
    assert 'panel("Titulares cadastrados"' not in page_part
    assert "open-holder-settings" in page_part
    assert "bankingHolderOptions()" in catalogs_js
    assert "loadBanking(false)" in provisions
    assert "banking.js?v=mobile-audit-r1" in html
    assert "catalogs.js?v=split-modes-r1" in html
    assert ".bank-people-grid{\n  display:flex;" in styles
    assert "align-items:stretch" in styles
    assert "grid-template-columns:repeat(auto-fill" in styles


def test_secondary_cannot_access_holder_admin_panel():
    js = (BASE / "banking.js").read_text(encoding="utf-8")
    start = js.index("function bankingHolderCatalogPanel(){")
    assert 'if(me?.family_enabled&&me.family_role!=="principal")return "";' in js[start:start+250]
    # A filtragem de contas em papéis secundários continua no backend.
    api = (BASE.parent / "main.py").read_text(encoding="utf-8")
    assert 'family_service.filter_rows(user, "conta", accounts)' in api
