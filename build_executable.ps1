# Script para gerar executavel do GALINT
# Uso: .\build_executable.ps1

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "   GALINT - Build Executavel" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Verificar se esta no venv
if (-not $env:VIRTUAL_ENV) {
    Write-Host "AVISO: Virtual environment nao detectado!" -ForegroundColor Yellow
    Write-Host "Ativando .venv..." -ForegroundColor Yellow
    & .\.venv\Scripts\Activate.ps1
}

# Verificar PyInstaller
Write-Host "[1/5] Verificando PyInstaller..." -ForegroundColor Green
$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyinstaller) {
    Write-Host "PyInstaller nao encontrado. Instalando..." -ForegroundColor Yellow
    pip install pyinstaller
}

# Limpar builds antigos
Write-Host "[2/5] Limpando builds antigos..." -ForegroundColor Green
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}
if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}

# Ler versao
Write-Host "[3/5] Lendo versao..." -ForegroundColor Green
$version = Get-Content "version.txt" -ErrorAction SilentlyContinue
if (-not $version) {
    $version = "1.0.0"
}
Write-Host "Versao: $version" -ForegroundColor Cyan

# Build
Write-Host "[4/5] Compilando executavel..." -ForegroundColor Green
Write-Host "Isso pode levar alguns minutos..." -ForegroundColor Yellow
pyinstaller galint.spec --clean
if ($LASTEXITCODE -ne 0) {
    Write-Host "" 
    Write-Host "ERRO: PyInstaller retornou codigo $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

# Verificar resultado
Write-Host "[5/5] Verificando build..." -ForegroundColor Green
if (Test-Path "dist\GALINT\GALINT.exe") {
    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Green
    Write-Host "   BUILD CONCLUIDO!" -ForegroundColor Green
    Write-Host "=====================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Executavel criado:" -ForegroundColor Cyan
    Write-Host "  dist\GALINT\GALINT.exe" -ForegroundColor White
    Write-Host ""
    
    $size = (Get-Item "dist\GALINT\GALINT.exe").Length / 1MB
    Write-Host "Tamanho: $([math]::Round($size, 2)) MB" -ForegroundColor Cyan
    
    Write-Host ""
    Write-Host "Proximos passos:" -ForegroundColor Yellow
    Write-Host "  1. Testar: .\dist\GALINT\GALINT.exe" -ForegroundColor White
    Write-Host "  2. Criar instalador: .\build_installer.ps1" -ForegroundColor White
    Write-Host "  3. Distribuir para clientes" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "ERRO: Falha no build!" -ForegroundColor Red
    Write-Host "Verifique os logs acima." -ForegroundColor Red
    exit 1
}
