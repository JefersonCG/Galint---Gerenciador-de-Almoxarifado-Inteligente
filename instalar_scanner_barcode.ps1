# Script de Instalacao - Scanner de Codigo de Barras
# 
# Este script instala e configura o sistema de retiradas via Telegram
# com scanner de codigo de barras integrado.
#
# Uso: .\instalar_scanner_barcode.ps1

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  INSTALADOR - Scanner Codigo de Barras via Telegram" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# Definir caminho do Python
$pythonExe = ".\.venv\Scripts\python.exe"

# Verificar se Python existe
if (-not (Test-Path $pythonExe)) {
    Write-Host "[ERRO] Python nao encontrado em $pythonExe" -ForegroundColor Red
    Write-Host "   Execute primeiro: .\setup_ambiente_dev.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Python encontrado: $pythonExe" -ForegroundColor Green
Write-Host ""

# ======================================================
# ETAPA 1: Verificar bibliotecas existentes
# ======================================================

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "📦 ETAPA 1: Verificando bibliotecas..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow

$checkLibs = @"
try:
    import pyzbar
    print('pyzbar: ✓')
    pyzbar_ok = True
except ImportError:
    print('pyzbar: ✗')
    pyzbar_ok = False

try:
    import cv2
    print('opencv: ✓')
    cv2_ok = True
except ImportError:
    print('opencv: ✗')
    cv2_ok = False

exit(0 if (pyzbar_ok and cv2_ok) else 1)
"@

$libsInstalled = $false
& $pythonExe -c $checkLibs
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Todas as bibliotecas já estão instaladas!" -ForegroundColor Green
    $libsInstalled = $true
} else {
    Write-Host "⚠️  Algumas bibliotecas estão faltando" -ForegroundColor Yellow
}
Write-Host ""

# ======================================================
# ETAPA 2: Instalar bibliotecas (se necessário)
# ======================================================

if (-not $libsInstalled -and -not $SkipLibraries -and -not $TestOnly) {
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    Write-Host "📥 ETAPA 2: Instalando bibliotecas..." -ForegroundColor Yellow
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Instalando: pyzbar" -ForegroundColor Cyan
    Write-Host "   Instalando: opencv-python-headless==4.8.1.78" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   ⏳ Isso pode levar alguns minutos (download ~40MB)..." -ForegroundColor DarkYellow
    Write-Host ""
    
    & $pythonExe -m pip install --upgrade pip | Out-Null
    & $pythonExe -m pip install pyzbar opencv-python-headless==4.8.1.78
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "❌ ERRO: Falha na instalação das bibliotecas" -ForegroundColor Red
        Write-Host "   Tente instalar manualmente:" -ForegroundColor Yellow
        Write-Host "   $pythonExe -m pip install pyzbar opencv-python-headless" -ForegroundColor White
        exit 1
    }
    
    Write-Host ""
    Write-Host "✅ Bibliotecas instaladas com sucesso!" -ForegroundColor Green
    Write-Host ""
} elseif (-not $libsInstalled -and $SkipLibraries) {
    Write-Host "⚠️  AVISO: Instalação de bibliotecas pulada (--SkipLibraries)" -ForegroundColor Yellow
    Write-Host ""
}

# ======================================================
# ETAPA 3: Verificar campo no banco de dados
# ======================================================

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "🗄️  ETAPA 3: Verificando banco de dados..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow

$checkDB = @"
from galint_flask import create_app
from galint_flask.extensions import db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('telegram_users')]
    
    if 'can_withdraw_via_telegram' in columns:
        print('Campo exists: ✓')
        exit(0)
    else:
        print('Campo exists: ✗')
        exit(1)
"@

$fieldExists = $false
& $pythonExe -c $checkDB 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Campo 'can_withdraw_via_telegram' já existe!" -ForegroundColor Green
    $fieldExists = $true
} else {
    Write-Host "⚠️  Campo 'can_withdraw_via_telegram' não encontrado" -ForegroundColor Yellow
}
Write-Host ""

# ======================================================
# ETAPA 4: Executar migration (se necessário)
# ======================================================

if (-not $fieldExists -and -not $SkipMigration -and -not $TestOnly) {
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    Write-Host "🔧 ETAPA 4: Executando migration..." -ForegroundColor Yellow
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    Write-Host ""
    
    & $pythonExe -m flask db upgrade
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "❌ ERRO: Falha ao executar migration" -ForegroundColor Red
        Write-Host "   Tente executar manualmente:" -ForegroundColor Yellow
        Write-Host "   $pythonExe -m flask db upgrade" -ForegroundColor White
        exit 1
    }
    
    Write-Host ""
    Write-Host "✅ Migration executada com sucesso!" -ForegroundColor Green
    Write-Host ""
} elseif (-not $fieldExists -and $SkipMigration) {
    Write-Host "⚠️  AVISO: Migration pulada (--SkipMigration)" -ForegroundColor Yellow
    Write-Host ""
}

# ======================================================
# ETAPA 5: Teste final
# ======================================================

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "✅ ETAPA 5: Verificação final..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow

$finalCheck = @"
from galint_flask.utils.barcode_photo_processor import BarcodePhotoProcessor

if BarcodePhotoProcessor.is_available():
    print('Scanner: ✓')
    exit(0)
else:
    missing = BarcodePhotoProcessor.get_missing_libraries()
    print(f'Scanner: ✗ (faltando: {missing})')
    exit(1)
"@

& $pythonExe -c $finalCheck
$scannerReady = ($LASTEXITCODE -eq 0)

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "      📊 RESUMO DA INSTALAÇÃO" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

if ($libsInstalled -or -not $SkipLibraries) {
    Write-Host "📦 Bibliotecas:        $('✅ OK' )" -ForegroundColor Green
} else {
    Write-Host "📦 Bibliotecas:        $('⚠️  PULADO' )" -ForegroundColor Yellow
}

if ($fieldExists -or -not $SkipMigration) {
    Write-Host "🗄️  Banco de Dados:    $('✅ OK' )" -ForegroundColor Green
} else {
    Write-Host "🗄️  Banco de Dados:    $('⚠️  PULADO' )" -ForegroundColor Yellow
}

if ($scannerReady) {
    Write-Host "📸 Scanner:            $('✅ DISPONÍVEL' )" -ForegroundColor Green
} else {
    Write-Host "📸 Scanner:            $('❌ NÃO DISPONÍVEL' )" -ForegroundColor Red
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

if ($scannerReady) {
    Write-Host ""
    Write-Host "🎉 INSTALAÇÃO CONCLUÍDA COM SUCESSO!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📖 Próximos passos:" -ForegroundColor Cyan
    Write-Host "   1. Acesse: Configurações → Telegram" -ForegroundColor White
    Write-Host "   2. Habilite retiradas para usuários desejados" -ForegroundColor White
    Write-Host "   3. Teste enviando /scanear no Telegram" -ForegroundColor White
    Write-Host ""
    Write-Host "📄 Documentação completa: TELEGRAM_SCANNER_BARCODE.md" -ForegroundColor Cyan
    Write-Host ""
    exit 0
} else {
    Write-Host ""
    Write-Host "⚠️  INSTALAÇÃO INCOMPLETA" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Para completar, execute:" -ForegroundColor Yellow
    Write-Host "   .\instalar_scanner_barcode.ps1" -ForegroundColor White
    Write-Host ""
    exit 1
}
