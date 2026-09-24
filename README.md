# DB Automate - Central Automate

Sistema de automação e monitoramento da infraestrutura de bancos de dados.

O projeto centraliza informações no PostgreSQL e utiliza agentes distribuídos nos servidores para monitorar serviços Windows, executar backups de bancos SAP SQL Anywhere e registrar o resultado das operações.

A Central Automate processa os registros enviados pelos agentes e utiliza integração com Telegram para envio de alertas e interação com os responsáveis.

---

## Arquitetura

A solução é dividida em três componentes principais:

```text
                    PostgreSQL
                      automate
                         |
                 schema db_automate
                         |
          +--------------+--------------+
          |                             |
   Monitor Agent                   Backup Agent
          |                             |
   Serviços Windows               SQL Anywhere
          |                             |
          +--------------+--------------+
                         |
                  Central Automate
                         |
                      Telegram
                         |
                    Responsáveis
```

### Monitor Agent

Executado nos servidores monitorados.

Responsável por:

- identificar automaticamente o servidor pelo hostname;
- consultar no PostgreSQL quais serviços devem ser monitorados;
- consultar o status dos serviços Windows;
- registrar os resultados no banco central;
- executar uma nova rodada de monitoramento a cada 20 minutos.

Os serviços monitorados não ficam definidos diretamente no código. A configuração é obtida através das tabelas do schema `db_automate`.

Estados registrados podem incluir, entre outros:

```text
RUNNING
STOPPED
STOPPING
NAO_ENCONTRADO
```

---

### Backup Agent

Agente responsável pela execução automática de backups dos bancos SAP SQL Anywhere.

Responsabilidades:

- identificar o servidor pelo hostname;
- consultar as bases ativas configuradas para o servidor;
- verificar a periodicidade de cada backup;
- conectar ao SQL Anywhere via ODBC;
- executar o backup;
- truncar o Transaction Log após o backup;
- registrar sucesso ou erro no PostgreSQL;
- permitir execução extraordinária através da opção de backup forçado.

O comando utilizado pelo agente segue a estrutura:

```sql
BACKUP DATABASE
DIRECTORY '<diretorio>'
TRANSACTION LOG TRUNCATE
```

A verificação da agenda de backups ocorre a cada 10 minutos.

Um backup forçado possui prioridade sobre a agenda normal. Sua execução não altera os horários do ciclo normal de backup.

---

### Central Automate

A Central é responsável por interpretar os registros produzidos pelos agentes e decidir quando um alerta deve ser enviado.

O ciclo principal executa:

1. processamento de mensagens recebidas pelo Telegram;
2. controle diário da quantidade de alertas;
3. processamento das novas rodadas de monitoramento;
4. processamento dos erros de backup.

A Central executa uma nova verificação a cada 20 minutos.

Somente novas rodadas são processadas durante a execução da aplicação, evitando o reprocessamento contínuo do mesmo resultado.

---

## Monitoramento de serviços

O Monitor Agent consulta os serviços configurados para cada servidor utilizando PowerShell:

```powershell
Get-Service -Name '<servico>'
```

O resultado é gravado em:

```text
db_automate.logs_db_automate
```

A Central consulta a última rodada de cada agente configurado com a função `Monitor`.

Quando encontra serviços com status:

```text
STOPPED
STOPPING
```

é gerado um alerta.

Exemplo:

```text
?? DB Automate - Warning

Servidor: SERVIDOR
Função: Monitor
Data: DD/MM/AAAA HH:MM:SS

Serviços interrompidos:
- SERVICO_1
- SERVICO_2
```

---

## Horários de exceção

Cada agente pode possuir períodos nos quais alertas de monitoramento não devem ser enviados.

Esses períodos são configurados no cadastro do agente através de `hora_excecao`.

Exemplo:

```text
11-12
```

Também é possível trabalhar com intervalos separados por `;`.

A Central verifica a janela de exceção antes de enviar um alerta.

Isso permite evitar falsos positivos durante períodos conhecidos de manutenção ou outras operações programadas.

---

## Monitoramento de backups

O Backup Agent registra cada tentativa na tabela:

```text
db_automate.logs_db_automate
```

Os registros podem possuir status como:

```text
SUCESSO
ERRO
```

A Central verifica o último resultado de cada base.

Quando o último backup registrado para uma base está em erro, um alerta é enviado pelo Telegram.

Exemplo:

```text
?? DB Automate - Erro de Backup

Servidor: SERVIDOR
Função: Backup
Base: BASE
Data: DD/MM/AAAA HH:MM:SS

Erro:
<detalhes do erro>

Deseja forçar uma nova tentativa de backup?

Digite 1 para SIM.
Qualquer outra resposta para NÃO.
```

---

## Backup forçado pelo Telegram

Quando um erro de backup é identificado, a Central registra uma pendência de resposta para o usuário que recebeu o alerta.

Caso seja enviada a resposta:

```text
1
```

a Central atualiza:

```text
db_automate.periodicidade_backup.forcar_backup = TRUE
```

No próximo ciclo do Backup Agent, essa base passa a ter prioridade e o backup é executado independentemente do horário normal.

Depois da tentativa, o indicador `forcar_backup` retorna para `FALSE`.

A execução forçada é emergencial e não altera a agenda normal de backups.

---

## Integração com Telegram

A integração utiliza a API de Bots do Telegram.

O módulo é responsável por:

- consultar mensagens recebidas;
- identificar `chat_id`;
- identificar nome e username;
- processar comandos;
- enviar mensagens;
- receber respostas relacionadas aos alertas de backup.

