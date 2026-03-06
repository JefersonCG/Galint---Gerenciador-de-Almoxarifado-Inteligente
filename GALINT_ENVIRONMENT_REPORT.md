# GALINT - RelatÃ³rio Completo do Ambiente
**Data de GeraÃ§Ã£o:** 09/01/2026 10:34:39
**Sistema Operacional:** Microsoft Windows NT 10.0.19045.0

---
## 1. Python e Ambiente Virtual
### Python Instalado
âœ… **Python 3.10.0**

### Ambiente Virtual
âœ… **.venv/** existe

### Pacotes Python Instalados (via .venv)
```text
Package            Version
------------------ --------
alembic            1.17.2
APScheduler        3.10.4
blinker            1.9.0
certifi            2026.1.4
charset-normalizer 3.4.4
click              8.3.1
colorama           0.4.6
et_xmlfile         2.0.0
Flask              3.0.3
Flask-Login        0.6.3
Flask-Migrate      4.1.0
Flask-SQLAlchemy   3.1.1
greenlet           3.3.0
gunicorn           20.1.0
idna               3.11
itsdangerous       2.2.0
Jinja2             3.1.6
lxml               6.0.2
Mako               1.3.5
MarkupSafe         3.0.3
openpyxl           3.1.2
pillow             12.1.0
pip                25.3
psycopg2-binary    2.9.11
pyTelegramBotAPI   4.12.0
python-barcode     0.15.1
python-docx        0.8.11
python-dotenv      1.0.1
pytz               2025.2
reportlab          4.4.7
requests           2.32.3
segno              1.6.1
setuptools         57.4.0
six                1.17.0
SQLAlchemy         2.0.45
tomli              2.3.0
typing_extensions  4.15.0
tzdata             2025.3
tzlocal            5.3.1
urllib3            2.6.3
waitress           3.0.2
Werkzeug           3.1.5
```n
## 2. DependÃªncias Python (requirements.txt)
### Pacotes NecessÃ¡rios
```text
flask==3.0.3
flask-sqlalchemy==3.1.1
flask-login==0.6.3
python-dotenv==1.0.1
flask-migrate==4.1.0
psycopg2-binary==2.9.11
python-docx==0.8.11
Mako==1.3.5
openpyxl==3.1.2
requests==2.32.3
APScheduler==3.10.4
pyTelegramBotAPI==4.12.0
gunicorn==20.1.0
reportlab
waitress==3.0.2
segno==1.6.1
python-barcode==0.15.1
```n
## 3. Node.js e npm (Mobile App)
âŒ **Node.js/npm nÃ£o encontrado**

### DependÃªncias do App Mobile (package.json)
**DependÃªncias:**
```json
{
    "@react-native-async-storage/async-storage":  "2.2.0",
    "@react-navigation/native":  "^6.1.9",
    "@react-navigation/native-stack":  "^6.9.17",
    "axios":  "^1.6.2",
    "expo":  "~54.0.0",
    "expo-build-properties":  "~0.14.8",
    "expo-camera":  "~17.0.10",
    "expo-status-bar":  "~3.0.9",
    "react":  "19.1.0",
    "react-native":  "0.81.5",
    "react-native-gesture-handler":  "~2.28.0",
    "react-native-safe-area-context":  "~5.6.0",
    "react-native-screens":  "~4.16.0"
}
```n
**DependÃªncias de Desenvolvimento:**
```json
{
    "@babel/core":  "^7.20.0",
    "@expo/ngrok":  "^4.1.0",
    "babel-preset-expo":  "^54.0.8"
}
```n
## 4. PostgreSQL (Banco de Dados)
âœ… **PostgreSQL detectado:** psql (PostgreSQL) 16.11
âœ… **psql.exe:** C:\Program Files\PostgreSQL\16\bin\psql.exe

### DATABASE_URL (sanitizado)
- env override presente: **False**
- .env presente: **True**
- .env safe: **localhost:5432/galint_db**

### Teste de ConexÃ£o com o Banco (scripts/db_connection_check.py)
```text
URL (safe): localhost:5432/galint_db
host= localhost port= 5432 db= galint_db user= postgres has_password= True
TCP: OK
psql: executando teste...
psql: FALHOU (returncode=2)
psql stderr:
psql: erro: a conexÒo com o servidor em "localhost" (::1), porta 5432 falhou: FATAL:  autenticaþÒo do tipo senha falhou para o usußrio "postgres"
Dica: se aparecer 'no pg_hba.conf entry', ajuste pg_hba.conf no servidor.
```n
### ConfiguraÃ§Ã£o do Banco (config.py)
âœ… Arquivo de configuraÃ§Ã£o existe

## 5. ExtensÃµes do VS Code
### ExtensÃµes Instaladas
```text
alexcvzz.vscode-sqlite@0.14.1
ckolkman.vscode-postgres@1.4.3
cweijan.dbclient-jdbc@1.4.6
cweijan.vscode-postgresql-client2@8.4.4
dbcode.dbcode@1.26.1
github.copilot@1.388.0
github.copilot-chat@0.35.3
mechatroner.rainbow-csv@3.23.0
ms-azuretools.vscode-containers@2.3.0
ms-ceintl.vscode-language-pack-pt-br@1.108.2026010709
ms-dotnettools.csdevkit@1.90.2
ms-dotnettools.csharp@2.110.4
ms-dotnettools.vscode-dotnet-runtime@3.0.0
ms-python.debugpy@2025.18.0
ms-python.python@2026.0.0
ms-python.vscode-pylance@2025.10.4
ms-python.vscode-python-envs@1.16.0
ms-vscode.powershell@2025.4.0
philnash.ngrok-for-vscode@1.10.1
sixth.sixth-ai@0.0.64
wholroyd.jinja@0.0.8
```n
### ExtensÃµes Recomendadas
```text
ms-python.python
ms-python.vscode-pylance
ms-python.debugpy
ms-vscode.powershell
dbaeumer.vscode-eslint
esbenp.prettier-vscode
ms-azuretools.vscode-docker
mtxr.sqltools
mtxr.sqltools-driver-pg
```
## 6. Ferramentas Adicionais
âŒ **Git nÃ£o encontrado**
âœ… **uv:** uv 0.9.22 (82a6a66b8 2026-01-06)
âœ… **uvx:** uvx 0.9.22 (82a6a66b8 2026-01-06)
âš ï¸  **Expo CLI nÃ£o verificado**

## 7. Estrutura do Projeto

### Backend Flask (galint_flask/)
- **config.py** - ConfiguraÃ§Ãµes do app
- **models.py** - Modelos de banco de dados
- **extensions.py** - ExtensÃµes Flask
- **views/** - Rotas e views
- **services/** - LÃ³gica de negÃ³cio
- **templates/** - Templates Jinja2
- **templates_mako/** - Templates Mako
- **static/** - Arquivos estÃ¡ticos
- **migrations/** - MigraÃ§Ãµes do banco

### Frontend Mobile (galint-mobile/)
- **App.js** - Componente principal
- **package.json** - DependÃªncias Node.js
- **src/** - CÃ³digo-fonte do app

### Scripts
- **app.py** - Entry point da aplicaÃ§Ã£o
- **run_app.ps1** - Script de inicializaÃ§Ã£o
- **run_https.ps1** - InicializaÃ§Ã£o com HTTPS
- **scripts/** - Scripts de manutenÃ§Ã£o e configuraÃ§Ã£o

### ConfiguraÃ§Ãµes
- **requirements.txt** - DependÃªncias Python
- **instance/** - ConfiguraÃ§Ãµes de instÃ¢ncia
- **certs/** - Certificados SSL
## 8. ConfiguraÃ§Ãµes NecessÃ¡rias

### VariÃ¡veis de Ambiente (exemplo)
```bash
# PostgreSQL
DATABASE_URL=postgresql://usuario:senha@localhost:5432/galint_db

# Flask
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=sua-chave-secreta

# Telegram Bot (se usar)
TELEGRAM_BOT_TOKEN=seu-token-aqui
```

### Arquivos de ConfiguraÃ§Ã£o
- **instance/secret_key.txt** - Chave secreta do Flask
- **instance/network_settings.json** - ConfiguraÃ§Ãµes de rede
- **certs/** - Certificados SSL (se usar HTTPS)
## 9. Como Configurar em Nova MÃ¡quina

### Passo 1: Instalar Ferramentas Base
```powershell
# Python 3.9+
# Download: https://www.python.org/downloads/

# Node.js 18+
# Download: https://nodejs.org/

# PostgreSQL 13+
# Download: https://www.postgresql.org/download/

# Git
# Download: https://git-scm.com/downloads

# VS Code
# Download: https://code.visualstudio.com/
```

### Passo 2: Clonar/Copiar Projeto
```powershell
# Se usando Git
git clone <repositorio>

# Ou copiar a pasta completa
```

### Passo 3: Configurar Python
```powershell
# Criar ambiente virtual
python -m venv .venv

# Ativar ambiente
.\.venv\Scripts\Activate.ps1

# Instalar dependÃªncias
pip install -r requirements.txt
```

### Passo 4: Configurar Mobile (opcional)
```powershell
cd galint-mobile
npm install
```

### Passo 5: Configurar Banco de Dados
```powershell
# Criar banco PostgreSQL
psql -U postgres
CREATE DATABASE galint_db;

# Rodar migraÃ§Ãµes
python app.py migrate
```

### Passo 6: Instalar ExtensÃµes VS Code
```powershell
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension ms-vscode.powershell
code --install-extension mtxr.sqltools
code --install-extension mtxr.sqltools-driver-pg
```

### Passo 7: Executar AplicaÃ§Ã£o
```powershell
# Modo desenvolvimento
python app.py

# Ou usar script
.\run_app.ps1
```
