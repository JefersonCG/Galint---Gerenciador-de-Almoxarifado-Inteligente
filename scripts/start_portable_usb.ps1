param(
    [string]$EnvFile = ".\\.env.portable",
    [string]$PortableVenvPath = ".\\.venv_portable",
    [string]$BindAddress = '0.0.0.0',
    [int]$Port = 5000
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

Write-Host "=== GALINT - Pendrive com Python portatil ===" -ForegroundColor Cyan

Import-EnvFile -PathValue $envPath

if (-not (Test-Path $pythonExe)) {
    throw "Ambiente portatil nao encontrado em: $pythonExe`nExecute antes: .\\scripts\\setup_portable_usb.ps1"
}

if (-not $env:GALINT_FLASK_CONFIG) { $env:GALINT_FLASK_CONFIG = 'production' }
if (-not $env:FLASK_ENV) { $env:FLASK_ENV = 'production' }
if (-not $env:GALINT_FEATURE_WORKSPACE_WINDOWS) { $env:GALINT_FEATURE_WORKSPACE_WINDOWS = '0' }
if (-not $env:GALINT_TELEGRAM_KEEP_WEBHOOK) { $env:GALINT_TELEGRAM_KEEP_WEBHOOK = 'false' }

Write-Host "Iniciando servidor Waitress em http://localhost:$Port" -ForegroundColor Green
Write-Host "LAN: http://SEU_IP:$Port" -ForegroundColor Cyan

& $pythonExe -m waitress --host=$BindAddress --port=$Port --call galint_flask:create_app
