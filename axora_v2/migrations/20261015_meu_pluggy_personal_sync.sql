-- AXORA: conexão pessoal MeuPluggy, apenas leitura de saldo e extrato.
-- Sem alterações ou exclusões de Registros e Provisões atuais.
BEGIN;
ALTER TABLE public.finance_bank_accounts
  ADD COLUMN IF NOT EXISTS pluggy_item_id uuid,
  ADD COLUMN IF NOT EXISTS pluggy_account_id uuid,
  ADD COLUMN IF NOT EXISTS pluggy_balance numeric(16,2),
  ADD COLUMN IF NOT EXISTS pluggy_last_synced timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS axora_personal_pluggy_account_unique
  ON public.finance_bank_accounts(pluggy_account_id)
  WHERE pluggy_account_id IS NOT NULL;
COMMIT;
NOTIFY pgrst, 'reload schema';
