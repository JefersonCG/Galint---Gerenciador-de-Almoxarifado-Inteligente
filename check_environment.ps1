# ============================================================================
# GALINT - Script de Verificação e Documentação de Ambiente
# ============================================================================
# Este script documenta dependências, extensões e configurações necessárias
# para rodar o sistema GALINT completo.
#
# Uso recomendado (não-interativo):
#   .\check_environment.ps1 -NoPrompt
# ============================================================================

param(
    [string]$OutputFile = "GALINT_ENVIRONMENT_REPORT.md",
    [switch]$NoPrompt
)

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  GALINT - Análise Completa do Ambiente" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$outputFile = $OutputFile
$reportContent = @"
# GALINT - Relatório Completo do Ambiente
**Data de Geração:** $(Get-Date -Format "dd/MM/yyyy HH:mm:ss")
**Sistema Operacional:** $([System.Environment]::OSVersion.VersionString)

---

"@

# ============================================================================
# 1. PYTHON E DEPENDÊNCIAS
# ============================================================================
Write-Host "[1/8] Verificando Python e Ambiente Virtual..." -ForegroundColor Yellow

$reportContent += @"
## 1. Python e Ambiente Virtual

"@

# Verificar Python
try {
    $pythonVersion = python --version 2>&1
    $reportContent += "### Python Instalado`n✅ **$pythonVersion**`n`n"
    Write-Host "  ✅ Python encontrado: $pythonVersion" -ForegroundColor Green
} catch {
    $reportContent += "### Python Instalado`n❌ **Python não encontrado no PATH**`n`n"
    Write-Host "  ❌ Python não encontrado!" -ForegroundColor Red
}

# Verificar ambiente virtual
if (Test-Path ".venv") {
    $reportContent += "### Ambiente Virtual`n✅ **.venv/** existe`n`n"
    Write-Host "  ✅ Ambiente virtual encontrado" -ForegroundColor Green

    $venvPython = Join-Path (Resolve-Path ".venv").Path "Scripts\\python.exe"
    $venvPipList = $null
    if (Test-Path $venvPython) {
        $reportContent += "### Pacotes Python Instalados (via .venv)`n``````text`n"
        try {
            $venvPipList = & $venvPython -m pip list --disable-pip-version-check 2>&1 | Out-String
            $reportContent += $venvPipList
            $reportContent += "``````n`n"
            Write-Host "  ✅ Pacotes Python do .venv documentados" -ForegroundColor Green
        } catch {
            $reportContent += "❌ Falha ao listar pacotes do .venv: $($_.Exception.Message)`n`n"
            Write-Host "  ❌ Falha ao listar pacotes do .venv" -ForegroundColor Red
        }
    } else {
        $reportContent += "### Pacotes Python Instalados`n⚠️  **.venv encontrado, mas python.exe não localizado em .venv\\Scripts**`n`n"
        Write-Host "  ⚠️  .venv existe, mas python.exe não encontrado" -ForegroundColor Yellow
    }
} else {
    $reportContent += "### Ambiente Virtual`n❌ **.venv/** não encontrado`n`n"
    Write-Host "  ❌ Ambiente virtual não encontrado!" -ForegroundColor Red
}

# ============================================================================
# 2. REQUIREMENTS.TXT
# ============================================================================
Write-Host "[2/8] Analisando requirements.txt..." -ForegroundColor Yellow

$reportContent += @"
## 2. Dependências Python (requirements.txt)

"@

if (Test-Path "requirements.txt") {
    $requirements = Get-Content "requirements.txt"
    $reportContent += "### Pacotes Necessários`n``````text`n"
    $reportContent += ($requirements -join "`n")
    $reportContent += "`n``````n`n"
    Write-Host "  ✅ requirements.txt documentado" -ForegroundColor Green
} else {
    $reportContent += "❌ **requirements.txt não encontrado**`n`n"
    Write-Host "  ❌ requirements.txt não encontrado!" -ForegroundColor Red
}

# ============================================================================
# 3. NODE.JS E NPM (para app mobile)
# ============================================================================
Write-Host "[3/8] Verificando Node.js e npm..." -ForegroundColor Yellow

$reportContent += @"
## 3. Node.js e npm (Mobile App)

"@

try {
    $nodeVersion = node --version 2>&1
    $npmVersion = npm --version 2>&1
    $reportContent += "### Node.js e npm`n"
    $reportContent += "✅ **Node.js:** $nodeVersion`n"
    $reportContent += "✅ **npm:** $npmVersion`n`n"
    Write-Host "  ✅ Node.js: $nodeVersion" -ForegroundColor Green
    Write-Host "  ✅ npm: $npmVersion" -ForegroundColor Green
} catch {
    $reportContent += "❌ **Node.js/npm não encontrado**`n`n"
    Write-Host "  ❌ Node.js/npm não encontrado!" -ForegroundColor Red
}

