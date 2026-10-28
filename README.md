# Central Automate

### Plataforma de Automação, Monitoramento e Gerenciamento de Serviços e Bancos de Dados

**Versão:** 1.0.0  
**Linguagem:** Python  
**Banco de dados:** PostgreSQL  
**Integrações:** SQL Anywhere, Windows Services e Telegram  
**Categoria:** Automação de infraestrutura, monitoramento e administração de bancos de dados

---

## 1. Visão Geral

O **Central Automate** é uma solução desenvolvida em Python para centralizar e automatizar atividades operacionais relacionadas ao monitoramento de infraestrutura, gerenciamento de serviços, execução de backups e acompanhamento de processos corporativos.

O projeto foi concebido para reduzir a necessidade de intervenções manuais em rotinas administrativas, permitindo que verificações e operações recorrentes sejam executadas automaticamente, com registro de ocorrências e notificações.

A solução utiliza uma arquitetura baseada em agentes especializados, responsáveis por executar tarefas específicas e compartilhar informações por meio de um banco de dados PostgreSQL.

Entre suas principais aplicações estão o monitoramento de serviços Windows, o acompanhamento de bancos de dados SQL Anywhere, a execução automatizada de backups, a identificação de falhas operacionais e a comunicação de alertas via Telegram.

O Central Automate também contempla o acompanhamento de processos associados ao ambiente de dados, incluindo o Pombo Data Lake e o Metabase.

---

## 2. Objetivos

O desenvolvimento do Central Automate tem como principais objetivos:

- Centralizar processos de monitoramento e automação.
- Reduzir atividades operacionais repetitivas.
- Automatizar rotinas de backup de bancos de dados.
- Identificar falhas em serviços e processos.
- Disponibilizar notificações sobre ocorrências relevantes.
- Registrar informações operacionais em uma base centralizada.
- Facilitar o acompanhamento de ambientes corporativos.
- Apoiar a administração e a manutenção preventiva de sistemas.
- Permitir a expansão gradual das funcionalidades por meio de novos agentes.

A proposta é disponibilizar uma solução modular, capaz de atender diferentes necessidades de automação sem exigir a implementação de uma plataforma de monitoramento de grande porte.

---

## 3. Arquitetura da Solução

O Central Automate utiliza uma arquitetura modular composta por agentes Python, um banco de dados central PostgreSQL e integrações com serviços externos.

### Estrutura conceitual

```text
                    CENTRAL AUTOMATE
                           |
             +-------------+-------------+
             |                           |
       Orquestração                  PostgreSQL
             |                       db_automate
             |                           |
     +-------+--------+                  |
     |       |        |                  |
  Backup  Monitor   Data Agent           |
   Agent   Agent        |                |
     |       |          |                |
     |       |          |                |
SQL Anywhere |     Pombo Data Lake       |
             |       Metabase            |
      Windows Services                   |
             |                           |
             +------------+--------------+
                          |
                   Registros e Alertas
                          |
                       Telegram
```

Cada agente possui responsabilidades específicas, permitindo que diferentes rotinas sejam executadas de forma independente.

O PostgreSQL funciona como repositório central para informações de configuração, acompanhamento de execuções e registros operacionais.

---

## 4. Principais Funcionalidades

### 4.1. Monitoramento de Serviços Windows

O sistema realiza verificações periódicas de serviços do Windows, permitindo identificar situações em que componentes importantes da infraestrutura não estejam funcionando conforme o esperado.

Entre as atividades contempladas estão:

- Consulta ao estado de serviços Windows.
- Identificação de serviços interrompidos.
- Registro de ocorrências de monitoramento.
- Acompanhamento periódico dos serviços configurados.
- Integração das informações com a estrutura central de alertas.

O monitoramento é executado pelo agente especializado `monitor_agent.py`.

### 4.2. Automação de Backups

O Central Automate possui um agente dedicado à execução de backups de bancos de dados SQL Anywhere.

O processo utiliza conexões ODBC para acessar os bancos monitorados e executar os comandos de backup.

As funcionalidades incluem:

- Consulta às configurações de backup.
- Identificação de rotinas programadas.
- Execução de backups de bancos SQL Anywhere.
- Registro das execuções.
- Acompanhamento de resultados.
- Identificação de falhas.
- Integração com o banco central de controle.

O agente utiliza instruções nativas do SQL Anywhere, incluindo:

```sql
BACKUP DATABASE
```

A implementação contempla a utilização de:

```sql
TRANSACTION LOG TRUNCATE
```

O truncamento do log deve ser utilizado somente quando compatível com a estratégia de recuperação e retenção de logs do ambiente.

**Arquivo responsável:** `backup_agent.py`

### 4.3. Monitoramento e Alertas de Backup

