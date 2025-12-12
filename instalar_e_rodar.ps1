# Script de instalacao e execucao do GALINT Mobile
# Autor: GALINT Team
# Data: 10/12/2025

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GALINT Mobile - Instalacao e Execucao" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar se Node.js esta instalado
Write-Host "[1/4] Verificando Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    Write-Host "  Node.js encontrado: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERRO: Node.js nao encontrado!" -ForegroundColor Red
    Write-Host "  Por favor, instale Node.js de: https://nodejs.org/" -ForegroundColor Yellow
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Verificar se npm esta instalado
Write-Host "[2/4] Verificando npm..." -ForegroundColor Yellow
try {
    $npmVersion = npm --version
    Write-Host "  npm encontrado: v$npmVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERRO: npm nao encontrado!" -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Verificar se node_modules existe
if (-Not (Test-Path "node_modules")) {
    Write-Host "[3/4] Instalando dependencias (isso pode demorar alguns minutos)..." -ForegroundColor Yellow
    Write-Host "  Aguarde, baixando ~500MB de pacotes..." -ForegroundColor Cyan
    
    npm install
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Dependencias instaladas com sucesso!" -ForegroundColor Green
    } else {
        Write-Host "  ERRO ao instalar dependencias!" -ForegroundColor Red
        Read-Host "Pressione Enter para sair"
        exit 1
    }
} else {
    Write-Host "[3/4] Dependencias ja instaladas!" -ForegroundColor Green
}

Write-Host ""
Write-Host "[4/4] Iniciando servidor de desenvolvimento..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  INSTRUCOES:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "1. Um QR Code aparecera abaixo" -ForegroundColor White
Write-Host "2. Abra o app 'Expo Go' no seu Android" -ForegroundColor White
Write-Host "3. Toque em 'Scan QR Code'" -ForegroundColor White
Write-Host "4. Aponte para o QR Code na tela" -ForegroundColor White
Write-Host "5. O app GALINT abrira automaticamente!" -ForegroundColor White
Write-Host ""
Write-Host "Servidor/IP: 10.0.0.245" -ForegroundColor Cyan
Write-Host "Porta HTTPS: 5443" -ForegroundColor Cyan
Write-Host "Porta HTTP:  5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pressione Ctrl+C para parar o servidor" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Iniciar Expo
npm start
