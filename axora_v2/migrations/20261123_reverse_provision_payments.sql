-- AXORA BETA | Reversao auditada de quitacao e estorno de saldo, atomicos.
-- Exclusivamente axora_beta. Nao altera public, producao nem dados existentes.
-- O registro criado para a quitacao e retirado; registros vinculados previamente
-- sao preservados. O historico de reversao fica nesta tabela independente.
BEGIN;

CREATE TABLE IF NOT EXISTS axora_beta.finance_provision_payment_reversals (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES axora_beta.finance_workspaces(id) ON DELETE RESTRICT,
  occurrence_id bigint NOT NULL REFERENCES axora_beta.finance_provision_occurrences(id) ON DELETE RESTRICT,
  movement_id bigint NOT NULL,
  actor_user_id bigint NOT NULL REFERENCES axora_beta.finance_users(id) ON DELETE RESTRICT,
  was_existing_record boolean NOT NULL,
  paid_amount numeric(14,2) NOT NULL CHECK(paid_amount>0),
  restored_wallet_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK(restored_wallet_amount>=0),
  movement_snapshot jsonb NOT NULL,
  costs_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
  payments_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
  wallet_sources_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
  provision_link_snapshot jsonb,
  variable_reference_after numeric(14,2),
  reversed_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT axora_reversed_movement_once UNIQUE(workspace_id,movement_id)
);
CREATE INDEX IF NOT EXISTS finance_provision_payment_reversals_by_occurrence
  ON axora_beta.finance_provision_payment_reversals(workspace_id,occurrence_id,reversed_at DESC);
ALTER TABLE axora_beta.finance_provision_payment_reversals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE axora_beta.finance_provision_payment_reversals FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON axora_beta.finance_provision_payment_reversals TO service_role;
GRANT USAGE,SELECT ON SEQUENCE axora_beta.finance_provision_payment_reversals_id_seq TO service_role;

