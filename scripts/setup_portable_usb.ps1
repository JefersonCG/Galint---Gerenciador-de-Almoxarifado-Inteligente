param(
    [string]$PortablePythonPath = ".\\portable_runtime\\python\\python.exe",
    [string]$PortableVenvPath = ".\\.venv_portable",
    [string]$EnvTemplate = ".\\.env.portable.example",
    [string]$EnvTarget = ".\\.env.portable"
)

$ErrorActionPreference = 'Stop'

function Resolve-ProjectPath([string]$RootPath, [string]$PathValue) {
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path $RootPath $PathValue
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = (Resolve-Path (Join-Path $scriptDir ".." )).Path
Set-Location $projectRoot

$portablePython = Resolve-ProjectPath -RootPath $projectRoot -PathValue $PortablePythonPath
$portableVenv = Resolve-ProjectPath -RootPath $projectRoot -PathValue $PortableVenvPath
$envTemplatePath = Resolve-ProjectPath -RootPath $projectRoot -PathValue $EnvTemplate
$envTargetPath = Resolve-ProjectPath -RootPath $projectRoot -PathValue $EnvTarget

Write-Host "=== GALINT - Setup pendrive com Python portatil ===" -ForegroundColor Cyan

if (-not (Test-Path $portablePython)) {
    throw "Python portatil nao encontrado em: $portablePython`nColoque um Python Windows completo com pip/venv em portable_runtime\\python ou informe -PortablePythonPath."
}

if (-not (Test-Path $envTargetPath) -and (Test-Path $envTemplatePath)) {
    Copy-Item $envTemplatePath $envTargetPath
    Write-Host "Arquivo de ambiente criado em $envTargetPath" -ForegroundColor Yellow
    Write-Host "Edite o .env.portable antes de iniciar o sistema." -ForegroundColor Yellow
}

$venvPython = Join-Path $portableVenv "Scripts\\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Criando ambiente virtual portatil em $portableVenv..." -ForegroundColor Green
    & $portablePython -m venv $portableVenv
}

if (-not (Test-Path $venvPython)) {
    throw "Falha ao criar o ambiente virtual portatil em: $portableVenv"
}

Write-Host "Atualizando pip, setuptools e wheel..." -ForegroundColor Green
& $venvPython -m pip install --upgrade pip setuptools wheel

Write-Host "Instalando dependencias do GALINT..." -ForegroundColor Green
& $venvPython -m pip install -r requirements.txt

Write-Host "" 
Write-Host "Setup concluido." -ForegroundColor Green
Write-Host "1. Ajuste o arquivo .env.portable com a conexao PostgreSQL." -ForegroundColor White
Write-Host "2. Inicie com: powershell -ExecutionPolicy Bypass -File .\\scripts\\start_portable_usb.ps1" -ForegroundColor White