# Verificar package.json do mobile
if (Test-Path "galint-mobile/package.json") {
    try {
        $packageJson = Get-Content "galint-mobile/package.json" -Raw | ConvertFrom-Json
        $reportContent += "### Dependências do App Mobile (package.json)`n"
        $reportContent += "**Dependências:**`n``````json`n"
        $reportContent += ($packageJson.dependencies | ConvertTo-Json -Depth 5)
        $reportContent += "`n``````n`n"
        $reportContent += "**Dependências de Desenvolvimento:**`n``````json`n"
        $reportContent += ($packageJson.devDependencies | ConvertTo-Json -Depth 5)
        $reportContent += "`n``````n`n"
        Write-Host "  ✅ package.json do mobile documentado" -ForegroundColor Green
    } catch {
        $reportContent += "⚠️  Falha ao ler/parsear galint-mobile/package.json: $($_.Exception.Message)`n`n"
        Write-Host "  ⚠️  Falha ao parsear package.json" -ForegroundColor Yellow
    }
}

# ============================================================================
# 4. POSTGRESQL
# ============================================================================
Write-Host "[4/8] Verificando PostgreSQL..." -ForegroundColor Yellow

$reportContent += @"
## 4. PostgreSQL (Banco de Dados)

"@

function Find-PsqlPath {
    try {
        $cmd = Get-Command psql -ErrorAction Stop
        return $cmd.Source
    } catch {
        # Tenta localizar instalação padrão do Windows
        $candidates = Get-ChildItem "C:\Program Files\PostgreSQL" -Recurse -Filter psql.exe -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        return $candidates
    }
}

$psqlPath = Find-PsqlPath
if ($psqlPath) {
    try {
        $psqlVersion = & $psqlPath --version 2>&1
        $reportContent += "✅ **PostgreSQL detectado:** $psqlVersion`n"
        $reportContent += "✅ **psql.exe:** $psqlPath`n`n"
        Write-Host "  ✅ PostgreSQL: $psqlVersion" -ForegroundColor Green
    } catch {
        $reportContent += "⚠️  **PostgreSQL detectado, mas falhou ao executar psql --version**`n"
        $reportContent += "✅ **psql.exe:** $psqlPath`n`n"
        Write-Host "  ⚠️  psql encontrado, mas não executou" -ForegroundColor Yellow
    }
} else {
    $reportContent += "❌ **PostgreSQL não encontrado (PATH nem Program Files)**`n`n"
    Write-Host "  ⚠️  PostgreSQL não encontrado no PATH" -ForegroundColor Yellow
}

# Documentar DATABASE_URL de forma segura (sem senha)
function Get-EnvValueFromFile {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path $Path)) { return $null }
    $lines = Get-Content $Path -ErrorAction SilentlyContinue
    foreach ($line in $lines) {
        $trim = $line.Trim()
        if (-not $trim) { continue }
        if ($trim.StartsWith('#')) { continue }
        if ($trim -match "^$Key\s*=\s*(.+)$") {
            return $Matches[1]
        }
    }
    return $null
}

function Mask-DbUrl {
    param([string]$Url)
    if (-not $Url) { return $null }
    $u = $Url.Trim()
    if (($u.StartsWith('"') -and $u.EndsWith('"')) -or ($u.StartsWith("'") -and $u.EndsWith("'"))) {
        $u = $u.Substring(1, $u.Length - 2)
    }
    if ($u -match '@') {
        return ($u -split '@', 2)[1]
    }
    return $u
}

$dbUrlEnv = $env:GALINT_DATABASE_URI
if (-not $dbUrlEnv) { $dbUrlEnv = $env:DATABASE_URL }
$dbUrlFile = Get-EnvValueFromFile -Path ".env" -Key "GALINT_DATABASE_URI"
if (-not $dbUrlFile) { $dbUrlFile = Get-EnvValueFromFile -Path ".env" -Key "DATABASE_URL" }
if (-not $dbUrlFile) { $dbUrlFile = Get-EnvValueFromFile -Path ".env" -Key "SQLALCHEMY_DATABASE_URI" }

$reportContent += "### DATABASE_URL (sanitizado)`n"
$reportContent += "- env override presente: **$([bool]$dbUrlEnv)**`n"
$reportContent += "- .env presente: **$([bool]$dbUrlFile)**`n"
if ($dbUrlEnv) {
    $reportContent += "- env safe: **$(Mask-DbUrl $dbUrlEnv)**`n"
}
if ($dbUrlFile) {
    $reportContent += "- .env safe: **$(Mask-DbUrl $dbUrlFile)**`n"
}
$reportContent += "`n"

