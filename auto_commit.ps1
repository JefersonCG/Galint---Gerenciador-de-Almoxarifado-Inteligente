# Script de Auto-Commit - GALINT Flask
# Executa commit automático de todas as alterações
# USO: .\auto_commit.ps1 "mensagem opcional"

param(
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"

Write-Host "`n🔍 GALINT Flask - Auto Commit" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan

# Verificar se está no diretório correto
if (-not (Test-Path ".git")) {
    Write-Host "❌ ERRO: Não está em um repositório Git!" -ForegroundColor Red
    exit 1
}

# Verificar se há alterações
$status = git status --porcelain
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "✅ Nenhuma alteração para commitar" -ForegroundColor Green
    exit 0
}

# Contar arquivos modificados/novos
$changes = ($status -split "`n").Count
Write-Host "📝 Alterações detectadas: $changes arquivos" -ForegroundColor Yellow

# Adicionar todos os arquivos
Write-Host "`n➕ Adicionando arquivos ao Git..." -ForegroundColor White
git add -A

# Gerar mensagem automática se não fornecida
if ([string]::IsNullOrWhiteSpace($Message)) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Message = "chore: auto-commit em $timestamp - $changes arquivos alterados"
}

# Fazer commit
Write-Host "💾 Fazendo commit..." -ForegroundColor White
git commit -m $Message

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ COMMIT REALIZADO COM SUCESSO!" -ForegroundColor Green
    Write-Host "📌 Mensagem: $Message" -ForegroundColor Gray
    
    # Mostrar último commit
    Write-Host "`n📊 Último commit:" -ForegroundColor Cyan
    git log -1 --pretty=format:"%h - %s (%ci)" --stat | Select-Object -First 20
    
    # Verificar submodulo mobile
    if (Test-Path "galint-mobile/.git") {
        Write-Host "`n🔄 Verificando mobile..." -ForegroundColor Yellow
        Push-Location galint-mobile
        $mobileStatus = git status --porcelain
        if (-not [string]::IsNullOrWhiteSpace($mobileStatus)) {
            Write-Host "⚠️  Mobile tem alterações pendentes!" -ForegroundColor Yellow
            Write-Host "💡 Execute: cd galint-mobile; .\auto_commit.ps1" -ForegroundColor Gray
        } else {
            Write-Host "✅ Mobile está sincronizado" -ForegroundColor Green
        }
        Pop-Location
    }
} else {
    Write-Host "`n❌ ERRO ao fazer commit!" -ForegroundColor Red
    exit 1
}

Write-Host "`n═══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "💡 Dica: Use 'git log --oneline -10' para ver histórico" -ForegroundColor Gray
