"""A experiência do perfil secundário é neutra e não anuncia dados ocultos."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "static"

def test_bank_cards_do_not_have_hidden_balance_notices():
    source = (ROOT / "banking.js").read_text()
    assert "Saldo visível" not in source
    assert "Contas autorizadas" not in source
    assert "Somente os saldos" not in source
    assert "Os rótulos de visibilidade familiar serão ativados" not in source
    assert "if(me?.family_enabled && me.family_role!==\"principal\")return \"\";" in source
    assert "bank-person-detail" in source
    assert "bank-account-currency" in source

def test_family_labels_are_not_listed_for_secondary():
    source = (ROOT / "family.js").read_text()
    assert "Você vê apenas dados próprios" not in source
    assert "Ser beneficiário ou pagador não libera acesso" not in source
    assert "const summaryNote=own()" in source

def test_sidebar_hides_disallowed_routes_visually():
    source = (ROOT / "app.js").read_text()
    css = (ROOT / "family.css").read_text()
    assert '.nav-link[hidden]' in css
    assert '["reconciliation","accounts","debts","forecasts","import"].includes(next)' in source
    assert 'if(next==="settings"&&!restricted)' in source

def test_all_money_amounts_in_bank_cards_do_not_split():
    css = (ROOT / "banking.css").read_text()
    assert ".bank-account-currency{white-space:nowrap!important" in css
    assert ".bank-person-amount>strong" in css
    assert "grid-template-columns:repeat(auto-fit" in css
