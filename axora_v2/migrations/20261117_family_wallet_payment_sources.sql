-- AXORA BETA | Lançamentos familiares com saída de uma ou várias contas.
-- Somente axora_beta. Sem alterações em public ou nas provisões legadas.
-- Execução transacional: rateio + lançamento + desconto + histórico são atômicos.
BEGIN;

CREATE TABLE axora_beta.finance_family_balance_debits(
 workspace_id uuid NOT NULL REFERENCES axora_beta.finance_workspaces(id) ON DELETE RESTRICT,
 request_id uuid NOT NULL,
 movement_id bigint NOT NULL,
 actor_user_id bigint NOT NULL REFERENCES axora_beta.finance_users(id) ON DELETE RESTRICT,
 amount numeric(15,2) NOT NULL CHECK(amount>0),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,request_id),
 UNIQUE(workspace_id,movement_id),
 FOREIGN KEY(movement_id,workspace_id)
  REFERENCES axora_beta.finance_movements(id,workspace_id) ON DELETE RESTRICT
);

CREATE TABLE axora_beta.finance_family_balance_debit_sources(
 workspace_id uuid NOT NULL,
 request_id uuid NOT NULL,
 movement_id bigint NOT NULL,
 payer_profile_id bigint NOT NULL,
 account_id bigint NOT NULL,
 amount numeric(15,2) NOT NULL CHECK(amount>0),
 PRIMARY KEY(workspace_id,request_id,account_id),
 FOREIGN KEY(workspace_id,request_id) REFERENCES
  axora_beta.finance_family_balance_debits(workspace_id,request_id) ON DELETE RESTRICT,
 FOREIGN KEY(movement_id,workspace_id) REFERENCES
  axora_beta.finance_movements(id,workspace_id) ON DELETE RESTRICT,
 FOREIGN KEY(workspace_id,payer_profile_id) REFERENCES
  axora_beta.finance_family_profiles(workspace_id,id) ON DELETE RESTRICT,
 FOREIGN KEY(account_id,workspace_id) REFERENCES
  axora_beta.finance_bank_accounts(id,workspace_id) ON DELETE RESTRICT
);
CREATE INDEX family_wallet_sources_by_movement ON axora_beta.finance_family_balance_debit_sources(workspace_id,movement_id);
ALTER TABLE axora_beta.finance_family_balance_debits ENABLE ROW LEVEL SECURITY;
ALTER TABLE axora_beta.finance_family_balance_debit_sources ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE axora_beta.finance_family_balance_debits,
 axora_beta.finance_family_balance_debit_sources FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON TABLE axora_beta.finance_family_balance_debits,
 axora_beta.finance_family_balance_debit_sources TO service_role;

