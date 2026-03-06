"""Testar busca com acentos."""
from galint_flask import create_app
from galint_flask.models import Item
from galint_flask.extensions import db

app = create_app()
with app.app_context():
    termos = ['fibraco', 'fibraço', 'FIBRACO', 'FIBRAÇO', 'fibra']
    for t in termos:
        item = Item.query.filter(Item.descricao.ilike(f'%{t}%')).first()
        if item:
            print(f"'{t}' -> ENCONTROU: {item.descricao}")
        else:
            print(f"'{t}' -> NAO ENCONTROU")
