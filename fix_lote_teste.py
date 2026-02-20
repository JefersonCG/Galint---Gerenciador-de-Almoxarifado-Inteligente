"""Script para reverter alteração de teste no item 7891035539947"""
from galint_flask import create_app
from galint_flask.models import Item, Entrada
from galint_flask.extensions import db

app = create_app()
with app.app_context():
    # Encontrar o item
    item = Item.query.get('7891035539947')
    if item:
        print(f"Item: {item.descricao}")
        print(f"Lote atual: {item.lote}")
        
        # Reverter o lote
        item.lote = '25255DHL4'
        
        # Remover a entrada de teste (a última entrada desse item com 5 unidades)
        entrada_teste = Entrada.query.filter_by(codigo_item='7891035539947').order_by(Entrada.id_entrada.desc()).first()
        if entrada_teste and entrada_teste.quantidade == 5:
            print(f"Removendo entrada de teste: {entrada_teste.quantidade} unidades (ID: {entrada_teste.id_entrada})")
            db.session.delete(entrada_teste)
        
        db.session.commit()
        print(f"Lote restaurado para: {item.lote}")
        print("CORRIGIDO!")
    else:
        print("Item não encontrado")
