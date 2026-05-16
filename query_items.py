from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Entrada
from sqlalchemy import func

app = create_app()
with app.app_context():
    search_term = 'VÁLVULA DE RETENÇÃO VERTICAL 2'
    # Simplified search: filter by description containing the term, ignoring case
    # Note: Unidecode or similar would be better for accents, but we'll try ilike first
    items = Item.query.filter(Item.descricao.ilike(f'%{search_term}%')).all()
    
    if not items:
        # Try a more relaxed search if exact description with accents fails
        search_term_clean = 'VALVULA DE RETENCAO VERTICAL 2'
        items = Item.query.filter(Item.descricao.ilike(f'%{search_term_clean}%')).all()

    for item in items:
        print(f'Item: {item.codigo} | {item.descricao} | Brand: {getattr(item, "marca", "N/A")}')
        
        # DocumentoEntradaEstoque items
        doc_items = DocumentoEntradaEstoqueItem.query.filter_by(codigo_item=item.codigo).all()
        for di in doc_items:
            doc = di.documento
            if doc:
                print(f'  [Doc] NF: {doc.numero_documento} | Date: {doc.data_emissao} | Supplier: {doc.fornecedor} | Qty: {di.quantidade} | Unit: {di.valor_unitario}')
        
        # Legacy Entrada records
        entradas = Entrada.query.filter_by(codigo_item=item.codigo).all()
        for e in entradas:
            # Check if this entrada is already linked to a DocumentoEntradaEstoqueItem to avoid duplicates if possible
            # But the query asks for both, so we print them.
            print(f'  [Legacy] Date: {e.data_entrada} | Qty: {e.quantidade} | Unit: {getattr(e, "valor_unitario", "N/A")}')
        print('-' * 40)
