# Gestão Financeira

Aplicativo Streamlit criado a partir da lógica do arquivo `ACOMPANHAMENTOS.xlsx`.

## Escopo da V1

- Dashboard com realizado, previsto, saldos e dívidas.
- Registro de movimentações efetivamente realizadas.
- Contas e previsões futuras separadas do caixa realizado.
- Contas/saldos para conciliação do dinheiro localizado.
- Controle de dívidas renegociadas e não renegociadas.
- Importação do Excel atual sem armazenar o arquivo no GitHub.
- Configuração de metas financeiras.

Os módulos de **Supermercado**, **Descontos Unimed**, **Notas UNIPAM** e **Corridas** não fazem parte do núcleo financeiro da V1. Eles podem ser incorporados depois sem alterar a arquitetura principal.

## Rodar localmente

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Publicar no Streamlit Cloud

1. Crie o app apontando para este repositório.
2. Defina `streamlit_app.py` como arquivo principal.
3. Para testar layout e importação, o app funciona sem banco em modo de sessão.
4. Para persistência, configure o Supabase conforme abaixo.

## Configurar Supabase

Execute `supabase_schema.sql` no SQL Editor do projeto Supabase.

Depois, em **Streamlit Cloud > App settings > Secrets**, adicione:

```toml
SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
SUPABASE_KEY = "SUA-CHAVE"
```

Nunca coloque a chave em um arquivo versionado no GitHub.

## Importação do Excel

No menu **Importar Excel**, selecione o `ACOMPANHAMENTOS.xlsx`. A V1 reconhece automaticamente:

- `REGISTRO DE MOVIMENTAÇÕES`
- `CONTROLE DE ENTSAÍDAS`
- `DINHEIRO`
- `DEMAIS DÍVIDAS`

A importação substitui essas quatro bases após confirmação do usuário. O arquivo `.xlsx` é ignorado pelo Git e não deve ser enviado ao repositório.

## Regra central

`REGISTRO DE MOVIMENTAÇÕES` representa o **realizado**. `CONTROLE DE ENTSAÍDAS` representa o **previsto**. As duas bases permanecem separadas para permitir cálculo de saldo real e saldo projetado sem duplicidade.
