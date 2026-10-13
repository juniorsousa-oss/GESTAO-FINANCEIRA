-- AXORA 2.0: segmentação financeira real, sem reaproveitar Excel.
-- IMPORTANTE: aplicar coordenado com a versão nova do backend.
-- Todos os dados legados foram arquivados; não altera finance_users nem finance_brand_assets.
BEGIN;

ALTER TABLE public.finance_movements ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT;
ALTER TABLE public.finance_movements ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.finance_forecasts ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT;
ALTER TABLE public.finance_forecasts ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.finance_accounts ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT;
ALTER TABLE public.finance_accounts ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.finance_debts ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT;
ALTER TABLE public.finance_debts ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.finance_settings ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT;
ALTER TABLE public.finance_settings ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.finance_accounts DROP CONSTRAINT IF EXISTS finance_accounts_name_key;
ALTER TABLE public.finance_settings DROP CONSTRAINT IF EXISTS finance_settings_key_key;
CREATE UNIQUE INDEX IF NOT EXISTS finance_accounts_workspace_name ON public.finance_accounts(workspace_id,name);
CREATE UNIQUE INDEX IF NOT EXISTS finance_settings_workspace_key ON public.finance_settings(workspace_id,key);

ALTER TABLE public.finance_provision_rules ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT;
ALTER TABLE public.finance_provision_occurrences ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT;
ALTER TABLE public.finance_provision_rules ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.finance_provision_occurrences ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.finance_provision_rules ADD CONSTRAINT axora_rule_workspace_unique UNIQUE(id,workspace_id);
ALTER TABLE public.finance_provision_occurrences ADD CONSTRAINT axora_occurrence_workspace_fk
  FOREIGN KEY(rule_id,workspace_id) REFERENCES public.finance_provision_rules(id,workspace_id);
CREATE INDEX IF NOT EXISTS axora_occurrence_workspace_status_due
  ON public.finance_provision_occurrences(workspace_id,status,due_date);

CREATE OR REPLACE FUNCTION public.axora_user_workspace(p_user_id bigint)
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE w uuid;
BEGIN
  IF NOT EXISTS(SELECT 1 FROM public.finance_users WHERE id=p_user_id AND is_active) THEN
    RAISE EXCEPTION 'Usuario inativo';
  END IF;
  PERFORM pg_advisory_xact_lock(p_user_id);
  SELECT workspace_id INTO w FROM public.finance_workspace_members
    WHERE user_id=p_user_id ORDER BY added_at LIMIT 1;
  IF w IS NULL THEN
    INSERT INTO public.finance_workspaces(name,created_by)
      VALUES('Espaço financeiro pessoal',p_user_id) RETURNING id INTO w;
    INSERT INTO public.finance_workspace_members(workspace_id,user_id,role)
      VALUES(w,p_user_id,'owner');
  END IF;
  RETURN w;
