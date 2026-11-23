-- AXORA BETA: exclusao atomica e auditada de registro manual, mesmo com rateio
-- ou historico de credito/debito de saldo. Nenhum objeto em public/producao.
BEGIN;
CREATE TABLE IF NOT EXISTS axora_beta.finance_manual_movement_deletions(
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES axora_beta.finance_workspaces(id) ON DELETE RESTRICT,
  movement_id bigint NOT NULL,
  actor_user_id bigint NOT NULL REFERENCES axora_beta.finance_users(id) ON DELETE RESTRICT,
  movement_snapshot jsonb NOT NULL,
  costs_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
  payments_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
  visibility_snapshot jsonb,
  credit_sources_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
  debit_sources_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
  credited_reversed numeric(14,2) NOT NULL DEFAULT 0,
  debited_restored numeric(14,2) NOT NULL DEFAULT 0,
  wallet_delta numeric(14,2) NOT NULL DEFAULT 0,
  deleted_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id,movement_id)
);
CREATE INDEX IF NOT EXISTS finance_manual_movement_deletions_workspace
  ON axora_beta.finance_manual_movement_deletions(workspace_id,deleted_at DESC);
ALTER TABLE axora_beta.finance_manual_movement_deletions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE axora_beta.finance_manual_movement_deletions
  FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON TABLE axora_beta.finance_manual_movement_deletions TO service_role;
GRANT USAGE,SELECT ON SEQUENCE axora_beta.finance_manual_movement_deletions_id_seq TO service_role;

CREATE OR REPLACE FUNCTION axora_beta.axora_manual_delete_validate(
  p_workspace_id uuid,p_actor_id bigint,p_movement_id bigint
) RETURNS void LANGUAGE plpgsql SECURITY INVOKER
SET search_path TO 'axora_beta','pg_temp' AS $validate$
BEGIN
  IF p_workspace_id IS NULL OR p_actor_id IS NULL OR p_movement_id IS NULL
     OR p_movement_id<1 THEN RAISE EXCEPTION 'Dados do registro invalidos'; END IF;
  PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
  IF NOT EXISTS(
    SELECT 1 FROM finance_workspaces w
      JOIN finance_family_profiles f
        ON f.workspace_id=w.id AND f.linked_user_id=p_actor_id
        AND f.active AND f.relationship='principal'
      JOIN finance_users u ON u.id=p_actor_id AND u.is_active
    WHERE w.id=p_workspace_id AND w.created_by=p_actor_id AND w.is_active
  ) THEN
    RAISE EXCEPTION 'Somente o titular principal pode excluir este registro';
  END IF;
END;
$validate$;
REVOKE ALL ON FUNCTION axora_beta.axora_manual_delete_validate(uuid,bigint,bigint)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_manual_delete_validate(uuid,bigint,bigint)
  TO service_role;

