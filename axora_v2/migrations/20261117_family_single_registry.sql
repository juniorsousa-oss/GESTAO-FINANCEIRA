-- AXORA BETA — Cadastro familiar central em Configurações.
-- Executar SOMENTE no schema axora_beta após 20261116_family_hierarchy_management.sql.
-- Não executar em public / produção sem homologação e backup.
-- Mantém titularidade e saldo; jamais concede visibilidade financeira.
BEGIN;

ALTER TABLE axora_beta.finance_family_profiles
  DROP CONSTRAINT IF EXISTS finance_family_profiles_relationship_check;
ALTER TABLE axora_beta.finance_family_profiles
  ADD CONSTRAINT finance_family_profiles_relationship_check
  CHECK (relationship IN ('principal','conjuge','pai','mae','filho','sogro','tio','outro'));

ALTER TABLE axora_beta.finance_bank_holders
  DROP CONSTRAINT IF EXISTS finance_bank_holders_relationship_check;
ALTER TABLE axora_beta.finance_bank_holders
  ADD CONSTRAINT finance_bank_holders_relationship_check
  CHECK (relationship IN ('proprio','conjuge','pai','mae','filho','sogro','tio','familiar','outro'));

ALTER TABLE axora_beta.finance_bank_holders
  ADD COLUMN IF NOT EXISTS family_profile_id bigint;

-- Ligações cruzadas respeitam workspace e nunca mudam a titularidade da conta.
DO $constraint$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    WHERE c.conrelid='axora_beta.finance_bank_holders'::regclass
      AND c.conname='axora_bank_holder_family_profile_fk'
  ) THEN
    ALTER TABLE axora_beta.finance_bank_holders
      ADD CONSTRAINT axora_bank_holder_family_profile_fk
      FOREIGN KEY (workspace_id,family_profile_id)
      REFERENCES axora_beta.finance_family_profiles(workspace_id,id) ON DELETE RESTRICT;
  END IF;
END $constraint$;
CREATE UNIQUE INDEX IF NOT EXISTS axora_beta_holder_profile_unique
  ON axora_beta.finance_bank_holders(workspace_id,family_profile_id)
  WHERE family_profile_id IS NOT NULL;

-- Primeiro preserva a relação mais específica anteriormente cadastrada
-- na área bancária (ex.: Mãe/Pai) caso o perfil familiar ainda esteja "Outro".
-- Nunca sobrescreve um perfil específico nem atribui permissões automaticamente.
WITH existing_relations AS (
 SELECT p.id profile_id,h.relationship,h.workspace_id
 FROM axora_beta.finance_bank_holders h
 JOIN axora_beta.finance_family_profiles p
   ON h.workspace_id=p.workspace_id
  AND lower(btrim(h.name))=lower(btrim(p.display_name))
 WHERE p.active AND p.relationship='outro'
   AND h.relationship IN ('conjuge','pai','mae','filho','sogro','tio')
   AND (h.linked_user_id IS NULL OR p.linked_user_id IS NULL
        OR h.linked_user_id=p.linked_user_id)
   AND (SELECT count(*) FROM axora_beta.finance_bank_holders h2
        WHERE h2.workspace_id=h.workspace_id
          AND lower(btrim(h2.name))=lower(btrim(h.name)))=1
   AND (SELECT count(*) FROM axora_beta.finance_family_profiles p2
        WHERE p2.workspace_id=p.workspace_id AND p2.active
          AND lower(btrim(p2.display_name))=lower(btrim(p.display_name)))=1
)
UPDATE axora_beta.finance_family_profiles p
SET relationship=e.relationship
FROM existing_relations e
WHERE p.id=e.profile_id AND p.workspace_id=e.workspace_id;

