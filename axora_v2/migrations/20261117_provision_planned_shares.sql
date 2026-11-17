-- AXORA BETA | Rateio planejado de provisões, sem antecipar lançamentos.
-- Aplicar somente em axora_beta após migrações familiares de 2026-11-17.
-- Criação da série + percentuais ocorre na mesma transação SQL.
BEGIN;
CREATE TABLE axora_beta.finance_provision_cost_shares(
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES axora_beta.finance_workspaces(id) ON DELETE RESTRICT,
  rule_id bigint NOT NULL,
  profile_id bigint NOT NULL,
  percentage numeric(5,2) NOT NULL CHECK (percentage>0 AND percentage<=100),
  CONSTRAINT axora_provision_split_rule_fk FOREIGN KEY(rule_id,workspace_id)
    REFERENCES axora_beta.finance_provision_rules(id,workspace_id) ON DELETE RESTRICT,
  CONSTRAINT axora_provision_split_profile_fk FOREIGN KEY(workspace_id,profile_id)
    REFERENCES axora_beta.finance_family_profiles(workspace_id,id) ON DELETE RESTRICT,
  CONSTRAINT axora_provision_split_one_profile UNIQUE(workspace_id,rule_id,profile_id)
);
CREATE INDEX axora_provision_split_lookup ON axora_beta.finance_provision_cost_shares(workspace_id,rule_id);
ALTER TABLE axora_beta.finance_provision_cost_shares ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE axora_beta.finance_provision_cost_shares FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON axora_beta.finance_provision_cost_shares TO service_role;
GRANT USAGE,SELECT ON SEQUENCE axora_beta.finance_provision_cost_shares_id_seq TO service_role;

CREATE FUNCTION axora_beta.axora_family_create_provision_with_shares(
 p_workspace_id uuid, p_actor_id bigint,
 p_description text, p_category text, p_responsible text,
 p_start_due_date date, p_planned_value numeric,
 p_value_mode text, p_recurrence text, p_frequency text,
 p_end_date date, p_installment_count integer,
 p_payment_method text, p_payment_url text,
 p_pix_kind text, p_pix_value text, p_pix_receiver_name text,
 p_pix_receiver_city text, p_shares jsonb
) RETURNS bigint
LANGUAGE plpgsql SET search_path TO 'axora_beta', 'public'
AS $function$
DECLARE
 v_rule bigint;
 v_count integer;
BEGIN
 PERFORM axora_beta.axora_family_validate_actor(p_workspace_id,p_actor_id);
 IF NOT EXISTS(
   SELECT 1 FROM axora_beta.finance_workspaces w
   JOIN axora_beta.finance_family_profiles f
     ON f.workspace_id=w.id AND f.linked_user_id=p_actor_id AND f.active
   WHERE w.id=p_workspace_id AND w.created_by=p_actor_id
     AND w.is_active AND f.relationship='principal'
 ) THEN RAISE EXCEPTION 'Somente o principal pode planejar rateio familiar'; END IF;

 IF jsonb_typeof(p_shares) IS DISTINCT FROM 'array' THEN
   RAISE EXCEPTION 'Rateio inválido'; END IF;
 v_count:=jsonb_array_length(p_shares);
 IF v_count<1 OR v_count>50 THEN
   RAISE EXCEPTION 'Quantidade de participantes inválida'; END IF;
 IF EXISTS(
   SELECT 1 FROM jsonb_to_recordset(p_shares)
   AS s(profile_id bigint, percentage numeric)
   WHERE s.profile_id IS NULL OR s.percentage IS NULL
      OR s.percentage<=0 OR s.percentage>100
      OR s.percentage<>round(s.percentage,2)
      OR NOT EXISTS(SELECT 1 FROM axora_beta.finance_family_profiles f
        WHERE f.workspace_id=p_workspace_id AND f.id=s.profile_id AND f.active)
 ) THEN RAISE EXCEPTION 'Participante ou percentual inválido'; END IF;
 IF EXISTS(
   SELECT 1 FROM jsonb_to_recordset(p_shares)
   AS s(profile_id bigint, percentage numeric)
   GROUP BY profile_id HAVING count(*)>1
 ) THEN RAISE EXCEPTION 'Participante duplicado'; END IF;
 IF (SELECT coalesce(sum(s.percentage),0) FROM jsonb_to_recordset(p_shares)
     AS s(profile_id bigint, percentage numeric))<>100
 THEN RAISE EXCEPTION 'Rateio deve totalizar 100%'; END IF;

 v_rule:=axora_beta.axora_create_provision_with_method(
   p_workspace_id,p_description,p_category,p_responsible,
   p_start_due_date,p_planned_value,p_value_mode,p_recurrence,
   p_frequency,p_end_date,p_installment_count,p_payment_method,
   p_payment_url,p_pix_kind,p_pix_value,p_pix_receiver_name,p_pix_receiver_city
 );
 INSERT INTO axora_beta.finance_provision_cost_shares(
   workspace_id,rule_id,profile_id,percentage
 ) SELECT p_workspace_id,v_rule,s.profile_id,s.percentage
   FROM jsonb_to_recordset(p_shares) AS s(profile_id bigint,percentage numeric);
 RETURN v_rule;
END;
$function$;

REVOKE ALL ON FUNCTION axora_beta.axora_family_create_provision_with_shares(
 uuid,bigint,text,text,text,date,numeric,text,text,text,date,integer,
 text,text,text,text,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION axora_beta.axora_family_create_provision_with_shares(
 uuid,bigint,text,text,text,date,numeric,text,text,text,date,integer,
 text,text,text,text,text,text,jsonb) TO service_role;
COMMIT;
