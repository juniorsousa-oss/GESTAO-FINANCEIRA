-- AXORA Pluggy piloto: vínculo explícito e leitura bancária, isolados por workspace.
-- Não modifica lançamentos, usuários, históricos nem contas manuais existentes.
BEGIN;
CREATE TABLE IF NOT EXISTS public.finance_pluggy_intents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
  account_id bigint NOT NULL,
  initiated_by bigint NOT NULL REFERENCES public.finance_users(id) ON DELETE RESTRICT,
  expires_at timestamptz NOT NULL DEFAULT (now()+interval '40 minutes'),
  created_at timestamptz NOT NULL DEFAULT now(),
  provider_item_id uuid,
  completed_at timestamptz,
  FOREIGN KEY(account_id,workspace_id)
    REFERENCES public.finance_bank_accounts(id,workspace_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS axora_pluggy_intent_workspace
  ON public.finance_pluggy_intents(workspace_id,initiated_by,created_at DESC);
ALTER TABLE public.finance_pluggy_intents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.finance_pluggy_intents FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.finance_pluggy_intents TO service_role;

ALTER TABLE public.finance_bank_accounts
  ADD COLUMN IF NOT EXISTS pluggy_item_id uuid,
  ADD COLUMN IF NOT EXISTS pluggy_account_id uuid,
  ADD COLUMN IF NOT EXISTS pluggy_sandbox boolean,
  ADD COLUMN IF NOT EXISTS pluggy_balance numeric(16,2),
  ADD COLUMN IF NOT EXISTS pluggy_last_synced timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS axora_pluggy_provider_account_unique
  ON public.finance_bank_accounts(pluggy_account_id)
  WHERE pluggy_account_id IS NOT NULL;
ALTER TABLE public.finance_bank_accounts
  DROP CONSTRAINT IF EXISTS finance_bank_accounts_connection_status_check;
ALTER TABLE public.finance_bank_accounts
  ADD CONSTRAINT axora_bank_connection_status_check
  CHECK(connection_status IN ('manual','pluggy_sandbox','pluggy_live'));

COMMIT;
NOTIFY pgrst,'reload schema';