-- Somente chamada por wrappers, sempre sob transação única.
CREATE FUNCTION axora_beta.axora_family_apply_wallet_debits(
 p_workspace_id uuid,p_actor_id bigint,p_request_id uuid,
 p_movement_id bigint,p_amount numeric,p_payments jsonb,p_sources jsonb
) RETURNS void LANGUAGE plpgsql SET search_path TO 'axora_beta','pg_temp' AS $f$
DECLARE v_row record; v_count integer; v_after numeric(15,2);
BEGIN
 IF NOT EXISTS(
   SELECT 1 FROM finance_workspaces w JOIN finance_family_profiles f
   ON f.workspace_id=w.id AND f.linked_user_id=p_actor_id AND f.active
   WHERE w.id=p_workspace_id AND w.is_active AND w.created_by=p_actor_id
     AND f.relationship='principal'
 ) THEN RAISE EXCEPTION 'Somente o principal pode alterar saldos da carteira'; END IF;

 IF p_request_id IS NULL OR p_movement_id IS NULL OR p_amount IS NULL
   OR p_amount<=0 OR p_amount<>round(p_amount,2)
   OR jsonb_typeof(p_sources) IS DISTINCT FROM 'array'
   OR jsonb_typeof(p_payments) IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'Pagamento bancário inválido'; END IF;
 v_count:=jsonb_array_length(p_sources);
 IF v_count<1 OR v_count>50 THEN RAISE EXCEPTION 'Selecione de 1 a 50 contas'; END IF;
 IF EXISTS(
   SELECT 1 FROM jsonb_to_recordset(p_sources) AS s(profile_id bigint,account_id bigint,amount numeric)
   WHERE s.profile_id IS NULL OR s.account_id IS NULL OR s.amount IS NULL
      OR s.amount<=0 OR s.amount>999999999999.99 OR s.amount<>round(s.amount,2)
 ) THEN RAISE EXCEPTION 'Fonte de pagamento inválida'; END IF;
 IF EXISTS(
   SELECT account_id FROM jsonb_to_recordset(p_sources)
     AS s(profile_id bigint,account_id bigint,amount numeric)
   GROUP BY account_id HAVING count(*)>1
 ) THEN RAISE EXCEPTION 'Conta repetida no mesmo pagamento'; END IF;
 IF (SELECT coalesce(sum(s.amount),0) FROM jsonb_to_recordset(p_sources)
    AS s(profile_id bigint,account_id bigint,amount numeric))<>p_amount
 THEN RAISE EXCEPTION 'Contas não totalizam o valor da despesa'; END IF;
 IF EXISTS(
   SELECT 1 FROM
    (SELECT profile_id,sum(amount) AS amount FROM jsonb_to_recordset(p_sources)
      AS s(profile_id bigint,account_id bigint,amount numeric) GROUP BY profile_id) s
    FULL JOIN
    (SELECT profile_id,sum(amount) AS amount FROM jsonb_to_recordset(p_payments)
      AS p(profile_id bigint,amount numeric) GROUP BY profile_id) p USING(profile_id)
   WHERE s.amount IS DISTINCT FROM p.amount
 ) THEN RAISE EXCEPTION 'Conta de origem difere do valor informado para cada pagador'; END IF;

 -- Mesma ordenação de bloqueio das transferências, evita corridas entre abas.
 PERFORM a.id FROM finance_bank_accounts a
 JOIN (SELECT DISTINCT account_id FROM jsonb_to_recordset(p_sources)
       AS s(profile_id bigint,account_id bigint,amount numeric)) s
 ON s.account_id=a.id
 WHERE a.workspace_id=p_workspace_id ORDER BY a.id FOR UPDATE;

 SELECT count(*) INTO v_count
 FROM jsonb_to_recordset(p_sources) AS s(profile_id bigint,account_id bigint,amount numeric)
 JOIN finance_bank_accounts a ON a.id=s.account_id AND a.workspace_id=p_workspace_id
 JOIN finance_bank_holders h ON h.id=a.holder_id AND h.workspace_id=a.workspace_id
 WHERE h.family_profile_id=s.profile_id
   AND a.connection_status='manual' AND a.pluggy_account_id IS NULL
   AND a.pluggy_item_id IS NULL
   AND a.manual_balance IS NOT NULL AND a.manual_balance>=s.amount;
 IF v_count<>jsonb_array_length(p_sources)
 THEN RAISE EXCEPTION 'Conta indisponível, titular incorreto ou saldo insuficiente'; END IF;

 INSERT INTO finance_family_balance_debits(workspace_id,request_id,movement_id,actor_user_id,amount)
 VALUES(p_workspace_id,p_request_id,p_movement_id,p_actor_id,p_amount);

 FOR v_row IN
   SELECT * FROM jsonb_to_recordset(p_sources)
    AS s(profile_id bigint,account_id bigint,amount numeric) ORDER BY account_id
 LOOP
   UPDATE finance_bank_accounts SET manual_balance=manual_balance-v_row.amount
   WHERE id=v_row.account_id AND workspace_id=p_workspace_id
     AND manual_balance>=v_row.amount
   RETURNING manual_balance INTO v_after;
   IF NOT FOUND THEN RAISE EXCEPTION 'Saldo modificado durante quitação'; END IF;
   INSERT INTO finance_family_balance_debit_sources(
     workspace_id,request_id,movement_id,payer_profile_id,account_id,amount
   ) VALUES(p_workspace_id,p_request_id,p_movement_id,v_row.profile_id,v_row.account_id,v_row.amount);
 END LOOP;
END;
$f$;

