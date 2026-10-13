# AXORA 2.0 — Reinício financeiro nativo

## Decisão validada (13/10/2026)
Abandonar a lógica de importação Excel como origem operacional. Reconstruir gradualmente um sistema nativo com:
1. Provisões recorrentes e únicas;
2. Registro automático ao confirmar quitação;
3. Contas e saldos (próxima etapa);
4. Dívidas, transferências, parcelamentos e conciliação (etapas seguintes);
5. Mesma lógica de operação para todos os usuários, com isolamento por workspace.

## Reset financeiro — executado
O Supabase compartilhado tem as tabelas financeiras legadas:
- finance_movements: 132 registros arquivados; tabela atual 0
- finance_forecasts: 495 registros arquivados; tabela atual 0
- finance_accounts: 10 registros arquivados; tabela atual 0
- finance_debts: 9 registros arquivados; tabela atual 0

Cópias internas no schema `axora_legacy_20261013`:
`movements`, `forecasts`, `accounts`, `debts`, `users`, `brand_assets`, `settings`.
As contagens foram conferidas antes e depois da limpeza. `finance_users` (2) e `finance_brand_assets` (5) permaneceram ativos. Nenhuma tabela de outro aplicativo foi excluída.

**Observação:** arquivo interno no mesmo banco não equivale a um backup externo independente.

## Estado do banco
- Migração `migrations/20261013_provisoes_mvp.sql`: **aplicada**. Criou tabelas e RPCs iniciais de Provisões, vazias.
- Migração `migrations/20261013_finance_workspace_isolation.sql`: **preparada no GitHub, ainda não aplicada**. Deve entrar coordenada com o novo backend do AXORA.
- Enquanto a segunda migração não entrar, **não publicar o novo código no servidor**; ele espera `workspace_id` e novas assinaturas de RPC.
- Não repetir a limpeza. Os dados operacionais já foram zerados.

## Comportamento nativo fase 1
**Provisões**: data, categoria, descrição, responsável, valor, natureza fixa/variável, ocorrência única, recorrência indefinida, recorrência com término ou parcelamento.
**Registros**: movimentações realizadas. Quitações integrais criam uma saída financeira com vínculo único à provisão e removem o vencimento da lista pendente. O vínculo bloqueia edição ou exclusão isolada.
**Multiusuário**: cada usuário possui um espaço financeiro privado. Compartilhamento de membros no mesmo espaço exigirá permissões e fluxo próprios antes de ser habilitado.
**Legado**: a importação Excel foi desativada (HTTP 410). Previsões do Excel também. Abas antigas de contas/dívidas permanecem fora da navegação até serem redesenhadas.
**Identidade**: branding, autenticação, logos e estrutura visual foram preservadas.

## Sequência segura de ativação no mesmo ambiente (sem banco isolado)
1. Aguardar CI do GitHub passar na branch `main`.
2. Antes da migração, confirmar a janela de atualização na Hostinger e assegurar que nenhum cliente esteja cadastrando novos registros.
3. Aplicar `20261013_finance_workspace_isolation.sql` no Supabase conectado, verificando `workspace_id` e RPCs. **Essa etapa altera o schema financeiro e requer implantação coordenada.**
4. Executar rebuild do contêiner `financeiro` a partir da branch `main`, sem apagar volumes nem modificar Traefik.
5. Confirmar `healthy`, autenticação dos usuários preservados e novo menu Provisões/Registros.
6. Cadastrar uma provisão **fictícia** pequena para validar vencimento e confirmação de quitação. Verificar que surgiu exatamente um Registro. Validar isolamento entre os dois usuários com dados fictícios.
7. Decidir junto ao usuário se removeremos os registros fictícios depois do teste, mantendo rastreabilidade.
8. Só iniciar registros financeiros reais depois do teste funcional aprovado.

## Controles pendentes
- Pagamento parcial, estorno auditável e comprovantes.
- Contas bancárias, saldos iniciais, transferências e conciliação.
- Contratos recorrentes com edição de apenas uma parcela ou ocorrências futuras.
- Equipes compartilhando um workspace com papéis diferenciados.
- Segurança separada das tabelas de outros produtos presentes no Supabase compartilhado.

**Não executar comandos SQL no terminal Bash da Hostinger.** SQL vai no Supabase; comandos Docker vão no terminal da VPS.