# Teste de conexão usando o script Python (sem vazar senha)
if (Test-Path $venvPython) {
    if (Test-Path "scripts/db_connection_check.py") {
        try {
            $reportContent += "### Teste de Conexão com o Banco (scripts/db_connection_check.py)`n``````text`n"
            $dbCheckOut = & $venvPython "scripts/db_connection_check.py" 2>&1 | Out-String
            $reportContent += $dbCheckOut
            $reportContent += "``````n`n"
            Write-Host "  ✅ Teste de conexão com banco incluído no relatório" -ForegroundColor Green
        } catch {
            $reportContent += "⚠️  Falha ao rodar o teste de conexão com banco: $($_.Exception.Message)`n`n"
            Write-Host "  ⚠️  Falha ao rodar teste de conexão" -ForegroundColor Yellow
        }
    }
}

# Verificar configuração do banco
if (Test-Path "galint_flask/config.py") {
    $reportContent += "### Configuração do Banco (config.py)`n"
    $reportContent += "✅ Arquivo de configuração existe`n`n"
}

# ============================================================================
# 5. EXTENSÕES VS CODE
# ============================================================================
Write-Host "[5/8] Listando extensões do VS Code..." -ForegroundColor Yellow

$reportContent += @"
## 5. Extensões do VS Code

"@

try {
    $codeCmd = Get-Command code -ErrorAction Stop
    $extensions = & $codeCmd.Source --list-extensions --show-versions 2>&1
    if ($LASTEXITCODE -eq 0) {
        $reportContent += "### Extensões Instaladas`n``````text`n"
        $reportContent += ($extensions -join "`n")
        $reportContent += "`n``````n`n"
        Write-Host "  ✅ Extensões VS Code documentadas" -ForegroundColor Green
    } else {
        throw "Erro ao listar extensões"
    }
} catch {
    $reportContent += "❌ **Não foi possível listar extensões (comando 'code' não disponível no PATH)**`n`n"
    Write-Host "  ⚠️  VS Code CLI não disponível (comando 'code')" -ForegroundColor Yellow
}

# Extensões recomendadas para o projeto
$reportContent += @"
### Extensões Recomendadas
``````text
ms-python.python
ms-python.vscode-pylance
ms-python.debugpy
ms-vscode.powershell
dbaeumer.vscode-eslint
esbenp.prettier-vscode
ms-azuretools.vscode-docker
mtxr.sqltools
mtxr.sqltools-driver-pg
``````

"@

# ============================================================================
# 6. FERRAMENTAS ADICIONAIS
# ============================================================================
Write-Host "[6/8] Verificando ferramentas adicionais..." -ForegroundColor Yellow

$reportContent += @"
## 6. Ferramentas Adicionais

"@

# Git
try {
    $gitVersion = git --version 2>&1
    $reportContent += "✅ **Git:** $gitVersion`n"
    Write-Host "  ✅ Git: $gitVersion" -ForegroundColor Green
} catch {
    $reportContent += "❌ **Git não encontrado**`n"
    Write-Host "  ❌ Git não encontrado!" -ForegroundColor Red
}

# uv / uvx (Astral) - usado por algumas extensões do VS Code (ex.: microsoft/markdown)
try {
    $uvVersion = uv --version 2>&1
    $reportContent += "✅ **uv:** $uvVersion`n"
    Write-Host "  ✅ uv: $uvVersion" -ForegroundColor Green
} catch {
    $reportContent += "⚠️  **uv não encontrado no PATH** (recomendado instalar para suporte a algumas extensões)`n"
    Write-Host "  ⚠️  uv não encontrado no PATH" -ForegroundColor Yellow
}

try {
    $uvxVersion = uvx --version 2>&1
    $reportContent += "✅ **uvx:** $uvxVersion`n"
    Write-Host "  ✅ uvx: $uvxVersion" -ForegroundColor Green
} catch {
    $reportContent += "⚠️  **uvx não encontrado no PATH** (pode causar erro: O comando uvx necessário para executar microsoft/markdown não foi encontrado)`n"
    Write-Host "  ⚠️  uvx não encontrado no PATH" -ForegroundColor Yellow
}

# Expo CLI (para mobile)
try {
    $expoVersion = npx expo --version 2>&1
    $reportContent += "✅ **Expo CLI:** $expoVersion`n"
    Write-Host "  ✅ Expo CLI disponível" -ForegroundColor Green
} catch {
    $reportContent += "⚠️  **Expo CLI não verificado**`n"
    Write-Host "  ⚠️  Expo CLI não verificado" -ForegroundColor Yellow
}

