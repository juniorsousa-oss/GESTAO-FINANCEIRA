# AXORA — Central de Conciliação, primeira versão funcional

**Status:** código na branch `main`, migração `20261014_banking_reconciliation_mvp.sql` aplicada no Supabase e correção da função `20261014_banking_reconciliation_hotfix.sql` aplicada. **A nova versão exige rebuild do contêiner Hostinger**.

## O que já está disponível no código
- **Contas bancárias**: cadastro manual de titulares com vínculo (próprio, cônjuge, mãe, pai etc.), várias contas do mesmo banco e contas de titulares distintos; nenhuma senha ou dado bancário sensível precisa ser fornecido.
- **Conciliação**: introdução manual de transações para testar; entrada com valor positivo e saída com valor negativo; transações entram sempre como pendentes.
- **Sugestões explicáveis**: combinação de valor, sinal, data e semelhança da descrição, ordenada por proximidade. Pontuação não é autorização.
- **Revisão obrigatória**: operador escolhe opção, vê resumo e aciona `Confirmar decisão`. Nenhum processo assíncrono confirma sem operador.
- **Vincular Registro existente**: somente cria associação, jamais duplica lançamento.
- **Quitar Provisão**: transação, quitação, novo Registro e histórico gravados na mesma transação SQL, apenas para saída de valor idêntico e provisão aberta.
- **Criar Registro**: usa conta bancária/valor/data, categoria ativa e confirmação.
- **Transferência**: confirma as duas pontas de valores opostos em contas distintas sem criar receita ou despesa fictícia.
- **Ignorar**: exige motivo, mantendo auditoria.
- **Histórico**: decisões imutáveis, ator, data, destino.
- **Segurança**: sessão autenticada, CSRF, filtragem por workspace, confirmação por membro autorizado, RLS nas novas tabelas e bloqueio a duplicidade. Registros vinculados não são editáveis/excluíveis isoladamente.

## Não incluso nesta fase
- **Open Finance CAIXA/Nubank**: nenhuma conta bancária conectada; nenhuma atualização de saldo/extrato real.
- **CSV/OFX**: importação real de extratos ficará para a próxima etapa. O cadastro manual é somente um meio para validar a conciliação.
- **Espaço familiar compartilhado entre logins**: a base mantém um workspace privado por usuário e permite múltiplos titulares/contas neste workspace. O convite de familiares, seleção de espaços e permissões por conta ainda precisa ser implementado e testado antes de permitir compartilhamento. Nomear uma pessoa como titular **não** concede acesso à conta dela.
- **Diferenças de valor, pagamentos parciais, vários Registros por transação, tarifas associadas e estorno de conciliação**: permanecem bloqueados para evitar distorções e serão tratados em etapas específicas.
- **Saldos automáticos e conciliação automática**: não disponíveis. A pontuação orienta, nunca decide.

## Migração
1. `migrations/20261014_banking_reconciliation_mvp.sql` cria tabelas e RPC. O GitHub contém a versão corrigida da função.
2. `migrations/20261014_banking_reconciliation_hotfix.sql` substituiu o nome de alias conflitante detectado na simulação.
3. As duas migrações foram aplicadas ao banco conectado. **Não reaplicar a migração no terminal Bash.**
4. Verificações SQL foram executadas dentro de uma transação com `ROLLBACK`: Registro existente, Provisão, transferência entre duas contas, novo Registro, descarte, duplicidade e auditoria.
5. Conferido após os testes: 0 titulares, 0 contas bancárias, 0 transações bancárias e 0 eventos de auditoria — nenhuma simulação persistida. Demais Registros, Provisões, usuários e branding preservados.

## Implantação na Hostinger
```bash
cd /docker/gestao-financeira
docker compose build --pull --no-cache financeiro
docker compose up -d --no-deps --force-recreate financeiro
docker compose ps
```
Esperar `healthy`; no navegador usar Ctrl+F5.

## Roteiro de homologação (com dados fictícios)
1. **Contas bancárias** → cadastrar dois titulares (pessoal e familiar), dois bancos e duas contas distintas.
2. **Conciliação** → adicionar débito fictício de valor coincidente com uma Provisão de teste. Confirmar que apenas a sugestão aparece antes da revisão, sem dar baixa.
3. Selecionar **Quitar Provisão**; revisar/confirmar. Deve sair da fila, quitar Provisão e criar um Registro uma única vez.
4. Criar um Registro de teste, depois uma transação bancária do mesmo valor e sinal. Escolher **Vincular Registro existente** e confirmar; não deve duplicar Registro.
5. Criar duas transações opostas de mesmo valor em contas distintas e confirmar a **Transferência**; não deve incrementar receitas/despesas do Dashboard.
6. Testar **Criar Registro** com categoria ativa e **Ignorar** com justificativa.
7. Confirmar histórico e tentar usar transação já conciliada: backend deve recusar.
8. Verificar versão mobile, login, Dashboard e as Provisões anteriormente cadastradas.
9. Só após a validação discutir importação real de extratos, revogação de vínculos, relatórios e conexão Open Finance.

Todos os testes devem ser feitos com dados fictícios. No estado atual, decisões de teste confirmadas ficam registradas no banco e não há estorno automático; não usar transações reais ainda.
