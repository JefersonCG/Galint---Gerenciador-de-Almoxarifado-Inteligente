# Script para executar o Flask com HTTPS em desenvolvimento

param(
    [string]$BindAddress = '10.0.0.245',
    [int]$Port = 5443
)

Write-Host "=== Iniciando GALINT Flask com HTTPS ===" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$certDir = Join-Path $scriptDir "certs"
$certPath = Join-Path $certDir "cert.pem"
$keyPath = Join-Path $certDir "key.pem"

# Verificar se certificados existem
if (-Not (Test-Path $certPath) -or -Not (Test-Path $keyPath)) {
    Write-Host "Certificados SSL não encontrados!" -ForegroundColor Red
    Write-Host "Gerando certificados agora..." -ForegroundColor Yellow
    & (Join-Path $scriptDir "generate_cert.ps1")
    
    if (-Not (Test-Path $certPath) -or -Not (Test-Path $keyPath)) {
        Write-Host "Falha ao gerar certificados. Abortando." -ForegroundColor Red
        exit 1
    }
}

# Ativar ambiente virtual
$cwd = (Get-Item "$scriptDir" | Resolve-Path).Path
$parent = Split-Path -Parent $cwd
$grandParent = Split-Path -Parent $parent

$candidates = @(
    (Join-Path $grandParent '.venv\Scripts\Activate.ps1'),
    (Join-Path $parent '.venv\Scripts\Activate.ps1'),
    (Join-Path $cwd '.venv\Scripts\Activate.ps1')
)

$activateScript = $null
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { $activateScript = $c; break }
}

if (-Not $activateScript) {
    Write-Error "Ambiente virtual não encontrado (procurei em .venv no diretório atual, pai e avô)." -ErrorAction Stop
}

& $activateScript

# Verificar se pyOpenSSL está instalado
Write-Host "Verificando dependências SSL..." -ForegroundColor Yellow
pip show pyOpenSSL | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando pyOpenSSL..." -ForegroundColor Yellow
    pip install pyOpenSSL
}

# Iniciar Flask com HTTPS
Write-Host "`nIniciando servidor HTTPS em https://${BindAddress}:${Port}" -ForegroundColor Green
Write-Host "Certificado: $certPath" -ForegroundColor Gray
Write-Host "Chave: $keyPath" -ForegroundColor Gray
Write-Host "`nPressione Ctrl+C para parar o servidor.`n" -ForegroundColor Yellow

Set-Location $scriptDir
$env:FLASK_APP = 'app:app'
$env:SSL_CERT_PATH = $certPath
$env:SSL_KEY_PATH = $keyPath

# Executar com SSL
python -c "
from galint_flask import create_app
import os

app = create_app()
cert_path = os.getenv('SSL_CERT_PATH')
key_path = os.getenv('SSL_KEY_PATH')

if __name__ == '__main__':
    app.run(
        host='$BindAddress',
        port=$Port,
        debug=True,
        ssl_context=(cert_path, key_path)
    )
"