$reportContent += "`n"

# ============================================================================
# 7. ESTRUTURA DO PROJETO
# ============================================================================
Write-Host "[7/8] Documentando estrutura do projeto..." -ForegroundColor Yellow

$reportContent += @"
## 7. Estrutura do Projeto

### Backend Flask (galint_flask/)
- **config.py** - Configurações do app
- **models.py** - Modelos de banco de dados
- **extensions.py** - Extensões Flask
- **views/** - Rotas e views
- **services/** - Lógica de negócio
- **templates/** - Templates Jinja2
- **templates_mako/** - Templates Mako
- **static/** - Arquivos estáticos
- **migrations/** - Migrações do banco

### Frontend Mobile (galint-mobile/)
- **App.js** - Componente principal
- **package.json** - Dependências Node.js
- **src/** - Código-fonte do app

### Scripts
- **app.py** - Entry point da aplicação
- **run_app.ps1** - Script de inicialização
- **run_https.ps1** - Inicialização com HTTPS
- **scripts/** - Scripts de manutenção e configuração

### Configurações
- **requirements.txt** - Dependências Python
- **instance/** - Configurações de instância
- **certs/** - Certificados SSL

"@

# ============================================================================
# 8. VARIÁVEIS DE AMBIENTE E CONFIGURAÇÕES
# ============================================================================
Write-Host "[8/8] Verificando configurações..." -ForegroundColor Yellow

$reportContent += @"
## 8. Configurações Necessárias

### Variáveis de Ambiente (exemplo)
``````bash
# PostgreSQL
DATABASE_URL=postgresql://usuario:senha@localhost:5432/galint_db

# Flask
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=sua-chave-secreta

# Telegram Bot (se usar)
TELEGRAM_BOT_TOKEN=seu-token-aqui
``````

### Arquivos de Configuração
- **instance/secret_key.txt** - Chave secreta do Flask
- **instance/network_settings.json** - Configurações de rede
- **certs/** - Certificados SSL (se usar HTTPS)

"@

# ============================================================================
# 9. COMANDOS DE INSTALAÇÃO
# ============================================================================
$reportContent += @"
## 9. Como Configurar em Nova Máquina

### Passo 1: Instalar Ferramentas Base
``````powershell
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
``````

### Passo 2: Clonar/Copiar Projeto
``````powershell
# Se usando Git
git clone <repositorio>

# Ou copiar a pasta completa
``````

### Passo 3: Configurar Python
``````powershell
# Criar ambiente virtual
python -m venv .venv

# Ativar ambiente
.\.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt
``````

### Passo 4: Configurar Mobile (opcional)
``````powershell
cd galint-mobile
npm install
``````

### Passo 5: Configurar Banco de Dados
``````powershell
# Criar banco PostgreSQL
psql -U postgres
CREATE DATABASE galint_db;

# Rodar migrações
python app.py migrate
``````

### Passo 6: Instalar Extensões VS Code
``````powershell
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension ms-vscode.powershell
code --install-extension mtxr.sqltools
code --install-extension mtxr.sqltools-driver-pg
``````

### Passo 7: Executar Aplicação
``````powershell
# Modo desenvolvimento
python app.py

# Ou usar script
.\run_app.ps1
``````

"@

# ============================================================================
# SALVAR RELATÓRIO
# ============================================================================
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Salvando relatório..." -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# Gravar com UTF-8 BOM para evitar caracteres quebrados em alguns viewers.
[System.IO.File]::WriteAllText($outputFile, $reportContent, (New-Object System.Text.UTF8Encoding($true)))

Write-Host ""
Write-Host "✅ Relatório gerado com sucesso!" -ForegroundColor Green
Write-Host "📄 Arquivo: $outputFile" -ForegroundColor Cyan
Write-Host ""
Write-Host "Você pode copiar este arquivo para outra máquina" -ForegroundColor Yellow
Write-Host "e usar como referência para configurar o ambiente." -ForegroundColor Yellow
Write-Host ""

# Abrir arquivo no VS Code (opcional)
if (-not $NoPrompt) {
    try {
        $response = Read-Host "Deseja abrir o relatório no VS Code? (S/N)"
        if ($response -eq "S" -or $response -eq "s") {
            $codeCmd = Get-Command code -ErrorAction Stop
            & $codeCmd.Source $outputFile
        }
    } catch {
        Write-Host "  ⚠️  Não foi possível abrir no VS Code automaticamente." -ForegroundColor Yellow
    }
}

# Garantir exit code 0 (o relatório deve ser gerado mesmo com avisos)
$global:LASTEXITCODE = 0
exit 0