O token do bot não deve ser armazenado no código-fonte.

Ele é obtido através da variável de ambiente:

```text
DB_AUTOMATE_TELEGRAM_TOKEN
```

---

## Controle de destinatários

Os usuários que interagem com o bot podem ser registrados na tabela:

```text
db_automate.contatos
```

O controle de quantidade de mensagens utiliza:

```text
db_automate.quantidade_envios
```

A Central verifica se o contato está ativo e se ainda pode receber mensagens conforme `quantidade_atual` e `quantidade_final`.

O contador é reiniciado quando é identificado um novo dia.

---

## Banco de controle

O sistema utiliza PostgreSQL como banco central.

Database:

```text
automate
```

Schema principal:

```text
db_automate
```

Entre as estruturas utilizadas pela aplicação estão:

```text
db_automate.agentes
db_automate.funcoes
db_automate.agente_funcoes
db_automate.logs_db_automate
db_automate.contatos
db_automate.quantidade_envios
db_automate.bases
db_automate.periodicidade_backup
```

Essas tabelas controlam agentes, funções, serviços, logs, destinatários, bases e periodicidade dos backups.

---

## Configuração

### Central Automate

A Central utiliza as seguintes variáveis de ambiente:

```text
DB_AUTOMATE_HOST
DB_AUTOMATE_PORT
DB_AUTOMATE_NAME
DB_AUTOMATE_USER
DB_AUTOMATE_PASSWORD
DB_AUTOMATE_TELEGRAM_TOKEN
```

Exemplo:

```text
DB_AUTOMATE_HOST=<servidor_postgresql>
DB_AUTOMATE_PORT=54320
DB_AUTOMATE_NAME=automate
DB_AUTOMATE_USER=<usuario>
DB_AUTOMATE_PASSWORD=<senha>
DB_AUTOMATE_TELEGRAM_TOKEN=<token>
```

Nunca versionar valores reais de senha ou token.

---

### Monitor Agent

Diretório padrão:

```text
C:\Monitor_Agent
```

Configuração:

```text
C:\Monitor_Agent\.env
```

Variáveis:

```text
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD
```

O agente também mantém logs locais em:

```text
C:\Monitor_Agent\log\monitor_agent.log
```

---

### Backup Agent

Diretório padrão:

```text
C:\Backup_Agent
```

Configuração:

```text
C:\Backup_Agent\.env
```

Variáveis:

```text
DB_AUTOMATE_HOST
DB_AUTOMATE_PORT
DB_AUTOMATE_NAME
DB_AUTOMATE_USER
DB_AUTOMATE_PASSWORD
```

Logs locais:

```text
C:\Backup_Agent\log\backup_agent.log
```

---

## Dependências Python

Principais dependências externas utilizadas pelo projeto:

```text
psycopg
pyodbc
python-dotenv
```

Instalação:

```powershell
pip install psycopg pyodbc python-dotenv
```

A integração com Telegram utiliza módulos da biblioteca padrão do Python, incluindo `urllib`.

---

## Requisitos

- Windows;
- Python 3;
- PostgreSQL;
- acesso ao schema `db_automate`;
- PowerShell;
- driver ODBC do SAP SQL Anywhere nos servidores de backup;
- acesso de rede entre agentes e PostgreSQL;
- acesso dos Backup Agents às instâncias SQL Anywhere;
- acesso à API do Telegram para a Central.

---

## Estrutura do projeto

```text
Central_Automate/
|
|-- Central_Automate.py
|-- monitor_agent.py
|-- backup_agent.py
|-- backup_alertas.py
|-- Telegram.py
|-- iniciar_central.bat
|-- automate.txt
|-- README.md
|-- .gitignore
```

### Central_Automate.py

Orquestra o processamento central de monitoramento, alertas, Telegram e erros de backup.

### monitor_agent.py

Executa o monitoramento dos serviços Windows configurados para cada servidor.

### backup_agent.py

Controla a agenda e execução dos backups SQL Anywhere.

### backup_alertas.py

Processa erros de backup, controla respostas pendentes e solicita backups forçados.

### Telegram.py

Implementa a comunicação com a API do Telegram.

---

## Segurança

Arquivos e informações sensíveis não devem ser enviados ao repositório.

O `.gitignore` deve excluir pelo menos:

```gitignore
.venv/
venv/
__pycache__/
*.py[cod]

build/
dist/
*.spec

*.log

.env
.env.*
```

Senhas de PostgreSQL, credenciais de bancos SQL Anywhere e tokens do Telegram não devem ser inseridos diretamente no código-fonte.

---

## Fluxo resumido

```text
Monitor Agent
     |
     | status dos serviços
     v
PostgreSQL
     |
     v
Central Automate
     |
     | problema detectado
     v
Telegram
```

Para backups:

```text
Backup Agent
     |
     | executa backup
     v
SQL Anywhere
     |
     | resultado
     v
PostgreSQL
     |
     | erro detectado
     v
Central Automate
     |
     v
Telegram
     |
     | resposta "1"
     v
forcar_backup = TRUE
     |
     v
Backup Agent
```

---

## Versionamento

O projeto utiliza versionamento Git.

A primeira versão estável será identificada como:

```text
v1.0.0
```

Convenção sugerida:

```text
v1.0.1 - correções
v1.1.0 - novas funcionalidades compatíveis
v2.0.0 - alterações estruturais ou incompatíveis
```

---

## Status

Projeto em produção e em evolução.

Versão inicial de referência:

```text
v1.0.0
```