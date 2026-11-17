-- AXORA BETA | Correção idempotente do bloqueio de contas no pagamento.
-- Diagnóstico confirmado em PostgreSQL 17/11/2026: SQLSTATE 0A000
--   FOR UPDATE is not allowed with DISTINCT clause.
-- Causa: FOR UPDATE sem tabela especificada tenta bloquear a subconsulta
-- DISTINCT das contas, além das próprias contas.
-- Corrige para FOR UPDATE OF a: bloqueia somente finance_bank_accounts
-- em ordem determinística, preservando validação, atomicidade e idempotência.
-- NÃO altera dados, saldos, outras funções ou schema public.
BEGIN;
CREATE OR REPLACE FUNCTION axora_beta.axora_family_apply_wallet_debits(
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
 WHERE a.workspace_id=p_workspace_id ORDER BY a.id FOR UPDATE OF a;

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
COMMIT;
