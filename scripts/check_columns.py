"""Verifica se as colunas foram adicionadas à tabela telegram_config."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from galint_flask import create_app
from galint_flask.extensions import db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.session.get_bind())
    cols = inspector.get_columns('telegram_config')
    print('Colunas encontradas em telegram_config:')
    for c in cols:
        print('-', c['name'], c.get('type'))
