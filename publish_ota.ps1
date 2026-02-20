Param(
    [string]$Channel = 'preview',
    [string]$Message = '',
    [string]$ExpoToken = ''
)

$ErrorActionPreference = 'Stop'

try {
    if ($PSScriptRoot) {
        Set-Location -Path $PSScriptRoot
    }
}
catch {
}

try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
}
catch {
}

if (-not $Message -or $Message.Trim().Length -eq 0) {
    $Message = "OTA update $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

$nodeVer = '20.19.6'
$nodeHome = Join-Path $env:USERPROFILE "tools\node-v$nodeVer-win-x64"
if (Test-Path $nodeHome) {
    $env:Path = "$nodeHome;$env:Path"
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

# Permite rodar EAS mesmo sem Git instalado/configurado
$env:EAS_NO_VCS = '1'

# Autenticação recomendada (não-interativa)
if ($ExpoToken -and ($ExpoToken.Trim().Length -gt 0)) {
    $env:EXPO_TOKEN = $ExpoToken.Trim()
}

Write-Host "Usando Node: $(node -v)" -ForegroundColor Cyan
Write-Host "Publicando OTA: channel=$Channel" -ForegroundColor Cyan
Write-Host "Mensagem: $Message" -ForegroundColor Cyan

# Garantir dependências (para bundling)
Write-Host "Instalando dependências (npm install)..." -ForegroundColor Cyan
npm install

# Requer login: `eas login` (ou EXPO_TOKEN)
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
        eas login

        eas whoami 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Login não concluído. Confira usuário/senha (ou use EXPO_TOKEN) e tente novamente."
        }
    }
}

# Publica update OTA
# Observação: só aplica em builds com runtimeVersion compatível.
eas update --channel $Channel --message $Message

Write-Host "OTA publicada. ExitCode=$LASTEXITCODE" -ForegroundColor Cyan
