-- Preserva a assinatura institucional atual e habilita quatro layouts oficiais AXORA.
-- Essa migração não altera movimentações, usuários ou contas.
ALTER TABLE public.finance_brand_assets
  DROP CONSTRAINT IF EXISTS finance_brand_assets_key_check;
ALTER TABLE public.finance_brand_assets
  ADD CONSTRAINT finance_brand_assets_key_check
  CHECK (key IN (
    'institutional_signature',
    'axora_primary',
    'axora_secondary',
    'axora_icon',
    'axora_favicon'
  ));
