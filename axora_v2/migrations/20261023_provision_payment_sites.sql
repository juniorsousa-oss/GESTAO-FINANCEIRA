-- AXORA: endereço oficial para consultar/pagar cada compromisso (um link por série).
-- Migração aditiva: mantém valores, datas, ocorrências e pagamentos existentes.
BEGIN;

ALTER TABLE public.finance_provision_rules
  ADD COLUMN IF NOT EXISTS payment_url text;

ALTER TABLE public.finance_provision_rules
  ADD CONSTRAINT axora_provision_payment_url_format CHECK (
    payment_url IS NULL OR (
      length(payment_url) BETWEEN 12 AND 2048
      AND payment_url ~* '^https://[a-z0-9][a-z0-9.-]*\\.[a-z]{2,}(:443)?([/?#][^[:space:]]*)?$'
      AND payment_url !~ '[[:space:]@\\]'
    )
  );

-- Cadastro e gravação do link são uma única operação; sem cadastro parcial.
CREATE OR REPLACE FUNCTION public.axora_create_provision_with_link(
  p_workspace_id uuid,
  p_description text,p_category text,p_responsible text,
  p_start_due_date date,p_planned_value numeric,p_value_mode text,
  p_recurrence text,p_frequency text,p_end_date date,
  p_installment_count integer,p_payment_url text
) RETURNS bigint LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_id bigint;
BEGIN
  v_id:=public.axora_create_provision(
    p_workspace_id,p_description,p_category,p_responsible,p_start_due_date,
    p_planned_value,p_value_mode,p_recurrence,p_frequency,p_end_date,p_installment_count
  );
  UPDATE public.finance_provision_rules
  SET payment_url=nullif(btrim(p_payment_url),'')
  WHERE id=v_id AND workspace_id=p_workspace_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Compromisso não localizado após cadastro'; END IF;
  RETURN v_id;
END;
$$;

-- O link é uma propriedade da série, independente do escopo dos outros campos.
-- A edição original preserva suas regras para parcelas pagas e vencimentos.
CREATE OR REPLACE FUNCTION public.axora_edit_provision_with_link(
  p_workspace_id uuid,p_occurrence_id bigint,p_scope text,
  p_due_date date,p_description text,p_category text,p_responsible text,
  p_planned_value numeric,p_value_mode text,p_payment_url text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_result jsonb;
BEGIN
  v_result:=public.axora_edit_provision(
    p_workspace_id,p_occurrence_id,p_scope,p_due_date,p_description,p_category,
    p_responsible,p_planned_value,p_value_mode
  );
  UPDATE public.finance_provision_rules
  SET payment_url=nullif(btrim(p_payment_url),'')
  WHERE workspace_id=p_workspace_id AND id=(
    SELECT rule_id FROM public.finance_provision_occurrences
    WHERE id=p_occurrence_id AND workspace_id=p_workspace_id
  );
  IF NOT FOUND THEN RAISE EXCEPTION 'Série não localizada após edição'; END IF;
  RETURN v_result || jsonb_build_object('payment_url_updated',true);
END;
$$;

REVOKE ALL ON FUNCTION public.axora_create_provision_with_link(
  uuid,text,text,text,date,numeric,text,text,text,date,integer,text
) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.axora_edit_provision_with_link(
  uuid,bigint,text,date,text,text,text,numeric,text,text
) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_create_provision_with_link(
  uuid,text,text,text,date,numeric,text,text,text,date,integer,text
) TO service_role;
GRANT EXECUTE ON FUNCTION public.axora_edit_provision_with_link(
  uuid,bigint,text,date,text,text,text,numeric,text,text
) TO service_role;

COMMIT;
NOTIFY pgrst,'reload schema';
