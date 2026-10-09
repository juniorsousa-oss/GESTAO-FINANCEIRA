# AXORA 2.0 — Atualização do projeto EXISTENTE na Hostinger

**Situação:** o projeto Docker `gestao-financeira` e o domínio `axora.nexonlabs.com.br` já existem. A versão antiga roda no Streamlit Community Cloud e pode continuar disponível durante o corte.

## Atualização sem criar novo projeto

1. **Antes do deploy:** guardar o YAML atual da Hostinger e verificar um backup restaurável do Supabase.
2. No projeto `gestao-financeira`, acessar **Gerenciar → Editor .yaml**.
3. Substituir o YAML pelo arquivo atualizado de [docker-compose.yml](docker-compose.yml) da branch `main` **após a integração aprovada da V2**. O nome do serviço continuará `financeiro`.
4. Na área **Ambiente** do mesmo projeto, manter `SUPABASE_URL` e `SUPABASE_KEY` atualmente utilizados. Adicionar **`SESSION_SECRET`** com 32+ caracteres aleatórios diferentes dos usados no ATRIA e no Opera Hub; não compartilhar esse valor em chats ou prints. Guardar o segredo em local seguro, pois trocá-lo invalida sessões.
5. Validar se o gerenciador usa a seção de variáveis do Compose ou variáveis do ambiente; com a sintaxe `${SESSION_SECRET:?}`, o valor deve estar disponível **durante a leitura do Compose**, não apenas dentro do contêiner.
6. O novo Dockerfile passa a executar **FastAPI em 8000**, com healthcheck `/health`. O Traefik continua atendendo ao mesmo domínio.
7. Clique em **Implantar** somente depois de conferir o YAML, as variáveis e o backup.
8. Confirmar `https://axora.nexonlabs.com.br/health` (esperado `"engine":"FastAPI"`), login pela senha antiga, dados e layout no computador e celular.
9. Se houver erro, não excluir bancos nem fazer SQL; verificar logs do serviço e restaurar o YAML anterior. A versão Cloud segue independente.

**Branch de segurança:** `backup/axora-streamlit-before-v2-20261009` guarda o código e o Compose Streamlit anteriores.

---

## Referência histórica da implantação Streamlit

# Migração: Streamlit Community Cloud → Hostinger (VPS)

## Escopo e isolamento

- **Aplicativo:** AXORA (Gestão Financeira) (mantém Streamlit como framework, mas sai do Community Cloud).
- **Domínio planejado:** `https://axora.nexonlabs.com.br`.
- **Repositório:** `juniorsousa-oss/GESTAO-FINANCEIRA`; aplicativo principal `streamlit_app.py`.
- **Hospedagem:** VPS Hostinger com Docker Manager, Traefik e certificado Let's Encrypt, seguindo a arquitetura usada no ATRIA.
- **Banco:** mesmo projeto Supabase já conectado, com as tabelas `finance_*`. **Não recriar tabelas e não executar supabase_schema.sql outra vez.**
- **Não desligar o aplicativo antigo** até terminar a validação no novo domínio.
- **Não usar credenciais do ATRIA ou Opera Hub:** cada aplicação utiliza suas próprias variáveis e credenciais.

## 1. Antes de implantar

1. Validar que a VPS usada no ATRIA/Opera Hub suporta mais um contêiner e tem memória livre.
2. Fazer backup dos dados reais do projeto Supabase e verificar como restaurar o backup.
3. Conferir em `finance_users` se a conta atual está ativa. O login utiliza os mesmos registros de usuário; recriar a tabela faria perder a associação dos logins.
4. Separar **somente na Hostinger/VPS** os valores atuais de `SUPABASE_URL`, `SUPABASE_KEY`, `APP_ACCESS_PASSWORD` (se existir) e `APP_OWNER_NAME`.
5. Jamais colocar a chave de serviço (`service_role` ou `sb_secret_...`) em commits, URLs, prints ou no frontend.

## 2. DNS do subdomínio

No DNS de `nexonlabs.com.br`, criar registro:

| Tipo | Nome | Valor | TTL |
|---|---|---|---|
| A | financeiro | IPv4 público da VPS Hostinger | 300 (ou padrão) |

Não alterar os registros existentes de `atria.nexonlabs.com.br` ou do Opera Hub.
Se houver Cloudflare, usar DNS-only durante a emissão inicial do SSL.

