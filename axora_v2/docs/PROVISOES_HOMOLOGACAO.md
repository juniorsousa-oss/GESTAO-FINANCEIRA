# AXORA — Provisões, fase 1 / homologação

## Objetivo aprovado
- Nova aba **Provisões** apresenta somente vencimentos em aberto.
- Cada compromisso possui primeiro vencimento, categoria, descrição, responsável e valor previsto.
- Tipos: único, recorrente indeterminado, recorrente com data final e parcelado.
- Periodicidade e valor fixo/estimado são atributos diferentes.
- Vencimentos recorrentes são gerados sob demanda até 18 meses à frente, preservando dia original (incluindo último dia do mês).
- Uma quitação **integral** confirmada cria exatamente uma saída na tabela existente `finance_movements`, e o vencimento deixa Provisões.
- O registro permanece vinculado ao vencimento, protegendo edição/exclusão manual. Sem lançamento duplicado mesmo diante de duas tentativas simultâneas.
- A aba **Registros** continua usando a base histórica `finance_movements`, identificando origem Manual/Provisão.

## Limitações deliberadas da primeira etapa
- Sem pagamento parcial, estorno ou edição de provisões já cadastradas.
- Sem baixa automática de contas bancárias, conciliação, anexo de comprovante ou notificações.
- A aba **Previsões antigas** mantém a lógica histórica, sem conversão automática. Não cadastrar novas contas por ela para testar o novo fluxo.
- O dashboard ainda reflete o mecanismo antigo de previsões; atualização das métricas será feita após validação da nova base.
- Dados financeiros e usuários permanecem na mesma base compartilhada (a aplicação ainda não é multi-tenant).

## Passos de implantação SEGURA (ambiente de homologação)
1. Escolher Supabase de **teste isolado**, não a base financeira real. Confirmar que as tabelas do schema financeiro de teste estão instaladas e fazer backup.
2. No **SQL Editor do projeto de teste**, executar uma vez `axora_v2/migrations/20261013_provisoes_mvp.sql`. É SQL para o banco, **não** comando para o terminal Linux.
3. Revisar chaves `SUPABASE_URL`, `SUPABASE_KEY`, `SESSION_SECRET` e os domínios para uma instância AXORA de teste separada. Nunca divulgar chaves.
4. Reconstruir somente o contêiner AXORA de teste a partir do GitHub atualizado; não trocar configuração da instalação financeira de produção.
5. Acessar o novo menu **Provisões** e cadastrar os exemplos abaixo.
6. Se a migração ainda não estiver instalada, a tela mostrará aviso; não será possível gravar contas. As áreas antigas continuam funcionando.

## Roteiro de validação funcional
1. **Única**: Internet 20/10/2026 R$ 120,00; deve gerar só um vencimento.
2. **Recorrência mensal fixa**: aluguel no dia 31 com valor R$ 1.800,00; gerar o último dia nos meses sem 31, sem mudança retroativa.
3. **Mensal variável**: energia R$ 200,00 estimados; na quitação ajustar o efetivamente pago para R$ 187,45.
4. **Prazo definido**: contrato com término; não aparecer após a data final.
5. **Parcelamento**: seguro com 10 parcelas mensais; não deve criar a parcela 11.
6. **Pagamento**: quitar um vencimento na data informada; deve desaparecer de Provisões e surgir uma vez em Registros como saída, com competência da data efetiva.
7. **Duplicidade**: tentar quitar o mesmo vencimento duas vezes; segunda operação deve ser recusada pelo servidor.
8. **Integridade**: edição/exclusão isolada de um Registro vinculado deve ser bloqueada; Registros manuais continuam editáveis.
9. **Responsividade**: conferir campos e tabela no celular, sem prejudicar menu lateral ou cabeçalho fixo.
10. **Segurança**: tentar gravar sem CSRF e sem login; o servidor deve recusar. Confirmar que nenhuma tabela anterior foi apagada.
11. **Sem base real**: usar somente dados fictícios nesta etapa; não gerar despesas reais de teste na base financeira de produção.

## Reinício futuro da base
Nenhum comando de exclusão foi adicionado. A limpeza da base real é outra operação, que exigirá backup verificável, escopo explícito (quais tabelas), ambiente alvo e aprovação antes de qualquer `DELETE` ou `TRUNCATE`.

## Arquivos envolvidos
- Migração SQL: `migrations/20261013_provisoes_mvp.sql`
- API: `main.py`, validações em `provisions.py`
- UI: `static/index.html`, `static/app.js`, `static/provisions.js`, `static/provisions.css`
- Testes: `tests/test_provisions_mvp.py`
