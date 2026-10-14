# AXORA — primeira conexão Pluggy (piloto de leitura)

## Objetivo e status
Primeiro conectar uma conta Nubank para validar consentimento, leitura de saldo e importação de até 100 transações **já contabilizadas** dos últimos 90 dias.
CAIXA também possui conector Open Finance, mas pode exigir MFA e autorização adicional com processamento demorado.

**Implementado na branch main:** widget opcional, autorização temporária por titular e conta cadastrada, conferência da conta, associação única, consulta de saldo e importação idempotente para a fila de Conciliação. **Não há conta bancária conectada ainda**: é necessário configurar uma conta de desenvolvedor Pluggy, publicar a versão no servidor e o titular autorizar a conexão.

**Modo padrão = sandbox (sem bancos reais).** Produção só com `PLUGGY_ENABLE_LIVE=true` e acesso autorizado ao produto Dados/Open Finance no plano Pluggy.

## Segurança
- `PLUGGY_CLIENT_ID` e `PLUGGY_CLIENT_SECRET` são secrets **somente no backend Hostinger**, nunca no GitHub, frontend ou mensagem de chat.
- Backend gera API key de curta duração e connect token para o widget, com identificador aleatório de intenção por conta e workspace.
- Antes de associar ao AXORA, backend valida via API oficial: item, clientUserId da intenção, conta, tipo BANK, moeda BRL e sandbox/real de acordo com o modo permitido.
- Exige consentimento do titular no banco; o app não captura nem armazena senhas ou CPF.
- Uma conta vinculada não pode ser excluída ou atribuída a outro titular por simples edição.
- Importação de extrato não cria Registros, não baixa Provisões, não inicia PIX e não confirma conciliações.
- Transações só entram na fila se foram marcadas POSTED e com identificação única do provedor; reimportações ignoram duplicidades sem alterar decisões humanas antigas.
- **Limites do piloto:** apenas uma conta provedora por conta AXORA, até 100 transações por sincronização dos 90 dias recentes, primeira página, sem webhooks ou revogação gerenciada. Não usar para controle financeiro crítico até homologar dados e funcionamento real.

## Custos e plano
Segundo preços públicos da Pluggy (outubro/2026), o produto Dados parte de **R$ 2.500/mês**, com **15 dias de teste gratuito** sem cartão. Após o teste, as conexões reais são pausadas se não houver plano. O sandbox e a API de testes são suficientes para a homologação inicial. Não contratar plano recorrente antes de avaliar viabilidade comercial e alternativas.

Links oficiais:
- Cadastro: https://dashboard.pluggy.ai/
- Preços: https://www.pluggy.ai/precos
- Início rápido: https://v2.docs.pluggy.ai/pt/docs/quickstart
- Cobertura Nubank e CAIXA: https://v2.docs.pluggy.ai/pt/docs/open-finance/overview

## Procedimento
1. Criar conta no painel Pluggy e obter Client ID e Client Secret para testes.
2. Na configuração do serviço `financeiro` na Hostinger, criar segredos de ambiente:
   - `PLUGGY_CLIENT_ID`: do painel Pluggy
   - `PLUGGY_CLIENT_SECRET`: do painel Pluggy
   - `PLUGGY_ENABLE_LIVE=false` para validação inicial
3. Garantir que Docker Compose repassa os três nomes ao contêiner; não inclua os valores em prints, Git ou conversas.
4. Rebuild do serviço financeiro:
   ```sh
   cd /docker/gestao-financeira
   docker compose build --pull --no-cache financeiro
   docker compose up -d --no-deps --force-recreate financeiro
   docker compose ps
   ```
5. AXORA → Contas bancárias → **Conectar banco** na conta escolhida.
6. No sandbox, o widget permitirá somente um conector de teste. Dados fictícios oficiais do Pluggy Bank: usuário `user-ok`, senha fictícia `password-ok`, MFA fictício `123456`. Essas credenciais são **exclusivas do sandbox público**.
7. Confira a conta retornada; só então pressione **Vincular esta conta**.
8. Pressione **Sincronizar extrato**; confira as movimentações importadas na Central de Conciliação, ainda pendentes. Teste reimportar para conferir idempotência.
9. Para produção, após o teste e a aprovação comercial, habilitar Open Finance para a conta de desenvolvedor, configurar `PLUGGY_ENABLE_LIVE=true` e repetir o consentimento do titular em uma **nova conta AXORA**, começando preferencialmente pelo Nubank.

## Próximas etapas antes da produção
Webhooks autenticados para autorização que conclui depois do fechamento do navegador (especialmente CAIXA); sincronização paginada em lotes maiores; revogação de consentimento e exclusão segura do vínculo; reconciliação de transações atualizadas ou removidas pelo banco; controle de compartilhamento entre logins por conta; controles de privacidade/retenção LGPD; telemetria e testes end-to-end com o conector real.

**Não compartilhar credenciais ou capturas que revelem CPF, conta completa, extrato ou token.**
