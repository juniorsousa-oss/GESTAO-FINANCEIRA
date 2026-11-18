-- AXORA BETA | Carteira de dívidas (modelo ACOMPANHAMENTOS / DEMAIS DÍVIDAS)
-- Nenhuma importação automática nem alteração nos saldos ou lançamentos.
-- A renegociação cria Provisões futuras numa transação indivisível.
BEGIN;
ALTER TABLE axora_beta.finance_debts
  ADD COLUMN IF NOT EXISTS category text,
  ADD COLUMN IF NOT EXISTS responsible text,
  ADD COLUMN IF NOT EXISTS initial_paid_installments integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS linked_provision_rule_id bigint,
  ADD COLUMN IF NOT EXISTS renegotiated_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS axora_debts_linked_rule_unique
  ON axora_beta.finance_debts (linked_provision_rule_id)
  WHERE linked_provision_rule_id IS NOT NULL;
ALTER TABLE axora_beta.finance_debts
  ADD CONSTRAINT axora_debts_linked_rule_fk FOREIGN KEY(linked_provision_rule_id)
  REFERENCES axora_beta.finance_provision_rules(id) ON DELETE RESTRICT;

CREATE OR REPLACE FUNCTION axora_beta.axora_debt_renegotiate(
  p_workspace_id uuid, p_actor_id bigint, p_debt_id bigint,
  p_total_installments integer, p_paid_installments integer,
  p_installment_value numeric, p_first_due_date date,
  p_category text, p_responsible text, p_profile_id bigint DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'axora_beta', 'public'
AS $function$
DECLARE
  v_debt axora_beta.finance_debts%ROWTYPE;
  v_rule bigint;
  v_remaining integer;
  v_name text;
BEGIN
  -- Mesmo a API usando service_role, o banco valida o principal do workspace.
  IF NOT EXISTS(
    SELECT 1 FROM axora_beta.finance_workspaces w
    WHERE w.id=p_workspace_id AND w.created_by=p_actor_id AND w.is_active
  ) THEN RAISE EXCEPTION 'Somente o principal pode renegociar dívidas'; END IF;
  IF p_debt_id IS NULL OR p_debt_id<1 THEN
    RAISE EXCEPTION 'Dívida inválida'; END IF;
  SELECT * INTO v_debt FROM axora_beta.finance_debts d
    WHERE d.id=p_debt_id AND d.workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Dívida não encontrada'; END IF;
  IF v_debt.linked_provision_rule_id IS NOT NULL OR
     upper(coalesce(v_debt.status,''))='RENEGOCIADO' THEN
    RAISE EXCEPTION 'Esta dívida já possui acordo; não duplicar provisões'; END IF;
  IF p_total_installments IS NULL OR p_total_installments<1 OR p_total_installments>360
     OR p_paid_installments IS NULL OR p_paid_installments<0
     OR p_paid_installments>=p_total_installments THEN
    RAISE EXCEPTION 'Quantidade de parcelas inválida'; END IF;
  IF p_installment_value IS NULL OR p_installment_value<=0 OR
     p_installment_value>1000000000000 OR
     round(p_installment_value,2)<>p_installment_value THEN
    RAISE EXCEPTION 'Valor da parcela inválido'; END IF;
  IF p_first_due_date IS NULL THEN RAISE EXCEPTION 'Primeiro vencimento obrigatório'; END IF;
  IF length(btrim(coalesce(p_category,''))) NOT BETWEEN 1 AND 120 THEN
    RAISE EXCEPTION 'Categoria inválida'; END IF;
  IF length(btrim(coalesce(p_responsible,''))) NOT BETWEEN 1 AND 120 THEN
    RAISE EXCEPTION 'Responsável inválido'; END IF;
  IF p_profile_id IS NOT NULL THEN
    SELECT f.display_name INTO v_name FROM axora_beta.finance_family_profiles f
    WHERE f.workspace_id=p_workspace_id AND f.id=p_profile_id AND f.active;
    IF NOT FOUND THEN RAISE EXCEPTION 'Responsável não pertence a esta família'; END IF;
    IF v_name<>btrim(p_responsible) THEN
      RAISE EXCEPTION 'Responsável divergente do cadastro familiar'; END IF;
  END IF;
  v_remaining:=p_total_installments-p_paid_installments;
  -- A primeira provisão é a primeira parcela ainda em aberto. Pagas fora do
  -- AXORA não são lançadas retroativamente nem geram pagamentos duplicados.
  v_rule:=axora_beta.axora_create_provision(
    p_workspace_id,v_debt.description,btrim(p_category),btrim(p_responsible),
    p_first_due_date,p_installment_value,'fixed','installments','monthly',
    NULL,v_remaining
  );
  IF p_profile_id IS NOT NULL THEN
    INSERT INTO axora_beta.finance_provision_cost_shares(
      workspace_id,rule_id,profile_id,percentage
    ) VALUES(p_workspace_id,v_rule,p_profile_id,100);
  END IF;
  UPDATE axora_beta.finance_debts
  SET status='RENEGOCIADO',
      category=btrim(p_category),responsible=btrim(p_responsible),
      total_installments=p_total_installments,
      paid_installments=p_paid_installments,
      initial_paid_installments=p_paid_installments,
      installment_value=p_installment_value,
      open_value=round(v_remaining*p_installment_value,2),
      linked_provision_rule_id=v_rule,
      renegotiated_at=now()
  WHERE id=p_debt_id AND workspace_id=p_workspace_id;
  RETURN jsonb_build_object(
    'debt_id',p_debt_id,'provision_rule_id',v_rule,
    'remaining_installments',v_remaining,
    'open_value',round(v_remaining*p_installment_value,2)
  );
END;
$function$;

-- Atualiza o saldo da dívida quando cada Provisão vinculada é quitada.
-- Não há movimentação bancária neste trigger: apenas saldo da dívida.
CREATE OR REPLACE FUNCTION axora_beta.axora_debt_sync_on_payment()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'axora_beta','public'
AS $function$
BEGIN
  UPDATE axora_beta.finance_debts d
     SET paid_installments=LEAST(d.total_installments,
        d.initial_paid_installments+
        (SELECT count(*) FROM axora_beta.finance_provision_occurrences o
         WHERE o.workspace_id=d.workspace_id
           AND o.rule_id=d.linked_provision_rule_id AND o.status='paid')),
         open_value=round(GREATEST(0,d.total_installments-d.initial_paid_installments-
        (SELECT count(*) FROM axora_beta.finance_provision_occurrences o
         WHERE o.workspace_id=d.workspace_id
           AND o.rule_id=d.linked_provision_rule_id AND o.status='paid'))*
         d.installment_value,2)
   WHERE d.workspace_id=NEW.workspace_id
     AND d.linked_provision_rule_id=NEW.rule_id;
  RETURN NEW;
END;
$function$;
DROP TRIGGER IF EXISTS axora_debt_paid_occurrence_sync ON axora_beta.finance_provision_occurrences;
CREATE TRIGGER axora_debt_paid_occurrence_sync
AFTER UPDATE OF status ON axora_beta.finance_provision_occurrences
FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION axora_beta.axora_debt_sync_on_payment();

REVOKE ALL ON FUNCTION axora_beta.axora_debt_renegotiate(uuid,bigint,bigint,integer,integer,numeric,date,text,text,bigint)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_debt_renegotiate(uuid,bigint,bigint,integer,integer,numeric,date,text,text,bigint)
  TO service_role;
REVOKE ALL ON FUNCTION axora_beta.axora_debt_sync_on_payment() FROM PUBLIC,anon,authenticated;
NOTIFY pgrst, 'reload schema';
COMMIT;
