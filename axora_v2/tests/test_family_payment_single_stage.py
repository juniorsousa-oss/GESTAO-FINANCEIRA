"""Fluxo único de pagamento, sem dupla coleta de quem pagou."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_payment_form_has_only_one_payment_stage():
    html=(ROOT/"static/index.html").read_text()
    js=(ROOT/"static/family.js").read_text()
    css=(ROOT/"static/family.css").read_text()
    assert html.count("<legend>Como foi pago?</legend>")==1
    assert '<legend>Quem pagou? (total em R$)</legend>' not in html
    assert 'id="family-payer-list"' not in html
    assert 'data-family-payers' not in html
    assert 'id="family-manual-payer-list"' in html
    assert 'id="family-wallet-source-list"' in html
    assert 'id="family-manual-details"' in html
    assert 'id="family-wallet-details"' in html
    assert 'Sem descontar saldo' in html
    assert 'Descontar da carteira' in html
    assert 'name="balance_mode" value="none" checked' in html
    assert 'family.css?v=family-hidden-payment-20261123-r1' in html
    assert 'family.js?v=family-hidden-payment-20261123-r1' in html
    assert 'form.querySelector("#family-manual-payer-list").replaceChildren()' in js
    assert 'manualAddPayer(form,true)' in js
    assert 'const {payments,accountSources:expenseSources}=paymentAllocation(form)' in js
    assert 'data-wallet-payer' in js
    assert 'data-family-pagador' not in js
    assert 'form.querySelectorAll("#family-wallet-source-list .family-wallet-source")' in js
    assert 'data-manual-payer' in js and 'data-manual-amount' in js
    assert '.family-manual-payer' in css
    assert '#family-manual-details[hidden]' in css

def test_cost_split_and_existing_backend_contract_remain_separate():
    js=(ROOT/"static/family.js").read_text()
    assert 'entryRows("cost",null,config.shares)' in js
    assert 'walletPaymentSources(form)' in js
    assert 'const useWallet=accountSources!==null' in js
    assert 'body.account_sources=accountSources' in js
    assert 'body.balance_mode="wallet"' in js
    assert 'body.request_id=form.dataset.walletRequestId' in js
    assert 'return {payments:manualPayments(form),accountSources:null}' in js
    assert 'const payments=[...totals].map' in js
    assert 'return {payments,accountSources:sources}' in js
