# Script alternativo - Download direto do Poppler
# Versao testada e conhecida

$ErrorActionPreference = "Stop"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Instalador do Poppler (metodo alternativo)" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Usar versao conhecida e estavel
$installDir = "C:\poppler"
$tempDir = "$env:TEMP\poppler_install"

# URLs alternativas (testadas e conhecidas)
$downloads = @(
    @{
        Version = "23.07.0"
        Url = "https://github.com/oschwartz10612/poppler-windows/releases/download/v23.07.0-0/Release-23.07.0-0.zip"
    },
    @{
        Version = "22.04.0"
        Url = "https://github.com/oschwartz10612/poppler-windows/releases/download/v22.04.0-0/Release-22.04.0-0.zip"
    },
    @{
        Version = "21.11.0"
        Url = "https://github.com/oschwartz10612/poppler-windows/releases/download/v21.11.0-0/Release-21.11.0-0.zip"
    }
)

Write-Host "[INFO] Tentando baixar Poppler de diferentes versoes..." -ForegroundColor Yellow
Write-Host ""

$success = $false
$downloadedFile = $null
$versionUsed = $null

foreach ($download in $downloads) {
    Write-Host "[TESTE] Tentando versao $($download.Version)..." -ForegroundColor Cyan
    Write-Host "        URL: $($download.Url)" -ForegroundColor Gray
    
    try {
        $zipFile = "$tempDir\poppler-$($download.Version).zip"
        
        # Criar diretorio temporario
        if (-not (Test-Path $tempDir)) {
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
        }
        
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $download.Url -OutFile $zipFile -UseBasicParsing -TimeoutSec 30
        
        if (Test-Path $zipFile) {
            Write-Host "[OK] Download bem-sucedido!" -ForegroundColor Green
            $downloadedFile = $zipFile
            $versionUsed = $download.Version
            $success = $true
            break
        }
    } catch {
        Write-Host "[FALHA] Nao foi possivel baixar esta versao." -ForegroundColor Yellow
        continue
    }
}

if (-not $success) {
    Write-Host ""
    Write-Host "[ERRO] Nenhuma versao pode ser baixada automaticamente." -ForegroundColor Red
    Write-Host ""
    Write-Host "Solucao manual:" -ForegroundColor Yellow
    Write-Host "1. Acesse: https://github.com/oschwartz10612/poppler-windows/releases" -ForegroundColor Gray
    Write-Host "2. Baixe o arquivo Release-XX.XX.X-0.zip mais recente" -ForegroundColor Gray
    Write-Host "3. Extraia para: C:\poppler" -ForegroundColor Gray
    Write-Host "4. Adicione ao PATH: C:\poppler\poppler-XX.XX.X\Library\bin" -ForegroundColor Gray
    
    # Limpar temporarios
    if (Test-Path $tempDir) {
        Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    exit 1
}

# Criar diretorio de instalacao
Write-Host ""
Write-Host "[1/2] Criando diretorio de instalacao..." -ForegroundColor Cyan
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

# Extrair
Write-Host "[2/2] Extraindo arquivos..." -ForegroundColor Cyan
try {
    Expand-Archive -Path $downloadedFile -DestinationPath $installDir -Force
    Write-Host "[OK] Extracao concluida!" -ForegroundColor Green
} catch {
    Write-Host "[ERRO] Erro ao extrair: $_" -ForegroundColor Red
    exit 1
}

# Limpar temporarios
if (Test-Path $tempDir) {
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}

# Verificar instalacao - procurar em varios locais possiveis
$possiblePaths = @(
    "$installDir\poppler-$versionUsed\Library\bin",
    "$installDir\Library\bin",
    "$installDir\bin"
)

$installedPath = $null
foreach ($path in $possiblePaths) {
    if (Test-Path "$path\pdfinfo.exe") {
        $installedPath = $path
        break
    }
}

if ($installedPath) {
    Write-Host ""
    Write-Host "[OK] Poppler instalado com sucesso!" -ForegroundColor Green
    Write-Host "     Versao: $versionUsed" -ForegroundColor Green
    Write-Host "     Localizacao: $installedPath" -ForegroundColor Green
    Write-Host ""
    
    # Adicionar ao PATH do sistema
    Write-Host "[INFO] Adicionando ao PATH do sistema..." -ForegroundColor Cyan
    
    try {
        $currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
        if ($currentPath -notlike "*$installedPath*") {
            $newPath = "$installedPath;$currentPath"
            [Environment]::SetEnvironmentVariable("PATH", $newPath, "Machine")
            Write-Host "[OK] PATH atualizado! Reinicie o terminal para aplicar." -ForegroundColor Green
        } else {
            Write-Host "[OK] PATH ja contem o diretorio do Poppler." -ForegroundColor Green
        }
    } catch {
        Write-Host "[AVISO] Nao foi possivel adicionar ao PATH do sistema." -ForegroundColor Yellow
        Write-Host "        Execute este script como Administrador para adicionar ao PATH." -ForegroundColor Yellow
        Write-Host "        Ou adicione manualmente: $installedPath" -ForegroundColor Yellow
    }
    
    # Adicionar ao PATH da sessao atual
    $env:PATH = "$installedPath;$env:PATH"
    
    # Testar
    Write-Host ""
    Write-Host "[INFO] Testando instalacao..." -ForegroundColor Cyan
    try {
        $output = & "$installedPath\pdfinfo.exe" -v 2>&1
        Write-Host "[OK] Poppler funcionando!" -ForegroundColor Green
        Write-Host "     Info: $output" -ForegroundColor Gray
    } catch {
        Write-Host "[AVISO] Teste falhou, mas os arquivos foram instalados." -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "============================================="-ForegroundColor Cyan
    Write-Host "  Instalacao concluida!" -ForegroundColor Green
    Write-Host "============================================="-ForegroundColor Cyan
    Write-Host ""
    Write-Host "Reinicie seu terminal e execute: python app.py" -ForegroundColor Yellow
    
} else {
    Write-Host ""
    Write-Host "[ERRO] pdfinfo.exe nao encontrado apos extracao" -ForegroundColor Red
    Write-Host "       Por favor, verifique: $installDir" -ForegroundColor Gray
    exit 1
}
