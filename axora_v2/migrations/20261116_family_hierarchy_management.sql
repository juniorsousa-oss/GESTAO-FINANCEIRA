-- AXORA FAMÍLIA | Cadastro transacional de subusuários e gestão de vínculos
-- Migração aplicada em axora_beta no Supabase existente em 2026-11-16.
-- Para cada instância cliente, adaptar o schema com revisão dos controles.
-- Não execute diretamente no schema public / produção sem homologação.
BEGIN;
CREATE OR REPLACE FUNCTION axora_beta.axora_family_change_relationship(p_workspace_id uuid, p_actor_id bigint, p_profile_id bigint, p_relationship text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'axora_beta', 'public'
AS $function$
DECLARE v_owner bigint; v_count bigint;
BEGIN
  PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
  SELECT created_by INTO v_owner FROM axora_beta.finance_workspaces
    WHERE id=p_workspace_id AND is_active FOR UPDATE;
  IF v_owner IS DISTINCT FROM p_actor_id
    OR p_relationship NOT IN ('conjuge','filho','outro') THEN
      RAISE EXCEPTION 'Alteração não permitida';
  END IF;
  UPDATE axora_beta.finance_family_profiles
  SET relationship=p_relationship
  WHERE workspace_id=p_workspace_id AND id=p_profile_id
     AND active AND relationship<>'principal';
  GET DIAGNOSTICS v_count=ROW_COUNT;
  IF v_count<>1 THEN RAISE EXCEPTION 'Perfil secundário não encontrado'; END IF;
  RETURN jsonb_build_object('ok',true,'relationship',p_relationship);
END;
$function$;

CREATE OR REPLACE FUNCTION axora_beta.axora_family_upsert_member(p_workspace_id uuid, p_actor_id bigint, p_display_name text, p_relationship text, p_password_hash text DEFAULT NULL::text, p_profile_id bigint DEFAULT NULL::bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'axora_beta', 'public'
AS $function$
DECLARE
  v_owner bigint;
  v_profile bigint;
  v_member bigint;
  v_name text;
  v_existing record;
BEGIN
  PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
  SELECT created_by INTO v_owner FROM axora_beta.finance_workspaces
   WHERE id=p_workspace_id AND is_active FOR UPDATE;
  IF v_owner IS DISTINCT FROM p_actor_id THEN
    RAISE EXCEPTION 'Somente o principal pode cadastrar membros';
  END IF;
  IF p_relationship NOT IN ('conjuge','filho','outro') THEN
    RAISE EXCEPTION 'Vínculo inválido';
  END IF;
  v_name := btrim(coalesce(p_display_name,''));
  IF char_length(v_name) NOT BETWEEN 1 AND 80 THEN
    RAISE EXCEPTION 'Nome inválido';
  END IF;
  IF p_password_hash IS NOT NULL THEN
    IF char_length(v_name)>40 OR p_password_hash !~ '^pbkdf2_sha256\$390000\$[0-9a-f]{32}\$[0-9a-f]{64}$' THEN
      RAISE EXCEPTION 'Cadastro de login inválido';
    END IF;
  END IF;
  IF p_profile_id IS NULL THEN
    IF (SELECT count(*) FROM axora_beta.finance_family_profiles
         WHERE workspace_id=p_workspace_id)>=50 THEN
      RAISE EXCEPTION 'Quantidade máxima de pessoas cadastradas';
    END IF;
    IF EXISTS(SELECT 1 FROM axora_beta.finance_family_profiles
       WHERE workspace_id=p_workspace_id AND lower(display_name)=lower(v_name)
         AND active) THEN RAISE EXCEPTION 'Pessoa já cadastrada nesta família'; END IF;
  ELSE
    SELECT id, display_name, relationship, linked_user_id INTO v_existing
      FROM axora_beta.finance_family_profiles
      WHERE id=p_profile_id AND workspace_id=p_workspace_id
        AND active AND relationship<>'principal' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Perfil familiar indisponível'; END IF;
    IF v_existing.linked_user_id IS NOT NULL THEN
      RAISE EXCEPTION 'Este perfil já possui acesso';
    END IF;
    IF p_password_hash IS NULL OR v_existing.display_name<>v_name
       OR v_existing.relationship<>p_relationship THEN
      RAISE EXCEPTION 'Ativação de login não corresponde ao perfil';
    END IF;
  END IF;

  IF p_password_hash IS NOT NULL THEN
    INSERT INTO axora_beta.finance_users(display_name,password_hash,is_admin,is_active)
     VALUES (v_name,p_password_hash,false,true) RETURNING id INTO v_member;
    INSERT INTO axora_beta.finance_workspace_members(workspace_id,user_id,role)
     VALUES (p_workspace_id,v_member,'viewer');
  END IF;

  IF p_profile_id IS NULL THEN
    INSERT INTO axora_beta.finance_family_profiles(
       workspace_id,display_name,relationship,linked_user_id,active)
    VALUES (p_workspace_id,v_name,p_relationship,v_member,true)
    RETURNING id INTO v_profile;
  ELSE
    UPDATE axora_beta.finance_family_profiles
       SET linked_user_id=v_member
     WHERE id=p_profile_id AND workspace_id=p_workspace_id
       AND linked_user_id IS NULL
    RETURNING id INTO v_profile;
    IF v_profile IS NULL THEN RAISE EXCEPTION 'Falha de concorrência'; END IF;
  END IF;

  RETURN jsonb_build_object('id',v_profile,'display_name',v_name,
    'relationship',p_relationship,'linked_user_id',v_member,
    'active',true,'access',CASE WHEN v_member IS NULL THEN 'perfil' ELSE 'login' END);
END;
$function$;

REVOKE ALL ON FUNCTION axora_beta.axora_family_change_relationship(uuid,bigint,bigint,text),
 axora_beta.axora_family_upsert_member(uuid,bigint,text,text,text,bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_family_change_relationship(uuid,bigint,bigint,text),
 axora_beta.axora_family_upsert_member(uuid,bigint,text,text,text,bigint) TO service_role;
COMMIT;
