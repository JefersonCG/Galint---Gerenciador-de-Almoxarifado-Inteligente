# Script de Instalacao - Scanner de Codigo de Barras via Telegram
# Uso: .\instalar_scanner.ps1

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  Scanner de Codigo de Barras - Instalacao Automatica" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

$pythonExe = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "[ERRO] Python nao encontrado" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Python encontrado" -ForegroundColor Green
Write-Host ""

# ETAPA 1: Verificar bibliotecas
Write-Host "-------------------------------------------------------" -ForegroundColor Yellow
Write-Host " ETAPA 1: Verificando bibliotecas existentes..." -ForegroundColor Yellow
Write-Host "-------------------------------------------------------" -ForegroundColor Yellow

$checkLibs = @"
try:
    import pyzbar
    print('pyzbar: OK')
    pyzbar_ok = True
except ImportError:
    print('pyzbar: FALTANDO')
    pyzbar_ok = False

try:
    import cv2
    print('opencv: OK')
    cv2_ok = True
except ImportError:
    print('opencv: FALTANDO')
    cv2_ok = False

exit(0 if (pyzbar_ok and cv2_ok) else 1)
"@

$libsInstalled = $false
& $pythonExe -c $checkLibs
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Todas as bibliotecas ja instaladas!" -ForegroundColor Green
    $libsInstalled = $true
} else {
    Write-Host "[INFO] Algumas bibliotecas precisam ser instaladas" -ForegroundColor Yellow
}
Write-Host ""

# ETAPA 2: Instalar bibliotecas
if (-not $libsInstalled) {
    Write-Host "-------------------------------------------------------" -ForegroundColor Yellow
    Write-Host " ETAPA 2: Instalando bibliotecas..." -ForegroundColor Yellow
    Write-Host "-------------------------------------------------------" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Instalando: pyzbar" -ForegroundColor Cyan
    Write-Host "   Instalando: opencv-python-headless" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   [AVISO] Isso pode levar alguns minutos (download ~40MB)" -ForegroundColor DarkYellow
    Write-Host ""
    
    & $pythonExe -m pip install --upgrade pip --quiet
    & $pythonExe -m pip install pyzbar opencv-python-headless==4.8.1.78
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "[ERRO] Falha na instalacao das bibliotecas" -ForegroundColor Red
        Write-Host "   Tente instalar manualmente:" -ForegroundColor Yellow
        Write-Host "   $pythonExe -m pip install pyzbar opencv-python-headless" -ForegroundColor White
        exit 1
    }
    
    Write-Host ""
    Write-Host "[OK] Bibliotecas instaladas!" -ForegroundColor Green
    Write-Host ""
}

# ETAPA 3: Verificar campo no banco
Write-Host "-------------------------------------------------------" -ForegroundColor Yellow
Write-Host " ETAPA 3: Verificando banco de dados..." -ForegroundColor Yellow
Write-Host "-------------------------------------------------------" -ForegroundColor Yellow

$checkDB = @"
from galint_flask import create_app
from galint_flask.extensions import db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('telegram_users')]
    
    if 'can_withdraw_via_telegram' in columns:
        print('Campo can_withdraw_via_telegram: OK')
        exit(0)
    else:
        print('Campo can_withdraw_via_telegram: FALTANDO')
        exit(1)
"@

$fieldExists = $false
& $pythonExe -c $checkDB 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Campo 'can_withdraw_via_telegram' ja existe!" -ForegroundColor Green
    $fieldExists = $true
} else {
    Write-Host "[INFO] Campo 'can_withdraw_via_telegram' nao encontrado" -ForegroundColor Yellow
}
Write-Host ""

# ETAPA 4: Executar migration
if (-not $fieldExists) {
    Write-Host "-------------------------------------------------------" -ForegroundColor Yellow
    Write-Host " ETAPA 4: Executando migration..." -ForegroundColor Yellow
    Write-Host "-------------------------------------------------------" -ForegroundColor Yellow
    Write-Host ""
    
    & $pythonExe -m flask db upgrade
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "[ERRO] Falha ao executar migration" -ForegroundColor Red
        Write-Host "   Tente executar manualmente:" -ForegroundColor Yellow
        Write-Host "   $pythonExe -m flask db upgrade" -ForegroundColor White
        exit 1
    }
    
    Write-Host ""
    Write-Host "[OK] Migration executada!" -ForegroundColor Green
    Write-Host ""
}

# ETAPA 5: Teste final
Write-Host "-------------------------------------------------------" -ForegroundColor Yellow
Write-Host " ETAPA 5: Verificacao final..." -ForegroundColor Yellow
Write-Host "-------------------------------------------------------" -ForegroundColor Yellow

$finalCheck = @"
from galint_flask.utils.barcode_photo_processor import BarcodePhotoProcessor

if BarcodePhotoProcessor.is_available():
    print('Scanner: DISPONIVEL')
    exit(0)
else:
    missing = BarcodePhotoProcessor.get_missing_libraries()
    print(f'Scanner: NAO DISPONIVEL (faltando: {missing})')
    exit(1)
"@

& $pythonExe -c $finalCheck
$scannerReady = ($LASTEXITCODE -eq 0)

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  RESUMO DA INSTALACAO" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

if ($libsInstalled -or $scannerReady) {
    Write-Host "Bibliotecas:      [OK]" -ForegroundColor Green
} else {
    Write-Host "Bibliotecas:      [ERRO]" -ForegroundColor Red
}

if ($fieldExists -or $scannerReady) {
    Write-Host "Banco de Dados:   [OK]" -ForegroundColor Green
} else {
    Write-Host "Banco de Dados:   [ERRO]" -ForegroundColor Red
}

if ($scannerReady) {
    Write-Host "Scanner:          [DISPONIVEL]" -ForegroundColor Green
} else {
    Write-Host "Scanner:          [NAO DISPONIVEL]" -ForegroundColor Red
}

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan

if ($scannerReady) {
    Write-Host ""
    Write-Host "[SUCESSO] Instalacao concluida!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Proximos passos:" -ForegroundColor Cyan
    Write-Host "  1. Acesse: Configuracoes -> Telegram" -ForegroundColor White
    Write-Host "  2. Habilite retiradas para usuarios desejados" -ForegroundColor White
    Write-Host "  3. Teste enviando /scanear no Telegram" -ForegroundColor White
    Write-Host ""
    Write-Host "Documentacao: TELEGRAM_SCANNER_BARCODE.md" -ForegroundColor Cyan
    Write-Host ""
    exit 0
} else {
    Write-Host ""
    Write-Host "[ERRO] Instalacao incompleta" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Para completar, execute:" -ForegroundColor Yellow
    Write-Host "  .\instalar_scanner.ps1" -ForegroundColor White
    Write-Host ""
    exit 1
}
