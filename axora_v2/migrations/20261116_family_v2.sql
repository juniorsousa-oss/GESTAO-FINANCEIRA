-- AXORA FAMILIAR V2 — MIGRAÇÃO PARA SUPABASE BETA ISOLADO.
-- Não aplicar no Supabase de produção até homologar privacidade entre logins.
-- Idempotente quanto a tabelas; executar como migração única em banco novo.

BEGIN;

ALTER TABLE public.finance_movements
  ADD CONSTRAINT finance_movements_family_workspace_id_unique UNIQUE (id, workspace_id);

CREATE TABLE public.finance_family_profiles (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
  display_name text NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 1 AND 80),
  relationship text NOT NULL CHECK (relationship IN ('principal','conjuge','filho','outro')),
  linked_user_id bigint REFERENCES public.finance_users(id) ON DELETE RESTRICT,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id,id)
);
CREATE UNIQUE INDEX finance_family_one_principal ON public.finance_family_profiles(workspace_id) WHERE relationship='principal';
CREATE UNIQUE INDEX finance_family_one_login ON public.finance_family_profiles(linked_user_id) WHERE linked_user_id IS NOT NULL AND active;

CREATE TABLE public.finance_family_visibility (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
  resource_type text NOT NULL CHECK (resource_type IN ('registro','provisao','conta','transacao')),
  resource_id bigint NOT NULL CHECK(resource_id > 0),
  creator_user_id bigint NOT NULL REFERENCES public.finance_users(id) ON DELETE RESTRICT,
  label text NOT NULL DEFAULT 'privado' CHECK(label IN ('privado','casal','familia','selecionados')),
  changed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id,resource_type,resource_id),
  UNIQUE(id,workspace_id)
);
CREATE TABLE public.finance_family_visibility_grants(
  visibility_id bigint NOT NULL,
  workspace_id uuid NOT NULL,
  user_id bigint NOT NULL REFERENCES public.finance_users(id) ON DELETE RESTRICT,
  granted_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(visibility_id,user_id),
  FOREIGN KEY(visibility_id,workspace_id)
    REFERENCES public.finance_family_visibility(id,workspace_id) ON DELETE CASCADE
);
CREATE TABLE public.finance_family_cost_allocations(
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL,
  movement_id bigint NOT NULL,
  profile_id bigint NOT NULL,
  amount numeric(15,2) NOT NULL CHECK(amount >= 0),
  FOREIGN KEY(movement_id,workspace_id) REFERENCES public.finance_movements(id,workspace_id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,profile_id) REFERENCES public.finance_family_profiles(workspace_id,id) ON DELETE RESTRICT,
  UNIQUE(workspace_id,movement_id,profile_id)
);
CREATE TABLE public.finance_family_payment_allocations(
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL,
  movement_id bigint NOT NULL,
  payer_profile_id bigint NOT NULL,
  source_account_id bigint,
  amount numeric(15,2) NOT NULL CHECK(amount > 0),
  FOREIGN KEY(movement_id,workspace_id) REFERENCES public.finance_movements(id,workspace_id) ON DELETE RESTRICT,
  FOREIGN KEY(workspace_id,payer_profile_id) REFERENCES public.finance_family_profiles(workspace_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(source_account_id,workspace_id) REFERENCES public.finance_bank_accounts(id,workspace_id) ON DELETE RESTRICT,
  UNIQUE(workspace_id,movement_id,payer_profile_id)
);
CREATE TABLE public.finance_family_visibility_audit(
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
  visibility_id bigint NOT NULL,
  actor_user_id bigint NOT NULL REFERENCES public.finance_users(id) ON DELETE RESTRICT,
  prior_label text,
  next_label text NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(visibility_id,workspace_id) REFERENCES public.finance_family_visibility(id,workspace_id) ON DELETE RESTRICT
);

-- Cada conta principal existente recebe um perfil principal privado.
-- Nenhum registro antigo vira "casal" automaticamente.
INSERT INTO public.finance_family_profiles(workspace_id,display_name,relationship,linked_user_id)
  SELECT w.id,u.display_name,'principal',u.id
  FROM public.finance_workspaces w JOIN public.finance_users u ON u.id=w.created_by
  WHERE w.created_by IS NOT NULL AND w.is_active AND u.is_active
  AND EXISTS (SELECT 1 FROM public.finance_workspace_members m
              WHERE m.workspace_id=w.id AND m.user_id=w.created_by AND m.role='owner');

-- Helpers transacionais: o cliente nunca envia o workspace com autoridade.
CREATE FUNCTION public.axora_family_validate_actor(p_workspace_id uuid,p_actor_id bigint)
RETURNS void LANGUAGE plpgsql SET search_path TO 'public' AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM public.finance_family_profiles p
    JOIN public.finance_users u ON u.id=p.linked_user_id AND u.is_active
    WHERE p.workspace_id=p_workspace_id AND p.linked_user_id=p_actor_id AND p.active
  ) THEN RAISE EXCEPTION 'Perfil familiar sem acesso ao espaço'; END IF;
