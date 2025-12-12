Param(
    [string]$Profile = 'preview'
)

$ErrorActionPreference = 'Stop'

# Evita caracteres quebrados no terminal
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
}
catch {
}

$nodeVer = '20.19.6'
$nodeHome = Join-Path $env:USERPROFILE "tools\node-v$nodeVer-win-x64"
if (-not (Test-Path $nodeHome)) {
    throw "Node portátil não encontrado em: $nodeHome."
}

$env:Path = "$nodeHome;$env:Path"

Write-Host "Usando Node: $(node -v)" -ForegroundColor Cyan
Write-Host "Rodando build: eas build -p android --profile $Profile" -ForegroundColor Cyan

# Requer login: `eas login`
try {
    $null = eas whoami 2>$null
}
catch {
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "Você ainda NÃO está logado no EAS. Vou abrir o login agora..." -ForegroundColor Yellow
    Write-Host "Digite seu e-mail/usuário e senha do Expo." -ForegroundColor Yellow
    eas login

    eas whoami 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Login não concluído. Confira usuário/senha (ou redefina a senha em https://expo.dev) e tente novamente."
    }
}

# Na primeira vez pode perguntar para criar o projeto EAS e gerar a keystore.
eas build -p android --profile $Profile

Write-Host "Build finalizada. ExitCode=$LASTEXITCODE" -ForegroundColor Cyan
