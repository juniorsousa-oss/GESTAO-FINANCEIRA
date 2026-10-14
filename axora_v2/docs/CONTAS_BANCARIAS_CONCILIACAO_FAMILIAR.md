# AXORA — Contas bancárias, gestão familiar e conciliação assistida

**Definição funcional aprovada:** oferecer simultaneamente gestão familiar centralizada e contas individuais com compartilhamento explícito. Não fazer conciliação ou quitação bancária sem confirmação do operador.

## 1. Dois modelos complementares

### A. Pessoal/familiar centralizado
- Um usuário autorizado administra um espaço financeiro familiar.
- Contas de titulares distintos podem aparecer nesse espaço **somente após autorização de cada titular** e configuração de acesso apropriada.
- Cada conta mantém vínculo com instituição, titular, identificador mascarado, tipo, moeda, saldo, consentimento, conexão e última sincronização.
- A visão consolidada considera apenas contas permitidas ao usuário atual e deve evitar duplicar transferências internas.

### B. Acesso individual com compartilhamento
- Cada usuário tem espaço financeiro pessoal privado por padrão.
- Titulares podem convidar outros usuários para espaços familiares ou compartilhar contas determinadas.
- Quatro papéis iniciais: proprietário, administrador do espaço, operador de conciliação e leitor. Cada conta terá permissões próprias (visualizar saldo, extrato, conciliar, administrar conexão).
- A API precisa permitir selecionar explicitamente um workspace autorizado, validá-lo no servidor a cada operação e nunca confiar em `workspace_id` enviado sem checar a sessão.
- Usuários sem autorização para determinada conta **não podem** inferir seus dados por busca, sugestão, totalização ou exportação.

## 2. Origem de transações (faseada)
1. Cadastro manual das contas, titulares, autorizações e saldos informados.
2. Importação de extrato CSV/OFX para testar a conciliação, sem conexão bancária obrigatória.
3. Open Finance via provedor contratado (CAIXA, Nubank e outros bancos, sob confirmação de cobertura e consentimento individual).
4. Sincronização agendada e reautorização. Somente leitura bancária na primeira versão; não executar PIX, transferências ou pagamentos.

Credenciais bancárias e senhas **não** devem ser armazenadas no AXORA. Guardar somente referências/tokens estritamente necessários ao provedor, com proteção, rotação e revogação.

## 3. Banco de dados — entidades e vínculos
- `finance_holders`: titular, dados mínimos e workspace; convite/vínculo com usuário AXORA quando aplicável.
- `finance_bank_accounts`: titular, instituição, tipo, apelido, últimos dígitos, identificador externo protegido, workspace, moeda, estado, saldo informado, atualização.
- `finance_account_permissions`: permissões explícitas por usuário e conta.
- `finance_bank_connections`: provedor, consentimento, validade, escopos, estado e histórico de sincronização; conexão não se confunde com a conta bancária.
- `finance_bank_transactions`: fatos bancários imutáveis, com fonte, chave externa única por conta, data, valor assinado, descrição, identificador/hash, moeda e status de revisão.
- `finance_reconciliation_links`: vínculo transação ↔ Registro, Provisão ou transferência, com autor, data, decisão e estorno lógico; impedir vínculos concorrentes.
- `finance_reconciliation_audit`: quem decidiu, quando, o que foi vinculado, alterado ou revertido.

Índices únicos por `(bank_account_id, provider_transaction_id)` e identidade secundária verificável para extratos importados, permitindo reimportação idempotente. Não inferir duplicidade somente de data/valor/descrição, pois duas compras idênticas podem ser legítimas.

## 4. Central de Conciliação — regra do usuário

**Fila principal = somente transações bancárias ainda não conciliadas ou classificadas.**

Campos da lista: instituição, conta, titular autorizado, data, descrição original, entrada/saída, valor, origem e status de sincronização.

Para cada transação, mostrar sugestões explicáveis, com pontuação **indicativa** de proximidade:
- Valor e direção (exatamente igual ou diferença justificável);
- Proximidade da data bancária com vencimento ou Registro;
- Semelhança de descrição/favorecido, com normalização de texto;
- Contexto da conta/titular e referências transacionais quando presentes.

Os filtros de permissão, conta, moeda, status, workspace e sinal da operação são **obrigatórios antes** do cálculo. Provisões já quitadas não são candidatas a uma nova quitação; porém seus Registros podem ser candidatos a **vínculo bancário sem novo lançamento**.

Apresentar faixa "alta", "média" ou "baixa" e explicar por que cada candidato foi sugerido. Percentual não significa confirmação de pagamento.

### Decisões exclusivas do operador
1. **Vincular a Registro existente**: associa transação e Registro, **sem** criar outra receita/despesa.
2. **Quitar Provisão aberta**: exige confirmação, registra pagamento e cria o Registro se ainda não existir; associação e baixa devem ser atômicas.
3. **Criar novo Registro**: classificar/categorizar e confirmar o lançamento correspondente.
4. **Transferência interna**: associar os lados da transferência entre contas autorizadas e impedir dupla contagem na visão consolidada.
5. **Manter pendente**, **marcar para revisão** ou **ignorar com motivo**.
6. **Desfazer** por procedimento auditado; nunca excluir transações bancárias originais.

Nenhuma transação deve ser marcada como paga, ignorada ou registrada automaticamente apenas por confiança da sugestão.

## 5. Regras contábeis e operacionais
- Separar saldo bancário consultado, saldo informado manualmente e saldo projetado; nunca somar diretamente como se fossem o mesmo indicador.
- Movimentações bancárias são fatos brutos; Registros são lançamentos validados. **Não criar lançamentos financeiros durante a sincronização.**
- Para transações já pagas manualmente no AXORA, oferecer primeiro "vincular Registro existente" (sem duplicidade).
- Transferências entre duas contas autorizadas aparecem nos respectivos extratos, mas o resultado consolidado não vira receita/despesa líquida artificial.
- Divergências de valor, encargos, juros, pagamento parcial e pagamentos agrupados precisam de confirmação específica e permanecem pendentes até haver regra aprovada.
- O Dashboard deve diferenciar saldo bancário, despesas realizadas, provisões em aberto e valores conciliados.
- Um titular pode ter diversas contas no mesmo banco; várias pessoas podem ter contas na mesma instituição.

## 6. Critérios de aceite e etapas

**Etapa 1:** cadastro de titulares, contas manuais, seleção de espaço financeiro e permissões, com interface de testes.
**Etapa 2:** importar extratos, detectar repetidos de forma segura e listar transações em análise.
**Etapa 3:** motor de proximidade explicável, ações manuais de conciliação, proteção de duplicidade, auditoria e reversão.
**Etapa 4:** conectar provedor Open Finance e automatizar sincronização, nunca a decisão de conciliação.

Casos obrigatórios: duas contas da mesma instituição/titulares diferentes; mesmo titular com contas múltiplas; operador sem permissão; duas transações iguais legítimas; extrato reimportado; pagamento já marcado manualmente; parcela pendente; transferências entre contas; revogação do consentimento; alternância entre espaços pessoais e familiares.

**Status:** especificação funcional registrada. Não há conexão Open Finance nem alterações de schema de contas bancárias implantadas por este documento. Implementar e homologar cada etapa antes de publicar.
