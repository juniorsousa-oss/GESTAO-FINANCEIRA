-- AXORA BETA | Crédito opcional em contas manuais para entradas familiares
-- Não altera contas automáticas, investimentos, lançamentos existentes ou produção.
-- Cadastro + distribuição + atualização das contas são atomicamente transacionais.
BEGIN;

CREATE TABLE IF NOT EXISTS axora_beta.finance_family_balance_credits(
  workspace_id uuid NOT NULL REFERENCES axora_beta.finance_workspaces(id) ON DELETE RESTRICT,
  request_id uuid NOT NULL,
  movement_id bigint NOT NULL,
  actor_user_id bigint NOT NULL REFERENCES axora_beta.finance_users(id) ON DELETE RESTRICT,
  recipient_profile_id bigint NOT NULL,
  amount numeric(15,2) NOT NULL CHECK(amount>0),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(workspace_id,request_id),
  UNIQUE(workspace_id,movement_id),
  FOREIGN KEY(movement_id,workspace_id)
    REFERENCES axora_beta.finance_movements(id,workspace_id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,recipient_profile_id)
    REFERENCES axora_beta.finance_family_profiles(workspace_id,id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS axora_beta.finance_family_balance_credit_sources(
  workspace_id uuid NOT NULL,
  request_id uuid NOT NULL,
  movement_id bigint NOT NULL,
  recipient_profile_id bigint NOT NULL,
  account_id bigint NOT NULL,
  amount numeric(15,2) NOT NULL CHECK(amount>0),
  PRIMARY KEY(workspace_id,request_id,account_id),
  FOREIGN KEY(workspace_id,request_id)
    REFERENCES axora_beta.finance_family_balance_credits(workspace_id,request_id) ON DELETE RESTRICT,
  FOREIGN KEY(movement_id,workspace_id)
    REFERENCES axora_beta.finance_movements(id,workspace_id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,recipient_profile_id)
    REFERENCES axora_beta.finance_family_profiles(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(account_id,workspace_id)
    REFERENCES axora_beta.finance_bank_accounts(id,workspace_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS family_wallet_credits_by_movement
  ON axora_beta.finance_family_balance_credit_sources(workspace_id,movement_id);
ALTER TABLE axora_beta.finance_family_balance_credits ENABLE ROW LEVEL SECURITY;
ALTER TABLE axora_beta.finance_family_balance_credit_sources ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE axora_beta.finance_family_balance_credits,
  axora_beta.finance_family_balance_credit_sources FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON TABLE axora_beta.finance_family_balance_credits,
  axora_beta.finance_family_balance_credit_sources TO service_role;

CREATE OR REPLACE FUNCTION axora_beta.axora_family_record_income_to_wallet(
  p_workspace_id uuid,p_actor_id bigint,p_movement_date date,p_description text,
  p_value numeric,p_classification text,p_category text,p_label text,p_costs jsonb,
  p_payments jsonb,p_request_id uuid,p_sources jsonb
) RETURNS jsonb LANGUAGE plpgsql SET search_path TO 'axora_beta','pg_temp' AS $f$
DECLARE
  v_prior bigint;
  v_result jsonb;
  v_movement bigint;
  v_profile bigint;
  v_count integer;
  v_amount numeric;
  v_row record;
  v_after numeric;
BEGIN
  -- Primeiro verifica o papel/identidade. Somente o titular principal
  -- pode registrar entrada que afete saldo manual do workspace.
  PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
  IF NOT EXISTS(
    SELECT 1 FROM finance_workspaces w
      JOIN finance_family_profiles f
        ON f.workspace_id=w.id AND f.linked_user_id=p_actor_id AND f.active
    WHERE w.id=p_workspace_id AND w.is_active AND w.created_by=p_actor_id
      AND f.relationship='principal'
  ) THEN RAISE EXCEPTION 'Somente o titular principal pode atualizar saldos'; END IF;
  IF p_request_id IS NULL OR p_classification IS DISTINCT FROM 'ENTRADA'
     OR p_value IS NULL OR p_value<=0 OR p_value>999999999999.99
     OR p_value<>round(p_value,2)
     OR jsonb_typeof(p_costs) IS DISTINCT FROM 'array'
     OR jsonb_array_length(p_costs)<>1
     OR jsonb_typeof(p_payments) IS DISTINCT FROM 'array'
     OR jsonb_array_length(p_payments)<>0
     OR jsonb_typeof(p_sources) IS DISTINCT FROM 'array'
  THEN RAISE EXCEPTION 'Entrada com crédito inválida'; END IF;
  SELECT c.profile_id,c.amount INTO v_profile,v_amount
    FROM jsonb_to_recordset(p_costs) AS c(profile_id bigint,amount numeric);
  IF v_profile IS NULL OR v_amount IS DISTINCT FROM p_value OR NOT EXISTS(
    SELECT 1 FROM finance_family_profiles f
     WHERE f.id=v_profile AND f.workspace_id=p_workspace_id AND f.active
  ) THEN RAISE EXCEPTION 'Recebedor ou valor de crédito inválido'; END IF;
  v_count:=jsonb_array_length(p_sources);
  IF v_count<1 OR v_count>50 THEN RAISE EXCEPTION 'Selecione de 1 a 50 contas'; END IF;
  IF EXISTS(
    SELECT 1 FROM jsonb_to_recordset(p_sources)
      AS s(profile_id bigint,account_id bigint,amount numeric)
    WHERE s.profile_id IS DISTINCT FROM v_profile
      OR s.account_id IS NULL OR s.amount IS NULL OR s.amount<=0
      OR s.amount>999999999999.99 OR s.amount<>round(s.amount,2)
  ) THEN RAISE EXCEPTION 'Conta, recebedor ou valor de crédito inválido'; END IF;
  IF EXISTS(
    SELECT s.account_id FROM jsonb_to_recordset(p_sources)
      AS s(profile_id bigint,account_id bigint,amount numeric)
    GROUP BY s.account_id HAVING count(*)>1
  ) THEN RAISE EXCEPTION 'Conta repetida no crédito'; END IF;
  IF (SELECT coalesce(sum(s.amount),0) FROM jsonb_to_recordset(p_sources)
      AS s(profile_id bigint,account_id bigint,amount numeric))<>p_value
  THEN RAISE EXCEPTION 'Total das contas não corresponde à entrada'; END IF;

  -- Token idempotente: evita lançamento/crédito duplicado em reenvios do app.
  PERFORM pg_advisory_xact_lock(hashtextextended(p_workspace_id::text||p_request_id::text,0));
  SELECT movement_id INTO v_prior
    FROM finance_family_balance_credits
    WHERE workspace_id=p_workspace_id AND request_id=p_request_id;
  IF FOUND THEN RETURN jsonb_build_object(
    'ok',true,'already_applied',true,'movement_id',v_prior,'balance_credited',true);
  END IF;

  -- Mesma ordem crescente de locks das transferências e pagamentos.
  PERFORM a.id FROM finance_bank_accounts a
    JOIN (SELECT DISTINCT s.account_id FROM jsonb_to_recordset(p_sources)
      AS s(profile_id bigint,account_id bigint,amount numeric)) src
      ON src.account_id=a.id
    WHERE a.workspace_id=p_workspace_id
    ORDER BY a.id FOR UPDATE OF a;
  SELECT count(*) INTO v_count
    FROM jsonb_to_recordset(p_sources) AS s(profile_id bigint,account_id bigint,amount numeric)
    JOIN finance_bank_accounts a ON a.id=s.account_id AND a.workspace_id=p_workspace_id
    JOIN finance_bank_holders h ON h.id=a.holder_id AND h.workspace_id=a.workspace_id
    WHERE h.family_profile_id=v_profile
      AND a.connection_status='manual'
      AND a.pluggy_account_id IS NULL AND a.pluggy_item_id IS NULL
      AND a.manual_balance IS NOT NULL
      AND a.manual_balance+s.amount<=999999999999.99;
  IF v_count<>jsonb_array_length(p_sources)
  THEN RAISE EXCEPTION 'Conta inexistente, não manual, titular divergente ou limite de saldo excedido'; END IF;

  v_result:=axora_beta.axora_family_record(p_workspace_id,p_actor_id,
    p_movement_date,p_description,p_value,p_classification,p_category,
    p_label,p_costs,p_payments);
  v_movement:=(v_result->>'movement_id')::bigint;
  INSERT INTO finance_family_balance_credits(
    workspace_id,request_id,movement_id,actor_user_id,recipient_profile_id,amount
  ) VALUES(p_workspace_id,p_request_id,v_movement,p_actor_id,v_profile,p_value);
  FOR v_row IN
    SELECT s.profile_id,s.account_id,s.amount
      FROM jsonb_to_recordset(p_sources)
      AS s(profile_id bigint,account_id bigint,amount numeric)
      ORDER BY s.account_id
  LOOP
    UPDATE finance_bank_accounts
      SET manual_balance=manual_balance+v_row.amount
      WHERE id=v_row.account_id AND workspace_id=p_workspace_id
        AND connection_status='manual'
        AND pluggy_item_id IS NULL AND pluggy_account_id IS NULL
        AND manual_balance IS NOT NULL
      RETURNING manual_balance INTO v_after;
    IF NOT FOUND THEN RAISE EXCEPTION 'Conta alterada durante o crédito'; END IF;
    INSERT INTO finance_family_balance_credit_sources(
      workspace_id,request_id,movement_id,recipient_profile_id,account_id,amount
    ) VALUES(p_workspace_id,p_request_id,v_movement,v_profile,v_row.account_id,v_row.amount);
  END LOOP;
  RETURN v_result||jsonb_build_object(
    'already_applied',false,'balance_credited',true,'recipient_profile_id',v_profile);
END;
$f$;

REVOKE ALL ON FUNCTION axora_beta.axora_family_record_income_to_wallet(
  uuid,bigint,date,text,numeric,text,text,text,jsonb,jsonb,uuid,jsonb)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_family_record_income_to_wallet(
  uuid,bigint,date,text,numeric,text,text,text,jsonb,jsonb,uuid,jsonb)
  TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