CREATE OR REPLACE FUNCTION axora_beta.axora_manual_delete_preview(
  p_workspace_id uuid,p_actor_id bigint,p_movement_id bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path TO 'axora_beta','pg_temp' AS $preview$
DECLARE
  v_m finance_movements%ROWTYPE;
  v_credit numeric:=0;
  v_debit numeric:=0;
  v_credit_sources numeric:=0;
  v_debit_sources numeric:=0;
  v_credit_count integer:=0;
  v_debit_count integer:=0;
BEGIN
  PERFORM axora_beta.axora_manual_delete_validate(
    p_workspace_id,p_actor_id,p_movement_id);
  SELECT * INTO v_m FROM finance_movements
    WHERE id=p_movement_id AND workspace_id=p_workspace_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Registro manual nao encontrado'; END IF;
  IF v_m.provision_occurrence_id IS NOT NULL OR EXISTS(
    SELECT 1 FROM finance_provision_record_links l
    WHERE l.workspace_id=p_workspace_id AND l.movement_id=p_movement_id
  ) THEN RAISE EXCEPTION 'Registro vinculado a provisao: utilize Desfazer pagamento'; END IF;
  IF EXISTS(
    SELECT 1 FROM finance_bank_transactions b
    WHERE b.workspace_id=p_workspace_id AND b.movement_id=p_movement_id
  ) THEN RAISE EXCEPTION 'Desfaca primeiro a conciliacao bancaria do registro'; END IF;

  SELECT coalesce(sum(c.amount),0) INTO v_credit
    FROM finance_family_balance_credits c
    WHERE c.workspace_id=p_workspace_id AND c.movement_id=p_movement_id;
  SELECT coalesce(sum(d.amount),0) INTO v_debit
    FROM finance_family_balance_debits d
    WHERE d.workspace_id=p_workspace_id AND d.movement_id=p_movement_id;
  SELECT count(*),coalesce(sum(s.amount),0)
    INTO v_credit_count,v_credit_sources
    FROM finance_family_balance_credit_sources s
    WHERE s.workspace_id=p_workspace_id AND s.movement_id=p_movement_id;
  SELECT count(*),coalesce(sum(s.amount),0)
    INTO v_debit_count,v_debit_sources
    FROM finance_family_balance_debit_sources s
    WHERE s.workspace_id=p_workspace_id AND s.movement_id=p_movement_id;
  IF (v_credit<>0 AND (v_debit<>0 OR v_m.classification<>'ENTRADA'))
     OR (v_debit<>0 AND v_m.classification<>'SAÍDA')
     OR (v_credit=0 AND v_credit_count<>0)
     OR (v_debit=0 AND v_debit_count<>0)
     OR (v_credit>0 AND (v_credit_count=0 OR v_credit<>v_credit_sources))
     OR (v_debit>0 AND (v_debit_count=0 OR v_debit<>v_debit_sources))
  THEN RAISE EXCEPTION 'Registro e carteira divergentes: revisao necessaria antes da exclusao'; END IF;
  RETURN jsonb_build_object(
    'id',v_m.id,'description',v_m.description,'amount',v_m.value,
    'classification',v_m.classification,
    'wallet_delta',v_debit-v_credit,
    'credited_reversed',v_credit,'debited_restored',v_debit,
    'has_wallet_effect',(v_debit>0 OR v_credit>0)
  );
END;
$preview$;
REVOKE ALL ON FUNCTION axora_beta.axora_manual_delete_preview(uuid,bigint,bigint)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_manual_delete_preview(uuid,bigint,bigint)
  TO service_role;

CREATE OR REPLACE FUNCTION axora_beta.axora_manual_delete_movement(
  p_workspace_id uuid,p_actor_id bigint,p_movement_id bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path TO 'axora_beta','pg_temp' AS $delete$
DECLARE
  v_m finance_movements%ROWTYPE;
  v_preview jsonb;
  v_credit numeric(14,2);
  v_debit numeric(14,2);
  v_delta numeric(14,2);
  v_s record;
  v_count integer;
  v_costs jsonb;
  v_payments jsonb;
  v_credit_sources jsonb;
  v_debit_sources jsonb;
  v_visibility jsonb;
BEGIN
  PERFORM axora_beta.axora_manual_delete_validate(
    p_workspace_id,p_actor_id,p_movement_id);
  PERFORM pg_advisory_xact_lock(hashtextextended(
    'axora-delete-manual:'||p_workspace_id::text||':'||p_movement_id::text,0));
  SELECT * INTO v_m FROM finance_movements
    WHERE id=p_movement_id AND workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Registro manual nao encontrado ou ja excluido'; END IF;
  -- O preview faz as mesmas verificacoes de reconciliacao, provisao e fonte.
  v_preview:=axora_beta.axora_manual_delete_preview(
    p_workspace_id,p_actor_id,p_movement_id);
  v_credit:=(v_preview->>'credited_reversed')::numeric;
  v_debit:=(v_preview->>'debited_restored')::numeric;
  v_delta:=v_debit-v_credit;

  -- Bloqueia todas as contas afetadas em ordem deterministica, como as
  -- operacoes atuais do wallet. O saldo historico pode legitimamente
  -- ficar negativo quando a entrada original ja foi gasta.
  PERFORM a.id FROM finance_bank_accounts a
    WHERE a.workspace_id=p_workspace_id AND a.id IN(
      SELECT account_id FROM finance_family_balance_credit_sources s
      WHERE s.workspace_id=p_workspace_id AND s.movement_id=p_movement_id
      UNION
      SELECT account_id FROM finance_family_balance_debit_sources s
      WHERE s.workspace_id=p_workspace_id AND s.movement_id=p_movement_id
    ) ORDER BY a.id FOR UPDATE OF a;

  SELECT count(*) INTO v_count FROM (
    SELECT s.account_id, sum(s.amount) AS amount,
      CASE WHEN v_credit>0 THEN -1 ELSE 1 END AS direction
      FROM finance_family_balance_credit_sources s
      WHERE s.workspace_id=p_workspace_id AND s.movement_id=p_movement_id
      GROUP BY s.account_id
    UNION ALL
    SELECT s.account_id,sum(s.amount) AS amount,1 AS direction
      FROM finance_family_balance_debit_sources s
      WHERE s.workspace_id=p_workspace_id AND s.movement_id=p_movement_id
      GROUP BY s.account_id
  ) x JOIN finance_bank_accounts a
    ON a.workspace_id=p_workspace_id AND a.id=x.account_id
  WHERE a.connection_status='manual' AND a.pluggy_account_id IS NULL
    AND a.pluggy_item_id IS NULL AND a.manual_balance IS NOT NULL
    AND a.manual_balance+x.direction*x.amount BETWEEN
      -999999999999.99 AND 999999999999.99;
  IF v_count<>(SELECT count(*) FROM (
      SELECT account_id FROM finance_family_balance_credit_sources
      WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id
      UNION SELECT account_id FROM finance_family_balance_debit_sources
      WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id
    ) AS account_ids)
  THEN RAISE EXCEPTION 'Conta de origem alterada: exclua somente apos revisar os saldos'; END IF;

  SELECT coalesce(jsonb_agg(to_jsonb(c)),'[]'::jsonb) INTO v_costs
    FROM finance_family_cost_allocations c
    WHERE c.workspace_id=p_workspace_id AND c.movement_id=p_movement_id;
  SELECT coalesce(jsonb_agg(to_jsonb(p)),'[]'::jsonb) INTO v_payments
    FROM finance_family_payment_allocations p
    WHERE p.workspace_id=p_workspace_id AND p.movement_id=p_movement_id;
  SELECT coalesce(jsonb_agg(to_jsonb(s)),'[]'::jsonb) INTO v_credit_sources
    FROM finance_family_balance_credit_sources s
    WHERE s.workspace_id=p_workspace_id AND s.movement_id=p_movement_id;
  SELECT coalesce(jsonb_agg(to_jsonb(s)),'[]'::jsonb) INTO v_debit_sources
    FROM finance_family_balance_debit_sources s
    WHERE s.workspace_id=p_workspace_id AND s.movement_id=p_movement_id;
  SELECT to_jsonb(v) INTO v_visibility FROM finance_family_visibility v
    WHERE v.workspace_id=p_workspace_id AND v.resource_type='registro'
      AND v.resource_id=p_movement_id;

  -- Reverte somente o efeito bancario EFETIVAMENTE registrado, que pode
  -- ser diferente do valor mostrado se o usuario editou o historico.
  FOR v_s IN SELECT account_id,sum(amount) AS amount
    FROM finance_family_balance_credit_sources
    WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id
    GROUP BY account_id ORDER BY account_id
  LOOP
    UPDATE finance_bank_accounts SET manual_balance=manual_balance-v_s.amount
      WHERE workspace_id=p_workspace_id AND id=v_s.account_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Conta de credito alterada durante exclusao'; END IF;
  END LOOP;
  FOR v_s IN SELECT account_id,sum(amount) AS amount
    FROM finance_family_balance_debit_sources
    WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id
    GROUP BY account_id ORDER BY account_id
  LOOP
    UPDATE finance_bank_accounts SET manual_balance=manual_balance+v_s.amount
      WHERE workspace_id=p_workspace_id AND id=v_s.account_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Conta de debito alterada durante exclusao'; END IF;
  END LOOP;

  INSERT INTO finance_manual_movement_deletions(
    workspace_id,movement_id,actor_user_id,movement_snapshot,costs_snapshot,
    payments_snapshot,visibility_snapshot,credit_sources_snapshot,
    debit_sources_snapshot,credited_reversed,debited_restored,wallet_delta
  ) VALUES(
    p_workspace_id,p_movement_id,p_actor_id,to_jsonb(v_m),v_costs,v_payments,
    v_visibility,v_credit_sources,v_debit_sources,v_credit,v_debit,v_delta
  );

  -- A ordem respeita todas as FKs RESTRICT. Visibilidade permanece como
  -- tombstone por seu proprio historico de auditoria (FK RESTRICT).
  DELETE FROM finance_family_balance_credit_sources
    WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id;
  DELETE FROM finance_family_balance_credits
    WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id;
  DELETE FROM finance_family_balance_debit_sources
    WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id;
  DELETE FROM finance_family_balance_debits
    WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id;
  DELETE FROM finance_family_cost_allocations
    WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id;
  DELETE FROM finance_family_payment_allocations
    WHERE workspace_id=p_workspace_id AND movement_id=p_movement_id;
  DELETE FROM finance_movements
    WHERE workspace_id=p_workspace_id AND id=p_movement_id
      AND provision_occurrence_id IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'Registro mudou durante exclusao'; END IF;

  RETURN jsonb_build_object('ok',true,'deleted_id',p_movement_id,
    'wallet_delta',v_delta,'credited_reversed',v_credit,
    'debited_restored',v_debit);
END;
$delete$;
REVOKE ALL ON FUNCTION axora_beta.axora_manual_delete_movement(uuid,bigint,bigint)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_manual_delete_movement(uuid,bigint,bigint)
  TO service_role;
COMMIT;
NOTIFY pgrst,'reload schema';
