# PYZBAR - DLLs Necessarias para Windows
#
# O pyzbar precisa das seguintes DLLs nativas:
# - libiconv.dll
# - libzbar-64.dll (ou libzbar-32.dll para sistemas 32-bit)
#
# SOLUCAO 1: Instalar via pip-system-certs (recomendado)
# pip install pyzbar[scripts]
# python -m pyzbar.scripts.read_zbar <image_file>
#
# SOLUCAO 2: Baixar DLLs manualmente
# 1. Download: https://github.com/NaturalHistoryMuseum/pyzbar/releases
# 2. Extrair DLLs para: .venv\Lib\site-packages\pyzbar\
#
# SOLUCAO 3: Usar zxing-cpp (alternativa mais moderna)
# pip uninstall pyzbar
# pip install zxing-cpp
# 
# Esta biblioteca usa C++ nativo e funciona melhor no Windows

Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host "  INSTALACAO DE DLLS PARA PYZBAR" -ForegroundColor Yellow
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "[INFO] O pyzbar precisa de DLLs nativas do Windows" -ForegroundColor Cyan
Write-Host ""
Write-Host "Opcao 1: Usar ZXING-CPP (recomendado para Windows)" -ForegroundColor Green
Write-Host "  - Mais moderno e nao precisa de DLLs extras" -ForegroundColor White
Write-Host "  - Performance superior" -ForegroundColor White
Write-Host "  - Suporta mais formatos" -ForegroundColor White
Write-Host ""
Write-Host "Comando:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe -m pip uninstall pyzbar -y" -ForegroundColor White
Write-Host "  .\.venv\Scripts\python.exe -m pip install zxing-cpp" -ForegroundColor White
Write-Host ""
Write-Host "Opcao 2: Baixar DLLs do pyzbar manualmente" -ForegroundColor Yellow
Write-Host "  1. Download: https://github.com/NaturalHistoryMuseum/pyzbar/releases" -ForegroundColor White
Write-Host "  2. Extrair libiconv.dll e libzbar-64.dll" -ForegroundColor White
Write-Host "  3. Copiar para: .venv\Lib\site-packages\pyzbar\" -ForegroundColor White
Write-Host ""
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host ""

$resposta = Read-Host "Deseja instalar ZXING-CPP agora? (S/N)"

if ($resposta -eq "S" -or $resposta -eq "s") {
    Write-Host ""
    Write-Host "[INFO] Desinstalando pyzbar..." -ForegroundColor Cyan
    .\.venv\Scripts\python.exe -m pip uninstall pyzbar -y
    
    Write-Host ""
    Write-Host "[INFO] Instalando zxing-cpp..." -ForegroundColor Cyan
    .\.venv\Scripts\python.exe -m pip install zxing-cpp
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "[SUCESSO] ZXING-CPP instalado!" -ForegroundColor Green
        Write-Host ""
        Write-Host "[INFO] Agora e necessario atualizar o codigo para usar zxing-cpp" -ForegroundColor Yellow
        Write-Host "       O codigo sera atualizado automaticamente..." -ForegroundColor Yellow
    } else {
        Write-Host ""
        Write-Host "[ERRO] Falha na instalacao" -ForegroundColor Red
    }
} else {
    Write-Host ""
    Write-Host "[INFO] Instalacao cancelada" -ForegroundColor Yellow
    Write-Host "       Siga as instrucoes acima para instalar manualmente" -ForegroundColor White
}
