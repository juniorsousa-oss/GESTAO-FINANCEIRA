# AXORA — MeuPluggy pessoal, leitura automática sem plano comercial

## O que foi implementado
- Integração pela API oficial do **MeuPluggy**, restrita a **um único usuário pessoal configurado**, com a conexão previamente autorizada em `meu.pluggy.ai` e na aplicação AXORA do Dashboard.
- O backend utiliza `POST /auth`, `GET /accounts?itemId=...` e `GET /v2/transactions` (cursor). Credenciais nunca aparecem no JavaScript nem no repositório.
- São lidas **somente contas do tipo BANK em BRL**. Cartões de crédito ainda não são importados para evitar dupla contabilização de compras/faturas.
- Na tela Contas bancárias, o usuário pessoal vê **Vincular MeuPluggy** e escolhe a conta correspondente àquela já cadastrada no AXORA; o nome e os quatro últimos dígitos ajudam na conferência.
- Após a vinculação, pode clicar em **Sincronizar**; além disso o backend faz sincronização **automática aproximadamente de hora em hora**, inclusive sem navegador aberto.
- Atualizações reais dependem do ritmo do MeuPluggy, normalmente aproximadamente **a cada 24 horas**. O AXORA não força atualização da instituição.
- Apenas transações **POSTED**, em BRL, são importadas para `finance_bank_transactions` com `status=pending`. A chave `(account_id,source,external_ref)` impede reimportações duplicadas.
- **Não** cria `finance_movements`, **não** quita `finance_provision_occurrences`, **não** envia PIX nem movimenta dinheiro. Operador valida na Central de Conciliação.

## Uso pessoal e segurança
O acesso gratuito é limitado ao uso pessoal conforme a documentação da Pluggy (até cinco conexões). Não utilizar credenciais pessoais como infraestrutura de clientes da Nexon Labs. Ao comercializar o aplicativo, contratar plano apropriado e implementar autorização individual por cliente.

As credenciais de servidor devem ficar fora do GitHub. Configure **somente na VPS**:
- `PLUGGY_CLIENT_ID`: Client ID da **aplicação AXORA**, não Pluggy Demo App;
- `PLUGGY_CLIENT_SECRET`: Client Secret da mesma aplicação;
- `PLUGGY_ITEM_ID`: UUID do item MeuPluggy **conectado dentro da aplicação AXORA**;
- `PLUGGY_PERSONAL_USER_ID`: identificador numérico do usuário AXORA titular da conexão.

O serviço Docker precisa receber essas quatro variáveis no contêiner `financeiro`. Defina-as em arquivo restrito ao administrador na Hostinger ou no gerenciamento privado de variáveis e referencie-as no Docker Compose. **Não inserir no GitHub, no JavaScript, em screenshots, em commits ou na conversa.**

Para conferir sem exibir valores secretos:
```bash
cd /docker/gestao-financeira
docker compose ps
docker compose exec financeiro python -c "import os; print({k:bool(os.getenv(k)) for k in ('PLUGGY_CLIENT_ID','PLUGGY_CLIENT_SECRET','PLUGGY_ITEM_ID','PLUGGY_PERSONAL_USER_ID')})"
```

## Ordem de ativação
1. Migração SQL `migrations/20261015_meu_pluggy_personal_sync.sql` no Supabase.
2. Conferir CI do GitHub após a última alteração.
3. Publicar versão nova do contêiner (rebuild somente `financeiro`).
4. Configurar as quatro variáveis no contêiner, sem revelar valores.
5. Reiniciar `financeiro`. A tela Contas bancárias passa a exibir os controles pessoais.
6. Clicar em **Vincular MeuPluggy** na conta Nubank correta, confirmar e clicar em **Sincronizar**.
7. Verificar saldo na conta, transações pendentes na Central de Conciliação e **nenhuma movimentação financeira criada automaticamente**.
8. Verificar novamente após uma atualização diária da Pluggy.

## Limitações intencionais
- Sem conexão gratuita de terceiros. Famílias e futuros clientes precisam de autorização e condições contratuais separadas.
- Não possui importação de cartões, investimentos, estorno de transação, alteração retroativa nem resolução automática de transações de substituição com novo ID.
- Consulta apenas transações liquidadas dos últimos 90 dias, com limite de segurança de 20 páginas por sincronização.
- Se o banco atrasar sua atualização, o AXORA exibirá o saldo da última consulta bem-sucedida; é possível ver a data/hora dessa consulta.
- Para descobrir saldos e transações é necessário configurar os segredos no contêiner e ter acesso à API do item pessoal. Sem esses dados a versão atual do AXORA segue operando em modo manual.

Fonte oficial: https://docs.pluggy.ai/pt/docs/guides/meu-pluggy-personal-use
