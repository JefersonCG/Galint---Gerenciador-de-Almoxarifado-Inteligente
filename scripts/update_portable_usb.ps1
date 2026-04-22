param(
    [string]$Remote = 'origin',
    [string]$Branch = 'master',
    [string]$EnvFile = ".\\.env.portable",
    [string]$PortableVenvPath = ".\\.venv_portable",
    [switch]$SkipRequirements,
    [switch]$SkipUpgrade
)

$ErrorActionPreference = 'Stop'

function Resolve-ProjectPath([string]$RootPath, [string]$PathValue) {
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path $RootPath $PathValue
}

function Import-EnvFile([string]$PathValue) {
    if (-not (Test-Path $PathValue)) {
        throw "Arquivo de ambiente nao encontrado em: $PathValue"
    }

    Get-Content $PathValue | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            return
        }

        $parts = $line.Split('=', 2)
        if ($parts.Count -ne 2) {
            return
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = (Resolve-Path (Join-Path $scriptDir ".." )).Path
Set-Location $projectRoot

$envPath = Resolve-ProjectPath -RootPath $projectRoot -PathValue $EnvFile
$venvRoot = Resolve-ProjectPath -RootPath $projectRoot -PathValue $PortableVenvPath
$pythonExe = Join-Path $venvRoot "Scripts\\python.exe"

Write-Host "=== GALINT - Atualizacao do pendrive ===" -ForegroundColor Cyan

if (-not (Test-Path $pythonExe)) {
    throw "Ambiente portatil nao encontrado em: $pythonExe`nExecute antes: .\\scripts\\setup_portable_usb.ps1"
}

$gitStatus = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao consultar o estado do Git. Verifique se o repositorio do pendrive foi clonado com .git."
}
if ($gitStatus) {
    throw "O pendrive tem alteracoes locais no repositorio. Limpe o working tree antes de atualizar."
}

Write-Host "Baixando atualizacoes de $Remote/$Branch..." -ForegroundColor Green
git pull --ff-only $Remote $Branch
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao atualizar o codigo no pendrive."
}

if (-not $SkipRequirements) {
    Write-Host "Atualizando dependencias Python..." -ForegroundColor Green
    & $pythonExe -m pip install -r requirements.txt
}

Import-EnvFile -PathValue $envPath
if (-not $env:GALINT_FEATURE_WORKSPACE_WINDOWS) { $env:GALINT_FEATURE_WORKSPACE_WINDOWS = '0' }

if (-not $SkipUpgrade) {
    Write-Host "Aplicando migrations pendentes..." -ForegroundColor Green
    & $pythonExe .\app.py upgrade
}

Write-Host "Atualizacao concluida. Reinicie pelo script start_portable_usb.ps1." -ForegroundColor Green
