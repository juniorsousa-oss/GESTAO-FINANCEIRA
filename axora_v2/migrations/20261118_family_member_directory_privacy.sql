-- AXORA BETA — diretório de familiares, independente de saldos e registros.
-- Reutiliza a ACL e a auditoria existente; nenhuma pessoa recebe permissão por padrão.
-- Apenas a rota autorizada do principal pode configurar o tipo perfil.
BEGIN;
ALTER TABLE axora_beta.finance_family_visibility
  DROP CONSTRAINT finance_family_visibility_resource_type_check;
ALTER TABLE axora_beta.finance_family_visibility
  ADD CONSTRAINT finance_family_visibility_resource_type_check
    CHECK (resource_type IN ('registro','provisao','conta','transacao','perfil'));
CREATE OR REPLACE FUNCTION axora_beta.axora_family_set_visibility(
  p_workspace_id uuid,p_actor_id bigint,p_resource_type text,
  p_resource_id bigint,p_label text,p_viewers bigint[])
RETURNS jsonb LANGUAGE plpgsql SET search_path TO 'axora_beta', 'public' AS $$
DECLARE v_old text; v_tag bigint; v_owner bigint; v_creator bigint;
BEGIN
  PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
  SELECT created_by INTO v_owner FROM axora_beta.finance_workspaces WHERE id=p_workspace_id;
  IF p_label NOT IN ('privado','casal','familia','selecionados')
     OR p_resource_id IS NULL OR p_resource_id<=0 OR
     p_resource_type NOT IN ('registro','provisao','conta','transacao','perfil')
  THEN RAISE EXCEPTION 'Visibilidade inválida'; END IF;
  IF (p_resource_type='registro' AND NOT EXISTS(
       SELECT 1 FROM axora_beta.finance_movements WHERE id=p_resource_id AND workspace_id=p_workspace_id))
     OR (p_resource_type='provisao' AND NOT EXISTS(
       SELECT 1 FROM axora_beta.finance_provision_rules WHERE id=p_resource_id AND workspace_id=p_workspace_id))
     OR (p_resource_type='conta' AND NOT EXISTS(
       SELECT 1 FROM axora_beta.finance_bank_accounts WHERE id=p_resource_id AND workspace_id=p_workspace_id))
     OR (p_resource_type='transacao' AND NOT EXISTS(
       SELECT 1 FROM axora_beta.finance_bank_transactions WHERE id=p_resource_id AND workspace_id=p_workspace_id))
     OR (p_resource_type='perfil' AND NOT EXISTS(
       SELECT 1 FROM axora_beta.finance_family_profiles
       WHERE id=p_resource_id AND workspace_id=p_workspace_id AND active))
  THEN RAISE EXCEPTION 'Recurso não pertence ao espaço'; END IF;
  IF p_label='selecionados' AND (p_viewers IS NULL OR cardinality(p_viewers)=0) THEN
    RAISE EXCEPTION 'Selecione ao menos um participante'; END IF;
  IF p_label<>'selecionados' AND coalesce(cardinality(p_viewers),0)>0 THEN
    RAISE EXCEPTION 'Seleção incompatível com rótulo'; END IF;
  IF EXISTS (SELECT 1 FROM unnest(coalesce(p_viewers,'{}'::bigint[])) AS v(user_id)
    WHERE NOT EXISTS (SELECT 1 FROM axora_beta.finance_family_profiles f
      WHERE f.workspace_id=p_workspace_id AND f.linked_user_id=v.user_id AND f.active))
  THEN RAISE EXCEPTION 'Permissão atribuída fora da família'; END IF;
  SELECT id,label,creator_user_id INTO v_tag,v_old,v_creator
    FROM axora_beta.finance_family_visibility
    WHERE workspace_id=p_workspace_id AND resource_type=p_resource_type
       AND resource_id=p_resource_id FOR UPDATE;
  IF p_actor_id<>v_owner AND (v_tag IS NULL OR p_actor_id<>v_creator) THEN
    RAISE EXCEPTION 'Somente titular ou criador pode alterar rótulo'; END IF;
  INSERT INTO axora_beta.finance_family_visibility(
    workspace_id,resource_type,resource_id,creator_user_id,label)
  VALUES(p_workspace_id,p_resource_type,p_resource_id,p_actor_id,p_label)
  ON CONFLICT (workspace_id,resource_type,resource_id)
  DO UPDATE SET label=EXCLUDED.label,changed_at=now()
  RETURNING id INTO v_tag;
  DELETE FROM axora_beta.finance_family_visibility_grants
    WHERE visibility_id=v_tag AND workspace_id=p_workspace_id;
  INSERT INTO axora_beta.finance_family_visibility_grants(visibility_id,workspace_id,user_id)
    SELECT v_tag,p_workspace_id,uid FROM unnest(coalesce(p_viewers,'{}'::bigint[])) AS uid;
  INSERT INTO axora_beta.finance_family_visibility_audit(
    workspace_id,visibility_id,actor_user_id,prior_label,next_label)
  VALUES(p_workspace_id,v_tag,p_actor_id,v_old,p_label);
  RETURN jsonb_build_object('ok',true,'label',p_label);
END;
$$;
-- Continua exclusiva da API privada usando credenciais server-side.
REVOKE ALL ON FUNCTION axora_beta.axora_family_set_visibility(uuid,bigint,text,bigint,text,bigint[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_family_set_visibility(uuid,bigint,text,bigint,text,bigint[]) TO service_role;
COMMIT;