Além da execução dos backups, o projeto contempla o acompanhamento de falhas e situações que exigem atenção.

O módulo de alertas consulta informações registradas no PostgreSQL e prepara notificações relacionadas às rotinas de backup.

Entre suas responsabilidades estão:

- Identificação de backups com falha.
- Consulta aos registros de execução.
- Preparação de mensagens de alerta.
- Integração com o Telegram.
- Tratamento de solicitações relacionadas à execução de backups.

**Arquivo responsável:** `backup_alertas.py`

### 4.4. Monitoramento de Processos de Dados

O Central Automate também contempla o acompanhamento de processos relacionados à infraestrutura de dados.

O agente especializado realiza verificações associadas ao funcionamento de componentes como:

**Pombo Data Lake**

Solução de integração e processamento de dados organizada em camadas Bronze, Silver e Gold.

O monitoramento permite acompanhar informações operacionais relacionadas à execução dos processos e identificar possíveis situações de falha ou ausência de atividade.

**Metabase**

Plataforma utilizada para consultas, análises e disponibilização de informações.

O agente contempla verificações relacionadas à disponibilidade e ao funcionamento do serviço.

**Arquivo responsável:** `Data_Agent.py`

### 4.5. Centralização de Alertas

O módulo principal é responsável pela coordenação de verificações e pelo tratamento de informações operacionais.

Suas responsabilidades incluem:

- Execução de rotinas periódicas.
- Consulta a registros de monitoramento.
- Identificação de situações que exigem notificação.
- Preparação de mensagens.
- Integração com o Telegram.
- Gerenciamento de registros locais de execução.

**Arquivo responsável:** `Central_Automate.py`

### 4.6. Integração com Telegram

O projeto utiliza a API de bots do Telegram como canal de comunicação.

Essa integração permite enviar mensagens relacionadas ao funcionamento dos agentes e às ocorrências identificadas.

Entre os recursos implementados estão:

- Comunicação com a API do Telegram.
- Envio de mensagens.
- Consulta de atualizações recebidas pelo bot.
- Apoio ao tratamento de solicitações e notificações operacionais.

**Arquivo responsável:** `Telegram.py`

---

## 5. Estrutura do Projeto

A estrutura principal do projeto é composta pelos seguintes arquivos:

```text
Central_Automate/
│
├── Central_Automate.py
│
├── Data_Agent.py
│
├── backup_agent.py
│
├── backup_alertas.py
│
├── monitor_agent.py
│
├── Telegram.py
│
├── iniciar_central.bat
│
├── Backup_Agent.spec
│
├── README.md
│
└── .gitignore
```

### Descrição dos componentes

| Arquivo | Responsabilidade |
|---|---|
| `Central_Automate.py` | Coordenação de verificações, registros e notificações |
| `Data_Agent.py` | Monitoramento de componentes da infraestrutura de dados |
| `backup_agent.py` | Execução automatizada de backups SQL Anywhere |
| `backup_alertas.py` | Tratamento de alertas e solicitações relacionadas a backups |
| `monitor_agent.py` | Monitoramento de serviços Windows |
| `Telegram.py` | Comunicação com a API do Telegram |
| `iniciar_central.bat` | Arquivo auxiliar de inicialização |
| `Backup_Agent.spec` | Configuração de empacotamento do agente de backup |
| `.gitignore` | Exclusão de arquivos locais e sensíveis do versionamento |

**Observação:** a estrutura apresentada contempla os componentes identificados no projeto. Arquivos auxiliares e configurações podem variar conforme o ambiente de instalação.

---

## 6. Tecnologias Utilizadas

### Python

Linguagem principal da solução, utilizada para implementar os agentes de monitoramento, automação e integração.

### PostgreSQL

Banco de dados utilizado para centralizar configurações, registros operacionais e informações relacionadas à execução das rotinas.

### SQL Anywhere

Sistema gerenciador de banco de dados utilizado nas rotinas automatizadas de backup.

A comunicação ocorre por meio de conexões ODBC.

### Windows Services

Recursos do sistema operacional Windows utilizados no acompanhamento do estado de serviços.

### Telegram Bot API

Interface utilizada para envio de notificações e comunicação com os agentes.

### ODBC

Tecnologia utilizada para conexão com os bancos SQL Anywhere.

---

## 7. Banco de Dados Central

O Central Automate utiliza o PostgreSQL como repositório central de informações.

A estrutura lógica contempla o schema:

```sql
db_automate
```

Esse schema concentra objetos relacionados ao funcionamento da solução.

Entre os grupos de informações utilizados pelo sistema estão:

- Configurações de agentes.
- Configurações de monitoramento.
- Programação de backups.
- Registros de execução.
- Informações sobre falhas.
- Contatos e destinatários de notificações.
- Controles operacionais.

### Exemplo de consulta

