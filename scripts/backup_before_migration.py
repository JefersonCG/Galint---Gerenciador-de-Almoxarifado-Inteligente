"""Backup do banco antes de aplicar migrações.

PostgreSQL-only: usa pg_dump para gerar um .sql.
"""
import sys
from pathlib import Path
import subprocess
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from galint_flask import create_app
app = create_app()
with app.app_context():
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    parsed = urlparse(uri)
    backups_dir = ROOT / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)

    if parsed.scheme.startswith('postgres') or parsed.scheme.startswith('postgresql'):
        # tentar usar pg_dump
        out_file = backups_dir / f'pg_backup_{__import__("datetime").datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.sql'
        cmd = ['pg_dump', f'--dbname={uri}', '--file', str(out_file)]
        try:
            subprocess.check_call(cmd)
            print('pg_dump salvo em', out_file)
            sys.exit(0)
        except FileNotFoundError:
            print('pg_dump não encontrado no PATH. Instale psql/pg_dump ou faça backup manualmente.')
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print('pg_dump retornou erro:', e)
            sys.exit(1)

    print('Tipo de banco não suportado automaticamente. URI=', uri)
    print('Faça backup manualmente antes de prosseguir.')
    sys.exit(1)
