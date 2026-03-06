import os
import sys

# Garantir que o diretório do projeto está no path (quando executado via venv)
sys.path.insert(0, os.getcwd())

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import RetiradaFerramenta

app = create_app()

with app.app_context():
    total = RetiradaFerramenta.query.filter_by(status='em_uso').count()
    print(f"TOTAL_EM_USO={total}")
    recent = (
        RetiradaFerramenta.query
        .filter_by(status='em_uso')
        .order_by(RetiradaFerramenta.data_retirada.desc())
        .limit(50)
        .all()
    )
    for r in recent:
        print(f"ID={r.id} COD={r.codigo_item} MAT={r.matricula} QTD={r.quantidade} DATA={r.data_retirada} DESCR={getattr(r.item, 'descricao', None)}")
