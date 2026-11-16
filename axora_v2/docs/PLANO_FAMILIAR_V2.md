# AXORA — Reestruturação familiar e controle por pessoa (proposta em desenvolvimento)

## Estado auditado (16/11/2026)
- 2 contas de usuário ativas, 1 workspace financeiro e 1 vínculo de membro.
- O sistema atual **não possui vínculo familiar entre os dois logins**. Um titular de conta bancária não é necessariamente um usuário com login.
- O AXORA BETA compartilha o projeto Supabase com a produção Hostinger. Portanto **esta branch não pode implantar migrações nem habilitar compartilhamento** até haver banco de homologação isolado.
- Não converter automaticamente registros legados em "casal": ausência de classificação significa PRIVADO para qualquer outro usuário.
- Nenhuma senha, saldo, registro ou transação real deve ser replicado no ambiente de teste.

## Modelo lógico
```
Workspace familiar (proprietário principal)
├── Principal — visão integral + administração
├── Cônjuge — seus dados próprios + rótulo "casal" + concessões específicas
├── Filho — perfil de custo, login opcional e acesso mínimo
└── Outro — perfil de custo, login opcional e acesso por concessão específica
```

**Pessoa / perfil financeiro** e **usuário que faz login** são entidades diferentes. Isso permite apurar os custos de crianças e dependentes sem lhes criar acesso ao aplicativo.

## Visibilidade (independente de custos)
| Rótulo | Principal | Cônjuge | Filho | Outro |
|---|---|---|---|---|
| Privado | Tudo | Apenas seus próprios | Apenas seus próprios | Apenas seus próprios |
| Casal | Tudo | Sim | Não | Não |
| Família | Tudo | Sim | Sim se tiver login | Não |
| Selecionados | Tudo | Se listado | Se listado | Se listado |

O criador de um registro do próprio workspace também pode visualizá-lo. Associação como pagador ou beneficiário **não concede leitura**. Usuário sem login não recebe acesso. Ao mudar papel/vínculo, recalcular acesso no servidor. Privado deve ser o padrão de novas informações.

### Segurança obrigatória antes de disponibilizar qualquer ramificação
1. Confirmar vínculo `finance_workspace_members` usando a sessão, não ID de usuário enviado pelo browser.
2. Consultar rótulo e concessões no banco ANTES de serializar qualquer resposta: Dashboard, Provisões, Registros, contas, conciliações, exportações, relatórios, links Pix, histórico e configurações.
3. Validar novamente em escrita, edição, exclusão, rateio e quitação. Impedir alterações de rótulos/grants por usuários sem autorização.
4. Preservar isolamento entre workspaces; negar recurso não classificado para todos exceto proprietário/criador verificado.
5. O backend usa chave privada: RLS somente não basta; endpoints e RPCs devem cumprir ACL do mesmo modo.
6. Sem habilitação parcial por UI: nenhuma tela deve revelar nomes, saldos nem agregados privados.
7. Testes de vazamento horizontal e vertical entre perfis, incluindo respostas de totais, contagens, erros, buscas e IDs.
8. Política para filhos: criar PERFIL sem login por padrão; se criado login, limitar a dados permitidos.

## Custos por pessoa e rateio
Para cada lançamento **único**, guardar:
- **Beneficiário(s):** quem gerou o custo; soma exata de parcelas = 100% do lançamento.
- **Pagador(es):** quem desembolsou; total dos pagamentos = valor lançado.
- **Visibilidade:** privado, casal, família ou selecionados, independentemente dos dois itens anteriores.
- **Categoria, data e descrição** no Registro.
- **Conta de origem (opcional):** não inferir saldo automaticamente, evitar débitos duplicados.

Exemplo: despesa escolar de R$ 300 de um filho. Beneficiário = filho (100%); pagamentos = principal R$ 200 + cônjuge R$ 100; visibilidade = casal. O custo do filho é R$ 300, o desembolso dos dois adultos soma R$ 300. Não criar dois Registros de R$ 300.

Indicadores: entradas por pessoa, despesas atribuídas à pessoa, pagamentos efetivados por pessoa, saldo líquido e custo per capita. Transferências internas ficam fora da apuração de despesas.

## Conta bancária
- Cards agrupados POR TITULAR, com soma do saldo manual, e `<details>` para revelar contas.
- Contas sem saldo informado não são igualadas a zero; totais parciais devem mostrar aviso.
- Rótulo de visibilidade deve existir por conta; "casal" é explícito, não presumido por relacionamento.
- Durante pausa de Pluggy, conta já vinculada mantém IDs históricos e aceita saldo manual, sem remover integração nem sobrescrever histórico.
- Não duplicar conta conjunta em totais, mesmo quando aparece nos dois usuários.
- API Pluggy desligada via `AXORA_BANK_MODE=manual` em ambientes apropriados; só reativar em etapa própria.

## Implantação gradual
1. Preparar regras, migração e interface em `feature/axora-family-v2`.
2. Criar Supabase BETA separado com dados sintéticos.
3. Aplicar migração em BETA; implementar e testar ACL em TODOS os endpoints e RPCs.
4. Testar dois logins e perfil-filho sem login; confirmar invisibilidade de todas as telas.
5. Migração assistida: mapear explicitamente os 2 logins existentes; classificar dados antigos como privados até aprovação.
6. Aprovar UI desktop/mobile e release; produção somente depois de backup e checklist de segurança.
