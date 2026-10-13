-- AXORA: alterações de provisões com escopo uma ocorrência ou desta em diante.
-- Não modifica pagamentos realizados, nem elimina provisões ou registros já gravados.
BEGIN;

ALTER TABLE public.finance_provision_rules
  ADD COLUMN IF NOT EXISTS stop_before_sequence integer;
ALTER TABLE public.finance_provision_rules
  ADD CONSTRAINT axora_provision_stop_sequence_check
  CHECK (stop_before_sequence IS NULL OR stop_before_sequence >= 1);

-- O modo 'prazo definido' passa a permitir quantidade de vencimentos.
-- Regras históricas que tinham end_date continuam válidas e não são convertidas.
ALTER TABLE public.finance_provision_rules
  DROP CONSTRAINT IF EXISTS finance_provision_rules_check;
ALTER TABLE public.finance_provision_rules
  ADD CONSTRAINT axora_provision_term_check CHECK (
    recurrence <> 'until_date' OR (
      (end_date IS NOT NULL AND end_date >= start_due_date) OR
      (installment_count BETWEEN 1 AND 360)
    )
  );

ALTER TABLE public.finance_provision_occurrences
  DROP CONSTRAINT IF EXISTS finance_provision_occurrences_check;
ALTER TABLE public.finance_provision_occurrences
  ADD CONSTRAINT axora_provision_settlement_check
  CHECK (status<>'paid' OR (payment_date IS NOT NULL AND paid_value>0));
ALTER TABLE public.finance_provision_occurrences
  DROP CONSTRAINT IF EXISTS finance_provision_occurrences_status_check;
ALTER TABLE public.finance_provision_occurrences
  ADD CONSTRAINT axora_provision_status_check
  CHECK (status IN ('open','paid','cancelled'));
ALTER TABLE public.finance_provision_occurrences
  ADD COLUMN IF NOT EXISTS description_override text,
  ADD COLUMN IF NOT EXISTS category_override text,
  ADD COLUMN IF NOT EXISTS responsible_override text,
  ADD COLUMN IF NOT EXISTS value_mode_override text,
  ADD COLUMN IF NOT EXISTS edited_at timestamptz,
  ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;
ALTER TABLE public.finance_provision_occurrences
  ADD CONSTRAINT axora_occurrence_override_value_mode_check
  CHECK (value_mode_override IS NULL OR value_mode_override IN ('fixed','variable'));

CREATE TABLE IF NOT EXISTS public.finance_provision_revisions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
  rule_id bigint NOT NULL,
  effective_sequence integer NOT NULL CHECK(effective_sequence>=1),
  anchor_due_date date NOT NULL,
  description text NOT NULL CHECK(length(btrim(description)) BETWEEN 1 AND 240),
  category text NOT NULL CHECK(length(btrim(category)) BETWEEN 1 AND 120),
  responsible text NOT NULL CHECK(length(btrim(responsible)) BETWEEN 1 AND 120),
  planned_value numeric(14,2) NOT NULL CHECK(planned_value>0),
  value_mode text NOT NULL CHECK(value_mode IN ('fixed','variable')),
  edited_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT axora_revision_rule_workspace_fk
    FOREIGN KEY(rule_id,workspace_id) REFERENCES public.finance_provision_rules(id,workspace_id),
  CONSTRAINT axora_revision_sequence_unique UNIQUE(rule_id,effective_sequence)
);
CREATE INDEX IF NOT EXISTS axora_revision_lookup
  ON public.finance_provision_revisions(rule_id,effective_sequence DESC);
ALTER TABLE public.finance_provision_revisions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.finance_provision_revisions FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.finance_provision_revisions TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.finance_provision_revisions_id_seq TO service_role;

