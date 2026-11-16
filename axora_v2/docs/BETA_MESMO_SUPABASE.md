# AXORA BETA no Supabase já existente — sem novo projeto
## Estrutura criada em 16/11/2026
- Projeto Supabase: `cuixazpxkvniqldmmnth` (mesmo da produção).
- Schema exclusivo: `axora_beta` (não é projeto separado).
- Origem: cópia somente da **estrutura** das 20 tabelas financeiras, 35 FKs, rotinas e gatilhos. **Nenhum registro de produção foi copiado**.
- Migração familiar aplicada exclusivamente em `axora_beta`: total 26 tabelas e 23 rotinas.
- RLS ativado nas 26 tabelas, com acessos diretos anon/authenticated revogados; somente `service_role` tem acesso à API de dados via backend privado.
- Teste: dois usuários fictícios, perfil dependente sem login, duas contas bancárias inventadas, uma despesa privada e uma despesa compartilhada de R$300 com rateio 200/100.
- Usuários reais de `public.finance_users` preservados.
## Conectar a API com segurança
1. No painel Supabase do projeto, abrir **Project Settings / Data API / Exposed schemas**.
2. **Adicionar** `axora_beta` à lista; **manter TODOS os schemas que já estiverem presentes** (especialmente `public` e os de outros apps). Não os substituir.
3. Salvar. Isso autoriza PostgREST a reconhecer o header `Accept-Profile: axora_beta` e `Content-Profile: axora_beta`.
4. No Render BETA (não na Hostinger), definir `SUPABASE_DB_SCHEMA=axora_beta`, `AXORA_FAMILY_V2_ENABLED=1`, `AXORA_BANK_MODE=manual`.
5. Validar login com os dois usuários fictícios e testes de isolamento. Não compartilhar senhas/segredos reais.
6. Somente após testes completos, planejar cada cliente e a promoção à produção.
## Importante
- A separação é **lógica dentro do mesmo banco/projeto**, não isolamento de infraestrutura. Quedas e limites do projeto são compartilhados.
- Nenhuma regra, dado ou segredo de produção deve ser alterado ao testar.
- Evitar sobrescrever a configuração global `pgrst.db_schemas` via SQL: poderia alterar a disponibilidade dos demais aplicativos.
