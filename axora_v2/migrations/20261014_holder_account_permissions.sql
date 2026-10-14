-- AXORA: database privileges for administrative CRUD on banking labels.
-- Executed only through authenticated, workspace-scoped application endpoints.
BEGIN;
GRANT UPDATE, DELETE ON public.finance_bank_holders TO service_role;
GRANT UPDATE, DELETE ON public.finance_bank_accounts TO service_role;
COMMIT;