-- Reconstroi datas mensais partindo sempre do dia do primeiro vencimento
-- (ex.: dia 31 passa ao último dia de fevereiro e volta ao dia 31 em março).
CREATE OR REPLACE FUNCTION public.axora_due_at(
  p_anchor date,p_frequency text,p_offset integer
) RETURNS date LANGUAGE plpgsql IMMUTABLE SET search_path=public AS $$
DECLARE v_step integer; v_month date; v_last integer;
BEGIN
  IF p_anchor IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Agenda invalida'; END IF;
  IF p_frequency='weekly' THEN RETURN p_anchor+(p_offset*7); END IF;
  IF p_frequency='biweekly' THEN RETURN p_anchor+(p_offset*14); END IF;
  v_step:=CASE p_frequency WHEN 'monthly' THEN 1 WHEN 'bimonthly' THEN 2
            WHEN 'quarterly' THEN 3 WHEN 'semiannual' THEN 6 WHEN 'yearly' THEN 12 ELSE NULL END;
  IF v_step IS NULL THEN RAISE EXCEPTION 'Periodicidade invalida'; END IF;
  v_month:=(date_trunc('month',p_anchor)::date+(v_step*p_offset)*interval '1 month')::date;
  v_last:=extract(day FROM (v_month+interval '1 month'-interval '1 day'))::integer;
  RETURN v_month+(least(extract(day FROM p_anchor)::integer,v_last)-1);
