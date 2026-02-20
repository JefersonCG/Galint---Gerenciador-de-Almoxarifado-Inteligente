"""Corrige entrada com codigo correto."""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Entrada, Item

app = create_app()
with app.app_context():
    # Buscar o item correto
    item_correto = db.session.query(Item).filter_by(codigo_item='7890203320561').first()
    
    if not item_correto:
        print("Item 7890203320561 NAO ENCONTRADO no banco!")
    else:
        print(f"Item encontrado: {item_correto.descricao}")
        print(f"Categoria: {item_correto.categoria}")
        
        # Buscar a entrada errada (ID 32)
        entrada_errada = db.session.query(Entrada).filter_by(id_entrada=32).first()
        
        if entrada_errada:
            print(f"\nEntrada ID 32 encontrada")
            print(f"Codigo ERRADO: {entrada_errada.codigo_item}")
            
            # Atualizar com o codigo correto
            entrada_errada.codigo_item = '7890203320561'
            
            db.session.commit()
            
            print(f"Codigo CORRIGIDO para: {entrada_errada.codigo_item}")
            print(f"Descricao: {item_correto.descricao}")
            print("\nENTRADA CORRIGIDA COM SUCESSO!")
        else:
            print("\nEntrada ID 32 nao encontrada")
