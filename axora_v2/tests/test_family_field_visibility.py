"""Regressões de visibilidade e rótulos no diálogo de entradas/saídas familiares.

A regra .family-dialog .field { display:grid } não pode se sobrepor ao
atributo HTML hidden: campo de recebedor é exclusivo de entradas.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "static"


def test_income_recipient_is_hidden_when_payment_is_an_expense():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "family.js").read_text(encoding="utf-8")
    css = (ROOT / "family.css").read_text(encoding="utf-8")

    assert 'id="family-income-recipient-wrap" hidden' in html
    assert 'if(income)income.hidden=expense;' in js
    assert '.family-dialog .field[hidden]' in css
    assert '.family-dialog fieldset[hidden] {display:none!important}' in css


def test_provision_payment_keeps_expense_type_and_correct_action_label():
    js = (ROOT / "family.js").read_text(encoding="utf-8")
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert 'form.elements.classification.disabled=Boolean(config.occurrence_id);' in js
    assert 'form.elements.classification.value=config.occurrence_id?"SAÍDA":"SAÍDA";' in js
    assert '"Confirmar pagamento":expense?"Salvar rateio":"Salvar entrada"' in js
    assert 'value="SAÍDA">Saída / despesa' in html
