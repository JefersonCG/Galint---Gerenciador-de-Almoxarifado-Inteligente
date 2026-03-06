# Script para instalar Poppler no Windows
# Poppler é necessário para conversão PDF->JPEG

$ErrorActionPreference = "Stop"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Instalador do Poppler para GALINT" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Configurações
$popplerVersion = "24.08.0"
$downloadUrl = "https://github.com/oschwartz10612/poppler-windows/releases/download/v$popplerVersion/Release-$popplerVersion-0.zip"
$installDir = "C:\poppler"
$zipFile = "$env:TEMP\poppler-${popplerVersion}.zip"

Write-Host "[INFO] Poppler versao: $popplerVersion" -ForegroundColor Yellow
Write-Host "[INFO] Diretorio de instalacao: $installDir" -ForegroundColor Yellow
Write-Host ""

# Verificar se ja esta instalado
$binPath = "$installDir\poppler-$popplerVersion\Library\bin"
if (Test-Path "$binPath\pdfinfo.exe") {
    Write-Host "[OK] Poppler ja esta instalado em: $binPath" -ForegroundColor Green
    Write-Host ""
    Write-Host "Deseja reinstalar? (S/N)" -ForegroundColor Yellow
    $resposta = Read-Host
    if ($resposta -ne "S" -and $resposta -ne "s") {
        Write-Host "Instalacao cancelada." -ForegroundColor Gray
        exit 0
    }
}

# Criar diretorio de instalacao
Write-Host "[1/4] Criando diretorio de instalacao..." -ForegroundColor Cyan
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

# Download
Write-Host "[2/4] Baixando Poppler..." -ForegroundColor Cyan
Write-Host "      URL: $downloadUrl" -ForegroundColor Gray
try {
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $downloadUrl -OutFile $zipFile -UseBasicParsing
    Write-Host "[OK] Download concluido!" -ForegroundColor Green
} catch {
    Write-Host "[ERRO] Erro ao baixar: $_" -ForegroundColor Red
    exit 1
}

# Extrair
Write-Host "[3/4] Extraindo arquivos..." -ForegroundColor Cyan
try {
    Expand-Archive -Path $zipFile -DestinationPath $installDir -Force
    Write-Host "[OK] Extracao concluida!" -ForegroundColor Green
} catch {
    Write-Host "[ERRO] Erro ao extrair: $_" -ForegroundColor Red
    exit 1
}

# Limpar arquivo temporario
Remove-Item $zipFile -Force -ErrorAction SilentlyContinue

# Verificar instalacao
Write-Host "[4/4] Verificando instalacao..." -ForegroundColor Cyan
$pdfinfoPaths = @(
    "$installDir\poppler-$popplerVersion\Library\bin\pdfinfo.exe",
    "$installDir\Library\bin\pdfinfo.exe"
)

$installedPath = $null
foreach ($path in $pdfinfoPaths) {
    if (Test-Path $path) {
        $installedPath = Split-Path $path -Parent
        break
    }
}

if ($installedPath) {
    Write-Host ""
    Write-Host "[OK] Poppler instalado com sucesso!" -ForegroundColor Green
    Write-Host "     Localizacao: $installedPath" -ForegroundColor Green
    Write-Host ""
    
    # Adicionar ao PATH do sistema (requer privilegios de administrador)
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
    
    Write-Host ""
    Write-Host "[INFO] Testando instalacao..." -ForegroundColor Cyan
    try {
        $output = & "$installedPath\pdfinfo.exe" -v 2>&1
        Write-Host "[OK] Poppler funcionando corretamente!" -ForegroundColor Green
        Write-Host "     Versao: $output" -ForegroundColor Gray
    } catch {
        Write-Host "[AVISO] Teste falhou, mas os arquivos foram instalados." -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host "  Instalacao concluida!" -ForegroundColor Green
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Proximos passos:" -ForegroundColor Yellow
    Write-Host "   1. Reinicie o terminal ou VS Code" -ForegroundColor Gray
    Write-Host "   2. Execute novamente: python app.py" -ForegroundColor Gray
    
} else {
    Write-Host ""
    Write-Host "[ERRO] Instalacao falhou: pdfinfo.exe nao encontrado" -ForegroundColor Red
    Write-Host "       Extraido em: $installDir" -ForegroundColor Gray
    Write-Host "       Por favor, verifique o conteudo do diretorio." -ForegroundColor Gray
    exit 1
}
