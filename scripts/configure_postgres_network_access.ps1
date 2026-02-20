param(
    [Parameter(Mandatory=$true)]
    [string]$ClientCidr,

    [string]$Database = "galint_db",
    [string]$DbUser = "postgres",
    [ValidateSet('scram-sha-256','md5','trust','reject','password')]
    [string]$AuthMethod = "scram-sha-256",

    [string]$PgData = "C:\Program Files\PostgreSQL\16\data",
    [string]$ServiceName = "postgresql-x64-16",

    [switch]$OpenFirewall
)

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$hba = Join-Path $PgData "pg_hba.conf"
if (-not (Test-Path $hba)) {
    Write-Host "ERRO: pg_hba.conf não encontrado em: $hba" -ForegroundColor Red
    Write-Host "Ajuste -PgData para o diretório data do PostgreSQL." -ForegroundColor Yellow
    exit 2
}

$line = "host    $Database    $DbUser    $ClientCidr    $AuthMethod"

$bak = "$hba.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Copy-Item $hba $bak -Force
Write-Host "Backup criado: $bak" -ForegroundColor Green

$content = Get-Content $hba -ErrorAction Stop
if ($content -contains $line) {
    Write-Host "Regra já existe no pg_hba.conf" -ForegroundColor Yellow
} else {
    $out = New-Object System.Collections.Generic.List[string]
    $inserted = $false

    foreach ($l in $content) {
        $out.Add($l)
        if (-not $inserted -and $l -match '^host\s+all\s+all\s+127\.0\.0\.1/32') {
            $out.Add($line)
            $inserted = $true
        }
    }

    if (-not $inserted) {
        $out.Add("")
        $out.Add("# GALINT - regra adicionada automaticamente")
        $out.Add($line)
    }

    Set-Content -Path $hba -Value $out -Encoding ASCII
    Write-Host "Inserida regra: $line" -ForegroundColor Green
}

if ($OpenFirewall) {
    try {
        $ruleName = "PostgreSQL 5432 (GALINT)"
        $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if (-not $existing) {
            New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5432 -RemoteAddress $ClientCidr | Out-Null
            Write-Host "Firewall liberado: TCP 5432 para $ClientCidr" -ForegroundColor Green
        } else {
            Write-Host "Firewall: regra já existe ($ruleName)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Falha ao ajustar Firewall: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

if (-not (Test-IsAdmin)) {
    Write-Host "ATENÇÃO: sem privilégios de Administrador não dá para reiniciar/recarregar o serviço." -ForegroundColor Yellow
    Write-Host "Reabra o PowerShell como Administrador e rode: Restart-Service $ServiceName" -ForegroundColor Yellow
    exit 0
}

try {
    Restart-Service $ServiceName -Force
    Write-Host "Serviço reiniciado: $ServiceName" -ForegroundColor Green
} catch {
    Write-Host "Falha ao reiniciar serviço ($ServiceName): $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "Você pode reiniciar manualmente em services.msc" -ForegroundColor Yellow
}
