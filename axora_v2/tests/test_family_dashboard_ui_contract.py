"""AXORA UI finance regression: all members and scope-safe dashboard."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1] / "static"


def test_sidebar_provisions_first_and_reconciliation_paused():
    html=(ROOT/"index.html").read_text()
    assert html.index('data-page="provisions"') < html.index('data-page="movements"')
    assert '<button data-page="reconciliation" class="nav-link" hidden' in html
    css=(ROOT/"banking-advanced.css").read_text()
    assert '.nav-link[data-page="reconciliation"]{display:none!important}' in css
    script=(ROOT/"app.js").read_text()
    assert 'if(next==="reconciliation")return;' in script
    assert 'panel("Conciliação de saldo"' not in script


def test_all_bank_only_members_have_same_attribution_fields():
    script=(ROOT/"family.js").read_text()
    assert 'function personMetrics(data, pending=false)' in script
    assert '["Entradas","entradas"]' in script
    assert '["Despesas atribuídas","despesas"]' in script
    assert '["Efetivamente pago","pagamentos"]' in script
    assert '["Saldo pessoal","saldo"]' in script
    assert 'personMetrics(metrics)' in script
    assert 'personMetrics(null,true)' in script
    assert 'data-family-action="activate-bank-member"' in script
    # Nunca criar logins ao ativar um perfil de rateio.
    assert 'display_name:name,relationship,password:null' in script


def test_dashboard_uses_authorized_banking_aggregate_not_global_legacy_cash():
    script=(ROOT/"app.js").read_text()
    bank=(ROOT/"banking.js").read_text()
    assert 'function bankDashboardMetric()' in script
    assert 'money(balances.combined)' in script
    assert 'money(balances.cash_total)' in script
    assert 'money(balances.investment_total)' in script
    assert 'metric("Saldo localizado",x.located' not in script
    assert 'bankDashboardMetric()' in script
    assert 'page==="dashboard"||page==="bank-accounts"' in bank
    # Não apresentar o nome "saldo autorizado" nem a existência de dados ocultos.
    assert '"Saldos autorizados"' not in script
    assert '"Saldos ocultos"' not in script


def test_family_card_name_and_relationship_have_separate_lines():
    """Action menus must not collapse member name and relationship inline."""
    css=(ROOT/"family.css").read_text()
    js=(ROOT/"family.js").read_text()
    html=(ROOT/"index.html").read_text()
    assert js.count('class="family-person-identity"><strong>') >= 2
    assert '</strong><small>' in js
    assert '.family-person-heading>.family-person-identity{' in css
    rules=css.split('.family-person-heading>.family-person-identity{',1)[1].split('}',1)[0]
    assert 'flex-direction:column;' in rules
    assert 'gap:6px;' in rules
    assert '.family-person-heading>div:last-child' not in css
    assert 'family.css?v=single-payment-stage-r1' in html