END;
$$;
REVOKE ALL ON FUNCTION public.axora_due_at(date,text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_due_at(date,text,integer) TO service_role;

-- Geração preserva revisões e cancelamentos, sem reabrir uma ocorrência.
CREATE OR REPLACE FUNCTION public.axora_ensure_provisions(
  p_workspace_id uuid,p_through date DEFAULT NULL
) RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
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
      coalesce(rev.planned_value,r.planned_value) amount,
      public.axora_due_at(coalesce(rev.anchor_due_date,r.start_due_date),r.frequency,
                          gs.seq-coalesce(rev.effective_sequence,1)) due_date
    FROM public.finance_provision_rules r
    CROSS JOIN LATERAL generate_series(
      1,least(5000,greatest(1,ceil((v_until-r.start_due_date)::numeric/7)::integer+3))
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
  WHERE s.due_date<=v_until
    AND (s.recurrence<>'once' OR s.seq=1)
    AND (s.recurrence<>'until_date' OR
         ((s.installment_count IS NOT NULL AND s.seq<=s.installment_count) OR
          (s.installment_count IS NULL AND s.due_date<=s.end_date)))
    AND (s.recurrence<>'installments' OR s.seq<=s.installment_count)
  ON CONFLICT(rule_id,sequence_no) DO NOTHING;
  GET DIAGNOSTICS v_added=ROW_COUNT;
  RETURN v_added;
END;
$$;

-- Liquidação considera o conteúdo efetivo do vencimento, inclusive edições individuais.
CREATE OR REPLACE FUNCTION public.axora_pay_provision(
  p_workspace_id uuid,p_occurrence_id bigint,p_payment_date date,p_amount numeric
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE o record; v_movement_id bigint;
BEGIN
  IF p_payment_date IS NULL OR p_amount IS NULL OR p_amount<=0 OR p_amount>999999999999.99 THEN
    RAISE EXCEPTION 'Pagamento inválido';
  END IF;
  SELECT i.id,i.status,
         coalesce(i.description_override,r.description) description,
         coalesce(i.category_override,r.category) category,
         coalesce(i.value_mode_override,r.value_mode) value_mode
    INTO o
  FROM public.finance_provision_occurrences i
  JOIN public.finance_provision_rules r ON r.id=i.rule_id AND r.workspace_id=i.workspace_id
  WHERE i.id=p_occurrence_id AND i.workspace_id=p_workspace_id FOR UPDATE OF i;
  IF NOT FOUND THEN RAISE EXCEPTION 'Provisão não encontrada'; END IF;
  IF o.status<>'open' THEN RAISE EXCEPTION 'Provisão não está em aberto'; END IF;
  INSERT INTO public.finance_movements(
    movement_date,description,value,category,competence,classification,
    allocation_value,fixed_variable,provision_occurrence_id,workspace_id
  ) VALUES (
    p_payment_date,o.description,p_amount,o.category,to_char(p_payment_date,'MM/YYYY'),
    'SAÍDA',0,CASE WHEN o.value_mode='fixed' THEN 'FIXO' ELSE 'VARIÁVEL' END,
    p_occurrence_id,p_workspace_id
  ) RETURNING id INTO v_movement_id;
  UPDATE public.finance_provision_occurrences
    SET status='paid',payment_date=p_payment_date,paid_value=p_amount
  WHERE id=p_occurrence_id AND workspace_id=p_workspace_id;
  RETURN jsonb_build_object('occurrence_id',p_occurrence_id,'movement_id',v_movement_id,'status','paid');
END;
$$;

-- Edição atomica com escolha explícita do escopo. Pagas/canceladas intocáveis.
CREATE OR REPLACE FUNCTION public.axora_edit_provision(
  p_workspace_id uuid,p_occurrence_id bigint,p_scope text,
  p_due_date date,p_description text,p_category text,p_responsible text,
  p_planned_value numeric,p_value_mode text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE o record; r record; v_changed integer; v_trim_description text:=btrim(p_description);
        v_trim_category text:=btrim(p_category);v_trim_responsible text:=btrim(p_responsible);
BEGIN
  IF p_scope IS NULL OR p_scope NOT IN ('single','future') OR p_due_date IS NULL OR
     p_description IS NULL OR p_category IS NULL OR p_responsible IS NULL OR
     p_planned_value IS NULL OR p_value_mode IS NULL OR
     length(v_trim_description) NOT BETWEEN 1 AND 240 OR
     length(v_trim_category) NOT BETWEEN 1 AND 120 OR
     length(v_trim_responsible) NOT BETWEEN 1 AND 120 OR
     p_planned_value IS NULL OR p_planned_value<=0 OR p_planned_value>999999999999.99 OR
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
$$;

-- Exclusão lógica: não apaga o histórico e não permite geração futura da série.
CREATE OR REPLACE FUNCTION public.axora_cancel_provision(
  p_workspace_id uuid,p_occurrence_id bigint,p_scope text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE o record; r record; v_changed integer;
BEGIN
  IF p_scope IS NULL OR p_scope NOT IN ('single','future') THEN RAISE EXCEPTION 'Escopo inválido'; END IF;
  SELECT x.* INTO r FROM public.finance_provision_rules x
  WHERE x.id=(SELECT i.rule_id FROM public.finance_provision_occurrences i
              WHERE i.id=p_occurrence_id AND i.workspace_id=p_workspace_id)
    AND x.workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Provisão não encontrada'; END IF;
  SELECT i.* INTO o FROM public.finance_provision_occurrences i
  WHERE i.id=p_occurrence_id AND i.workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Provisão não encontrada'; END IF;
  IF o.status<>'open' THEN RAISE EXCEPTION 'Somente provisões em aberto podem ser excluídas'; END IF;
  IF p_scope='future' THEN
    UPDATE public.finance_provision_rules SET
      stop_before_sequence=least(coalesce(stop_before_sequence,o.sequence_no),o.sequence_no)
    WHERE id=r.id AND workspace_id=p_workspace_id;
    UPDATE public.finance_provision_occurrences SET status='cancelled',cancelled_at=now()
    WHERE rule_id=r.id AND workspace_id=p_workspace_id AND sequence_no>=o.sequence_no
      AND status='open';
  ELSE
    UPDATE public.finance_provision_occurrences SET status='cancelled',cancelled_at=now()
    WHERE id=p_occurrence_id AND workspace_id=p_workspace_id AND status='open';
  END IF;
  GET DIAGNOSTICS v_changed=ROW_COUNT;
  RETURN jsonb_build_object('cancelled',v_changed,'scope',p_scope,'occurrence_id',p_occurrence_id);
END;
$$;

REVOKE ALL ON FUNCTION public.axora_edit_provision(uuid,bigint,text,date,text,text,text,numeric,text)
  FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.axora_cancel_provision(uuid,bigint,text)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_edit_provision(uuid,bigint,text,date,text,text,text,numeric,text)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.axora_cancel_provision(uuid,bigint,text) TO service_role;

COMMIT;
NOTIFY pgrst,'reload schema';