END;
$$;

CREATE FUNCTION public.axora_family_allocate(
  p_workspace_id uuid,p_movement_id bigint,p_costs jsonb,p_payments jsonb)
RETURNS void LANGUAGE plpgsql SET search_path TO 'public' AS $$
DECLARE
  v_amount numeric(15,2);
  v_class text;
  v_count int;
  v_item record;
BEGIN
  SELECT value,classification INTO v_amount,v_class FROM public.finance_movements
  WHERE id=p_movement_id AND workspace_id=p_workspace_id FOR UPDATE;
  IF NOT FOUND OR v_amount<=0 THEN RAISE EXCEPTION 'Registro inválido'; END IF;
  IF jsonb_typeof(p_costs)<>'array' THEN RAISE EXCEPTION 'Beneficiários inválidos'; END IF;
  v_count=jsonb_array_length(p_costs);
  IF v_count<1 OR v_count>50 THEN RAISE EXCEPTION 'Quantidade de beneficiários inválida'; END IF;
  IF EXISTS(
    SELECT 1 FROM jsonb_to_recordset(p_costs) AS c(profile_id bigint,amount numeric)
    WHERE c.amount IS NULL OR c.amount<0 OR c.amount<>round(c.amount,2) OR
      NOT EXISTS (SELECT 1 FROM public.finance_family_profiles f
        WHERE f.workspace_id=p_workspace_id AND f.id=c.profile_id AND f.active)
  ) THEN RAISE EXCEPTION 'Beneficiário fora da família'; END IF;
  IF EXISTS(SELECT 1 FROM (SELECT profile_id, count(*) n
      FROM jsonb_to_recordset(p_costs) AS c(profile_id bigint,amount numeric)
      GROUP BY profile_id HAVING count(*)>1) duplicate) THEN
    RAISE EXCEPTION 'Beneficiário duplicado'; END IF;
  IF (SELECT coalesce(sum(c.amount),0) FROM jsonb_to_recordset(p_costs)
      AS c(profile_id bigint,amount numeric))<>v_amount
  THEN RAISE EXCEPTION 'Beneficiários não totalizam o valor'; END IF;

  IF jsonb_typeof(p_payments)<>'array' THEN RAISE EXCEPTION 'Rateio de pagamento inválido'; END IF;
  IF v_class='SAÍDA' THEN
    IF jsonb_array_length(p_payments)<1 OR jsonb_array_length(p_payments)>50
    THEN RAISE EXCEPTION 'Informe quem pagou'; END IF;
    IF EXISTS(
      SELECT 1 FROM jsonb_to_recordset(p_payments) AS c(profile_id bigint,amount numeric,source_account_id bigint)
      WHERE c.amount IS NULL OR c.amount<=0 OR c.amount<>round(c.amount,2) OR
        NOT EXISTS (SELECT 1 FROM public.finance_family_profiles f
          WHERE f.workspace_id=p_workspace_id AND f.id=c.profile_id AND f.active)
        OR (c.source_account_id IS NOT NULL AND NOT EXISTS(
          SELECT 1 FROM public.finance_bank_accounts a
          WHERE a.id=c.source_account_id AND a.workspace_id=p_workspace_id))
    ) THEN RAISE EXCEPTION 'Pagador ou conta de origem inválida'; END IF;
    IF EXISTS(SELECT 1 FROM (SELECT profile_id,count(*) n
      FROM jsonb_to_recordset(p_payments) AS c(profile_id bigint,amount numeric)
      GROUP BY profile_id HAVING count(*)>1) duplicate) THEN
      RAISE EXCEPTION 'Pagador duplicado'; END IF;
    IF (SELECT coalesce(sum(c.amount),0) FROM jsonb_to_recordset(p_payments)
        AS c(profile_id bigint,amount numeric))<>v_amount
    THEN RAISE EXCEPTION 'Pagadores não totalizam o valor'; END IF;
  ELSIF v_class='ENTRADA' THEN
    IF jsonb_array_length(p_payments)<>0 THEN
      RAISE EXCEPTION 'Receita não deve ter pagador de despesa'; END IF;
  ELSE RAISE EXCEPTION 'Tipo financeiro inválido'; END IF;

  INSERT INTO public.finance_family_cost_allocations(workspace_id,movement_id,profile_id,amount)
    SELECT p_workspace_id,p_movement_id,profile_id,amount
    FROM jsonb_to_recordset(p_costs) AS c(profile_id bigint,amount numeric);
  INSERT INTO public.finance_family_payment_allocations(
      workspace_id,movement_id,payer_profile_id,source_account_id,amount)
    SELECT p_workspace_id,p_movement_id,profile_id,source_account_id,amount
    FROM jsonb_to_recordset(p_payments)
      AS c(profile_id bigint,amount numeric,source_account_id bigint);
