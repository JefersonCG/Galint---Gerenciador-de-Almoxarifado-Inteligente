Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$targetFile = 'galint_flask/templates/nf/index.html'

Push-Location $repoRoot
try {
    git restore --source=HEAD -- $targetFile
    Write-Host "Restaurado layout ERP de teste: $targetFile" -ForegroundColor Green
}
finally {
    Pop-Location
}
