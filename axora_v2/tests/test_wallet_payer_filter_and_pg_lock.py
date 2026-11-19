"""Regressão do erro real 0A000 e da filtragem de contas por responsável."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_wallet_lock_is_scoped_to_bank_account_table():
    original=(ROOT/"migrations/20261117_family_wallet_payment_sources.sql").read_text()
    fix=(ROOT/"migrations/20261117_family_wallet_lock_fix.sql").read_text()
    assert "ORDER BY a.id FOR UPDATE;" in original
    assert "ORDER BY a.id FOR UPDATE OF a;" in fix
    assert "FOR UPDATE;" not in fix
    assert "CREATE OR REPLACE FUNCTION axora_beta.axora_family_apply_wallet_debits" in fix
    assert "axora_beta.finance_bank_accounts" in fix or "finance_bank_accounts a" in fix
    assert "finance_family_balance_debits" in fix
    assert "manual_balance=manual_balance-v_row.amount" in fix
    assert "BEGIN;" in fix and fix.rstrip().endswith("COMMIT;")
    assert "ALTER TABLE public." not in fix
    assert "DROP TABLE" not in fix and "TRUNCATE" not in fix


def test_wallet_account_selection_requires_payer_and_filters_accounts():
    js=(ROOT/"static/family.js").read_text()
    css=(ROOT/"static/family.css").read_text()
    html=(ROOT/"static/index.html").read_text()
    assert "walletPayerOptions()" in js
    assert "walletAccountOptions(profileId)" in js
    assert "walletChoosePayer(form,row)" in js
    assert "walletChooseAccount(form,row)" in js
    assert "walletAvailableAccounts().filter(a=>a.profile_id===Number(profileId))" in js
    assert 'data-wallet-payer aria-label="Responsável pelo pagamento"' in js
    assert 'data-wallet-account aria-label="Conta de origem" disabled' in js
    assert 'account.profile_id!==payer' in js
    assert "rows.length===1" in js
    assert 'data-wallet-amount' in js
    assert 'family.js?v=income-wallet-20261119-r1' in html
    assert 'family.css?v=profile-directory-privacy-r1' in html
    assert "#family-wallet-source-list>.family-wallet-source" in css
    assert "Escolha o responsável" in js