END;
$$;

CREATE FUNCTION public.axora_family_record(
  p_workspace_id uuid,p_actor_id bigint,p_movement_date date,
  p_description text,p_value numeric,p_classification text,
  p_category text,p_label text,p_costs jsonb,p_payments jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path TO 'public' AS $$
DECLARE v_id bigint;
BEGIN
  PERFORM public.axora_family_validate_actor(p_workspace_id,p_actor_id);
  IF p_value IS NULL OR p_value<=0 OR p_value>999999999999.99 OR p_value<>round(p_value,2)
    OR p_movement_date IS NULL OR length(btrim(coalesce(p_description,''))) NOT BETWEEN 1 AND 240
    OR p_classification NOT IN ('SAÍDA','ENTRADA')
    OR p_label NOT IN ('privado','casal','familia','selecionados')
  THEN RAISE EXCEPTION 'Registro familiar inválido'; END IF;
  -- Concessões selecionadas devem ser aplicadas por RPC administrativa separada.
  IF p_label='selecionados' THEN RAISE EXCEPTION 'Informe acessos selecionados na administração'; END IF;
  INSERT INTO public.finance_movements(
    movement_date,description,value,category,competence,classification,
    allocation_value,fixed_variable,workspace_id)
  VALUES(p_movement_date,btrim(p_description),p_value,coalesce(nullif(btrim(p_category),''),'OUTROS'),
         to_char(p_movement_date,'MM/YYYY'),p_classification,0,'VARIÁVEL',p_workspace_id)
  RETURNING id INTO v_id;
  PERFORM public.axora_family_allocate(p_workspace_id,v_id,p_costs,p_payments);
  INSERT INTO public.finance_family_visibility(
    workspace_id,resource_type,resource_id,creator_user_id,label)
  VALUES(p_workspace_id,'registro',v_id,p_actor_id,p_label);
  RETURN jsonb_build_object('ok',true,'movement_id',v_id);
END;
$$;

CREATE FUNCTION public.axora_family_pay_provision(
  p_workspace_id uuid,p_actor_id bigint,p_occurrence_id bigint,
  p_payment_date date,p_amount numeric,p_label text,p_costs jsonb,p_payments jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path TO 'public' AS $$
DECLARE v_result jsonb; v_movement_id bigint;
BEGIN
  PERFORM public.axora_family_validate_actor(p_workspace_id,p_actor_id);
  IF p_label NOT IN ('privado','casal','familia') THEN
    RAISE EXCEPTION 'Visibilidade inválida'; END IF;
  -- Revalidar sob a transação SQL: mudanças de rótulo concorrentes não
  -- podem autorizar uma quitação pela chave privada do servidor.
  IF NOT EXISTS(SELECT 1 FROM public.finance_workspaces
    WHERE id=p_workspace_id AND created_by=p_actor_id)
    AND NOT EXISTS(
      SELECT 1 FROM public.finance_provision_occurrences o
      JOIN public.finance_family_visibility v ON v.workspace_id=o.workspace_id
        AND v.resource_type='provisao' AND v.resource_id=o.rule_id
      JOIN public.finance_family_profiles f ON f.workspace_id=o.workspace_id
        AND f.linked_user_id=p_actor_id AND f.active
      WHERE o.id=p_occurrence_id AND o.workspace_id=p_workspace_id AND
      (v.creator_user_id=p_actor_id OR
        (v.label='casal' AND f.relationship='conjuge') OR
        (v.label='familia' AND f.relationship IN ('conjuge','filho')) OR
        (v.label='selecionados' AND EXISTS(
          SELECT 1 FROM public.finance_family_visibility_grants g
          WHERE g.visibility_id=v.id AND g.workspace_id=v.workspace_id
            AND g.user_id=p_actor_id)))
    )
  THEN RAISE EXCEPTION 'Provisão não autorizada'; END IF;
  v_result := public.axora_pay_provision(p_workspace_id,p_occurrence_id,p_payment_date,p_amount);
  v_movement_id := (v_result->>'movement_id')::bigint;
  PERFORM public.axora_family_allocate(p_workspace_id,v_movement_id,p_costs,p_payments);
  INSERT INTO public.finance_family_visibility(
    workspace_id,resource_type,resource_id,creator_user_id,label)
  VALUES(p_workspace_id,'registro',v_movement_id,p_actor_id,p_label);
  RETURN v_result;
END;
$$;

CREATE FUNCTION public.axora_family_link_user(
  p_workspace_id uuid,p_actor_id bigint,p_profile_id bigint,p_user_id bigint)
RETURNS jsonb LANGUAGE plpgsql SET search_path TO 'public' AS $
DECLARE v_owner bigint; v_count integer;
BEGIN
  PERFORM public.axora_family_validate_actor(p_workspace_id,p_actor_id);
  SELECT created_by INTO v_owner FROM public.finance_workspaces
    WHERE id=p_workspace_id FOR UPDATE;
  IF v_owner IS DISTINCT FROM p_actor_id OR p_user_id=p_actor_id
  THEN RAISE EXCEPTION 'Somente o proprietário pode conceder login'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.finance_users
    WHERE id=p_user_id AND is_active AND NOT is_admin)
  THEN RAISE EXCEPTION 'Usuário não elegível'; END IF;
  IF EXISTS (SELECT 1 FROM public.finance_workspace_members
    WHERE user_id=p_user_id AND workspace_id<>p_workspace_id)
  THEN RAISE EXCEPTION 'Usuário possui outro espaço financeiro'; END IF;
  IF EXISTS(SELECT 1 FROM public.finance_family_profiles
    WHERE linked_user_id=p_user_id AND active)
  THEN RAISE EXCEPTION 'Usuário já está vinculado'; END IF;
  UPDATE public.finance_family_profiles SET linked_user_id=p_user_id
    WHERE id=p_profile_id AND workspace_id=p_workspace_id AND linked_user_id IS NULL
      AND active AND relationship<>'principal';
  GET DIAGNOSTICS v_count=ROW_COUNT;
  IF v_count<>1 THEN RAISE EXCEPTION 'Perfil inexistente ou já vinculado'; END IF;
  INSERT INTO public.finance_workspace_members(workspace_id,user_id,role)
    SELECT p_workspace_id,p_user_id,'viewer'
    WHERE NOT EXISTS(SELECT 1 FROM public.finance_workspace_members
      WHERE workspace_id=p_workspace_id AND user_id=p_user_id);
  RETURN jsonb_build_object('ok',true,'linked_user_id',p_user_id);
END;
$;

CREATE FUNCTION public.axora_family_set_visibility(
  p_workspace_id uuid,p_actor_id bigint,p_resource_type text,
  p_resource_id bigint,p_label text,p_viewers bigint[])
RETURNS jsonb LANGUAGE plpgsql SET search_path TO 'public' AS $$
DECLARE v_old text; v_tag bigint; v_owner bigint; v_creator bigint;
BEGIN
  PERFORM public.axora_family_validate_actor(p_workspace_id,p_actor_id);
  SELECT created_by INTO v_owner FROM public.finance_workspaces WHERE id=p_workspace_id;
  IF p_label NOT IN ('privado','casal','familia','selecionados')
     OR p_resource_id IS NULL OR p_resource_id<=0 OR
     p_resource_type NOT IN ('registro','provisao','conta','transacao')
  THEN RAISE EXCEPTION 'Visibilidade inválida'; END IF;
  IF (p_resource_type='registro' AND NOT EXISTS(
       SELECT 1 FROM public.finance_movements WHERE id=p_resource_id AND workspace_id=p_workspace_id))
     OR (p_resource_type='provisao' AND NOT EXISTS(
       SELECT 1 FROM public.finance_provision_rules WHERE id=p_resource_id AND workspace_id=p_workspace_id))
     OR (p_resource_type='conta' AND NOT EXISTS(
       SELECT 1 FROM public.finance_bank_accounts WHERE id=p_resource_id AND workspace_id=p_workspace_id))
     OR (p_resource_type='transacao' AND NOT EXISTS(
       SELECT 1 FROM public.finance_bank_transactions WHERE id=p_resource_id AND workspace_id=p_workspace_id))
  THEN RAISE EXCEPTION 'Recurso não pertence ao espaço'; END IF;
  IF p_label='selecionados' AND (p_viewers IS NULL OR cardinality(p_viewers)=0) THEN
    RAISE EXCEPTION 'Selecione ao menos um participante'; END IF;
  IF p_label<>'selecionados' AND coalesce(cardinality(p_viewers),0)>0 THEN
    RAISE EXCEPTION 'Seleção incompatível com rótulo'; END IF;
  IF EXISTS (SELECT 1 FROM unnest(coalesce(p_viewers,'{}'::bigint[])) AS v(user_id)
    WHERE NOT EXISTS (SELECT 1 FROM public.finance_family_profiles f
      WHERE f.workspace_id=p_workspace_id AND f.linked_user_id=v.user_id AND f.active))
  THEN RAISE EXCEPTION 'Permissão atribuída fora da família'; END IF;
  SELECT id,label,creator_user_id INTO v_tag,v_old,v_creator
    FROM public.finance_family_visibility
    WHERE workspace_id=p_workspace_id AND resource_type=p_resource_type
       AND resource_id=p_resource_id FOR UPDATE;
  IF p_actor_id<>v_owner AND (v_tag IS NULL OR p_actor_id<>v_creator) THEN
    RAISE EXCEPTION 'Somente titular ou criador pode alterar rótulo'; END IF;
  INSERT INTO public.finance_family_visibility(
    workspace_id,resource_type,resource_id,creator_user_id,label)
  VALUES(p_workspace_id,p_resource_type,p_resource_id,p_actor_id,p_label)
  ON CONFLICT (workspace_id,resource_type,resource_id)
  DO UPDATE SET label=EXCLUDED.label,changed_at=now()
  RETURNING id INTO v_tag;
  DELETE FROM public.finance_family_visibility_grants
    WHERE visibility_id=v_tag AND workspace_id=p_workspace_id;
  INSERT INTO public.finance_family_visibility_grants(visibility_id,workspace_id,user_id)
    SELECT v_tag,p_workspace_id,uid FROM unnest(coalesce(p_viewers,'{}'::bigint[])) AS uid;
  INSERT INTO public.finance_family_visibility_audit(
    workspace_id,visibility_id,actor_user_id,prior_label,next_label)
  VALUES(p_workspace_id,v_tag,p_actor_id,v_old,p_label);
  RETURN jsonb_build_object('ok',true,'label',p_label);
END;
$$;

-- RLS: as seis tabelas novas são usadas apenas por API privada do servidor.
ALTER TABLE public.finance_family_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_family_visibility ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_family_visibility_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_family_cost_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_family_payment_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_family_visibility_audit ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.finance_family_profiles, public.finance_family_visibility,
  public.finance_family_visibility_grants, public.finance_family_cost_allocations,
  public.finance_family_payment_allocations, public.finance_family_visibility_audit
  FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.finance_family_profiles,
  public.finance_family_visibility, public.finance_family_visibility_grants,
  public.finance_family_cost_allocations, public.finance_family_payment_allocations,
  public.finance_family_visibility_audit TO service_role;

REVOKE ALL ON FUNCTION
  public.axora_family_validate_actor(uuid,bigint),
  public.axora_family_allocate(uuid,bigint,jsonb,jsonb),
  public.axora_family_record(uuid,bigint,date,text,numeric,text,text,text,jsonb,jsonb),
  public.axora_family_pay_provision(uuid,bigint,bigint,date,numeric,text,jsonb,jsonb),
  public.axora_family_set_visibility(uuid,bigint,text,bigint,text,bigint[]),
  public.axora_family_link_user(uuid,bigint,bigint,bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  public.axora_family_validate_actor(uuid,bigint),
  public.axora_family_allocate(uuid,bigint,jsonb,jsonb),
  public.axora_family_record(uuid,bigint,date,text,numeric,text,text,text,jsonb,jsonb),
  public.axora_family_pay_provision(uuid,bigint,bigint,date,numeric,text,jsonb,jsonb),
  public.axora_family_set_visibility(uuid,bigint,text,bigint,text,bigint[]),
  public.axora_family_link_user(uuid,bigint,bigint,bigint)
  TO service_role;

COMMIT;
