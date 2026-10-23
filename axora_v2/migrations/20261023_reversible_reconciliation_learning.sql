-- AXORA 2026-10-23: reversão auditável e padrões supervisionados.
-- Não altera o extrato bancário e não concilia automaticamente.
BEGIN;

CREATE TABLE IF NOT EXISTS public.finance_reconciliation_learning (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
 transaction_id bigint NOT NULL,
 source_description text NOT NULL,
 target_description text NOT NULL,
 action text NOT NULL CHECK(action IN ('matched_record','matched_provision')),
 active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT finance_reconciliation_learning_transaction_unique UNIQUE(workspace_id,transaction_id),
 CONSTRAINT finance_reconciliation_learning_transaction_fk
   FOREIGN KEY(transaction_id,workspace_id)
   REFERENCES public.finance_bank_transactions(id,workspace_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS axora_reconciliation_learning_scope
 ON public.finance_reconciliation_learning(workspace_id,active,updated_at DESC,id DESC);
ALTER TABLE public.finance_reconciliation_learning ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.finance_reconciliation_learning FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON TABLE public.finance_reconciliation_learning TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.finance_reconciliation_learning_id_seq TO service_role;
-- A primeira conciliação anterior também é aproveitada.
INSERT INTO public.finance_reconciliation_learning(
 workspace_id,transaction_id,source_description,target_description,action)
SELECT t.workspace_id,t.id,t.description,m.description,'matched_record'
FROM public.finance_bank_transactions t
JOIN public.finance_movements m ON m.id=t.movement_id AND m.workspace_id=t.workspace_id
WHERE t.status='matched_record'
ON CONFLICT (workspace_id,transaction_id) DO NOTHING;
INSERT INTO public.finance_reconciliation_learning(
 workspace_id,transaction_id,source_description,target_description,action)
SELECT t.workspace_id,t.id,t.description,
       coalesce(o.description_override,r.description),'matched_provision'
FROM public.finance_bank_transactions t
JOIN public.finance_provision_occurrences o
 ON o.id=t.provision_occurrence_id AND o.workspace_id=t.workspace_id
JOIN public.finance_provision_rules r ON r.id=o.rule_id AND r.workspace_id=o.workspace_id
WHERE t.status='matched_provision'
ON CONFLICT (workspace_id,transaction_id) DO NOTHING;
ALTER TABLE public.finance_reconciliation_events
 DROP CONSTRAINT IF EXISTS finance_reconciliation_events_action_check;
ALTER TABLE public.finance_reconciliation_events
 ADD CONSTRAINT finance_reconciliation_events_action_check
 CHECK (action IN ('matched_record','matched_provision','recorded','transfer','ignored','reversed'));

CREATE OR REPLACE FUNCTION public.axora_confirm_reconciliation(
 p_workspace_id uuid,p_user_id bigint,p_transaction_id bigint,p_action text,
 p_target_id bigint DEFAULT NULL,p_counterpart_id bigint DEFAULT NULL,
 p_category text DEFAULT NULL,p_reason text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
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
   IF abs(o.planned_value-abs(t.amount))>0.01 THEN
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
$$;

CREATE OR REPLACE FUNCTION public.axora_undo_reconciliation(
 p_workspace_id uuid,p_user_id bigint,p_transaction_id bigint,p_reason text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE
 t record; other_tx record; m record; o record;
 v_reason text:=nullif(btrim(coalesce(p_reason,'')),'');
 v_movement bigint; v_occurrence bigint; v_counterpart bigint; v_previous text;
BEGIN
 IF v_reason IS NULL OR length(v_reason)<5 OR length(v_reason)>250 THEN
   RAISE EXCEPTION 'Informe o motivo do estorno (5 a 250 caracteres)';
 END IF;
 IF NOT EXISTS(
   SELECT 1 FROM public.finance_workspace_members member
   JOIN public.finance_workspaces w ON w.id=member.workspace_id
   JOIN public.finance_users u ON u.id=member.user_id
   WHERE member.workspace_id=p_workspace_id AND member.user_id=p_user_id
     AND member.role IN ('owner','admin','editor') AND u.is_active AND w.is_active
 ) THEN RAISE EXCEPTION 'Acesso não autorizado ao espaço financeiro'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext(p_workspace_id::text));
 SELECT * INTO t FROM public.finance_bank_transactions
 WHERE id=p_transaction_id AND workspace_id=p_workspace_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Transação não localizada'; END IF;
 IF t.status='pending' THEN RAISE EXCEPTION 'Esta transação já está pendente'; END IF;
 IF t.status NOT IN ('matched_record','matched_provision','transfer','ignored')
 THEN RAISE EXCEPTION 'Estorno não permitido: um novo Registro criado exige revisão manual'; END IF;
 v_movement:=t.movement_id; v_occurrence:=t.provision_occurrence_id;
 v_counterpart:=t.counterpart_id; v_previous:=t.status;
 IF t.status='matched_provision' THEN
   SELECT * INTO m FROM public.finance_movements
     WHERE id=t.movement_id AND workspace_id=p_workspace_id FOR UPDATE;
   SELECT i.*,coalesce(i.description_override,r.description) expected_description,
          coalesce(i.category_override,r.category) expected_category INTO o
   FROM public.finance_provision_occurrences i
   JOIN public.finance_provision_rules r ON r.id=i.rule_id AND r.workspace_id=i.workspace_id
   WHERE i.id=t.provision_occurrence_id AND i.workspace_id=p_workspace_id FOR UPDATE OF i;
   IF m.id IS NULL OR o.id IS NULL OR o.status<>'paid'
      OR o.payment_date IS DISTINCT FROM t.posted_on
      OR o.paid_value IS DISTINCT FROM abs(t.amount)
      OR m.provision_occurrence_id IS DISTINCT FROM o.id
      OR m.movement_date IS DISTINCT FROM t.posted_on
      OR m.description IS DISTINCT FROM o.expected_description
      OR m.category IS DISTINCT FROM o.expected_category
      OR m.value IS DISTINCT FROM abs(t.amount)
      OR m.classification<>'SAÍDA'
      OR EXISTS(SELECT 1 FROM public.finance_movements extra
         WHERE extra.provision_occurrence_id=o.id AND extra.id<>m.id)
      OR EXISTS(SELECT 1 FROM public.finance_bank_transactions link
         WHERE link.workspace_id=p_workspace_id AND link.id<>t.id AND link.movement_id=m.id)
   THEN RAISE EXCEPTION 'Provisão ou Registro alterado após conciliação: estorno bloqueado'; END IF;
 ELSIF t.status='transfer' THEN
   SELECT * INTO other_tx FROM public.finance_bank_transactions
     WHERE id=t.counterpart_id AND workspace_id=p_workspace_id FOR UPDATE;
   IF other_tx.id IS NULL OR other_tx.status<>'transfer'
      OR other_tx.counterpart_id IS DISTINCT FROM t.id THEN
     RAISE EXCEPTION 'Contrapartida da transferência alterada: estorno bloqueado';
   END IF;
 END IF;
 UPDATE public.finance_bank_transactions SET
   status='pending',movement_id=NULL,provision_occurrence_id=NULL,
   counterpart_id=NULL,reason=NULL,decided_by=NULL,decided_at=NULL
 WHERE id=t.id AND workspace_id=p_workspace_id;
 IF v_previous='transfer' THEN
   UPDATE public.finance_bank_transactions SET
     status='pending',movement_id=NULL,provision_occurrence_id=NULL,
     counterpart_id=NULL,reason=NULL,decided_by=NULL,decided_at=NULL
   WHERE id=other_tx.id AND workspace_id=p_workspace_id;
   INSERT INTO public.finance_reconciliation_events(
     workspace_id,transaction_id,actor_id,action,counterpart_id,notes)
   VALUES(p_workspace_id,other_tx.id,p_user_id,'reversed',t.id,v_reason);
 ELSIF v_previous='matched_provision' THEN
   DELETE FROM public.finance_movements WHERE id=v_movement AND workspace_id=p_workspace_id;
   UPDATE public.finance_provision_occurrences
     SET status='open',payment_date=NULL,paid_value=NULL
     WHERE id=v_occurrence AND workspace_id=p_workspace_id;
 END IF;
 UPDATE public.finance_reconciliation_learning SET active=false,updated_at=now()
 WHERE workspace_id=p_workspace_id AND transaction_id=t.id AND active;
 INSERT INTO public.finance_reconciliation_events(
   workspace_id,transaction_id,actor_id,action,
   movement_id,provision_occurrence_id,counterpart_id,notes)
 VALUES(p_workspace_id,t.id,p_user_id,'reversed',
        v_movement,v_occurrence,v_counterpart,v_reason);
 RETURN jsonb_build_object('transaction_id',t.id,'status','pending',
        'reversed_action',v_previous,'reverted',true);
END;
$$;
REVOKE ALL ON FUNCTION public.axora_undo_reconciliation(uuid,bigint,bigint,text)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_undo_reconciliation(uuid,bigint,bigint,text)
 TO service_role;

COMMIT;
NOTIFY pgrst,'reload schema';
