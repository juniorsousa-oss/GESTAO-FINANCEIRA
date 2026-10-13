-- AXORA 2.0: resolve PostgREST PGRST201 (HTTP 300) em Provisões.
-- A migração de isolamento acrescentou uma FK composta (rule_id,workspace_id)
-- sem remover a FK anterior (rule_id), criando duas relações para a mesma tabela.
-- Mantém apenas a FK composta, que também assegura isolamento por workspace.
-- Não altera, exclui ou recria quaisquer registros financeiros.
BEGIN;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid='public.finance_provision_occurrences'::regclass
      AND conname='axora_occurrence_workspace_fk'
      AND contype='f'
      AND confrelid='public.finance_provision_rules'::regclass
  ) THEN
    RAISE EXCEPTION 'FK composta de isolamento não encontrada. Nenhuma alteração feita.';
  END IF;
END;
$$;
ALTER TABLE public.finance_provision_occurrences
  DROP CONSTRAINT IF EXISTS finance_provision_occurrences_rule_id_fkey;
COMMIT;

-- Recarrega as relações para consultas PostgREST da API do AXORA.
NOTIFY pgrst, 'reload schema';