A estrutura de periodicidade de backup pode ser consultada por meio de:

```sql
SELECT *
FROM db_automate.periodicidade_backup;
```

O controle centralizado permite que os agentes consultem informações operacionais sem depender exclusivamente de configurações inseridas diretamente no código-fonte.

---

## 8. Funcionamento dos Agentes

A solução foi organizada em agentes com responsabilidades específicas.

### Central Automate

Responsável pelas verificações centrais e pela integração das informações de monitoramento com o sistema de alertas.

### Backup Agent

Responsável pela consulta de agendamentos e execução de backups SQL Anywhere.

### Monitor Agent

Responsável pela verificação periódica de serviços Windows.

### Data Agent

Responsável pelo acompanhamento de componentes e processos da infraestrutura de dados.

### Backup Alertas

Responsável pelo tratamento de alertas e solicitações relacionados aos backups.

### Telegram

Responsável pela comunicação com a API do Telegram.

A separação de responsabilidades facilita a manutenção dos componentes e permite a evolução independente de cada agente.

---

## 9. Instalação e Configuração

### 9.1. Pré-requisitos

Para executar o projeto, é necessário disponibilizar:

- Python 3.
- PostgreSQL acessível aos agentes.
- Drivers ODBC compatíveis com os bancos SQL Anywhere monitorados.
- Acesso aos serviços Windows que serão acompanhados.
- Conectividade com os sistemas monitorados.
- Credenciais de acesso aos bancos de dados.
- Bot do Telegram configurado, quando as notificações estiverem habilitadas.

### 9.2. Clonar o repositório

```powershell
git clone https://github.com/felipenunescardoso/Central-ChatBot-Automate.git
```

Acessar o diretório:

```powershell
cd Central-ChatBot-Automate
```

### 9.3. Criar o ambiente virtual

```powershell
python -m venv .venv
```

Ativar o ambiente:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 9.4. Instalar dependências

O projeto utiliza bibliotecas Python para comunicação com PostgreSQL, conexões ODBC, requisições HTTP e execução das rotinas de automação.

As dependências devem ser instaladas conforme os imports utilizados na versão publicada.

Exemplo de instalação das bibliotecas de integração:

```powershell
pip install psycopg pyodbc requests
```

O comando acima apresenta as principais bibliotecas de integração e não substitui um arquivo completo de dependências.

Recomenda-se manter um `requirements.txt` atualizado para facilitar futuras instalações.

---

## 10. Configuração de Ambiente

As configurações de conexão e autenticação devem ser mantidas fora do código-fonte sempre que possível.

O projeto utiliza variáveis de ambiente para acessar informações de conexão e autenticação.

Entre elas estão configurações relacionadas ao PostgreSQL e ao Telegram.

Exemplo ilustrativo:

```env
DB_AUTOMATE_HOST=localhost
DB_AUTOMATE_PORT=5432
DB_AUTOMATE_NAME=automate
DB_AUTOMATE_USER=usuario
DB_AUTOMATE_PASSWORD=senha

TELEGRAM_BOT_TOKEN=seu_token
```

**Atenção:** os nomes e valores devem ser conferidos com as variáveis efetivamente utilizadas na versão do código em execução.

Nunca publique senhas, tokens ou credenciais reais no repositório.

O arquivo `.gitignore` deve impedir o versionamento de arquivos `.env` contendo informações sensíveis.

---

## 11. Execução

Os agentes podem ser executados individualmente, conforme a necessidade operacional.

### Executar o módulo central

```powershell
python Central_Automate.py
```

### Executar o agente de backup

```powershell
python backup_agent.py
```

### Executar o monitoramento de serviços

```powershell
python monitor_agent.py
```

### Executar o monitoramento de dados

```powershell
python Data_Agent.py
```

O funcionamento de cada componente depende das configurações de conexão, permissões e estruturas de banco de dados exigidas pelo respectivo agente.

Em ambientes corporativos, recomenda-se avaliar a execução por meio de serviços ou agendamentos supervisionados, conforme os requisitos de disponibilidade.

---

## 12. Logs e Rastreabilidade

O projeto contempla registros operacionais para auxiliar na identificação de falhas e no acompanhamento das execuções.

Esses registros podem ser utilizados para:

- Identificar falhas de comunicação.
- Acompanhar execuções de backup.
- Verificar ocorrências relacionadas aos serviços monitorados.
- Investigar interrupções.
- Apoiar a análise de problemas operacionais.
- Registrar informações relevantes sobre o funcionamento dos agentes.

A utilização de registros centralizados no PostgreSQL contribui para a organização das informações e para a rastreabilidade das operações.

Os arquivos locais de log devem ser mantidos fora do controle de versão.

---

## 13. Segurança

A segurança das informações é um requisito importante para a operação do Central Automate.