CREATE OR REPLACE FUNCTION axora_beta.axora_family_reverse_provision_payment(
  p_workspace_id uuid,
  p_actor_id bigint,
  p_occurrence_id bigint,
  p_reference_value numeric DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path TO 'axora_beta','pg_temp' AS $fn$
DECLARE
  v_occ record;
  v_movement axora_beta.finance_movements%ROWTYPE;
  v_link jsonb;
  v_is_linked boolean := false;
  v_costs jsonb := '[]'::jsonb;
  v_payments jsonb := '[]'::jsonb;
  v_sources jsonb := '[]'::jsonb;
  v_source_count integer := 0;
  v_debit_total numeric;
  v_source_total numeric;
  v_ref_amount numeric;
  v_ref_paid_value numeric;
  v_ref_paid_date date;
  v_ref_required boolean := false;
  v_restore_amount numeric := 0;
  v_row record;
  v_restored_rows integer := 0;
BEGIN
  IF p_workspace_id IS NULL OR p_actor_id IS NULL OR p_occurrence_id IS NULL
     OR p_occurrence_id<1 THEN
    RAISE EXCEPTION 'Dados da reversao invalidos';
  END IF;
  PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
  -- Somente o titular principal tem autorizacao para restituir saldo.
  IF NOT EXISTS (
    SELECT 1 FROM finance_workspaces w
    JOIN finance_family_profiles f
      ON f.workspace_id=w.id AND f.linked_user_id=p_actor_id AND f.active
    JOIN finance_users u ON u.id=p_actor_id AND u.is_active
    WHERE w.id=p_workspace_id AND w.is_active AND w.created_by=p_actor_id
      AND f.relationship='principal'
  ) THEN RAISE EXCEPTION 'Somente o principal pode desfazer o pagamento'; END IF;

  -- Segura a mesma ocorrencia contra quitações/estornos simultaneos.
  PERFORM pg_advisory_xact_lock(hashtextextended(
      'axora-reverse:'||p_workspace_id::text||':'||p_occurrence_id::text, 0));
  SELECT o.*,coalesce(o.value_mode_override,r.value_mode) AS effective_mode,
         r.last_paid_value AS rule_last_paid_value,
         r.planned_value AS rule_planned_value,
         r.value_mode AS rule_mode
    INTO v_occ
    FROM finance_provision_occurrences o
    JOIN finance_provision_rules r
      ON r.id=o.rule_id AND r.workspace_id=o.workspace_id
    WHERE o.id=p_occurrence_id AND o.workspace_id=p_workspace_id
    FOR UPDATE OF o;
  IF NOT FOUND OR v_occ.status<>'paid' THEN
    RAISE EXCEPTION 'Esta provisao nao possui pagamento ativo para desfazer';
  END IF;
  SELECT * INTO v_movement FROM finance_movements
    WHERE workspace_id=p_workspace_id AND provision_occurrence_id=p_occurrence_id
    FOR UPDATE;
  IF NOT FOUND OR v_movement.classification<>'SAÍDA'
      OR v_movement.value IS DISTINCT FROM v_occ.paid_value THEN
    RAISE EXCEPTION 'Pagamento e registro divergentes: correcao automatica bloqueada';
  END IF;

  -- Uma conciliacao bancaria precisa primeiro ser desfeita no fluxo apropriado.
  IF EXISTS(
    SELECT 1 FROM finance_bank_transactions t
    WHERE t.workspace_id=p_workspace_id
      AND (t.movement_id=v_movement.id OR t.provision_occurrence_id=p_occurrence_id)
  ) THEN RAISE EXCEPTION 'Desfaca primeiro a conciliacao bancaria deste pagamento'; END IF;

  SELECT to_jsonb(l) INTO v_link
    FROM finance_provision_record_links l
    WHERE l.workspace_id=p_workspace_id AND l.occurrence_id=p_occurrence_id
      AND l.movement_id=v_movement.id;
  v_is_linked := v_link IS NOT NULL;
  IF EXISTS(SELECT 1 FROM finance_provision_record_links l
    WHERE l.workspace_id=p_workspace_id AND l.occurrence_id=p_occurrence_id
      AND l.movement_id<>v_movement.id)
    THEN RAISE EXCEPTION 'Vinculo de registro inconsistente'; END IF;

  SELECT coalesce(jsonb_agg(to_jsonb(c)),'[]'::jsonb)
    INTO v_costs FROM finance_family_cost_allocations c
    WHERE c.workspace_id=p_workspace_id AND c.movement_id=v_movement.id;
  SELECT coalesce(jsonb_agg(to_jsonb(p)),'[]'::jsonb)
    INTO v_payments FROM finance_family_payment_allocations p
    WHERE p.workspace_id=p_workspace_id AND p.movement_id=v_movement.id;
  SELECT coalesce(jsonb_agg(to_jsonb(s)),'[]'::jsonb),
         count(*),coalesce(sum(s.amount),0)
    INTO v_sources,v_source_count,v_source_total
    FROM finance_family_balance_debit_sources s
    WHERE s.workspace_id=p_workspace_id AND s.movement_id=v_movement.id;
  SELECT d.amount INTO v_debit_total FROM finance_family_balance_debits d
    WHERE d.workspace_id=p_workspace_id AND d.movement_id=v_movement.id;

  IF NOT v_is_linked THEN
    IF EXISTS(SELECT 1 FROM finance_family_balance_credits c
       WHERE c.workspace_id=p_workspace_id AND c.movement_id=v_movement.id)
    THEN RAISE EXCEPTION 'Entrada vinculada indevidamente: reversao bloqueada'; END IF;
    IF (v_debit_total IS NULL AND v_source_count<>0)
       OR (v_debit_total IS NOT NULL AND
           (v_source_count=0 OR v_debit_total<>v_source_total
            OR v_debit_total<>v_movement.value))
    THEN RAISE EXCEPTION 'Saldos e lancamento nao conferem; reversao bloqueada'; END IF;
    v_restore_amount:=coalesce(v_debit_total,0);
  END IF;

  -- Uma provisao variavel pode ter redefinido o valor dos proximos vencimentos.
  -- Se nao ha pagamento mais recente, reconstrua a referencia de maneira explicita.
  IF v_occ.effective_mode='variable' AND NOT EXISTS(
    SELECT 1 FROM finance_provision_occurrences later
      WHERE later.workspace_id=p_workspace_id AND later.rule_id=v_occ.rule_id
        AND later.sequence_no>v_occ.sequence_no AND later.status='paid'
  ) THEN
    v_ref_required:=true;
    IF v_occ.rule_last_paid_value IS DISTINCT FROM v_movement.value
       OR (v_occ.rule_mode='variable' AND
           v_occ.rule_planned_value IS DISTINCT FROM v_movement.value)
    THEN RAISE EXCEPTION 'Referencia variavel alterada: revise antes de estornar'; END IF;
    SELECT prev.paid_value, prev.payment_date
      INTO v_ref_paid_value,v_ref_paid_date
      FROM finance_provision_occurrences prev
      WHERE prev.workspace_id=p_workspace_id AND prev.rule_id=v_occ.rule_id
        AND prev.sequence_no<v_occ.sequence_no AND prev.status='paid'
      ORDER BY prev.sequence_no DESC LIMIT 1;
    IF v_ref_paid_value IS NOT NULL THEN
      v_ref_amount:=v_ref_paid_value;
    ELSE
      IF p_reference_value IS NULL OR p_reference_value<=0
          OR p_reference_value>999999999999.99
          OR p_reference_value<>round(p_reference_value,2) THEN
        RAISE EXCEPTION 'Informe valor de referencia anterior ao pagamento';
      END IF;
      v_ref_amount:=p_reference_value;
    END IF;
  END IF;

  -- Bloqueio ordenado de contas manuais para evitar concorrencia com transferencias.
  IF v_restore_amount>0 THEN
    PERFORM a.id FROM finance_bank_accounts a
      JOIN finance_family_balance_debit_sources s
        ON s.account_id=a.id AND s.workspace_id=a.workspace_id
    WHERE s.workspace_id=p_workspace_id AND s.movement_id=v_movement.id
    ORDER BY a.id FOR UPDATE OF a;
    SELECT count(*) INTO v_restored_rows
    FROM finance_family_balance_debit_sources s
    JOIN finance_bank_accounts a
      ON a.id=s.account_id AND a.workspace_id=s.workspace_id
    WHERE s.workspace_id=p_workspace_id AND s.movement_id=v_movement.id
      AND a.connection_status='manual' AND a.pluggy_account_id IS NULL
      AND a.pluggy_item_id IS NULL AND a.manual_balance IS NOT NULL
      AND a.manual_balance+s.amount<=999999999999.99;
    IF v_restored_rows<>v_source_count THEN
      RAISE EXCEPTION 'Uma conta de origem nao pode receber estorno automatico';
    END IF;
    FOR v_row IN SELECT account_id,amount FROM finance_family_balance_debit_sources
      WHERE workspace_id=p_workspace_id AND movement_id=v_movement.id
      ORDER BY account_id
    LOOP
      UPDATE finance_bank_accounts a SET manual_balance=a.manual_balance+v_row.amount
      WHERE a.id=v_row.account_id AND a.workspace_id=p_workspace_id
        AND a.connection_status='manual' AND a.pluggy_account_id IS NULL
        AND a.pluggy_item_id IS NULL AND a.manual_balance IS NOT NULL;
      IF NOT FOUND THEN RAISE EXCEPTION 'Conta alterada durante estorno'; END IF;
    END LOOP;
  END IF;

  -- Um registro ja existente deve sobreviver: apenas remove seu vinculo.
  IF v_is_linked THEN
    DELETE FROM finance_provision_record_links
      WHERE workspace_id=p_workspace_id AND occurrence_id=p_occurrence_id
        AND movement_id=v_movement.id;
    UPDATE finance_movements SET provision_occurrence_id=NULL
      WHERE id=v_movement.id AND workspace_id=p_workspace_id;
  ELSE
    -- Preserva snapshots de rateio, pagamento e saldo para auditoria.
    DELETE FROM finance_family_balance_debit_sources
      WHERE workspace_id=p_workspace_id AND movement_id=v_movement.id;
    DELETE FROM finance_family_balance_debits
      WHERE workspace_id=p_workspace_id AND movement_id=v_movement.id;
    DELETE FROM finance_family_cost_allocations
      WHERE workspace_id=p_workspace_id AND movement_id=v_movement.id;
    DELETE FROM finance_family_payment_allocations
      WHERE workspace_id=p_workspace_id AND movement_id=v_movement.id;
    -- A visibilidade/auditoria antiga permanece como tombstone, sem registro
    -- financeiro visivel. IDs de movimentos nao sao reutilizados.
    DELETE FROM finance_movements
      WHERE workspace_id=p_workspace_id AND id=v_movement.id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Registro de pagamento mudou durante estorno'; END IF;
  END IF;

  UPDATE finance_provision_occurrences
    SET status='open',payment_date=NULL,paid_value=NULL
    WHERE id=p_occurrence_id AND workspace_id=p_workspace_id AND status='paid';
  IF NOT FOUND THEN RAISE EXCEPTION 'Provisao alterada durante estorno'; END IF;

  -- Trigger de dividas recalcula parcelas pagas/abertas ao mudar status.
  IF v_ref_required THEN
    UPDATE finance_provision_rules r
    SET last_paid_value=v_ref_paid_value,last_paid_at=v_ref_paid_date,
        planned_value=CASE WHEN r.value_mode='variable'
                      THEN v_ref_amount ELSE r.planned_value END
    WHERE r.workspace_id=p_workspace_id AND r.id=v_occ.rule_id;
    UPDATE finance_provision_revisions rev SET planned_value=v_ref_amount
    WHERE rev.workspace_id=p_workspace_id AND rev.rule_id=v_occ.rule_id
      AND rev.value_mode='variable' AND rev.planned_value=v_movement.value;
    UPDATE finance_provision_occurrences future SET planned_value=v_ref_amount
    FROM finance_provision_rules rule
    WHERE future.rule_id=rule.id AND future.workspace_id=rule.workspace_id
      AND future.workspace_id=p_workspace_id AND future.rule_id=v_occ.rule_id
      AND future.sequence_no>v_occ.sequence_no AND future.status='open'
      AND coalesce(future.value_mode_override,rule.value_mode)='variable'
      AND future.planned_value=v_movement.value;
  END IF;

  INSERT INTO finance_provision_payment_reversals(
    workspace_id,occurrence_id,movement_id,actor_user_id,
    was_existing_record,paid_amount,restored_wallet_amount,movement_snapshot,
    costs_snapshot,payments_snapshot,wallet_sources_snapshot,
    provision_link_snapshot,variable_reference_after
  ) VALUES(
    p_workspace_id,p_occurrence_id,v_movement.id,p_actor_id,
    v_is_linked,v_movement.value,v_restore_amount,to_jsonb(v_movement),
    v_costs,v_payments,v_sources,v_link,v_ref_amount
  );

  RETURN jsonb_build_object(
    'ok',true,'status','open','occurrence_id',p_occurrence_id,
    'movement_id',v_movement.id,'linked_existing_record',v_is_linked,
    'restored_wallet_amount',v_restore_amount,
    'removed_movement',NOT v_is_linked);
END;
$fn$;

REVOKE ALL ON FUNCTION axora_beta.axora_family_reverse_provision_payment(
  uuid,bigint,bigint,numeric) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_family_reverse_provision_payment(
  uuid,bigint,bigint,numeric) TO service_role;

-- Consulta previa somente ao titular: a interface informa o impacto antes de confirmar.
CREATE OR REPLACE FUNCTION axora_beta.axora_family_reverse_payment_preview(
  p_workspace_id uuid,p_actor_id bigint,p_occurrence_id bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path TO 'axora_beta','pg_temp' AS $preview$
DECLARE v_occ record; v_movement_id bigint; v_amount numeric;
        v_linked boolean; v_wallet numeric; v_reference_needed boolean;
        v_bank_linked boolean;
BEGIN
  IF p_occurrence_id IS NULL OR p_occurrence_id<1 THEN
    RAISE EXCEPTION 'Provisao invalida';
  END IF;
  PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
  IF NOT EXISTS(
    SELECT 1 FROM finance_workspaces w JOIN finance_family_profiles f
      ON f.workspace_id=w.id AND f.linked_user_id=p_actor_id AND f.active
    JOIN finance_users u ON u.id=p_actor_id AND u.is_active
    WHERE w.id=p_workspace_id AND w.is_active AND w.created_by=p_actor_id
      AND f.relationship='principal'
  ) THEN RAISE EXCEPTION 'Somente o principal pode consultar reversao'; END IF;
  SELECT o.*,coalesce(o.value_mode_override,r.value_mode) AS effective_mode
    INTO v_occ FROM finance_provision_occurrences o
    JOIN finance_provision_rules r ON r.id=o.rule_id AND r.workspace_id=o.workspace_id
    WHERE o.id=p_occurrence_id AND o.workspace_id=p_workspace_id;
  IF NOT FOUND OR v_occ.status<>'paid' THEN
    RAISE EXCEPTION 'Provisao sem pagamento ativo';
  END IF;
  SELECT id,value INTO v_movement_id,v_amount FROM finance_movements
    WHERE workspace_id=p_workspace_id AND provision_occurrence_id=p_occurrence_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Registro vinculado nao encontrado'; END IF;
  SELECT EXISTS(
    SELECT 1 FROM finance_provision_record_links
    WHERE workspace_id=p_workspace_id AND occurrence_id=p_occurrence_id
      AND movement_id=v_movement_id
  ) INTO v_linked;
  SELECT coalesce(d.amount,0) INTO v_wallet
    FROM finance_family_balance_debits d
    WHERE d.workspace_id=p_workspace_id AND d.movement_id=v_movement_id;
  v_wallet:=coalesce(v_wallet,0);
  SELECT EXISTS(
    SELECT 1 FROM finance_bank_transactions t
    WHERE t.workspace_id=p_workspace_id
      AND (t.movement_id=v_movement_id OR t.provision_occurrence_id=p_occurrence_id)
  ) INTO v_bank_linked;
  v_reference_needed:=v_occ.effective_mode='variable'
    AND NOT EXISTS(SELECT 1 FROM finance_provision_occurrences later
      WHERE later.workspace_id=p_workspace_id AND later.rule_id=v_occ.rule_id
        AND later.sequence_no>v_occ.sequence_no AND later.status='paid')
    AND NOT EXISTS(SELECT 1 FROM finance_provision_occurrences previous
      WHERE previous.workspace_id=p_workspace_id AND previous.rule_id=v_occ.rule_id
        AND previous.sequence_no<v_occ.sequence_no AND previous.status='paid');
  RETURN jsonb_build_object('occurrence_id',p_occurrence_id,'paid_amount',v_amount,
    'restored_wallet_amount',CASE WHEN v_linked THEN 0 ELSE v_wallet END,
    'linked_existing_record',v_linked,
    'needs_reference',v_reference_needed,'bank_linked',v_bank_linked);
END;
$preview$;
REVOKE ALL ON FUNCTION axora_beta.axora_family_reverse_payment_preview(
  uuid,bigint,bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_family_reverse_payment_preview(
  uuid,bigint,bigint) TO service_role;

COMMIT;
NOTIFY pgrst,'reload schema';
