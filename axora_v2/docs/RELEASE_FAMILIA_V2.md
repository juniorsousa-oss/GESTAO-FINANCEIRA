# AXORA Família V2 — padronização entre ambientes e instâncias

## Base única, instâncias separadas
Este código será a referência para **AXORA Base/DEMO, AXORA BETA, AXORA produção e as instâncias de clientes**. A identidade institucional Nexon Labs é fixa; as marcas dos clientes seguem as configurações de personalização já aprovadas.

Cada cliente requer **workspace, credenciais e dados próprios**, sem visibilidade cruzada. O principal só pode consultar o próprio workspace. Cônjuge, filho e outros são vinculados ao workspace do principal por ação expressa, e a visibilidade se controla por **recurso**; o vínculo familiar não concede automaticamente leitura.

## Estado do código
- Acesso familiar: `family_service.py` e rotas `family_routes.py`, com ACL de negação por padrão.
- Rótulos: `privado`, `casal`, `familia`, `selecionados`. Itens antigos sem rótulo são privados.
- Pessoas: perfil financeiro com ou sem login. Login opcional, vinculação atômica.
- Operações: novo registro com beneficiários percentuais e pagadores em valores absolutos; quitação atômica de provisão.
- Dashboard Família: receitas, despesas atribuídas, desembolsos, resultado e quantidade de lançamentos antigos sem rateio.
- Contas bancárias: cards por pessoa com conta expansível e saldo manual. Histórico Pluggy preservado.
- Frontend mobile: `family.js`, `family.css` e atualizações das telas existentes.
- Testes: isolamento de informações, bloqueio de rotas não auditadas, CSRF, rateio e interrupção de integração bancária.

## Configuração **por instância**
```ini
AXORA_FAMILY_V2_ENABLED=0
AXORA_BANK_MODE=manual
```
Até aplicar migração e homologação em BETA, família permanece desativada. O modo manual pausa leitura/sincronização bancária sem apagar conexões históricas.

**Só habilitar `AXORA_FAMILY_V2_ENABLED=1` após executar a migração em banco isolado, confirmar respostas HTTPS das rotas e testar contas de principal e cônjuge.**

## Pendência de infraestrutura
O BETA Render `axora-beta-ec24` **compartilha Supabase com a produção Hostinger** nesta data. Não há separação real de banco. Nenhum SQL de família deve ser executado neste projeto antes da validação em projeto isolado.

1. Criar um projeto Supabase específico `axora-family-beta` em uma organização escolhida pelo usuário.
2. Recriar nele o esquema atual AXORA (migrações em ordem), **sem copiar saldos, dados bancários, senhas ou dados reais**.
3. Aplicar `axora_v2/migrations/20261116_family_v2.sql` no BETA; validar FKs, funções, RLS, rotas REST e grants. A checagem estática do parser não equivale a migração executada.
4. Inserir **dados fictícios** e testar principal e cônjuge com diferentes senhas.
5. Configurar Render BETA `SUPABASE_URL` e `SUPABASE_KEY` para esse projeto, `AXORA_BANK_MODE=manual` e `AXORA_FAMILY_V2_ENABLED=1`.
6. Homologar no desktop/iOS/Android, especialmente dashboard e exportações: cônjuge não deve visualizar nem inferir totais privados.
7. Backup de produção; migração assistida de usuários existentes. Nunca tratar a segunda conta como cônjuge sem vincular explicitamente. Se o usuário secundário já tiver workspace próprio e dados, não anexá-lo sem migrá-los com revisão.
8. Somente depois, merge/promoção ao `develop` e `main` do produto, habilitando recursos por cliente com seu próprio banco e configuração.
9. Antes de cada publicação: testes de ida/volta (revogação de visibilidade, reset de sessão, atualização de saldo, quitação/estorno, reconciliação, exportação).

## Atenção antes de comercializar
O AXORA usa FastAPI e uma chave de API de servidor para Supabase. RLS isolada **não substitui** a checagem de permissões no backend; toda API/RPC nova deve derivar usuário e workspace da sessão, jamais de parâmetros de formulário.

Nenhum sistema filho deve poder listar dados privados por agregações, exportação, imagens, filtros ou APIs alternativas. As rotas antigas não auditadas ficam bloqueadas para perfis secundários no modo familiar.
