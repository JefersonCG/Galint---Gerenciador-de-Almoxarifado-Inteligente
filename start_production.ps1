# Script para iniciar GALINT Flask com PostgreSQL em produção
# Executar no servidor após configurar .env

param(
    [string]$EnvFile = ".env",
    [switch]$StartPolling
)

Write-Host "=== Iniciando GALINT Flask (PostgreSQL) ===" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

# Carregar variáveis do arquivo .env
if (Test-Path $EnvFile) {
    Write-Host "Carregando configurações de $EnvFile..." -ForegroundColor Yellow
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.+)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
            Write-Host "  $name = $value" -ForegroundColor Gray
        }
    }
}
else {
    Write-Host "AVISO: Arquivo $EnvFile não encontrado!" -ForegroundColor Red
    Write-Host "Usando configurações padrão (pode não funcionar)." -ForegroundColor Yellow
}

# Definir ambiente de produção
$env:FLASK_ENV = "production"

# Modo recomendado para ambiente local/rede interna:
# - Polling (sem webhook) como único canal de updates
# - Não manter webhook ativo
$env:GALINT_TELEGRAM_KEEP_WEBHOOK = 'false'

# Verificar venv (preferir o .venv do diretório raiz)
$cwd = (Get-Location).Path
$parent = Split-Path -Parent $cwd
$grandParent = Split-Path -Parent $parent

$candidates = @(
    (Join-Path $grandParent ".venv\Scripts\python.exe"),
    (Join-Path $parent ".venv\Scripts\python.exe"),
    (Join-Path $cwd ".venv\Scripts\python.exe")
)

$pythonExe = $null
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { $pythonExe = $c; break }
}

if (-not $pythonExe) {
    Write-Host "ERRO: Ambiente virtual não encontrado!" -ForegroundColor Red
    Write-Host "Crie um venv em .venv (na pasta atual, pai ou avô)." -ForegroundColor Yellow
    exit 1
}

Write-Host "`nIniciando servidor Waitress na porta 5000..." -ForegroundColor Green
Write-Host "Acesse: http://localhost:5000" -ForegroundColor Cyan
Write-Host "Pressione Ctrl+C para parar`n" -ForegroundColor Yellow

# Opcional: iniciar polling do Telegram (sem webhook) no mesmo host
$pollingProc = $null
if ($StartPolling) {
    # Evitar dois pollings concorrentes:
    # o servidor (create_app) por padrão iniciaria polling em background.
    # Como vamos subir um processo dedicado, desligamos o auto-polling aqui.
    $env:GALINT_TELEGRAM_POLLING = 'false'
    Write-Host "Iniciando Telegram Polling em paralelo..." -ForegroundColor Green
    $pollingProc = Start-Process -FilePath $pythonExe -ArgumentList @("-u", ".\scripts\telegram_polling.py") -WorkingDirectory (Get-Location) -PassThru -NoNewWindow
    Write-Host "Telegram Polling PID: $($pollingProc.Id)" -ForegroundColor Gray
} else {
    # Padrão: 1 processo (Waitress) com polling em background dentro do app.
    $env:GALINT_TELEGRAM_POLLING = 'true'
}

try {
    # Iniciar aplicação
    & $pythonExe -m waitress --host=0.0.0.0 --port=5000 --call galint_flask:create_app
}
finally {
    if ($pollingProc -and -not $pollingProc.HasExited) {
        Write-Host "Encerrando Telegram Polling..." -ForegroundColor Yellow
        Stop-Process -Id $pollingProc.Id -Force -ErrorAction SilentlyContinue
    }
}
