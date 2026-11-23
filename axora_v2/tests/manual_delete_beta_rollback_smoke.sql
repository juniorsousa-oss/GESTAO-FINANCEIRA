-- Somente AXORA BETA. Todos os registros e saldos ficticios sao revertidos.
BEGIN;
DO $test$
<<smoke>>
DECLARE
  uid bigint; wid uuid; fid bigint; holder bigint; a1 bigint; a2 bigint;
  m1 bigint; m2 bigint; m3 bigint; v numeric; cnt integer;
  req1 uuid:=gen_random_uuid(); req2 uuid:=gen_random_uuid();
  result jsonb;
BEGIN
  INSERT INTO axora_beta.finance_users(display_name,password_hash,is_admin,is_active)
  VALUES('TESTE EXCLUSAO MANUAL DESCARTAVEL','hash-no-login',false,true)
  RETURNING id INTO uid;
  INSERT INTO axora_beta.finance_workspaces(name,created_by)
  VALUES('AXORA EXCLUSAO DESCARTAVEL',uid) RETURNING id INTO wid;
  INSERT INTO axora_beta.finance_workspace_members(workspace_id,user_id,role)
  VALUES(wid,uid,'owner');
  INSERT INTO axora_beta.finance_family_profiles(
    workspace_id,display_name,relationship,linked_user_id)
  VALUES(wid,'Teste de exclusao','principal',uid) RETURNING id INTO fid;
  INSERT INTO axora_beta.finance_bank_account_types(workspace_id,code,label)
  VALUES(wid,'corrente','Conta corrente');
  INSERT INTO axora_beta.finance_bank_holders(
    workspace_id,name,relationship,linked_user_id,family_profile_id)
  VALUES(wid,'Titular ficticio','proprio',uid,fid) RETURNING id INTO holder;
  INSERT INTO axora_beta.finance_bank_accounts(
    workspace_id,holder_id,bank_name,nickname,manual_balance)
  VALUES(wid,holder,'Banco teste','Conta ficticia 1',1000) RETURNING id INTO a1;
  INSERT INTO axora_beta.finance_bank_accounts(
    workspace_id,holder_id,bank_name,nickname,manual_balance)
  VALUES(wid,holder,'Banco teste','Conta ficticia 2',600) RETURNING id INTO a2;

  -- Entrada foi creditada por 750, mas depois editada no historico para 864.
  INSERT INTO axora_beta.finance_movements(
    workspace_id,movement_date,description,value,category,competence,
    classification,allocation_value,fixed_variable)
  VALUES(wid,current_date,'Receita manual teste',864,'Fonte de Renda',
    to_char(current_date,'MM/YYYY'),'ENTRADA',0,'VARIÁVEL')
  RETURNING id INTO m1;
  INSERT INTO axora_beta.finance_family_cost_allocations(
    workspace_id,movement_id,profile_id,amount)
  VALUES(wid,m1,fid,864);
  INSERT INTO axora_beta.finance_family_visibility(
    workspace_id,resource_type,resource_id,creator_user_id,label)
  VALUES(wid,'registro',m1,uid,'privado');
  INSERT INTO axora_beta.finance_family_balance_credits(
    workspace_id,request_id,movement_id,actor_user_id,recipient_profile_id,amount)
  VALUES(wid,req1,m1,uid,fid,750);
  INSERT INTO axora_beta.finance_family_balance_credit_sources(
    workspace_id,request_id,movement_id,recipient_profile_id,account_id,amount)
  VALUES(wid,req1,m1,fid,a1,500),(wid,req1,m1,fid,a2,250);
  result:=axora_beta.axora_manual_delete_preview(wid,uid,m1);
  IF (result->>'wallet_delta')::numeric<>-750 OR
      (result->>'amount')::numeric<>864 THEN
    RAISE EXCEPTION 'Prévia da entrada editada incorreta: %',result;
  END IF;
  result:=axora_beta.axora_manual_delete_movement(wid,uid,m1);
  IF (result->>'wallet_delta')::numeric<>-750 OR
      (result->>'deleted_id')::bigint<>m1 THEN
    RAISE EXCEPTION 'Estorno de entrada incorreto: %',result;
  END IF;
  SELECT manual_balance INTO v FROM axora_beta.finance_bank_accounts WHERE id=a1;
  IF v<>500 THEN RAISE EXCEPTION 'Conta 1 creditada: valor incorreto %',v; END IF;
  SELECT manual_balance INTO v FROM axora_beta.finance_bank_accounts WHERE id=a2;
  IF v<>350 THEN RAISE EXCEPTION 'Conta 2 creditada: valor incorreto %',v; END IF;
  SELECT count(*) INTO cnt FROM axora_beta.finance_manual_movement_deletions aud
    WHERE aud.workspace_id=wid AND aud.movement_id=m1
      AND aud.credited_reversed=750 AND aud.wallet_delta=-750;
  IF cnt<>1 THEN RAISE EXCEPTION 'Auditoria nao foi salva'; END IF;
  SELECT count(*) INTO cnt FROM axora_beta.finance_family_cost_allocations c
    WHERE c.movement_id=m1;
  IF cnt<>0 THEN RAISE EXCEPTION 'Rateio da entrada ainda existe'; END IF;
  SELECT count(*) INTO cnt FROM axora_beta.finance_family_balance_credits c
    WHERE c.movement_id=m1;
  IF cnt<>0 THEN RAISE EXCEPTION 'Credito legado ainda existe'; END IF;
  BEGIN
    PERFORM axora_beta.axora_manual_delete_movement(wid,uid,m1);
    RAISE EXCEPTION 'DUPLICATED_DELETE_ACCEPTED';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM='DUPLICATED_DELETE_ACCEPTED' THEN RAISE; END IF;
  END;

  -- Saida manual baixada com duas fontes: devolver somente valores debitados.
  INSERT INTO axora_beta.finance_movements(
    workspace_id,movement_date,description,value,category,competence,
    classification,allocation_value,fixed_variable)
  VALUES(wid,current_date,'Gasto manual teste',50,'Saúde',
    to_char(current_date,'MM/YYYY'),'SAÍDA',0,'VARIÁVEL')
  RETURNING id INTO m2;
  INSERT INTO axora_beta.finance_family_cost_allocations(
    workspace_id,movement_id,profile_id,amount) VALUES(wid,m2,fid,50);
  INSERT INTO axora_beta.finance_family_payment_allocations(
    workspace_id,movement_id,payer_profile_id,amount)
  VALUES(wid,m2,fid,50);
  INSERT INTO axora_beta.finance_family_balance_debits(
    workspace_id,request_id,movement_id,actor_user_id,amount)
  VALUES(wid,req2,m2,uid,50);
  INSERT INTO axora_beta.finance_family_balance_debit_sources(
    workspace_id,request_id,movement_id,payer_profile_id,account_id,amount)
  VALUES(wid,req2,m2,fid,a1,20),(wid,req2,m2,fid,a2,30);
  result:=axora_beta.axora_manual_delete_movement(wid,uid,m2);
  IF (result->>'wallet_delta')::numeric<>50 THEN
    RAISE EXCEPTION 'Debito nao foi devolvido: %',result; END IF;
  SELECT manual_balance INTO v FROM axora_beta.finance_bank_accounts WHERE id=a1;
  IF v<>520 THEN RAISE EXCEPTION 'Conta 1 apos gasto: %',v; END IF;
  SELECT manual_balance INTO v FROM axora_beta.finance_bank_accounts WHERE id=a2;
  IF v<>380 THEN RAISE EXCEPTION 'Conta 2 apos gasto: %',v; END IF;

  -- Registro historico: retirar sem mexer no banco, mas excluir rateio.
  INSERT INTO axora_beta.finance_movements(
    workspace_id,movement_date,description,value,category,competence,
    classification,allocation_value,fixed_variable)
  VALUES(wid,current_date,'Historico simples',100,'Outros',
    to_char(current_date,'MM/YYYY'),'ENTRADA',0,'VARIÁVEL')
  RETURNING id INTO m3;
  INSERT INTO axora_beta.finance_family_cost_allocations(
    workspace_id,movement_id,profile_id,amount) VALUES(wid,m3,fid,100);
  result:=axora_beta.axora_manual_delete_movement(wid,uid,m3);
  IF (result->>'wallet_delta')::numeric<>0 THEN
    RAISE EXCEPTION 'Historico movimentou saldo indevidamente: %',result; END IF;
  SELECT count(*) INTO cnt FROM axora_beta.finance_movements WHERE id=m3;
  IF cnt<>0 THEN RAISE EXCEPTION 'Historico continua ativo'; END IF;
END;
$test$;
ROLLBACK;