-- Executar SOMENTE no projeto Supabase AXORA BETA. Todos os cadastros
-- ficticios e alteracoes sao revertidos ao final pela transacao externa.
BEGIN;
DO $smoke$
<<smoke_block>>
DECLARE
  uid bigint; wid uuid; fid bigint; holder bigint; a1 bigint; a2 bigint;
  rule_id bigint; occurrence_id bigint; movement_id bigint;
  request_id uuid:=gen_random_uuid(); out_json jsonb; c integer; v numeric;
BEGIN
  INSERT INTO axora_beta.finance_users(display_name,password_hash,is_admin,is_active)
  VALUES('AXORA REVERSAO TESTE DESCARTAVEL','sem-login-teste',false,true)
  RETURNING id INTO uid;
  INSERT INTO axora_beta.finance_workspaces(name,created_by)
  VALUES('AXORA workspace descarte de teste',uid)
  RETURNING id INTO wid;
  INSERT INTO axora_beta.finance_workspace_members(workspace_id,user_id,role)
  VALUES(wid,uid,'owner');
  INSERT INTO axora_beta.finance_family_profiles(
    workspace_id,display_name,relationship,linked_user_id)
  VALUES(wid,'Pessoa de teste','principal',uid)
  RETURNING id INTO fid;
  INSERT INTO axora_beta.finance_bank_account_types(workspace_id,code,label)
  VALUES(wid,'corrente','Conta corrente');
  INSERT INTO axora_beta.finance_bank_holders(
    workspace_id,name,relationship,linked_user_id,family_profile_id)
  VALUES(wid,'Titular de teste','proprio',uid,fid)
  RETURNING id INTO holder;
  INSERT INTO axora_beta.finance_bank_accounts(
    workspace_id,holder_id,bank_name,nickname,manual_balance)
  VALUES(wid,holder,'Banco ficticio','Conta ficticia A',60)
  RETURNING id INTO a1;
  INSERT INTO axora_beta.finance_bank_accounts(
    workspace_id,holder_id,bank_name,nickname,manual_balance)
  VALUES(wid,holder,'Banco ficticio','Conta ficticia B',120)
  RETURNING id INTO a2;

  -- 1. Quitacao criada pelo app, com debito real em duas contas manuais.
  INSERT INTO axora_beta.finance_provision_rules(
    workspace_id,description,category,responsible,start_due_date,
    planned_value,value_mode,recurrence,frequency)
  VALUES(wid,'Exemplo pago','Outros','Pessoa de teste',current_date,
    91.05,'fixed','once','monthly')
  RETURNING id INTO rule_id;
  INSERT INTO axora_beta.finance_provision_occurrences(
    rule_id,workspace_id,sequence_no,due_date,planned_value,
    status,payment_date,paid_value)
  VALUES(rule_id,wid,1,current_date,91.05,'paid',current_date,91.05)
  RETURNING id INTO occurrence_id;
  INSERT INTO axora_beta.finance_movements(
    workspace_id,provision_occurrence_id,movement_date,description,value,
    category,competence,classification,allocation_value,fixed_variable)
  VALUES(wid,occurrence_id,current_date,'Pagamento ficticio',91.05,
    'Outros',to_char(current_date,'MM/YYYY'),'SAÍDA',0,'FIXO')
  RETURNING id INTO movement_id;
  INSERT INTO axora_beta.finance_family_balance_debits(
    workspace_id,request_id,movement_id,actor_user_id,amount)
  VALUES(wid,request_id,movement_id,uid,91.05);
  INSERT INTO axora_beta.finance_family_balance_debit_sources(
    workspace_id,request_id,movement_id,payer_profile_id,account_id,amount)
  VALUES(wid,request_id,movement_id,fid,a1,40),
        (wid,request_id,movement_id,fid,a2,51.05);

  out_json:=axora_beta.axora_family_reverse_provision_payment(
    wid,uid,occurrence_id,NULL);
  IF (out_json->>'restored_wallet_amount')::numeric <> 91.05
       OR (out_json->>'removed_movement')::boolean IS DISTINCT FROM true
    THEN RAISE EXCEPTION 'Estorno multiplo incorreto: %',out_json; END IF;
  SELECT manual_balance INTO v FROM axora_beta.finance_bank_accounts WHERE id=a1;
  IF v<>100 THEN RAISE EXCEPTION 'Conta A apos estorno deveria ser 100: %',v; END IF;
  SELECT manual_balance INTO v FROM axora_beta.finance_bank_accounts WHERE id=a2;
  IF v<>171.05 THEN RAISE EXCEPTION 'Conta B apos estorno deveria ser 171,05: %',v; END IF;
  SELECT count(*) INTO c FROM axora_beta.finance_movements WHERE id=movement_id;
  IF c<>0 THEN RAISE EXCEPTION 'Pagamento original continua ativo'; END IF;
  SELECT count(*) INTO c FROM axora_beta.finance_provision_payment_reversals rv
    WHERE rv.workspace_id=wid AND rv.movement_id=smoke_block.movement_id
      AND restored_wallet_amount=91.05;
  IF c<>1 THEN RAISE EXCEPTION 'Historico da reversao nao gravado'; END IF;
  BEGIN
    PERFORM axora_beta.axora_family_reverse_provision_payment(
      wid,uid,occurrence_id,NULL);
    RAISE EXCEPTION 'DUPLO_ESTORNO_ACEITO';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM='DUPLO_ESTORNO_ACEITO' THEN RAISE; END IF;
  END;

  -- 2. Vinculo a registro existente: registro permanece e banco nao muda.
  INSERT INTO axora_beta.finance_provision_rules(
    workspace_id,description,category,responsible,start_due_date,
    planned_value,value_mode,recurrence,frequency)
  VALUES(wid,'Exemplo vinculado','Outros','Pessoa de teste',current_date,
    50,'fixed','once','monthly')
  RETURNING id INTO rule_id;
  INSERT INTO axora_beta.finance_provision_occurrences(
    rule_id,workspace_id,sequence_no,due_date,planned_value,
    status,payment_date,paid_value)
  VALUES(rule_id,wid,1,current_date,50,'paid',current_date,50)
  RETURNING id INTO occurrence_id;
  INSERT INTO axora_beta.finance_movements(
    workspace_id,provision_occurrence_id,movement_date,description,value,
    category,competence,classification,allocation_value,fixed_variable)
  VALUES(wid,occurrence_id,current_date,'Registro preexistente',50,
    'Outros',to_char(current_date,'MM/YYYY'),'SAÍDA',0,'FIXO')
  RETURNING id INTO movement_id;
  INSERT INTO axora_beta.finance_provision_record_links(
    workspace_id,occurrence_id,movement_id,actor_id)
  VALUES(wid,occurrence_id,movement_id,uid);
  out_json:=axora_beta.axora_family_reverse_provision_payment(
    wid,uid,occurrence_id,NULL);
  IF (out_json->>'linked_existing_record')::boolean IS DISTINCT FROM true
       OR (out_json->>'removed_movement')::boolean IS DISTINCT FROM false
    THEN RAISE EXCEPTION 'Registro existente nao preservado'; END IF;
  SELECT count(*) INTO c FROM axora_beta.finance_movements
    WHERE id=movement_id AND provision_occurrence_id IS NULL;
  IF c<>1 THEN RAISE EXCEPTION 'Vinculo nao removido corretamente'; END IF;

  -- 3. Valor variavel inicial precisa restaurar referencia nos proximos meses.
  INSERT INTO axora_beta.finance_provision_rules(
    workspace_id,description,category,responsible,start_due_date,
    planned_value,value_mode,recurrence,frequency,last_paid_value,last_paid_at)
  VALUES(wid,'Exemplo variavel','Outros','Pessoa de teste',current_date,
    91.05,'variable','unlimited','monthly',91.05,current_date)
  RETURNING id INTO rule_id;
  INSERT INTO axora_beta.finance_provision_occurrences(
    rule_id,workspace_id,sequence_no,due_date,planned_value,
    status,payment_date,paid_value)
  VALUES(rule_id,wid,1,current_date,91.05,'paid',current_date,91.05)
  RETURNING id INTO occurrence_id;
  INSERT INTO axora_beta.finance_provision_occurrences(
    rule_id,workspace_id,sequence_no,due_date,planned_value,status)
  VALUES(rule_id,wid,2,current_date+interval '30 days',91.05,'open');
  INSERT INTO axora_beta.finance_movements(
    workspace_id,provision_occurrence_id,movement_date,description,value,
    category,competence,classification,allocation_value,fixed_variable)
  VALUES(wid,occurrence_id,current_date,'Quitacao variavel teste',91.05,
    'Outros',to_char(current_date,'MM/YYYY'),'SAÍDA',0,'VARIÁVEL');
  out_json:=axora_beta.axora_family_reverse_provision_payment(
    wid,uid,occurrence_id,74.50);
  SELECT planned_value INTO v FROM axora_beta.finance_provision_rules
    WHERE id=rule_id;
  IF v<>74.50 THEN RAISE EXCEPTION 'Referencia variavel da regra nao restaurada'; END IF;
  SELECT planned_value INTO v FROM axora_beta.finance_provision_occurrences occ
    WHERE occ.rule_id=smoke_block.rule_id AND occ.sequence_no=2 AND occ.workspace_id=wid;
  IF v<>74.50 THEN RAISE EXCEPTION 'Referencia futura nao restaurada'; END IF;
END;
$smoke$;
ROLLBACK;