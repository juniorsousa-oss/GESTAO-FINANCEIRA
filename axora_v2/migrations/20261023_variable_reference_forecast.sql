-- AXORA: contas recorrentes de valor variável com referência pelo último pagamento.
-- Aditivo. Preserva lançamentos e ocorrências anteriores.
ALTER TABLE public.finance_provision_rules ALTER COLUMN planned_value DROP NOT NULL;
ALTER TABLE public.finance_provision_revisions ALTER COLUMN planned_value DROP NOT NULL;
ALTER TABLE public.finance_provision_occurrences ALTER COLUMN planned_value DROP NOT NULL;

ALTER TABLE public.finance_provision_rules
  ADD CONSTRAINT axora_rule_fixed_requires_amount
  CHECK (value_mode='variable' OR planned_value IS NOT NULL);
ALTER TABLE public.finance_provision_revisions
  ADD CONSTRAINT axora_revision_fixed_requires_amount
  CHECK (value_mode='variable' OR planned_value IS NOT NULL);

ALTER TABLE public.finance_provision_rules
  ADD COLUMN IF NOT EXISTS last_paid_value numeric(14,2),
  ADD COLUMN IF NOT EXISTS last_paid_at date;

-- Trigger único para todas as quitações: manual, conciliação e Registro existente.
-- Não retroage valores para competências anteriores nem mexe em pagamentos quitados.
CREATE OR REPLACE FUNCTION public.axora_update_variable_reference()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $body$
DECLARE effective_mode text;
BEGIN
  IF NEW.status<>'paid' OR OLD.status<>'open' OR NEW.paid_value IS NULL OR NEW.paid_value<=0
  THEN RETURN NEW; END IF;
  SELECT coalesce(NEW.value_mode_override,r.value_mode) INTO effective_mode
    FROM public.finance_provision_rules r
    WHERE r.id=NEW.rule_id AND r.workspace_id=NEW.workspace_id;
  IF effective_mode IS DISTINCT FROM 'variable' THEN RETURN NEW; END IF;

  -- Um pagamento de parcela antiga não substitui referência de parcela posterior já paga.
  IF EXISTS(SELECT 1 FROM public.finance_provision_occurrences
            WHERE workspace_id=NEW.workspace_id AND rule_id=NEW.rule_id
              AND sequence_no>NEW.sequence_no AND status='paid') THEN RETURN NEW; END IF;

  UPDATE public.finance_provision_rules SET
    last_paid_value=NEW.paid_value,last_paid_at=NEW.payment_date,
    planned_value=CASE WHEN value_mode='variable' THEN NEW.paid_value ELSE planned_value END
  WHERE id=NEW.rule_id AND workspace_id=NEW.workspace_id;

  -- Regras revisadas também precisam incorporar a última referência para gerar novas parcelas.
  UPDATE public.finance_provision_revisions SET planned_value=NEW.paid_value
  WHERE rule_id=NEW.rule_id AND workspace_id=NEW.workspace_id
    AND value_mode='variable';

  UPDATE public.finance_provision_occurrences i SET planned_value=NEW.paid_value
  FROM public.finance_provision_rules r
  WHERE r.id=i.rule_id AND r.workspace_id=i.workspace_id
    AND i.rule_id=NEW.rule_id AND i.workspace_id=NEW.workspace_id
    AND i.sequence_no>NEW.sequence_no AND i.status='open'
    AND coalesce(i.value_mode_override,r.value_mode)='variable';
  RETURN NEW;
END;
$body$;

REVOKE ALL ON FUNCTION public.axora_update_variable_reference()
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_update_variable_reference() TO service_role;

DROP TRIGGER IF EXISTS axora_variable_paid_reference ON public.finance_provision_occurrences;
CREATE TRIGGER axora_variable_paid_reference
AFTER UPDATE OF status ON public.finance_provision_occurrences
FOR EACH ROW WHEN (OLD.status='open' AND NEW.status='paid')
EXECUTE FUNCTION public.axora_update_variable_reference();