São recomendadas as seguintes práticas:

**Proteção de credenciais**

Utilizar variáveis de ambiente ou mecanismos apropriados para armazenar informações sensíveis.

**Controle de acesso**

Conceder aos usuários e agentes apenas as permissões necessárias para executar suas atividades.

**Proteção dos backups**

Armazenar os arquivos de backup em diretórios protegidos, com políticas adequadas de retenção e recuperação.

**Proteção do Telegram**

Restringir o acesso ao bot e aos recursos de execução remota, quando disponíveis.

**Auditoria operacional**

Manter registros suficientes para identificar operações executadas e investigar ocorrências.

**Versionamento**

Não incluir credenciais, arquivos de dados, logs ou informações internas sensíveis nos commits.

---

## 14. Benefícios da Solução

A implementação do Central Automate oferece benefícios operacionais importantes.

### Redução de atividades manuais

Rotinas repetitivas podem ser executadas automaticamente, diminuindo a necessidade de acompanhamento constante.

### Monitoramento contínuo

Os agentes realizam verificações periódicas, contribuindo para a identificação antecipada de problemas.

### Centralização de informações

Configurações e registros operacionais são organizados em uma estrutura central PostgreSQL.

### Comunicação automatizada

O Telegram disponibiliza um canal de notificação para ocorrências relevantes.

### Modularidade

A arquitetura permite adicionar novas funcionalidades sem concentrar todas as responsabilidades em um único componente.

### Facilidade de manutenção

A separação dos agentes favorece a identificação de problemas e a evolução do código.

---

## 15. Possibilidades de Evolução

A arquitetura atual permite considerar futuras melhorias, conforme as necessidades operacionais.

Entre as possibilidades estão:

- Desenvolvimento de um painel web para acompanhamento dos agentes.
- Criação de indicadores de disponibilidade dos serviços.
- Implementação de dashboards de execução de backups.
- Ampliação dos recursos de auditoria.
- Centralização adicional de parâmetros operacionais.
- Implementação de mecanismos de escalonamento de alertas.
- Ampliação do monitoramento de processos corporativos.
- Integração com outras ferramentas de infraestrutura.
- Criação de relatórios consolidados de execução.
- Implantação de testes automatizados.

Essas funcionalidades representam oportunidades de evolução e não devem ser interpretadas como recursos já implementados.

---

## 16. Versionamento

O projeto utiliza Git para controle de versão e GitHub para armazenamento do código-fonte.

O desenvolvimento é organizado na branch principal:

```text
main
```

### Versão 1.0.0

A versão inicial contempla a estrutura principal dos agentes de automação e monitoramento.

**Componentes incluídos:**

- Módulo central de automação.
- Agente de monitoramento de serviços Windows.
- Agente de execução de backups SQL Anywhere.
- Módulo de alertas de backup.
- Agente de monitoramento da infraestrutura de dados.
- Integração com Telegram.
- Integração com PostgreSQL.

O versionamento permite acompanhar modificações, preservar o histórico de desenvolvimento e organizar futuras atualizações.

---

## 17. Aplicações Práticas

O Central Automate pode ser utilizado como ferramenta de apoio em ambientes que demandam administração recorrente de serviços e bancos de dados.

Entre os cenários de utilização estão:

**Administração de bancos de dados**

Automação de backups e acompanhamento das execuções.

**Infraestrutura de TI**

Monitoramento de serviços Windows e identificação de interrupções.

**Engenharia de Dados**

Acompanhamento operacional de componentes envolvidos no processamento e na disponibilização de dados.

**Operações de TI**

Centralização de verificações periódicas e notificações.

**Automação corporativa**

Redução de tarefas manuais e padronização de procedimentos operacionais.

---

## 18. Considerações Finais

O **Central Automate** representa uma abordagem prática para automação e monitoramento de ambientes corporativos, combinando Python, PostgreSQL, SQL Anywhere e integrações com serviços externos.

Sua arquitetura baseada em agentes permite distribuir responsabilidades, organizar processos e facilitar a manutenção das rotinas operacionais.

O projeto demonstra a aplicação de conceitos de desenvolvimento de software, administração de bancos de dados, integração de sistemas e automação de infraestrutura em uma solução voltada a necessidades reais de operação.

A proposta é manter uma base tecnológica modular, organizada e preparada para evoluir conforme o surgimento de novas demandas.

---

## 19. Autor

**Felipe Nunes**

Desenvolvimento de soluções em:

- Engenharia de Dados.
- Administração de Bancos de Dados.
- Automação de Processos.
- Integração de Sistemas.
- Business Intelligence.
- Desenvolvimento Python.
- Monitoramento de Infraestrutura.

**GitHub:** felipenunescardoso

---

**Central Automate — Automação, monitoramento e inteligência operacional em uma única solução.**