END;
$$;
REVOKE ALL ON FUNCTION public.axora_user_workspace(bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_user_workspace(bigint) TO service_role;

CREATE OR REPLACE FUNCTION public.axora_ensure_provisions(p_workspace_id uuid,p_through date DEFAULT NULL)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_added integer; v_until date := coalesce(p_through, current_date+interval '18 months');
BEGIN
  IF v_until > current_date + interval '30 months' THEN
    RAISE EXCEPTION 'Janela de geração excede 30 meses';
  END IF;
  WITH calculated AS (
    SELECT r.id,r.workspace_id,gs.i+1 AS seq,
      CASE WHEN r.frequency='weekly' THEN r.start_due_date + (gs.i*7)
           WHEN r.frequency='biweekly' THEN r.start_due_date + (gs.i*14)
           ELSE (
             date_trunc('month',r.start_due_date)::date
             + (gs.i * CASE r.frequency WHEN 'monthly' THEN 1
                   WHEN 'bimonthly' THEN 2 WHEN 'quarterly' THEN 3
                   WHEN 'semiannual' THEN 6 ELSE 12 END) * interval '1 month'
             + (
                least(extract(day FROM r.start_due_date)::int,
                extract(day FROM (
                   date_trunc('month',r.start_due_date)::date
                   + ((gs.i * CASE r.frequency WHEN 'monthly' THEN 1
                      WHEN 'bimonthly' THEN 2 WHEN 'quarterly' THEN 3
                      WHEN 'semiannual' THEN 6 ELSE 12 END) + 1) * interval '1 month'
                   - interval '1 day'))::int
                ) - 1
               ) * interval '1 day'
           )::date END AS due_date,
      r.planned_value, r.recurrence, r.end_date, r.installment_count
    FROM public.finance_provision_rules r
    CROSS JOIN LATERAL generate_series(
      0,
      least(10000,greatest(0,ceil((v_until-r.start_due_date)::numeric/7)::int + 1))
    ) AS gs(i)
    WHERE r.active AND r.workspace_id=p_workspace_id
  )
  INSERT INTO public.finance_provision_occurrences(rule_id,workspace_id,sequence_no,due_date,planned_value)
  SELECT id,workspace_id,seq,due_date,planned_value FROM calculated
  WHERE due_date <= v_until
    AND (recurrence <> 'once' OR seq=1)
    AND (recurrence <> 'until_date' OR due_date <= end_date)
    AND (recurrence <> 'installments' OR seq <= installment_count)
  ON CONFLICT (rule_id,sequence_no) DO NOTHING;
  GET DIAGNOSTICS v_added = ROW_COUNT;
  RETURN v_added;
END;
$$;


CREATE OR REPLACE FUNCTION public.axora_create_provision(
  p_workspace_id uuid,p_description text,p_category text,p_responsible text,
  p_start_due_date date,p_planned_value numeric,p_value_mode text,
  p_recurrence text,p_frequency text,p_end_date date DEFAULT NULL,
  p_installment_count integer DEFAULT NULL
) RETURNS bigint LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_id bigint;
BEGIN
  INSERT INTO public.finance_provision_rules(
    workspace_id,description,category,responsible,start_due_date,planned_value,
    value_mode,recurrence,frequency,end_date,installment_count
  ) VALUES (
    p_workspace_id,p_description,p_category,p_responsible,p_start_due_date,p_planned_value,
    p_value_mode,p_recurrence,p_frequency,p_end_date,p_installment_count
  ) RETURNING id INTO v_id;
  PERFORM public.axora_ensure_provisions(p_workspace_id);
  RETURN v_id;
END;
$$;


CREATE OR REPLACE FUNCTION public.axora_pay_provision(
  p_workspace_id uuid,p_occurrence_id bigint, p_payment_date date, p_amount numeric
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE o record; v_movement_id bigint;
BEGIN
  IF p_payment_date IS NULL OR p_amount IS NULL OR p_amount <= 0 OR p_amount > 1000000000000 THEN
    RAISE EXCEPTION 'Pagamento inválido';
  END IF;
  SELECT i.id,i.status,i.due_date,r.description,r.category,r.value_mode
    INTO o
  FROM public.finance_provision_occurrences i
  JOIN public.finance_provision_rules r ON r.id=i.rule_id
  WHERE i.id=p_occurrence_id AND i.workspace_id=p_workspace_id AND r.workspace_id=p_workspace_id FOR UPDATE OF i;
  IF NOT FOUND THEN RAISE EXCEPTION 'Provisão não encontrada'; END IF;
  IF o.status <> 'open' THEN RAISE EXCEPTION 'Provisão já quitada'; END IF;
  INSERT INTO public.finance_movements(
    movement_date,description,value,category,competence,classification,
    allocation_value,fixed_variable,provision_occurrence_id,workspace_id
  ) VALUES (
    p_payment_date,o.description,p_amount,o.category,
    to_char(p_payment_date,'MM/YYYY'),'SAÍDA',0,
    CASE WHEN o.value_mode='fixed' THEN 'FIXO' ELSE 'VARIÁVEL' END,
    p_occurrence_id,p_workspace_id
  ) RETURNING id INTO v_movement_id;
  UPDATE public.finance_provision_occurrences
    SET status='paid',payment_date=p_payment_date,paid_value=p_amount
    WHERE id=p_occurrence_id;
  RETURN jsonb_build_object('occurrence_id',p_occurrence_id,'movement_id',v_movement_id,'status','paid');
END;
$$;


-- Remove RPCs não segmentadas.
DROP FUNCTION IF EXISTS public.axora_create_provision(text,text,text,date,numeric,text,text,text,date,integer);
DROP FUNCTION IF EXISTS public.axora_ensure_provisions(date);
DROP FUNCTION IF EXISTS public.axora_pay_provision(bigint,date,numeric);
REVOKE ALL ON FUNCTION public.axora_create_provision(uuid,text,text,text,date,numeric,text,text,text,date,integer)
 FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.axora_ensure_provisions(uuid,date) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.axora_pay_provision(uuid,bigint,date,numeric) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_create_provision(uuid,text,text,text,date,numeric,text,text,text,date,integer)
 TO service_role;
GRANT EXECUTE ON FUNCTION public.axora_ensure_provisions(uuid,date) TO service_role;
GRANT EXECUTE ON FUNCTION public.axora_pay_provision(uuid,bigint,date,numeric) TO service_role;
COMMIT;
