param(
    [string]$PgData = "C:\Program Files\PostgreSQL\16\data",
    [string]$ServiceName = "postgresql-x64-16",
    [string]$DbUser = "postgres"
)

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Host "ERRO: execute este script como Administrador." -ForegroundColor Red
    exit 2
}

$hba = Join-Path $PgData "pg_hba.conf"
$psql = Join-Path (Split-Path $PgData -Parent) "bin\psql.exe"

if (-not (Test-Path $hba)) {
    Write-Host "ERRO: pg_hba.conf não encontrado em: $hba" -ForegroundColor Red
    exit 3
}
if (-not (Test-Path $psql)) {
    Write-Host "ERRO: psql.exe não encontrado em: $psql" -ForegroundColor Red
    exit 4
}

$newPassword = Read-Host "Digite a NOVA senha para o usuário $DbUser" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($newPassword))

$bak = "$hba.bak_reset_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Copy-Item $hba $bak -Force
Write-Host "Backup criado: $bak" -ForegroundColor Green

# Inserir regra trust temporária só para loopback IPv4 do usuário alvo
$trustLine = "host    all             $DbUser         127.0.0.1/32            trust"
$content = Get-Content $hba
if (-not ($content -contains $trustLine)) {
    $out = New-Object System.Collections.Generic.List[string]
    $inserted = $false
    foreach ($l in $content) {
        if (-not $inserted -and $l -match '^host\s+all\s+all\s+127\.0\.0\.1/32') {
            $out.Add($trustLine)
            $inserted = $true
        }
        $out.Add($l)
    }
    if (-not $inserted) {
        $out.Add($trustLine)
    }
    Set-Content -Path $hba -Value $out -Encoding ASCII
    Write-Host "Regra trust temporária adicionada para 127.0.0.1/32 ($DbUser)" -ForegroundColor Yellow
} else {
    Write-Host "Regra trust temporária já existia." -ForegroundColor Yellow
}

Restart-Service $ServiceName -Force
Write-Host "Serviço reiniciado (trust temporário ativo)" -ForegroundColor Yellow

# Alterar senha via conexão local trust
$env:PGPASSWORD = ""
& $psql -h 127.0.0.1 -U $DbUser -d postgres -c "ALTER USER \"$DbUser\" WITH PASSWORD '$plain';" | Out-Null
Write-Host "Senha atualizada para o usuário $DbUser" -ForegroundColor Green

# Restaurar pg_hba.conf
Copy-Item $bak $hba -Force
Write-Host "pg_hba.conf restaurado" -ForegroundColor Green

Restart-Service $ServiceName -Force
Write-Host "Serviço reiniciado (config original restaurada)" -ForegroundColor Green

Write-Host "Próximo passo: atualize o DATABASE_URL na .env com a nova senha e rode scripts/db_connection_check.py" -ForegroundColor Cyan
