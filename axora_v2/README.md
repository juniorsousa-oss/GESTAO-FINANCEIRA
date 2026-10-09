# AXORA 2.0 — Migração completa para web nativa

## Status

Esta implementação é uma **versão de homologação**. O endereço de produção continua na Hostinger com Streamlit até a validação e troca deliberada do Compose.

### Tecnologia

- Interface: HTML5, CSS, JavaScript vanilla (sem Streamlit).
- Backend: FastAPI + Python 3.12, porta 8000.
- Dados: **mesmo** projeto Supabase e tabelas finance_*, sem alteração de schema.
- Login: mesma senha do banco existente, verificada com PBKDF2-SHA256, cookie assinado HttpOnly, SameSite Lax, Secure e CSRF nas operações de escrita.
- Integração Excel e foto: reuso dos módulos Python `services.importer` e `services.profile` da V1, que não dependem do Streamlit.

### Comparativo funcional

| V1 | V2 |
|---|---|
| Login só com senha, nome e foto | Mesmo fluxo; sessão assinada de 8 horas |
| Dashboard: 6 cards, evolução, rosca, contas e conciliação | Cards, gráficos SVG, próximas previsões, metas e conciliação |
| Movimentações | Listagem, busca/filtros, cadastro, edição e exclusão |
| Contas e previsões | Listagem, filtros, cadastro, edição de status e valores |
| Contas e saldos | Conciliação, cadastro e edição de saldos |
| Dívidas | Indicadores, cadastro, edição e exclusão |
| Excel | Importação das quatro abas e exportação das quatro tabelas |
| Perfil | Nome, foto PNG/JPG, logout |
| Configurações | Metas financeiras e criação/listagem de usuários por administrador |

A importação continua **bloqueada se existir qualquer registro nas quatro bases**, para impedir substituição acidental. Não há conversão ou exclusão de dados.

## Limitação de privacidade que já existia na V1

Os usuários cadastrados compartilham as tabelas financeiras. Não disponibilizar para múltiplos clientes independentes sem:
1. vincular cada registro a um tenant/proprietário;
2. aplicar autenticação por usuário e autorização em cada consulta/escrita;
3. migrar os registros atuais de forma controlada;
4. testar isolamento e backup.

## Implantação — sem interromper o atual AXORA

1. Revisar a branch da V2 e os testes. Para homologar, não é necessário integrar à main: o Compose de staging aponta diretamente para a branch `feat/axora-web-v2-20261009`.
2. Fazer backup do banco Supabase e garantir plano de restauração.
3. Criar DNS **A** para `axora-hml.nexonlabs.com.br` apontando à mesma VPS, apenas para homologação.
4. Na Hostinger Docker Manager, criar um **novo** projeto `axora-web-hml` (não alterar ainda `gestao-financeira`).
5. Utilizar `axora_v2/docker-compose.stage.yml` da branch de homologação. Ele constrói a imagem diretamente dessa branch, sem tocar na versão principal.
6. Definir no ambiente do Compose:
   - `SUPABASE_URL`: mesma URL privada atual;
   - `SUPABASE_KEY`: chave de serviço do Supabase, nunca para navegador/GitHub;
   - `SESSION_SECRET`: uma string aleatória, exclusiva do AXORA, com pelo menos 32 caracteres;
   - `COOKIE_SECURE=1`.
7. **Não enviar segredos em print, chat ou commit.** Não reutilizar o segredo de sessão do ATRIA.
8. Certificar que Traefik possa enxergar o contêiner no Docker networking da VPS. Se os projetos usam redes isoladas, conectar o contêiner à rede compartilhada do Traefik e configurar `traefik.docker.network` explicitamente.
9. Implantar homologação e validar `https://axora-hml.nexonlabs.com.br/health` e o domínio com HTTPS.
10. Comparar V1 e V2: realizar acesso com a mesma senha, mesmos valores, foto, gráficos desktop/mobile, filtros, permissões, edição controlada, exportação, logout e retorno de sessão.
11. **Não usar contas de produção para testes destrutivos**; validar gravação/edição e importação em projeto Supabase isolado ou backup restaurável.
12. Depois da homologação, integrar a branch `feat/axora-web-v2-20261009` à `main`. Com tudo validado, copiar **conteúdo do Compose de produção** `axora_v2/docker-compose.production.yml` no projeto `gestao-financeira` da Hostinger, confirmando as variáveis privadas e o roteamento. Isso remove o contêiner antigo Streamlit somente na etapa de corte.
13. Garantir que apenas um router Traefik responda pelo host `axora.nexonlabs.com.br`; parar homologação no final ou deixá-la com um host diferente.
14. Conferir logs e saúde, comparar os mesmos registros e ter rollback pronto (Compose antigo no histórico do Hostinger e imagem anterior).

## Segurança de produção

- Servir somente com HTTPS; não publicar a porta 8000 na Internet.
- Supabase service role **somente** no backend.
- Controlar rate limiting também no proxy/Traefik para proteção distribuída em múltiplos contêineres.
- Usar backup periódico e logs seguros.
- A API não abre documentação pública Swagger, não usa CORS amplo e mantém política de conteúdo restritiva.
- A aplicação permanece com dados financeiros compartilhados entre contas da mesma instalação: **não é multi-tenant**.

## Verificação local (sem banco real)

```bash
pip install -r axora_v2/requirements.txt pytest httpx
python -m compileall -q axora_v2
node --check axora_v2/static/app.js
python -m pytest axora_v2/tests -q
```

Para rodar localmente com banco próprio de teste, configure as variáveis de ambiente acima, `COOKIE_SECURE=0` para localhost sem HTTPS e execute:

```bash
uvicorn axora_v2.main:app --host 127.0.0.1 --port 8000
```

Não executar uma instância de teste apontada a dados financeiros reais sem cópia de segurança e autorização.
