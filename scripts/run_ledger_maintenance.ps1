param(
    [switch]$ContinueOnError
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Error "Python da virtualenv nao encontrado em $python"
    exit 10
}

$env:GALINT_DISABLE_BACKGROUND_SERVICES = 'true'

function Invoke-Step {
    param(
        [string]$Label,
        [string]$ScriptPath
    )

    Write-Host ""
    Write-Host "=== $Label ==="
    & $python $ScriptPath | Out-Host
    $exitCode = $LASTEXITCODE
    Write-Host "Codigo de saida: $exitCode"

    if ($exitCode -ne 0 -and -not $ContinueOnError) {
        exit $exitCode
    }

    return [int]$exitCode
}

$backfillExit = Invoke-Step -Label 'Backfill consolidado' -ScriptPath (Join-Path $PSScriptRoot 'backfill_ledger_inventory.py')
$orphansExit = Invoke-Step -Label 'Relatorio de orfaos' -ScriptPath (Join-Path $PSScriptRoot 'report_ledger_orphans.py')
$reconcileExit = Invoke-Step -Label 'Reconciliacao final' -ScriptPath (Join-Path $PSScriptRoot 'reconcile_ledger_inventory.py')

$finalExit = 0
foreach ($code in @($backfillExit, $orphansExit, $reconcileExit)) {
    if ($code -gt $finalExit) {
        $finalExit = $code
    }
}

Write-Host ""
Write-Host '=== Resumo final ==='
Write-Host "Backfill: $backfillExit"
Write-Host "Orfaos: $orphansExit"
Write-Host "Reconciliacao: $reconcileExit"
Write-Host "Saida final: $finalExit"

exit $finalExit