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

**Projeto escolhido:** `cuixazpxkvniqldmmnth` (Supabase existente). Em
20/09/2026 foram criadas as cinco tabelas financeiras e, posteriormente, a
tabela privada `finance_users` para identificar o usuário pela senha.
O esquema `supabase_schema.sql` já foi aplicado ao projeto conectado;
não é necessário executá-lo novamente. As seis tabelas estão com RLS
ativado e sem permissões de acesso para `anon`/`authenticated`.
Nenhuma tabela dos outros aplicativos foi alterada nesta migração.

1. Em **Streamlit Cloud → App settings → Secrets**, mantenha as credenciais privadas:

```toml
SUPABASE_URL = "https://cuixazpxkvniqldmmnth.supabase.co"
SUPABASE_KEY = "SUA-CHAVE-PRIVADA-DE-SERVICO"
APP_ACCESS_PASSWORD = "SUA-SENHA-PRIVADA-FORTE"
# Opcional, apenas para nomear o primeiro perfil:
APP_OWNER_NAME = "Júnior"
```

2. No painel do Supabase, obtenha a chave privada (`service_role` ou
   `sb_secret_...`) nas configurações de API do projeto.
   Na **primeira entrada**, se `finance_users` ainda estiver vazia, a senha
   `APP_ACCESS_PASSWORD` cria o perfil administrador com o nome de
   `APP_OWNER_NAME` (por padrão, Júnior), sem gravar a senha em texto claro.
   Depois desse primeiro cadastro, o login identifica a conta pelo hash da
   senha no banco; a senha legada deixa de funcionar como alternativa.
   Não envie segredos por mensagem nem os inclua no GitHub.
3. Use exclusivamente a chave de serviço privada no backend Streamlit.
   Não insira nenhuma chave ou senha no GitHub, no navegador ou no chat.
   Não use `anon`/`publishable` para contornar as restrições de acesso.
4. A tela inicial solicita **apenas senha**. A identidade, nome e foto são
   carregados automaticamente da conta correspondente. A verificação da
   conexão abrange as cinco tabelas financeiras e a tabela de perfis.
   Sem credenciais, o modo de teste continua em sessão local.
5. Faça backup do Excel original antes de habilitar o projeto, pois os dados
   em memória do modo de teste **não migram automaticamente** para o Supabase.
6. A importação inicial permite gravar nas quatro tabelas financeiras vazias.
   Se já houver dados persistidos, o sistema bloqueia a substituição para
   evitar perda acidental. Reimportação/mesclagem futura exige backup e
   operação transacional.

## Identificação de usuários

No primeiro login, entre com a senha que já estava em `APP_ACCESS_PASSWORD`.
Em **Configurações → Meu perfil**, salve seu nome e foto (PNG/JPEG de até 1 MB).
O perfil é recuperado automaticamente nos próximos logins.

Na seção **Configurações → Gerenciar usuários**, o administrador pode criar
outro perfil, definindo o nome e uma senha exclusiva com pelo menos 12
caracteres. O sistema rejeita senhas já utilizadas por outra conta e as
armazena como hash PBKDF2 com salt. O novo usuário acessa a tela inicial
somente com sua senha. Use **Sair / trocar usuário** em Configurações
para iniciar outra sessão.

**Atenção à privacidade:** a identificação individual e os perfis não
isolam o conteúdo das tabelas financeiras. Nesta versão, todos os usuários
cadastrados visualizam e podem alterar a mesma base de movimentações,
previsões, contas e dívidas. O cadastro de outro usuário requer
confirmação explícita desse compartilhamento. Para disponibilizar
informações financeiras privativas por pessoa, é necessária uma migração
de propriedade dos registros, autorização por usuário e políticas de acesso
aos respectivos dados antes de permitir o uso multiusuário real.

## Importação do Excel

No menu **Importar Excel**, selecione o `ACOMPANHAMENTOS.xlsx`. A V1 reconhece automaticamente:

- `REGISTRO DE MOVIMENTAÇÕES`
- `CONTROLE DE ENTSAÍDAS`
- `DINHEIRO`
- `DEMAIS DÍVIDAS`

A importação substitui essas quatro bases após confirmação do usuário. O arquivo `.xlsx` é ignorado pelo Git e não deve ser enviado ao repositório.

## Regra central

`REGISTRO DE MOVIMENTAÇÕES` representa o **realizado**. `CONTROLE DE ENTSAÍDAS` representa o **previsto**. As duas bases permanecem separadas para permitir cálculo de saldo real e saldo projetado sem duplicidade.
