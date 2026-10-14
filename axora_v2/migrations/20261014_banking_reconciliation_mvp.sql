-- AXORA | Contas, titulares e conciliação assistida: MVP sem Open Finance.
-- Apenas dados informados manualmente; não atualiza saldos por sincronização bancária.
-- Nenhuma movimentação financeira é criada até uma confirmação explícita.
BEGIN;

CREATE TABLE IF NOT EXISTS public.finance_bank_holders (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
 name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 100),
 relationship text NOT NULL DEFAULT 'outro'
    CHECK (relationship IN ('proprio','conjuge','mae','pai','familiar','outro')),
 linked_user_id bigint REFERENCES public.finance_users(id) ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(id,workspace_id)
);
CREATE TABLE IF NOT EXISTS public.finance_bank_accounts (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
 holder_id bigint NOT NULL,
 bank_name text NOT NULL CHECK (length(btrim(bank_name)) BETWEEN 2 AND 80),
 nickname text NOT NULL CHECK (length(btrim(nickname)) BETWEEN 2 AND 100),
 account_type text NOT NULL DEFAULT 'corrente'
   CHECK (account_type IN ('corrente','poupanca','pagamento','outro')),
 masked_reference text CHECK (masked_reference IS NULL OR length(masked_reference)<=32),
 manual_balance numeric(16,2),
 currency text NOT NULL DEFAULT 'BRL' CHECK(currency='BRL'),
 connection_status text NOT NULL DEFAULT 'manual' CHECK(connection_status='manual'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(id,workspace_id),
 FOREIGN KEY(holder_id,workspace_id)
   REFERENCES public.finance_bank_holders(id,workspace_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS public.finance_bank_transactions (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 workspace_id uuid NOT NULL,
 account_id bigint NOT NULL,
 posted_on date NOT NULL,
 description text NOT NULL CHECK(length(btrim(description)) BETWEEN 1 AND 240),
 amount numeric(16,2) NOT NULL CHECK(amount<>0),
 source text NOT NULL DEFAULT 'manual' CHECK(source IN ('manual','import')),
 external_ref text NOT NULL DEFAULT gen_random_uuid()::text CHECK(length(external_ref) BETWEEN 8 AND 200),
 status text NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','matched_record','matched_provision','recorded','transfer','ignored')),
 movement_id bigint REFERENCES public.finance_movements(id) ON DELETE RESTRICT,
 provision_occurrence_id bigint REFERENCES public.finance_provision_occurrences(id) ON DELETE RESTRICT,
 counterpart_id bigint,
 reason text,
 decided_by bigint REFERENCES public.finance_users(id) ON DELETE RESTRICT,
 decided_at timestamptz,
 imported_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(account_id,source,external_ref),
 UNIQUE(id,workspace_id),
 FOREIGN KEY(account_id,workspace_id)
   REFERENCES public.finance_bank_accounts(id,workspace_id) ON DELETE RESTRICT,
 CHECK((status='pending' AND decided_at IS NULL AND movement_id IS NULL AND provision_occurrence_id IS NULL)
       OR (status<>'pending' AND decided_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS axora_bank_linked_movement_once
 ON public.finance_bank_transactions(movement_id) WHERE movement_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS axora_bank_linked_provision_once
 ON public.finance_bank_transactions(provision_occurrence_id) WHERE provision_occurrence_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS axora_bank_queue
 ON public.finance_bank_transactions(workspace_id,status,posted_on DESC,id DESC);
CREATE TABLE IF NOT EXISTS public.finance_reconciliation_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
 transaction_id bigint NOT NULL,
 actor_id bigint NOT NULL REFERENCES public.finance_users(id) ON DELETE RESTRICT,
 action text NOT NULL CHECK(action IN ('matched_record','matched_provision','recorded','transfer','ignored')),
 movement_id bigint,
 provision_occurrence_id bigint,
 counterpart_id bigint,
 notes text,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(transaction_id,workspace_id)
   REFERENCES public.finance_bank_transactions(id,workspace_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS axora_reconciliation_audit_scope
 ON public.finance_reconciliation_events(workspace_id,created_at DESC);

ALTER TABLE public.finance_bank_holders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_bank_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_bank_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_reconciliation_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.finance_bank_holders,public.finance_bank_accounts,
 public.finance_bank_transactions,public.finance_reconciliation_events FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON TABLE public.finance_bank_holders,public.finance_bank_accounts TO service_role;
GRANT SELECT,INSERT,UPDATE ON TABLE public.finance_bank_transactions TO service_role;
GRANT SELECT,INSERT ON TABLE public.finance_reconciliation_events TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.finance_bank_holders_id_seq,
 public.finance_bank_accounts_id_seq,public.finance_bank_transactions_id_seq,
 public.finance_reconciliation_events_id_seq TO service_role;

-- Banco e Registros são associados numa transação única. O operador decide sempre.
CREATE OR REPLACE FUNCTION public.axora_confirm_reconciliation(
 p_workspace_id uuid,p_user_id bigint,p_transaction_id bigint,p_action text,
 p_target_id bigint DEFAULT NULL,p_counterpart_id bigint DEFAULT NULL,
 p_category text DEFAULT NULL,p_reason text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE t record; other_tx record; m record; o record; v_movement bigint;
        v_status text; v_reason text :=nullif(btrim(coalesce(p_reason,'')),'');
        v_category text :=nullif(btrim(coalesce(p_category,'')),'');
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('matched_record','matched_provision','recorded','transfer','ignored')
 THEN RAISE EXCEPTION 'Ação de conciliação inválida'; END IF;
 IF NOT EXISTS(
   SELECT 1 FROM public.finance_workspace_members m
   JOIN public.finance_workspaces w ON w.id=m.workspace_id
   JOIN public.finance_users u ON u.id=m.user_id
   WHERE m.workspace_id=p_workspace_id AND m.user_id=p_user_id
     AND m.role IN ('owner','admin','editor') AND u.is_active AND w.is_active
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
   v_movement:=m.id; v_status:='matched_record';
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
   v_status:='matched_provision';
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
 RETURN jsonb_build_object('transaction_id',t.id,'status',v_status,
                           'movement_id',v_movement,'confirmed',true);
END;
$$;
REVOKE ALL ON FUNCTION public.axora_confirm_reconciliation(uuid,bigint,bigint,text,bigint,bigint,text,text)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_confirm_reconciliation(uuid,bigint,bigint,text,bigint,bigint,text,text)
 TO service_role;

COMMIT;
NOTIFY pgrst,'reload schema';
