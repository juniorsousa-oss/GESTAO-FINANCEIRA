-- Já aplicada no projeto Supabase AXORA em 09/10/2026.
-- Ativo institucional isolado das tabelas financeiras; acesso apenas service_role.
CREATE TABLE IF NOT EXISTS public.finance_brand_assets (
  key text PRIMARY KEY CHECK (key = 'institutional_signature'),
  content_type text NOT NULL CHECK (content_type IN ('image/webp','image/png')),
  image_data_uri text NOT NULL CHECK (char_length(image_data_uri) BETWEEN 40 AND 1500000),
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.finance_brand_assets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.finance_brand_assets FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.finance_brand_assets TO service_role;