-- Revisão de axora_ensure_provisions
CREATE OR REPLACE FUNCTION public.axora_ensure_provisions(p_workspace_id uuid, p_through date DEFAULT NULL::date)
 RETURNS integer
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE v_added integer; v_until date:=coalesce(p_through,(current_date+interval '18 months')::date);
BEGIN
  IF v_until>current_date+interval '30 months' THEN
    RAISE EXCEPTION 'Janela de geração excede 30 meses';
  END IF;
  WITH series AS (
    SELECT r.id,r.workspace_id,gs.seq,r.recurrence,r.end_date,r.installment_count,
      coalesce(rev.description,r.description) description,
      coalesce(rev.category,r.category) category,
      coalesce(rev.responsible,r.responsible) responsible,
      coalesce(rev.value_mode,r.value_mode) value_mode,
      CASE WHEN rev.id IS NOT NULL THEN rev.planned_value ELSE r.planned_value END amount,
      public.axora_due_at(coalesce(rev.anchor_due_date,r.start_due_date),r.frequency,
                          gs.seq-coalesce(rev.effective_sequence,1)) due_date
    FROM public.finance_provision_rules r
    CROSS JOIN LATERAL generate_series(
      1,
      CASE
        WHEN r.recurrence='once' THEN 1
        WHEN r.recurrence IN ('installments','until_date') AND r.installment_count IS NOT NULL
          THEN least(360,r.installment_count)
        WHEN r.recurrence='until_date' AND r.end_date IS NOT NULL
          THEN least(5000,greatest(1,ceil((r.end_date-r.start_due_date)::numeric/7)::integer+3))
        ELSE least(5000,greatest(1,ceil((v_until-r.start_due_date)::numeric/7)::integer+3))
      END
    ) AS gs(seq)
    LEFT JOIN LATERAL (
      SELECT v.* FROM public.finance_provision_revisions v
      WHERE v.rule_id=r.id AND v.workspace_id=r.workspace_id
        AND v.effective_sequence<=gs.seq
      ORDER BY v.effective_sequence DESC LIMIT 1
    ) rev ON true
    WHERE r.active AND r.workspace_id=p_workspace_id
      AND (r.stop_before_sequence IS NULL OR gs.seq<r.stop_before_sequence)
  )
  INSERT INTO public.finance_provision_occurrences(
    rule_id,workspace_id,sequence_no,due_date,planned_value,
    description_override,category_override,responsible_override,value_mode_override
  )
  SELECT s.id,s.workspace_id,s.seq,s.due_date,s.amount,
         -- Snapshot por ocorrência: futuras alterações não mudam pagamentos anteriores.
         s.description,s.category,s.responsible,s.value_mode
  FROM series s
  WHERE (s.recurrence IN ('once','installments','until_date') OR s.due_date<=v_until)
    AND (s.recurrence<>'once' OR s.seq=1)
    AND (s.recurrence<>'until_date' OR
         ((s.installment_count IS NOT NULL AND s.seq<=s.installment_count) OR
          (s.installment_count IS NULL AND s.due_date<=s.end_date)))
    AND (s.recurrence<>'installments' OR s.seq<=s.installment_count)
  ON CONFLICT(rule_id,sequence_no) DO NOTHING;
  GET DIAGNOSTICS v_added=ROW_COUNT;
  RETURN v_added;
END;
$function$
;

