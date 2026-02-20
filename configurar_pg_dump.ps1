# Script para configurar pg_dump automaticamente
# Execute como Administrador

$pgDumpPath = "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
$pgBinDir = "C:\Program Files\PostgreSQL\16\bin"

Write-Host "Configurando pg_dump para o GALINT..." -ForegroundColor Cyan
Write-Host ""

# Verificar se o arquivo existe
if (-Not (Test-Path $pgDumpPath)) {
    Write-Host "ERRO: pg_dump.exe nao encontrado em $pgDumpPath" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] pg_dump encontrado: $pgDumpPath" -ForegroundColor Green

# Definir variavel BACKUP_PG_DUMP para o usuario
Write-Host "[2/3] Definindo variavel BACKUP_PG_DUMP..." -ForegroundColor Yellow
[Environment]::SetEnvironmentVariable("BACKUP_PG_DUMP", $pgDumpPath, "User")
Write-Host "      Variavel BACKUP_PG_DUMP configurada!" -ForegroundColor Green

# Adicionar ao PATH do usuario se nao existir
Write-Host "[3/3] Adicionando PostgreSQL ao PATH..." -ForegroundColor Yellow
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$pgBinDir*") {
    $newPath = $currentPath + ";" + $pgBinDir
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "      PostgreSQL adicionado ao PATH!" -ForegroundColor Green
}
else {
    Write-Host "      PostgreSQL ja esta no PATH!" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  CONFIGURACAO CONCLUIDA COM SUCESSO!" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "PROXIMOS PASSOS:" -ForegroundColor Yellow
Write-Host "1. Feche este terminal" -ForegroundColor White
Write-Host "2. Abra um NOVO terminal" -ForegroundColor White
Write-Host "3. Reinicie o servidor Flask" -ForegroundColor White
Write-Host "4. Recarregue a pagina do GALINT no navegador" -ForegroundColor White
Write-Host ""
Write-Host "A mensagem de erro deve desaparecer!" -ForegroundColor Green
Write-Host ""

Read-Host "Pressione Enter para sair"
