"""Cria a tabela de autorizações de descarte de materiais avariados."""
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import DescarteAutorizacao

app = create_app()
with app.app_context():
    DescarteAutorizacao.__table__.create(bind=db.engine, checkfirst=True)
    print("Tabela 'descarte_autorizacoes' garantida no banco.")
