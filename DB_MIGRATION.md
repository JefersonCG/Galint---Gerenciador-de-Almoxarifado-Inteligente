#  Migrações de Banco (PostgreSQL-only)

Este projeto é **PostgreSQL-only** e usa Alembic/Flask-Migrate.

## Aplicar migrations
```powershell
$env:FLASK_APP='app:create_app()'
flask db upgrade
```

## Criar uma nova migration (quando o schema mudar)
```powershell
$env:FLASK_APP='app:create_app()'
flask db migrate -m "sua mensagem"
flask db upgrade
```

## Backup antes de mudanças
- Use `pg_dump` para gerar um `.sql`/`.backup` e guarde em local seguro.

Exemplo:
```powershell
pg_dump -U postgres -d galint_db -F c -f "galint_db_$(Get-Date -Format 'yyyyMMdd_HHmmss').backup"
```
