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

Para dinheiro pessoal, prefira **um projeto Supabase dedicado**, separado dos
bancos operacionais da empresa. A execução do SQL no projeto e a ativação das
credenciais devem ocorrer somente após a escolha do projeto pelo responsável.

1. Execute `supabase_schema.sql` no SQL Editor do projeto escolhido. O script
   prepara cinco tabelas, habilita RLS e remove acesso direto de
   `anon`/`authenticated`. Não crie políticas públicas para esses dados.
2. Em **Streamlit Cloud → App settings → Secrets**, adicione os três valores:

```toml
SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
SUPABASE_KEY = "SUA-CHAVE-PRIVADA-DE-SERVICO"
APP_ACCESS_PASSWORD = "SUA-SENHA-PRIVADA-FORTE"
```

3. Use exclusivamente a chave de serviço privada no backend Streamlit.
   Não insira nenhuma chave ou senha no GitHub, no navegador ou no chat.
   Não use `anon`/`publishable` para contornar as restrições de acesso.
4. O aplicativo exige senha antes de acessar o banco e só libera as páginas
   após testar (somente leitura) as cinco tabelas. Sem credenciais, continua
   funcionando em modo de sessão para validar visual e regras.
5. Faça backup do Excel original antes de habilitar o projeto, pois os dados
   em memória do modo de teste **não migram automaticamente** para o Supabase.
6. A importação inicial permite gravar nas quatro tabelas financeiras vazias.
   Se já houver dados persistidos, o sistema bloqueia a substituição para
   evitar perda acidental. Reimportação/mesclagem futura exige backup e
   operação transacional.

A senha simples desta V1 é apenas uma barreira inicial para **validação
privada**. Antes de disponibilizar o aplicativo a vários usuários, implemente
autenticação individual, autorização por usuário e políticas RLS vinculadas
à identidade de cada conta.

## Importação do Excel

No menu **Importar Excel**, selecione o `ACOMPANHAMENTOS.xlsx`. A V1 reconhece automaticamente:

- `REGISTRO DE MOVIMENTAÇÕES`
- `CONTROLE DE ENTSAÍDAS`
- `DINHEIRO`
- `DEMAIS DÍVIDAS`

A importação substitui essas quatro bases após confirmação do usuário. O arquivo `.xlsx` é ignorado pelo Git e não deve ser enviado ao repositório.

## Regra central

`REGISTRO DE MOVIMENTAÇÕES` representa o **realizado**. `CONTROLE DE ENTSAÍDAS` representa o **previsto**. As duas bases permanecem separadas para permitir cálculo de saldo real e saldo projetado sem duplicidade.
