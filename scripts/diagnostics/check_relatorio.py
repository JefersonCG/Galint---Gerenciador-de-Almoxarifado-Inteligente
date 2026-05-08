"""Script para simular exatamente a consulta do relatório."""
from galint_flask import create_app
from galint_flask.models import Saida, Item, Usuario
from galint_flask.extensions import db

app = create_app()
with app.app_context():
    search_term = "BICO"
    
    print("=" * 60)
    print(f"SIMULANDO BUSCA POR: {search_term}")
    print("=" * 60)
    
    # Exatamente como o código faz
    item = Item.query.filter(
        db.or_(
            Item.descricao.ilike(f"%{search_term}%"),
            Item.codigo_item.ilike(f"%{search_term}%")
        )
    ).first()
    
    if not item:
        print("Item não encontrado!")
    else:
        print(f"\nItem encontrado:")
        print(f"  Código: {item.codigo_item}")
        print(f"  Descrição: {item.descricao}")
        
        # Query exata do relatório
        query = db.session.query(
            Saida.id_saida,
            Saida.quantidade,
            Saida.data_saida,
            Saida.observacao,
            Saida.matricula.label("saida_matricula"),
            Usuario.nome.label("usuario_nome"),
        ).join(
            Usuario, Saida.matricula == Usuario.matricula, isouter=True
        ).filter(
            Saida.codigo_item == item.codigo_item
        )
        
        # Sem filtro de período
        query = query.order_by(Saida.data_saida.desc())
        
        saidas = query.all()
        
        print(f"\nSaídas encontradas: {len(saidas)}")
        for saida in saidas:
            print(f"  ID: {saida.id_saida}")
            print(f"  Quantidade: {saida.quantidade}")
            print(f"  Data: {saida.data_saida}")
            print(f"  Matrícula: {saida.saida_matricula}")
            print(f"  Usuário: {saida.usuario_nome}")
            print()
        
        # Verificar se o filtro de período está causando problema
        from datetime import datetime, timedelta
        
        print("\n=== VERIFICANDO FILTROS DE PERÍODO ===")
        for days in [7, 30, 90, 0]:
            if days > 0:
                cutoff = datetime.utcnow() - timedelta(days=days)
                count = Saida.query.filter(
                    Saida.codigo_item == item.codigo_item,
                    Saida.data_saida >= cutoff
                ).count()
            else:
                count = Saida.query.filter(Saida.codigo_item == item.codigo_item).count()
            print(f"  Período {days} dias: {count} saídas")
