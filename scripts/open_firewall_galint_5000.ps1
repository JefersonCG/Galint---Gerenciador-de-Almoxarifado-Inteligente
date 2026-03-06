param(
    [string]$RuleName = "GALINT Flask 5000",
    [string]$RemoteAddress = "LocalSubnet"
)

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Host "ERRO: execute este script como Administrador." -ForegroundColor Red
    Write-Host "Dica: clique com o botão direito no PowerShell > Executar como administrador." -ForegroundColor Yellow
    exit 2
}

$existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Regra já existe: $RuleName" -ForegroundColor Yellow
    exit 0
}

New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5000 -RemoteAddress $RemoteAddress -Profile Any | Out-Null
Write-Host "OK: liberada porta 5000 para $RemoteAddress" -ForegroundColor Green
