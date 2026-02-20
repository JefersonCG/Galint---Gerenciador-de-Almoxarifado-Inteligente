# Script de migração SQLite -> PostgreSQL
# Executar APÓS configurar PostgreSQL e criar arquivo .env

Write-Host "=== Migração SQLite para PostgreSQL ===" -ForegroundColor Cyan

# 1. Ativar ambiente virtual
Write-Host "`n[1/5] Ativando ambiente virtual..." -ForegroundColor Yellow
& ".\.venv\Scripts\Activate.ps1"

# 2. Verificar se .env existe
if (-not (Test-Path ".env")) {
    Write-Host "`nERRO: Arquivo .env não encontrado!" -ForegroundColor Red
    Write-Host "Copie .env.production para .env e configure os valores." -ForegroundColor Yellow
    exit 1
}

# 3. Criar tabelas no PostgreSQL
Write-Host "`n[2/5] Criando estrutura de tabelas no PostgreSQL..." -ForegroundColor Yellow
python -c @"
from galint_flask import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    print('✓ Tabelas criadas com sucesso!')
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nERRO ao criar tabelas! Verifique a conexão PostgreSQL." -ForegroundColor Red
    exit 1
}

# 4. Migrar dados (se houver SQLite)
$sqlitePath = "instance\galint.db"
if (Test-Path $sqlitePath) {
    Write-Host "`n[3/5] Migrando dados do SQLite..." -ForegroundColor Yellow
    Write-Host "AVISO: Esta operação pode demorar dependendo do tamanho do banco." -ForegroundColor Yellow
    
    # Aqui você pode adicionar script de migração personalizado
    # Por enquanto, vamos apenas avisar
    Write-Host "IMPORTANTE: Migração de dados deve ser feita manualmente ou com script específico." -ForegroundColor Red
    Write-Host "Consulte: scripts/copy_sqlite_to_postgres.py" -ForegroundColor Cyan
}
else {
    Write-Host "`n[3/5] Nenhum banco SQLite encontrado. Iniciando do zero." -ForegroundColor Green
}

# 5. Criar usuário admin padrão
Write-Host "`n[4/5] Garantindo usuário administrador padrão..." -ForegroundColor Yellow
python -c @"
from galint_flask import create_app
from galint_flask.services.users import user_service
app = create_app()
with app.app_context():
    user_service.ensure_default_admin()
    print('✓ Usuário admin garantido (matrícula: 0000000000000, senha: admin)')
"@

# 6. Teste de conexão
Write-Host "`n[5/5] Testando conexão..." -ForegroundColor Yellow
python -c @"
from galint_flask import create_app, db
app = create_app()
with app.app_context():
    result = db.session.execute(db.text('SELECT 1')).scalar()
    if result == 1:
        print('✓ Conexão PostgreSQL OK!')
    else:
        print('✗ Erro na conexão')
"@

Write-Host "`n=== Migração concluída! ===" -ForegroundColor Green
Write-Host "`nPróximos passos:" -ForegroundColor Cyan
Write-Host "1. Execute: .\start_production.ps1" -ForegroundColor White
Write-Host "2. Acesse: http://localhost:5000" -ForegroundColor White
Write-Host "3. Login: 0000000000000 / admin" -ForegroundColor White
Write-Host "4. IMPORTANTE: Altere a senha padrão!" -ForegroundColor Yellow
