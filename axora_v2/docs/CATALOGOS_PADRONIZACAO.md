# AXORA — Catálogos financeiros padronizados

## Objetivo
Evitar cadastros livres como "Moradia", "Casa" e "Despesas da casa" para o mesmo gasto, e diferentes grafias para um responsável.

## Fluxo
1. Abra **Configurações → Padronização de lançamentos**.
2. Revise as listas **Categorias** e **Responsáveis**. Os itens usados em provisões existentes são preservados no catálogo.
3. Adicione opções com grafia padronizada. A validação impede duplicidades ignorando maiúsculas/minúsculas.
4. Desative nomes que não deseja mais oferecer. Desativar não apaga nem modifica provisões ou registros anteriores; a opção pode ser reativada.
5. Clique em **Exportar listas (CSV)** para baixar `axora_categorias_responsaveis.csv`, compatível com Excel (UTF-8 BOM, separador ;). Colunas: Tipo, Nome padronizado, Situação e Orientação.
6. Abra **Provisões → Adicionar provisão**: os campos Categoria/Responsável serão seletores obrigatórios; não será possível gravar valores não cadastrados e ativos.

## Padrão inicial
- Categorias: Moradia, Alimentação, Transporte, Saúde, Educação, Assinaturas e serviços, Impostos e taxas, Lazer, Investimentos, Outros.
- Responsável: Próprio, mais os nomes que já existiam nas provisões do workspace.
- Todos os cadastros estão separados por workspace, inclusive futuros usuários.

## Implantação
- Migração SQL não destrutiva: `migrations/20261013_financial_catalogs.sql`; aplicar primeiro no Supabase do AXORA.
- Rebuild somente do serviço `financeiro` na Hostinger:
  `cd /docker/gestao-financeira && docker compose build --pull --no-cache financeiro && docker compose up -d --no-deps --force-recreate financeiro`
- Confirmar status healthy, login, Configurações, exportação CSV, novo cadastro, validação de nomes inativos e Provisões existentes.

## Cuidados
- O CSV é um guia de padronização, **não** importa automaticamente valores para Provisões.
- Os lançamentos guardam a descrição textual original; para futuras análises agregadas, deve-se evoluir para `catalog_id` com histórico imutável.
- Os campos de responsáveis identificam uma classificação operacional, não permissões do workspace.
