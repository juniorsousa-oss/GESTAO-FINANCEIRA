-- AXORA 2.0 | Catalogos por workspace (categorias e responsaveis).
-- Adicao nao destrutiva. Cadastros existentes de provisoes sao preservados
-- e entram automaticamente nos catalogos do seu workspace.
BEGIN;

CREATE TABLE IF NOT EXISTS public.finance_catalog_options (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE RESTRICT,
  kind text NOT NULL CHECK (kind IN ('category','responsible')),
  name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120 AND name=btrim(name)),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS finance_catalog_workspace_kind_name
  ON public.finance_catalog_options(workspace_id,kind,lower(name));
CREATE INDEX IF NOT EXISTS finance_catalog_workspace_lookup
  ON public.finance_catalog_options(workspace_id,kind,active,name);
ALTER TABLE public.finance_catalog_options ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.finance_catalog_options FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON TABLE public.finance_catalog_options TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.finance_catalog_options_id_seq TO service_role;

CREATE OR REPLACE FUNCTION public.axora_ensure_catalog(p_workspace_id uuid)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE v_added integer := 0; v_count integer;
BEGIN
  IF p_workspace_id IS NULL OR NOT EXISTS(
    SELECT 1 FROM public.finance_workspaces WHERE id=p_workspace_id AND is_active
  ) THEN
    RAISE EXCEPTION 'Espaco financeiro invalido';
  END IF;

  INSERT INTO public.finance_catalog_options(workspace_id,kind,name)
  SELECT p_workspace_id,'category',category
  FROM (VALUES
    ('Moradia'),('Alimentação'),('Transporte'),('Saúde'),
    ('Educação'),('Assinaturas e serviços'),('Impostos e taxas'),
    ('Lazer'),('Investimentos'),('Outros')
  ) AS defaults(category)
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS v_count=ROW_COUNT;
  v_added := v_added + v_count;

  INSERT INTO public.finance_catalog_options(workspace_id,kind,name)
  VALUES(p_workspace_id,'responsible','Próprio')
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS v_count=ROW_COUNT;
  v_added := v_added + v_count;

  -- Aproveita somente os nomes existentes, sem alterar lancamentos historicos.
  INSERT INTO public.finance_catalog_options(workspace_id,kind,name)
  SELECT DISTINCT ON (lower(btrim(category)))
    p_workspace_id,'category',btrim(category)
  FROM public.finance_provision_rules
  WHERE workspace_id=p_workspace_id AND category IS NOT NULL AND btrim(category)<>''
  ORDER BY lower(btrim(category)),btrim(category)
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS v_count=ROW_COUNT;
  v_added := v_added + v_count;

  INSERT INTO public.finance_catalog_options(workspace_id,kind,name)
  SELECT DISTINCT ON (lower(btrim(responsible)))
    p_workspace_id,'responsible',btrim(responsible)
  FROM public.finance_provision_rules
  WHERE workspace_id=p_workspace_id AND responsible IS NOT NULL AND btrim(responsible)<>''
  ORDER BY lower(btrim(responsible)),btrim(responsible)
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS v_count=ROW_COUNT;
  v_added := v_added + v_count;
  RETURN v_added;
END;
$$;
REVOKE ALL ON FUNCTION public.axora_ensure_catalog(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.axora_ensure_catalog(uuid) TO service_role;

-- Inclui as opcoes ja usadas, para nao bloquear a continuidade das provisoes
-- existentes. Workspaces futuros receberao as opcoes no primeiro uso.
SELECT public.axora_ensure_catalog(id) FROM public.finance_workspaces WHERE is_active;
COMMIT;
