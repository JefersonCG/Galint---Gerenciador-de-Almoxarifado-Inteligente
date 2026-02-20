#  Configuração de Ambiente de Desenvolvimento - GALINT (PostgreSQL-only)

Este projeto roda **somente com PostgreSQL**.

##  Pré-requisitos
- Windows 10/11
- Python 3.10+
- PostgreSQL 14+ (inclui `psql` e `pg_dump`)
- (Opcional) VS Code

##  Setup rápido (Windows PowerShell)

1) Criar e ativar venv
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) Instalar dependências
```powershell
pip install -r requirements.txt
```

3) Configurar variáveis de ambiente
Crie um `.env` na raiz (ou exporte no terminal):
```env
DATABASE_URL=postgresql://usuario:senha@localhost:5432/galint_db
SECRET_KEY=uma-chave-secreta
```

4) Aplicar migrations
```powershell
$env:FLASK_APP='app:create_app()'
flask db upgrade
```

5) Subir a aplicação
```powershell
python app.py
```

##  Troubleshooting
- Se der erro de conexão, valide host/porta/usuário/senha do `DATABASE_URL`.
- Se `psql`/`pg_dump` não forem encontrados, instale o PostgreSQL e garanta que o `bin` esteja no `PATH`.
