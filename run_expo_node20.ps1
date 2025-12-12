Param(
    [switch]$Tunnel = $true,
    [switch]$Clear = $true
)

$ErrorActionPreference = 'Stop'

$nodeVer = '20.19.6'
$nodeHome = Join-Path $env:USERPROFILE "tools\node-v$nodeVer-win-x64"

if (-not (Test-Path $nodeHome)) {
    throw "Node portátil não encontrado em: $nodeHome. Baixe/extrai o Node 20 antes."
}

# Força o uso do Node 20 (compatível com Expo) nesta sessão
$env:Path = "$nodeHome;$env:Path"

# Evita que alguma configuração global deixe o Metro em "CI mode" (sem reload/watch)
$env:CI = $null

Write-Host "Usando Node: $(node -v)" -ForegroundColor Cyan

# Encerra Metro/Expo antigos para evitar prompts e conflito de porta
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$args = @('expo', 'start')
if ($Tunnel) { $args += '--tunnel' }
if ($Clear) { $args += '--clear' }

if ($Tunnel) {
    # Aumenta um pouco o tempo de conexão do ngrok (rede lenta/bloqueada costuma estourar timeout)
    $env:EXPO_TUNNEL_TIMEOUT = '120000'

    # O Expo precisa do @expo/ngrok para 'tunnel'. Em modo não-interativo isso vira erro.
    $hasNgrok = $false
    try {
        $null = npm ls @expo/ngrok --depth=0 2>$null
        if ($LASTEXITCODE -eq 0) { $hasNgrok = $true }
    }
    catch {
        $hasNgrok = $false
    }

    if (-not $hasNgrok) {
        Write-Host "Instalando dependência necessária para tunnel: @expo/ngrok..." -ForegroundColor Yellow
        npm install --save-dev @expo/ngrok@^4.1.0
    }
}

Write-Host "Rodando: npx $($args -join ' ')" -ForegroundColor Cyan
npx @args
