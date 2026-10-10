-- FASE 1: base relacional de espaços e permissões.
-- NÃO habilita isolamento financeiro até a fase 2 (workspace_id e escopo em TODAS as APIs).
-- Não altera nem redistribui registros financeiros já existentes.
CREATE TABLE IF NOT EXISTS public.finance_workspaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name varchar(100) NOT NULL CHECK (length(trim(name)) BETWEEN 2 AND 100),
  created_by bigint REFERENCES public.finance_users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  is_active boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS public.finance_workspace_members (
  workspace_id uuid NOT NULL REFERENCES public.finance_workspaces(id) ON DELETE CASCADE,
  user_id bigint NOT NULL REFERENCES public.finance_users(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('owner','admin','editor','viewer')),
  added_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(workspace_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_finance_workspace_members_user
  ON public.finance_workspace_members (user_id,workspace_id);
ALTER TABLE public.finance_workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_workspace_members ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.finance_workspaces FROM anon,authenticated;
REVOKE ALL ON public.finance_workspace_members FROM anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.finance_workspaces TO service_role;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.finance_workspace_members TO service_role;
-- FASE 2 PENDENTE: atribuir workspace_id aos 4 conjuntos de dados e às metas,
-- migrar os registros existentes para um workspace legado, adicionar FKs/constraints,
-- escopar SELECT/INSERT/PATCH/DELETE/import/export/settings,
-- validar permissões server-side (inclusive auditoria e sessões).
