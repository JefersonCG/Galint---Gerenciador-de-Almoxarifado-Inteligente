"""Cria entrada de teste hoje."""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Entrada, Item, Usuario
from datetime import datetime

app = create_app()
with app.app_context():
    # Buscar um item qualquer
    item = db.session.query(Item).first()
    
    # Buscar um usuario admin
    usuario = db.session.query(Usuario).filter_by(is_admin=1).first()
    
    if item and usuario:
        # Criar entrada de HOJE
        entrada = Entrada(
            codigo_item=item.codigo_item,
            quantidade=1,
            matricula=usuario.matricula,
            data_entrada=datetime.now(),
            nota_fiscal="TESTE-HOJE-" + datetime.now().strftime("%H%M%S")
        )
        
        db.session.add(entrada)
        db.session.commit()
        
        print(f"Entrada criada: ID={entrada.id_entrada}")
        print(f"Item: {item.descricao}")
        print(f"Data/Hora: {entrada.data_entrada}")
        print(f"Nota Fiscal: {entrada.nota_fiscal}")
    else:
        print("Item ou usuario nao encontrado")
