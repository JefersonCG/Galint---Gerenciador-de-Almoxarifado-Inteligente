param(
    [string]$BackupName,
    [switch]$Latest
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python da venv não encontrado em $python"
}

Push-Location $root
try {
    $env:GALINT_DISABLE_BACKGROUND_SERVICES = "true"
    $env:GALINT_TELEGRAM_POLLING = "false"
    $env:GALINT_TELEGRAM_STARTUP_GREETING = "false"
    if ($Latest) {
        & $python -m flask --app app restore-db --latest
    }
    elseif ($BackupName) {
        & $python -m flask --app app restore-db --backup-name $BackupName
    }
    else {
        throw "Informe -Latest ou -BackupName <arquivo.sql>"
    }
}
finally {
    Pop-Location
}