-- Revisão de axora_edit_provision
CREATE OR REPLACE FUNCTION public.axora_edit_provision(p_workspace_id uuid, p_occurrence_id bigint, p_scope text, p_due_date date, p_description text, p_category text, p_responsible text, p_planned_value numeric, p_value_mode text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE o record; r record; v_changed integer; v_trim_description text:=btrim(p_description);
        v_trim_category text:=btrim(p_category);v_trim_responsible text:=btrim(p_responsible);
BEGIN
  IF p_scope IS NULL OR p_scope NOT IN ('single','future') OR p_due_date IS NULL OR
     p_description IS NULL OR p_category IS NULL OR p_responsible IS NULL OR
     p_value_mode IS NULL OR
     length(v_trim_description) NOT BETWEEN 1 AND 240 OR
     length(v_trim_category) NOT BETWEEN 1 AND 120 OR
     length(v_trim_responsible) NOT BETWEEN 1 AND 120 OR
     (p_planned_value IS NOT NULL AND (p_planned_value<=0 OR p_planned_value>999999999999.99)) OR
     (p_value_mode='fixed' AND p_planned_value IS NULL) OR
     p_value_mode NOT IN ('fixed','variable') THEN
    RAISE EXCEPTION 'Alteração inválida';
  END IF;
  SELECT x.* INTO r FROM public.finance_provision_rules x
  WHERE x.id=(SELECT i.rule_id FROM public.finance_provision_occurrences i
              WHERE i.id=p_occurrence_id AND i.workspace_id=p_workspace_id)
    AND x.workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Provisão não encontrada'; END IF;
  SELECT i.* INTO o FROM public.finance_provision_occurrences i
  WHERE i.id=p_occurrence_id AND i.workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Provisão não encontrada'; END IF;
  IF o.status<>'open' THEN RAISE EXCEPTION 'Somente provisões em aberto podem ser alteradas'; END IF;
  IF r.stop_before_sequence IS NOT NULL AND o.sequence_no>=r.stop_before_sequence THEN
    RAISE EXCEPTION 'Série encerrada';
  END IF;
  IF p_scope='future' THEN
    INSERT INTO public.finance_provision_revisions(
      workspace_id,rule_id,effective_sequence,anchor_due_date,description,
      category,responsible,planned_value,value_mode
    ) VALUES (
      p_workspace_id,r.id,o.sequence_no,p_due_date,v_trim_description,
      v_trim_category,v_trim_responsible,p_planned_value,p_value_mode
    ) ON CONFLICT(rule_id,effective_sequence) DO UPDATE SET
      anchor_due_date=excluded.anchor_due_date,description=excluded.description,
      category=excluded.category,responsible=excluded.responsible,
      planned_value=excluded.planned_value,value_mode=excluded.value_mode,edited_at=now();
    UPDATE public.finance_provision_occurrences i SET
      due_date=public.axora_due_at(p_due_date,r.frequency,i.sequence_no-o.sequence_no),
      planned_value=p_planned_value,description_override=v_trim_description,
      category_override=v_trim_category,responsible_override=v_trim_responsible,
      value_mode_override=p_value_mode,edited_at=now()
    WHERE i.workspace_id=p_workspace_id AND i.rule_id=r.id
      AND i.sequence_no>=o.sequence_no AND i.status='open';
  ELSE
    UPDATE public.finance_provision_occurrences SET
      due_date=p_due_date,planned_value=p_planned_value,
      description_override=v_trim_description,category_override=v_trim_category,
      responsible_override=v_trim_responsible,value_mode_override=p_value_mode,edited_at=now()
    WHERE id=p_occurrence_id AND workspace_id=p_workspace_id AND status='open';
  END IF;
  GET DIAGNOSTICS v_changed=ROW_COUNT;
  RETURN jsonb_build_object('updated',v_changed,'scope',p_scope,'occurrence_id',p_occurrence_id);
END;
$function$
;

-- Revisão de axora_confirm_reconciliation
CREATE OR REPLACE FUNCTION public.axora_confirm_reconciliation(p_workspace_id uuid, p_user_id bigint, p_transaction_id bigint, p_action text, p_target_id bigint DEFAULT NULL::bigint, p_counterpart_id bigint DEFAULT NULL::bigint, p_category text DEFAULT NULL::text, p_reason text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE t record; other_tx record; m record; o record; v_movement bigint;
        v_status text; v_pattern_label text; v_reason text :=nullif(btrim(coalesce(p_reason,'')),'');
        v_category text :=nullif(btrim(coalesce(p_category,'')),'');
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('matched_record','matched_provision','recorded','transfer','ignored')
 THEN RAISE EXCEPTION 'Ação de conciliação inválida'; END IF;
 IF NOT EXISTS(
   SELECT 1 FROM public.finance_workspace_members member
   JOIN public.finance_workspaces w ON w.id=member.workspace_id
   JOIN public.finance_users u ON u.id=member.user_id
   WHERE member.workspace_id=p_workspace_id AND member.user_id=p_user_id
     AND member.role IN ('owner','admin','editor') AND u.is_active AND w.is_active
 ) THEN RAISE EXCEPTION 'Acesso não autorizado ao espaço financeiro'; END IF;

 -- Evita disputas entre dois operadores conciliando transações do mesmo espaço.
 PERFORM pg_advisory_xact_lock(hashtext(p_workspace_id::text));
 SELECT * INTO t FROM public.finance_bank_transactions
 WHERE id=p_transaction_id AND workspace_id=p_workspace_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Transação não localizada'; END IF;
 IF t.status<>'pending' THEN RAISE EXCEPTION 'Movimentação bancária já analisada'; END IF;
 IF p_action='matched_record' THEN
   SELECT * INTO m FROM public.finance_movements
   WHERE id=p_target_id AND workspace_id=p_workspace_id FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Registro não localizado'; END IF;
   IF (t.amount<0 AND m.classification<>'SAÍDA')
      OR (t.amount>0 AND m.classification<>'ENTRADA')
      OR abs(abs(t.amount)-m.value)>0.01 THEN
     RAISE EXCEPTION 'Valor ou direção divergente: revisar antes de vincular'; END IF;
   IF EXISTS(SELECT 1 FROM public.finance_bank_transactions
             WHERE movement_id=m.id AND status<>'pending') THEN
     RAISE EXCEPTION 'Este Registro já está conciliado com outra transação'; END IF;
   v_movement:=m.id; v_status:='matched_record'; v_pattern_label:=m.description;
 ELSIF p_action='matched_provision' THEN
   IF t.amount>=0 THEN RAISE EXCEPTION 'Provisão de saída exige débito'; END IF;
   SELECT i.id,i.status,i.planned_value,
          coalesce(i.description_override,r.description) description,
          coalesce(i.category_override,r.category) category,
          coalesce(i.value_mode_override,r.value_mode) value_mode
     INTO o FROM public.finance_provision_occurrences i
     JOIN public.finance_provision_rules r ON r.id=i.rule_id AND r.workspace_id=i.workspace_id
     WHERE i.id=p_target_id AND i.workspace_id=p_workspace_id FOR UPDATE OF i;
   IF NOT FOUND THEN RAISE EXCEPTION 'Provisão não localizada'; END IF;
   IF o.status<>'open' THEN RAISE EXCEPTION 'Provisão já quitada ou cancelada'; END IF;
   IF o.value_mode='fixed' AND (o.planned_value IS NULL OR abs(o.planned_value-abs(t.amount))>0.01) THEN
     RAISE EXCEPTION 'Valor divergente: pagamento parcial/ajuste ainda indisponível'; END IF;
   INSERT INTO public.finance_movements(
     workspace_id,movement_date,description,value,category,competence,classification,
     allocation_value,fixed_variable,provision_occurrence_id
   ) VALUES(
     p_workspace_id,t.posted_on,o.description,abs(t.amount),o.category,
     to_char(t.posted_on,'MM/YYYY'),'SAÍDA',0,
     CASE WHEN o.value_mode='fixed' THEN 'FIXO' ELSE 'VARIÁVEL' END,o.id
   ) RETURNING id INTO v_movement;
   UPDATE public.finance_provision_occurrences SET
     status='paid',payment_date=t.posted_on,paid_value=abs(t.amount)
   WHERE id=o.id AND workspace_id=p_workspace_id;
   v_status:='matched_provision'; v_pattern_label:=o.description;
 ELSIF p_action='recorded' THEN
   IF v_category IS NULL OR NOT EXISTS(
     SELECT 1 FROM public.finance_catalog_options WHERE workspace_id=p_workspace_id
       AND kind='category' AND active AND lower(name)=lower(v_category)
   ) THEN RAISE EXCEPTION 'Escolha uma categoria ativa antes de registrar'; END IF;
   INSERT INTO public.finance_movements(
     workspace_id,movement_date,description,value,category,competence,
     classification,allocation_value,fixed_variable
   ) VALUES(
     p_workspace_id,t.posted_on,t.description,abs(t.amount),v_category,
     to_char(t.posted_on,'MM/YYYY'),
     CASE WHEN t.amount<0 THEN 'SAÍDA' ELSE 'ENTRADA' END,0,'VARIÁVEL'
   ) RETURNING id INTO v_movement;
   v_status:='recorded';
 ELSIF p_action='transfer' THEN
   SELECT * INTO other_tx FROM public.finance_bank_transactions
   WHERE id=p_counterpart_id AND workspace_id=p_workspace_id FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'Contrapartida não localizada'; END IF;
   IF other_tx.status<>'pending' OR other_tx.account_id=t.account_id
      OR other_tx.amount<>-t.amount THEN
     RAISE EXCEPTION 'Transferência exige contas distintas, valores iguais e sinais opostos'; END IF;
   UPDATE public.finance_bank_transactions SET status='transfer',
      counterpart_id=t.id,decided_by=p_user_id,decided_at=now()
   WHERE id=other_tx.id AND workspace_id=p_workspace_id;
   INSERT INTO public.finance_reconciliation_events(
       workspace_id,transaction_id,actor_id,action,counterpart_id
   ) VALUES(p_workspace_id,other_tx.id,p_user_id,'transfer',t.id);
   v_status:='transfer';
 ELSIF p_action='ignored' THEN
   IF length(v_reason)<5 OR v_reason IS NULL THEN
      RAISE EXCEPTION 'É obrigatório justificar a movimentação ignorada'; END IF;
   v_status:='ignored';
 END IF;

 UPDATE public.finance_bank_transactions SET
   status=v_status,movement_id=v_movement,
   provision_occurrence_id=CASE WHEN v_status='matched_provision' THEN p_target_id ELSE NULL END,
   counterpart_id=CASE WHEN v_status='transfer' THEN p_counterpart_id ELSE NULL END,
   reason=v_reason,decided_by=p_user_id,decided_at=now()
 WHERE id=t.id AND workspace_id=p_workspace_id;

 INSERT INTO public.finance_reconciliation_events(
   workspace_id,transaction_id,actor_id,action,movement_id,
   provision_occurrence_id,counterpart_id,notes
 ) VALUES(
   p_workspace_id,t.id,p_user_id,v_status,v_movement,
   CASE WHEN v_status='matched_provision' THEN p_target_id ELSE NULL END,
   CASE WHEN v_status='transfer' THEN p_counterpart_id ELSE NULL END,v_reason
 );
 IF v_status IN ('matched_record','matched_provision')
     AND length(btrim(coalesce(v_pattern_label,'')))>0 THEN
   INSERT INTO public.finance_reconciliation_learning(
       workspace_id,transaction_id,source_description,target_description,action,active)
   VALUES(p_workspace_id,t.id,t.description,v_pattern_label,v_status,true)
   ON CONFLICT (workspace_id,transaction_id)
   DO UPDATE SET source_description=excluded.source_description,
                 target_description=excluded.target_description,
                 action=excluded.action,active=true,updated_at=now();
 END IF;
 RETURN jsonb_build_object('transaction_id',t.id,'status',v_status,
                           'movement_id',v_movement,'confirmed',true);
END;
$function$
;

-- Revisão de axora_link_record_to_provision
CREATE OR REPLACE FUNCTION public.axora_link_record_to_provision(p_workspace_id uuid, p_user_id bigint, p_occurrence_id bigint, p_movement_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE o record; m record;
BEGIN
  IF NOT EXISTS(
    SELECT 1 FROM public.finance_workspace_members member
    JOIN public.finance_workspaces w ON w.id=member.workspace_id
    JOIN public.finance_users u ON u.id=member.user_id
    WHERE member.workspace_id=p_workspace_id AND member.user_id=p_user_id
      AND member.role IN ('owner','admin','editor') AND u.is_active AND w.is_active
  ) THEN RAISE EXCEPTION 'Usuário não pode vincular registros neste espaço'; END IF;

  PERFORM pg_advisory_xact_lock(hashtext(p_workspace_id::text));
  SELECT i.*,coalesce(i.value_mode_override,r.value_mode) effective_mode INTO o
    FROM public.finance_provision_occurrences i
    JOIN public.finance_provision_rules r ON r.id=i.rule_id AND r.workspace_id=i.workspace_id
    WHERE i.id=p_occurrence_id AND i.workspace_id=p_workspace_id FOR UPDATE OF i;
  IF NOT FOUND OR o.status<>'open' THEN
    RAISE EXCEPTION 'Previsão não está em aberto'; END IF;

  SELECT * INTO m FROM public.finance_movements
    WHERE id=p_movement_id AND workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND OR m.classification<>'SAÍDA' OR m.provision_occurrence_id IS NOT NULL
     OR m.movement_date IS NULL OR
     (o.effective_mode='fixed' AND (o.planned_value IS NULL OR abs(m.value-o.planned_value)>0.01)) THEN
    RAISE EXCEPTION 'Registro indisponível ou com valor/direção divergente'; END IF;

  IF EXISTS(SELECT 1 FROM public.finance_provision_record_links
            WHERE workspace_id=p_workspace_id
              AND (movement_id=p_movement_id OR occurrence_id=p_occurrence_id))
  THEN RAISE EXCEPTION 'Vínculo já registrado'; END IF;

  UPDATE public.finance_movements SET provision_occurrence_id=p_occurrence_id
    WHERE id=m.id AND workspace_id=p_workspace_id
      AND provision_occurrence_id IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'Registro alterado por outro operador'; END IF;

  UPDATE public.finance_provision_occurrences
    SET status='paid',payment_date=m.movement_date,paid_value=m.value
    WHERE id=o.id AND workspace_id=p_workspace_id AND status='open';
  IF NOT FOUND THEN RAISE EXCEPTION 'Previsão alterada por outro operador'; END IF;

  INSERT INTO public.finance_provision_record_links(
      workspace_id,occurrence_id,movement_id,actor_id)
  VALUES(p_workspace_id,o.id,m.id,p_user_id);
  RETURN jsonb_build_object('occurrence_id',o.id,'movement_id',m.id,
           'status','paid','linked_existing_record',true);
END;
$function$
;
