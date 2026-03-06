"""Marca as migrations como aplicadas (stamp) ou executa upgrade programaticamente.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from galint_flask import create_app
from flask_migrate import upgrade as fm_upgrade

app = create_app()

with app.app_context():
    migrations_dir = Path(app.root_path) / "migrations"
    try:
        print("Executando upgrade via Flask-Migrate (directory=...)")
        fm_upgrade(directory=str(migrations_dir))
        print("Upgrade finalizado com sucesso.")
    except Exception as e:
        print("Erro ao executar upgrade:", e)