-- Migra somente pares de mesmo nome normalizado que sejam únicos em AMBAS
-- tabelas e não apresentem divergência de login. Nomes ambíguos ficam sem
-- vínculo automático para decisão humana nas Configurações.
WITH safe_matches AS (
 SELECT h.id holder_id,p.id profile_id,p.relationship,p.linked_user_id,h.workspace_id
 FROM axora_beta.finance_bank_holders h
 JOIN axora_beta.finance_family_profiles p
   ON h.workspace_id=p.workspace_id
  AND lower(btrim(h.name))=lower(btrim(p.display_name))
 WHERE h.family_profile_id IS NULL AND p.active
   AND (h.linked_user_id IS NULL OR p.linked_user_id IS NULL
     OR h.linked_user_id=p.linked_user_id)
   AND (SELECT count(*) FROM axora_beta.finance_bank_holders h2
        WHERE h2.workspace_id=h.workspace_id
          AND lower(btrim(h2.name))=lower(btrim(h.name)))=1
   AND (SELECT count(*) FROM axora_beta.finance_family_profiles p2
        WHERE p2.workspace_id=p.workspace_id AND p2.active
          AND lower(btrim(p2.display_name))=lower(btrim(p.display_name)))=1
)
UPDATE axora_beta.finance_bank_holders h
 SET family_profile_id=s.profile_id,
     relationship=CASE WHEN s.relationship='principal' THEN 'proprio' ELSE s.relationship END,
     linked_user_id=coalesce(h.linked_user_id,s.linked_user_id)
 FROM safe_matches s
 WHERE h.workspace_id=s.workspace_id AND h.id=s.holder_id;

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
    OR p_relationship NOT IN ('conjuge','pai','mae','filho','sogro','tio','outro') THEN
      RAISE EXCEPTION 'Alteração não permitida';
  END IF;
  UPDATE axora_beta.finance_family_profiles
  SET relationship=p_relationship
  WHERE workspace_id=p_workspace_id AND id=p_profile_id
     AND active AND relationship<>'principal';
  GET DIAGNOSTICS v_count=ROW_COUNT;
  IF v_count<>1 THEN RAISE EXCEPTION 'Perfil secundário não encontrado'; END IF;
  -- O vínculo familiar é o mesmo do titular bancário já associado.
  UPDATE axora_beta.finance_bank_holders
    SET relationship=p_relationship
    WHERE workspace_id=p_workspace_id AND family_profile_id=p_profile_id;
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
  v_holder bigint;
  v_holder_count bigint;
  v_linked bigint;
BEGIN
  PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
  SELECT created_by INTO v_owner FROM axora_beta.finance_workspaces
   WHERE id=p_workspace_id AND is_active FOR UPDATE;
  IF v_owner IS DISTINCT FROM p_actor_id THEN
    RAISE EXCEPTION 'Somente o principal pode cadastrar membros';
  END IF;
  IF p_relationship NOT IN ('conjuge','pai','mae','filho','sogro','tio','outro') THEN
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

  -- Um cadastro familiar cria (ou vincula de forma inequívoca) o titular de
  -- contas no mesmo workspace, numa única transação SQL.
  IF p_profile_id IS NULL THEN
    SELECT count(*), min(id) INTO v_holder_count,v_holder
    FROM axora_beta.finance_bank_holders
    WHERE workspace_id=p_workspace_id
      AND lower(btrim(name))=lower(v_name);
    IF v_holder_count>1 THEN
      RAISE EXCEPTION 'Mais de um titular com esse nome. Resolva a duplicidade em Configurações.';
    END IF;
    IF v_holder_count=1 THEN
      SELECT linked_user_id INTO v_linked FROM axora_beta.finance_bank_holders
        WHERE workspace_id=p_workspace_id AND id=v_holder FOR UPDATE;
      IF v_member IS NOT NULL AND v_linked IS NOT NULL AND v_member<>v_linked THEN
        RAISE EXCEPTION 'Titular bancário pertence a outro login';
      END IF;
      UPDATE axora_beta.finance_bank_holders
      SET family_profile_id=v_profile, relationship=p_relationship,
          linked_user_id=coalesce(v_member,linked_user_id)
      WHERE id=v_holder AND workspace_id=p_workspace_id
        AND (family_profile_id IS NULL OR family_profile_id=v_profile);
      IF NOT FOUND THEN RAISE EXCEPTION 'Titular vinculado a outro perfil'; END IF;
    ELSE
      INSERT INTO axora_beta.finance_bank_holders
        (workspace_id,name,relationship,linked_user_id,family_profile_id)
      VALUES (p_workspace_id,v_name,p_relationship,v_member,v_profile);
    END IF;
  ELSE
    -- Ativar login em perfil existente não gera outro titular.
    UPDATE axora_beta.finance_bank_holders
    SET linked_user_id=v_member
    WHERE workspace_id=p_workspace_id AND family_profile_id=v_profile
      AND (linked_user_id IS NULL OR linked_user_id=v_member);
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
-- Após aplicar, atualizar o cache da API PostgREST da instância BETA.
