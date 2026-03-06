param(
    [string]$BindAddress = '0.0.0.0',
    [int]$Port = 5000
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Ativar ambiente virtual (preferir raiz do projeto, para evitar .venv duplicado)
$cwd = (Get-Item "$scriptDir" | Resolve-Path).Path
$parent = Split-Path -Parent $cwd
$grandParent = Split-Path -Parent $parent

$candidates = @(
    (Join-Path $grandParent '.venv\Scripts\Activate.ps1'),
    (Join-Path $parent '.venv\Scripts\Activate.ps1'),
    (Join-Path $cwd '.venv\Scripts\Activate.ps1')
)

$activateScript = $null
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { $activateScript = $c; break }
}

if (-Not $activateScript) {
    Write-Error "Ambiente virtual não encontrado (procurei em .venv no diretório atual, pai e avô)." -ErrorAction Stop
}

& $activateScript

Set-Location $scriptDir
$env:GALINT_TELEGRAM_POLLING = 'true'
$env:GALINT_TELEGRAM_KEEP_WEBHOOK = 'false'
$env:GALINT_DISABLE_BACKGROUND_SERVICES = 'false'
$env:FLASK_APP = 'app:app'
python -m flask run --host=$BindAddress --port=$Port