## 3. Docker Manager / Compose

1. Na Hostinger: **VPS → Gerenciar → Docker Manager → Compose**.
2. Criar projeto distinto: `gestao-financeira`.
3. Após integrar este PR à branch `main`, utilizar **Compose from URL** com o link RAW:
   `https://raw.githubusercontent.com/juniorsousa-oss/GESTAO-FINANCEIRA/main/docker-compose.yml`.
4. O arquivo usa o mesmo Traefik da arquitetura ATRIA, com router exclusivo `axora`, HTTPS e serviço na porta **8501**. Não criar publicação pública adicional dessa porta.
5. Antes de iniciar, providenciar as variáveis abaixo no ambiente de execução da VPS / do projeto Docker Compose.
   - `SUPABASE_URL` = URL do projeto Supabase já utilizado.
   - `SUPABASE_KEY` = chave privada de serviço do **mesmo** projeto; só no servidor.
   - `APP_ACCESS_PASSWORD` = senha legada de bootstrap caso a tabela `finance_users` ainda não possua usuários. Sem bootstrap, as contas existentes seguem funcionando normalmente.
   - `APP_OWNER_NAME` = nome para o bootstrap (opcional).
6. O `docker-compose.yml` exige URL e chave. **Sem elas o deploy deve falhar**, em vez de iniciar uma versão de teste em memória.
7. Use um arquivo `.env` privado *junto ao Compose no servidor* ou os campos de variáveis do gerenciador. **Não comitar `.env`**. O modelo `.env.example` não contém credenciais reais.
8. Implantar e conferir que contêiner e healthcheck estão saudáveis (`/_stcore/health`).

> Atenção: o gerenciador pode precisar que as variáveis sejam definidas antes de interpretar o Compose. Se a interface via URL não permitir isso, usar **Compose manually** com as variáveis configuradas em ambiente privado, sem salvar a chave de serviço em repositório público.

## 4. HTTPS e acesso

- Conferir resolução de `axora.nexonlabs.com.br` para o IP da VPS.
- Confirmar no Traefik o router `axora` e a emissão do certificado Let's Encrypt.
- Abrir `https://axora.nexonlabs.com.br` em janela anônima e na versão mobile.
- Se a interface carregar em branco, inspecionar logs e suporte a WebSocket no proxy. O Streamlit mantém sessão por WebSocket.

## 5. Checklist de validação

- [ ] Novo domínio responde com HTTPS válido.
- [ ] Healthcheck Streamlit retorna HTTP 200 em `/_stcore/health`.
- [ ] Tela inicial pede **apenas senha**.
- [ ] Autenticação com senha existente reconhece nome e foto corretos.
- [ ] Movimentações, previsões, contas/saldos e dívidas mostram os **mesmos dados persistidos**.
- [ ] Dashboard tem os mesmos valores do app antigo; gráfico em rosca e cards não ficam cortados no mobile.
- [ ] Configurações e gerenciamento de usuários funcionam.
- [ ] Exportação Excel funciona; testar importação em ambiente controlado, sem substituir dados reais.
- [ ] Logout e novo login funcionam; usuário desativado não mantém acesso.
- [ ] Conferir logs sem segredos e estabilidade após reinicialização do contêiner.

## 6. Corte definitivo e acompanhamento

Depois de comparar os dados entre os dois domínios, comunicar o novo endereço e **só então** retirar o deploy antigo do Streamlit Community Cloud. Para domínio público e carteira comercial, avaliar autenticação forte, segregação de dados por cliente/usuário e auditoria **antes** de liberar clientes externos: a V1 compartilha os dados financeiros entre usuários cadastrados.

## Observações operacionais

- O Supabase permanece independente da VPS; uma troca de hospedagem **não transfere nem apaga registros**.
- A chave de serviço dá acesso privilegiado. Mantê-la apenas no backend/container e rotacioná-la se suspeitar de exposição.
- O Dockerfile utiliza usuário não-root e faz healthcheck em `/_stcore/health`.
- Para subir via terminal da VPS (alternativa ao painel), use `docker compose --env-file .env up -d --build` em uma pasta com o Compose disponível e `.env` privado.
- Repositório público não deve conter banco, planilhas particulares ou arquivos `.streamlit/secrets.toml`.