CREATE FUNCTION axora_beta.axora_family_record_from_wallet(
 p_workspace_id uuid,p_actor_id bigint,p_movement_date date,p_description text,
 p_value numeric,p_classification text,p_category text,p_label text,p_costs jsonb,
 p_payments jsonb,p_request_id uuid,p_sources jsonb
) RETURNS jsonb LANGUAGE plpgsql SET search_path TO 'axora_beta','pg_temp' AS $f$
DECLARE v_prior bigint; v_result jsonb;
BEGIN
 IF p_request_id IS NULL OR p_classification IS DISTINCT FROM 'SAÍDA' THEN
  RAISE EXCEPTION 'Somente despesas com identificação podem usar saldo'; END IF;
 PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
 IF NOT EXISTS(SELECT 1 FROM finance_workspaces w JOIN finance_family_profiles f
   ON f.workspace_id=w.id AND f.linked_user_id=p_actor_id AND f.active
   WHERE w.id=p_workspace_id AND w.is_active AND w.created_by=p_actor_id
     AND f.relationship='principal')
 THEN RAISE EXCEPTION 'Somente o principal pode usar o saldo bancário'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_workspace_id::text||p_request_id::text,0));
 SELECT movement_id INTO v_prior FROM finance_family_balance_debits
 WHERE workspace_id=p_workspace_id AND request_id=p_request_id;
 IF FOUND THEN RETURN jsonb_build_object('ok',true,'already_applied',true,'movement_id',v_prior); END IF;
 v_result:=axora_beta.axora_family_record(p_workspace_id,p_actor_id,
   p_movement_date,p_description,p_value,p_classification,p_category,p_label,p_costs,p_payments);
 PERFORM axora_beta.axora_family_apply_wallet_debits(p_workspace_id,p_actor_id,
   p_request_id,(v_result->>'movement_id')::bigint,p_value,p_payments,p_sources);
 RETURN v_result||jsonb_build_object('already_applied',false,'balance_debited',true);
END;
$f$;

CREATE FUNCTION axora_beta.axora_family_pay_provision_from_wallet(
 p_workspace_id uuid,p_actor_id bigint,p_occurrence_id bigint,p_payment_date date,
 p_amount numeric,p_label text,p_costs jsonb,p_payments jsonb,p_request_id uuid,p_sources jsonb
) RETURNS jsonb LANGUAGE plpgsql SET search_path TO 'axora_beta','pg_temp' AS $f$
DECLARE v_prior bigint; v_result jsonb;
BEGIN
 IF p_request_id IS NULL THEN RAISE EXCEPTION 'Identificação do pagamento obrigatória'; END IF;
 PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
 IF NOT EXISTS(SELECT 1 FROM finance_workspaces w JOIN finance_family_profiles f
   ON f.workspace_id=w.id AND f.linked_user_id=p_actor_id AND f.active
   WHERE w.id=p_workspace_id AND w.is_active AND w.created_by=p_actor_id
     AND f.relationship='principal')
 THEN RAISE EXCEPTION 'Somente o principal pode usar o saldo bancário'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_workspace_id::text||p_request_id::text,0));
 SELECT movement_id INTO v_prior FROM finance_family_balance_debits
 WHERE workspace_id=p_workspace_id AND request_id=p_request_id;
 IF FOUND THEN RETURN jsonb_build_object('ok',true,'already_applied',true,'movement_id',v_prior); END IF;
 v_result:=axora_beta.axora_family_pay_provision(p_workspace_id,p_actor_id,p_occurrence_id,
   p_payment_date,p_amount,p_label,p_costs,p_payments);
 PERFORM axora_beta.axora_family_apply_wallet_debits(p_workspace_id,p_actor_id,
   p_request_id,(v_result->>'movement_id')::bigint,p_amount,p_payments,p_sources);
 RETURN v_result||jsonb_build_object('already_applied',false,'balance_debited',true);
END;
$f$;

REVOKE ALL ON FUNCTION axora_beta.axora_family_apply_wallet_debits(
 uuid,bigint,uuid,bigint,numeric,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION axora_beta.axora_family_record_from_wallet(
 uuid,bigint,date,text,numeric,text,text,text,jsonb,jsonb,uuid,jsonb) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION axora_beta.axora_family_pay_provision_from_wallet(
 uuid,bigint,bigint,date,numeric,text,jsonb,jsonb,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_family_apply_wallet_debits(
 uuid,bigint,uuid,bigint,numeric,jsonb,jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION axora_beta.axora_family_record_from_wallet(
 uuid,bigint,date,text,numeric,text,text,text,jsonb,jsonb,uuid,jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION axora_beta.axora_family_pay_provision_from_wallet(
 uuid,bigint,bigint,date,numeric,text,jsonb,jsonb,uuid,jsonb) TO service_role;
COMMIT;
