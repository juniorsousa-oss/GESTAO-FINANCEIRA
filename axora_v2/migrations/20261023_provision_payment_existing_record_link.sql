-- AXORA: vincular um Registro já existente a uma Previsão, sem criar despesa duplicada.
-- Não altera os dados reais até o operador escolher e confirmar um candidato.
BEGIN;

CREATE TABLE IF NOT EXISTS public.finance_provision_record_links (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
  occurrence_id bigint NOT NULL REFERENCES public.finance_provision_occurrences(id) ON DELETE RESTRICT,
  movement_id bigint NOT NULL REFERENCES public.finance_movements(id) ON DELETE RESTRICT,
  actor_id bigint NOT NULL REFERENCES public.finance_users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id,occurrence_id),
  UNIQUE(workspace_id,movement_id)
);
ALTER TABLE public.finance_provision_record_links ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.finance_provision_record_links FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON TABLE public.finance_provision_record_links TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.finance_provision_record_links_id_seq TO service_role;

CREATE OR REPLACE FUNCTION public.axora_link_record_to_provision(
  p_workspace_id uuid,p_user_id bigint,p_occurrence_id bigint,p_movement_id bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
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
  SELECT * INTO o FROM public.finance_provision_occurrences
    WHERE id=p_occurrence_id AND workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND OR o.status<>'open' THEN
    RAISE EXCEPTION 'Previsão não está em aberto'; END IF;

  SELECT * INTO m FROM public.finance_movements
    WHERE id=p_movement_id AND workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND OR m.classification<>'SAÍDA' OR m.provision_occurrence_id IS NOT NULL
     OR m.movement_date IS NULL OR abs(m.value-o.planned_value)>0.01 THEN
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
$$;
REVOKE ALL ON FUNCTION public.axora_link_record_to_provision(uuid,bigint,bigint,bigint)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_link_record_to_provision(uuid,bigint,bigint,bigint)
  TO service_role;

COMMIT;
NOTIFY pgrst,'reload schema';
