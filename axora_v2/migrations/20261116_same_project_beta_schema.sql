-- AXORA BETA em um mesmo projeto Supabase.
-- Executar UMA vez num projeto com tabelas public.finance_* existentes.
-- Não altera nem copia os dados de public e falha se o schema já existir.
BEGIN;
CREATE SCHEMA axora_beta;
DO $clone$
DECLARE t record; fk record; ddl text; n int:=0;
BEGIN
 FOR t IN SELECT table_name FROM information_schema.tables
   WHERE table_schema='public' AND table_name LIKE 'finance_%'
     AND table_type='BASE TABLE' ORDER BY table_name
 LOOP
   EXECUTE format('CREATE TABLE axora_beta.%I (LIKE public.%I INCLUDING ALL)',
                  t.table_name,t.table_name);
   EXECUTE format('ALTER TABLE axora_beta.%I ENABLE ROW LEVEL SECURITY',t.table_name);
   n:=n+1;
 END LOOP;
 IF n<20 THEN RAISE EXCEPTION 'Quantidade inesperada de tabelas: %',n; END IF;
 FOR fk IN SELECT tbl.relname,con.conname,pg_get_constraintdef(con.oid) ddl
   FROM pg_constraint con JOIN pg_class tbl ON tbl.oid=con.conrelid
   JOIN pg_namespace ns ON ns.oid=tbl.relnamespace
   WHERE ns.nspname='public' AND tbl.relname LIKE 'finance_%' AND con.contype='f'
 LOOP
   ddl:=replace(replace(fk.ddl,'REFERENCES public.finance_','REFERENCES axora_beta.finance_'),
     'REFERENCES finance_','REFERENCES axora_beta.finance_');
   EXECUTE format('ALTER TABLE axora_beta.%I ADD CONSTRAINT %I %s',
     fk.relname,'beta_'||fk.conname,ddl);
 END LOOP;
END $clone$;
DO $functions$
DECLARE f record; ddl text; total integer:=0;
BEGIN
 FOR f IN SELECT p.oid,p.proname FROM pg_proc p
   JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='public' AND p.proname LIKE 'axora_%'
   ORDER BY p.proname
 LOOP
   ddl:=pg_get_functiondef(f.oid);
   ddl:=replace(ddl,'public.','axora_beta.');
   ddl:=replace(ddl,'SET search_path TO ''public''',
     'SET search_path TO ''axora_beta'', ''public''');
   EXECUTE ddl;
   total:=total+1;
 END LOOP;
 IF total<17 THEN RAISE EXCEPTION 'Funções de origem ausentes: %',total; END IF;
END $functions$;
DO $triggers$
DECLARE t record; ddl text;
BEGIN
 FOR t IN SELECT pg_get_triggerdef(tr.oid) definition FROM pg_trigger tr
   JOIN pg_class c ON c.oid=tr.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relname LIKE 'finance_%' AND NOT tr.tgisinternal
 LOOP
   ddl:=replace(t.definition,'ON public.finance_','ON axora_beta.finance_');
   ddl:=replace(ddl,'EXECUTE FUNCTION axora_','EXECUTE FUNCTION axora_beta.axora_');
   EXECUTE ddl;
 END LOOP;
END $triggers$;
REVOKE ALL ON SCHEMA axora_beta FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA axora_beta TO service_role;
REVOKE ALL ON ALL TABLES IN SCHEMA axora_beta FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA axora_beta TO service_role;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA axora_beta TO service_role;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA axora_beta FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA axora_beta TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA axora_beta REVOKE ALL ON TABLES FROM PUBLIC,anon,authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA axora_beta GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA axora_beta GRANT USAGE,SELECT ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA axora_beta REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC,anon,authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA axora_beta GRANT EXECUTE ON FUNCTIONS TO service_role;
COMMIT;

-- Em seguida: executar a versão do SQL familiar ajustada exclusivamente
-- para axora_beta (substituir public. e search_path com revisão).
-- Configurar a área axora_beta nas opções Exposed schemas do Data API.
-- No AXORA BETA, definir SUPABASE_DB_SCHEMA=axora_beta.
-- NUNCA substituir pgrst.db_schemas global sem conhecer a lista atual:
-- outras aplicações Nexon Labs compartilham o mesmo projeto Supabase.
