Param(
    [string]$Profile = 'preview',
    [string]$ExpoToken = ''
)

$ErrorActionPreference = 'Stop'

# Sempre roda a partir da pasta do projeto (evita erro do EAS sobre "project directory")
try {
    if ($PSScriptRoot) {
        Set-Location -Path $PSScriptRoot
    }
}
catch {
}

# Evita caracteres quebrados no terminal
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
}
catch {
}

$nodeVer = '20.19.6'
$nodeHome = Join-Path $env:USERPROFILE "tools\node-v$nodeVer-win-x64"
if (Test-Path $nodeHome) {
    $env:Path = "$nodeHome;$env:Path"
}
else {
    Write-Host "Node portátil não encontrado em: $nodeHome" -ForegroundColor Yellow
    Write-Host "Vou usar o Node instalado no sistema (node no PATH)." -ForegroundColor Yellow
}

try {
    $null = node -v
}
catch {
    throw "Node.js não encontrado. Instale o Node (recomendado Node 20) e tente novamente."
}

# Garantir eas-cli
try {
    $null = Get-Command eas -ErrorAction Stop
}
catch {
    Write-Host "eas-cli não encontrado. Instalando via npm (global)..." -ForegroundColor Yellow
    npm install -g eas-cli
}

Write-Host "Usando Node: $(node -v)" -ForegroundColor Cyan
Write-Host "Rodando build: eas build -p android --profile $Profile" -ForegroundColor Cyan

# Permite rodar EAS mesmo sem Git instalado/configurado
$env:EAS_NO_VCS = '1'

# Em alguns ambientes Windows/OneDrive, o cálculo automático de fingerprint pode demorar/travar.
# Pular essa etapa torna o build mais previsível (principalmente para builds manuais/replicação).
if (-not $env:EAS_SKIP_AUTO_FINGERPRINT) {
    $env:EAS_SKIP_AUTO_FINGERPRINT = '1'
}

# Autenticação recomendada (não-interativa)
if ($ExpoToken -and ($ExpoToken.Trim().Length -gt 0)) {
    $env:EXPO_TOKEN = $ExpoToken.Trim()
}

# Garantir dependências instaladas (inclui plugins de build como expo-build-properties)
# Seguindo o guia de replicação: usar npm install (mais tolerante em ambientes Windows).
Write-Host "Instalando dependências (npm install)..." -ForegroundColor Cyan
npm install

# Requer login: `eas login`
# Alternativa (recomendado para evitar prompts): usar EXPO_TOKEN.
try {
    $null = eas whoami 2>$null
}
catch {
}

if ($LASTEXITCODE -ne 0) {
    if ($env:EXPO_TOKEN) {
        Write-Host "EXPO_TOKEN detectado. Continuando sem login interativo..." -ForegroundColor Cyan
    }
    else {
        Write-Host "Você ainda NÃO está logado no EAS. Vou abrir o login agora..." -ForegroundColor Yellow
        Write-Host "Digite seu e-mail/usuário e senha do Expo." -ForegroundColor Yellow
        eas login

        eas whoami 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Login não concluído. Confira usuário/senha (ou use EXPO_TOKEN) e tente novamente."
        }
    }
}

# Na primeira vez pode perguntar para criar o projeto EAS e gerar a keystore.
# Depois de configurado, rodar em modo não-interativo evita prompts (ex.: instalar em emulador/ADB).
Write-Host "EAS_NO_VCS=$env:EAS_NO_VCS" -ForegroundColor DarkGray
Write-Host "EAS_SKIP_AUTO_FINGERPRINT=$env:EAS_SKIP_AUTO_FINGERPRINT" -ForegroundColor DarkGray
eas build -p android --profile $Profile --non-interactive

Write-Host "Build finalizada. ExitCode=$LASTEXITCODE" -ForegroundColor Cyan
