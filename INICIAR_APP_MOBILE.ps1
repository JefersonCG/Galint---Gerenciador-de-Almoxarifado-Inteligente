# Script principal para iniciar o app mobile GALINT
# Este script inicia tanto o servidor Flask quanto o app mobile

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GALINT - Iniciando Sistema Completo" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$flaskPath = "C:\Users\LUIS\Desktop\GALINT FLASK"
$mobilePath = "C:\Users\LUIS\Desktop\GALINT FLASK\galint-mobile"

# Verificar se pastas existem
if (-Not (Test-Path $flaskPath)) {
    Write-Host "ERRO: Pasta Flask nao encontrada!" -ForegroundColor Red
    exit 1
}

if (-Not (Test-Path $mobilePath)) {
    Write-Host "ERRO: Pasta Mobile nao encontrada!" -ForegroundColor Red
    exit 1
}

Write-Host "[1/2] Iniciando servidor Flask (HTTP)..." -ForegroundColor Yellow

# Iniciar Flask em nova janela
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$flaskPath'; .\.venv\Scripts\Activate.ps1; python app.py"

Write-Host "  Servidor Flask iniciado em nova janela!" -ForegroundColor Green
Write-Host "  Aguardando servidor inicializar..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "[2/2] Iniciando app mobile..." -ForegroundColor Yellow

# Ir para pasta mobile
Set-Location $mobilePath

# Verificar se node_modules existe
if (-Not (Test-Path "node_modules")) {
    Write-Host "  Instalando dependencias (primeira execucao)..." -ForegroundColor Cyan
    npm install
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SISTEMA INICIADO COM SUCESSO!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Flask Server: http://10.0.0.245:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "INSTRUCOES PARA O CELULAR:" -ForegroundColor Yellow
Write-Host "1. Abra o app 'Expo Go' no Android" -ForegroundColor White
Write-Host "2. Escaneie o QR Code abaixo" -ForegroundColor White
Write-Host "3. O app GALINT abrira automaticamente" -ForegroundColor White
Write-Host ""
Write-Host "Configuracao no app:" -ForegroundColor Cyan
Write-Host "  IP: 10.0.0.245" -ForegroundColor White
Write-Host "  Porta: 5000" -ForegroundColor White
Write-Host "  Protocolo: HTTP" -ForegroundColor White
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Iniciar Expo
npm start
# Script principal para iniciar o app mobile GALINT
# Este script inicia tanto o servidor Flask quanto o app mobile

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GALINT - Iniciando Sistema Completo" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$flaskPath = "C:\Users\LUIS\Desktop\GALINT FLASK"
$mobilePath = "C:\Users\LUIS\Desktop\GALINT FLASK\galint-mobile"

# Verificar se pastas existem
if (-Not (Test-Path $flaskPath)) {
    Write-Host "ERRO: Pasta Flask nao encontrada!" -ForegroundColor Red
    exit 1
}

if (-Not (Test-Path $mobilePath)) {
    Write-Host "ERRO: Pasta Mobile nao encontrada!" -ForegroundColor Red
    exit 1
}

Write-Host "[1/2] Iniciando servidor Flask (HTTP)..." -ForegroundColor Yellow

# Iniciar Flask em nova janela
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$flaskPath'; .\.venv\Scripts\Activate.ps1; python app.py"

Write-Host "  Servidor Flask iniciado em nova janela!" -ForegroundColor Green
Write-Host "  Aguardando servidor inicializar..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "[2/2] Iniciando app mobile..." -ForegroundColor Yellow

# Ir para pasta mobile
Set-Location $mobilePath

# Verificar se node_modules existe
if (-Not (Test-Path "node_modules")) {
    Write-Host "  Instalando dependencias (primeira execucao)..." -ForegroundColor Cyan
    npm install
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SISTEMA INICIADO COM SUCESSO!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Flask Server: http://10.0.0.245:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "INSTRUCOES PARA O CELULAR:" -ForegroundColor Yellow
Write-Host "1. Abra o app 'Expo Go' no Android" -ForegroundColor White
Write-Host "2. Escaneie o QR Code abaixo" -ForegroundColor White
Write-Host "3. O app GALINT abrira automaticamente" -ForegroundColor White
Write-Host ""
Write-Host "Configuracao no app:" -ForegroundColor Cyan
Write-Host "  IP: 10.0.0.245" -ForegroundColor White
Write-Host "  Porta: 5000" -ForegroundColor White
Write-Host "  Protocolo: HTTP" -ForegroundColor White
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Iniciar Expo
npm start
