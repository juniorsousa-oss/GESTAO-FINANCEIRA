# AXORA — Edição e exclusão seletiva de Provisões

## Funcionamento
Cada vencimento da lista de **Provisões** possui **Registrar pagamento**, **Editar** e **Excluir**.

Em **Editar**, o AXORA permite corrigir:
- Descrição;
- Categoria e responsável do catálogo padronizado;
- Vencimento;
- Valor previsto;
- Natureza do valor (fixo ou variável).

Antes de salvar, é obrigatório escolher:
- **Somente este registro:** altera apenas o vencimento selecionado;
- **Este e todos os próximos:** atualiza as ocorrências **pendentes** da mesma série, a partir da selecionada. Vencimentos futuros ainda não gerados seguem a nova regra. Se a data mudar, as datas subsequentes mantêm a periodicidade original e partem do novo dia escolhido.

Em **Excluir**, a mesma escolha:
- **Somente este registro:** marca apenas o vencimento selecionado como cancelado;
- **Este e todos os próximos:** cancela as pendências da série a partir daquele ponto e interrompe futuras gerações. O histórico anterior e pagamentos já confirmados ficam intactos.

O banco usa cancelamento lógico; não remove fisicamente histórico nem exclui os Registros de pagamentos realizados. Uma ocorrência já paga não pode ser editada ou cancelada.

## Cadastro com quantidade
O tipo **Recorrente por quantidade definida** passa a pedir **Quantidade de vencimentos**, de 1 a 360, em vez de data do último lançamento. O tipo **Parcelado por quantidade** também pede número de parcelas, de 1 a 360.

Compromissos antigos com data final (por exemplo, contratos de longa duração já cadastrados) são preservados com seu prazo original. A mudança da quantidade e periodicidade de uma série já criada ainda não faz parte desta edição; um lançamento novo pode utilizar as novas regras.

## Implantação
1. Migração aditiva: `axora_v2/migrations/20261013_provisions_revisions.sql`.
2. Após concluir a migração, publicar a branch `main` no serviço `financeiro` da Hostinger:
   ```bash
   cd /docker/gestao-financeira
   docker compose build --pull --no-cache financeiro
   docker compose up -d --no-deps --force-recreate financeiro
   docker compose ps
   ```
3. Verificar `healthy`, autenticação, listagem de Provisões, modais de edição/cancelamento, Dashboard e Registros.

## Testes executados
- CI: testes Python, validações de JavaScript, interface, build e inicialização do contêiner.
- Supabase: simulação em transação com `ROLLBACK` para criação de três vencimentos, edição individual, alteração dos futuros, pagamento com campos editados, proteção da ocorrência paga, cancelamento individual e cancelamento futuro.
- Contagens verificadas após teste: 2 regras existentes, 44 ocorrências, sem movimentações ou cancelamentos fictícios persistidos.
