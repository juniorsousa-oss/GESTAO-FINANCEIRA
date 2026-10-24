-- AXORA: meios de pagamento por serie de provisoes; aditivo e reversivel via backup.
-- Nao altera valores, quitações, saldos, movimentos ou dados bancarios.
ALTER TABLE public.finance_provision_rules
  ADD COLUMN IF NOT EXISTS payment_method text NOT NULL DEFAULT 'none',
  ADD COLUMN IF NOT EXISTS pix_kind text,
  ADD COLUMN IF NOT EXISTS pix_value text,
  ADD COLUMN IF NOT EXISTS pix_receiver_name text,
  ADD COLUMN IF NOT EXISTS pix_receiver_city text;

-- Preservar atalhos ja cadastrados na modalidade Link.
UPDATE public.finance_provision_rules
SET payment_method='link'
WHERE payment_url IS NOT NULL AND payment_method='none';

ALTER TABLE public.finance_provision_rules
  ADD CONSTRAINT axora_provision_payment_method_check
  CHECK (payment_method IN ('none','link','pix')),
  ADD CONSTRAINT axora_provision_payment_details_check
  CHECK (
    (payment_method='none' AND payment_url IS NULL
       AND pix_kind IS NULL AND pix_value IS NULL
       AND pix_receiver_name IS NULL AND pix_receiver_city IS NULL)
    OR (payment_method='link' AND payment_url IS NOT NULL
       AND pix_kind IS NULL AND pix_value IS NULL
       AND pix_receiver_name IS NULL AND pix_receiver_city IS NULL)
    OR (payment_method='pix' AND payment_url IS NULL
       AND pix_kind IN ('key','brcode') AND pix_value IS NOT NULL
       AND length(pix_value) BETWEEN 3 AND 1200
       AND ((pix_kind='key'
             AND length(pix_receiver_name) BETWEEN 2 AND 25
             AND length(pix_receiver_city) BETWEEN 2 AND 15)
            OR (pix_kind='brcode'
                AND pix_receiver_name IS NULL AND pix_receiver_city IS NULL)))
  );

-- Cadastro: gravacao atomica do metodo com a regra, mantendo retrocompatibilidade.
CREATE OR REPLACE FUNCTION public.axora_create_provision_with_method(
 p_workspace_id uuid,
 p_description text,p_category text,p_responsible text,
 p_start_due_date date,p_planned_value numeric,p_value_mode text,
 p_recurrence text,p_frequency text,p_end_date date,p_installment_count integer,
 p_payment_method text,p_payment_url text,p_pix_kind text,p_pix_value text,
 p_pix_receiver_name text,p_pix_receiver_city text
) RETURNS bigint LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_id bigint;
BEGIN
 v_id:=public.axora_create_provision(
   p_workspace_id,p_description,p_category,p_responsible,p_start_due_date,p_planned_value,
   p_value_mode,p_recurrence,p_frequency,p_end_date,p_installment_count);
 UPDATE public.finance_provision_rules
 SET payment_method=p_payment_method,
     payment_url=p_payment_url,
     pix_kind=p_pix_kind,
     pix_value=p_pix_value,
     pix_receiver_name=p_pix_receiver_name,
     pix_receiver_city=p_pix_receiver_city
 WHERE id=v_id AND workspace_id=p_workspace_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'Provisão não localizada após cadastro'; END IF;
 RETURN v_id;
END;
$$;

-- A forma de pagamento e propriedade da serie: editar um vencimento pode
-- trocar o metodo para todos, mas nao mexe nos valores dos pagamentos passados.
CREATE OR REPLACE FUNCTION public.axora_edit_provision_with_method(
 p_workspace_id uuid,p_occurrence_id bigint,p_scope text,
 p_due_date date,p_description text,p_category text,p_responsible text,
 p_planned_value numeric,p_value_mode text,
 p_payment_method text,p_payment_url text,p_pix_kind text,p_pix_value text,
 p_pix_receiver_name text,p_pix_receiver_city text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_out jsonb;
BEGIN
 v_out:=public.axora_edit_provision(
    p_workspace_id,p_occurrence_id,p_scope,p_due_date,p_description,p_category,
    p_responsible,p_planned_value,p_value_mode);
 UPDATE public.finance_provision_rules
 SET payment_method=p_payment_method,
     payment_url=p_payment_url,
     pix_kind=p_pix_kind,
     pix_value=p_pix_value,
     pix_receiver_name=p_pix_receiver_name,
     pix_receiver_city=p_pix_receiver_city
 WHERE workspace_id=p_workspace_id AND id=(
   SELECT rule_id FROM public.finance_provision_occurrences
   WHERE id=p_occurrence_id AND workspace_id=p_workspace_id);
 IF NOT FOUND THEN RAISE EXCEPTION 'Série não localizada após edição'; END IF;
 RETURN v_out || jsonb_build_object('payment_method_updated',true);
END;
$$;

REVOKE ALL ON FUNCTION public.axora_create_provision_with_method(
 uuid,text,text,text,date,numeric,text,text,text,date,integer,text,text,text,text,text,text
) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.axora_edit_provision_with_method(
 uuid,bigint,text,date,text,text,text,numeric,text,text,text,text,text,text,text
) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_create_provision_with_method(
 uuid,text,text,text,date,numeric,text,text,text,date,integer,text,text,text,text,text,text
) TO service_role;
GRANT EXECUTE ON FUNCTION public.axora_edit_provision_with_method(
 uuid,bigint,text,date,text,text,text,numeric,text,text,text,text,text
) TO service_role;
NOTIFY pgrst,'reload schema';
