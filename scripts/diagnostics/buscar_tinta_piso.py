#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Busca item TINTA PISO PREMIUM BRANCA."""

from app import app
from galint_flask.extensions import db
from galint_flask.models import Item, InventarioEvento

if __name__ == '__main__':
    with app.app_context():
        print("="*80)
        print("BUSCANDO TINTA PISO PREMIUM BRANCA")
        print("="*80)
        
        # Tentar com codigo exato
        item = Item.query.filter_by(codigo_item="7891323879497").first()
        
        if not item:
            # Buscar por descricao
            items = Item.query.filter(
                Item.descricao.ilike("%TINTA PISO PREMIUM BRANCA%")
            ).all()
            
            if items:
                print(f"\nEncontrados {len(items)} itens com 'TINTA PISO PREMIUM BRANCA':")
                for it in items:
                    print(f"\n  Codigo: {it.codigo_item}")
                    print(f"  Descricao: {it.descricao}")
                    print(f"  Embalagens: {it.estoque_embalagens}")
                    print(f"  Soltas: {it.estoque_unidades_soltas}")
                    print(f"  litros_por_embalagem: {it.litros_por_embalagem}")
                    
                    # Ver ultimo evento
                    ultimo = InventarioEvento.query.filter_by(
                        codigo_item=it.codigo_item
                    ).order_by(InventarioEvento.data_evento.desc()).first()
                    
                    if ultimo:
                        print(f"  Ultimo evento: {ultimo.id_evento} - {ultimo.data_evento}")
                        print(f"    Descricao: {ultimo.descricao[:100]}")
            else:
                print("\nNenhum item encontrado com 'TINTA PISO PREMIUM BRANCA'")
                
                # Buscar por codigo parcial
                items = Item.query.filter(
                    Item.codigo_item.like("%7891323879497%")
                ).all()
                
                if items:
                    print(f"\nItens com codigo similar:")
                    for it in items:
                        print(f"  {it.codigo_item} - {it.descricao}")
                else:
                    # Buscar todos itens com "PISO"
                    items = Item.query.filter(Item.descricao.ilike("%PISO%")).limit(5).all()
                    print(f"\nAlguns itens com 'PISO':")
                    for it in items:
                        print(f"  {it.codigo_item} - {it.descricao}")
        else:
            print(f"\nItem encontrado!")
            print(f"Codigo: {item.codigo_item}")
            print(f"Descricao: {item.descricao}")
            print(f"Embalagens: {item.estoque_embalagens}")
            print(f"Soltas: {item.estoque_unidades_soltas}")
        
        print("\n" + "="*80)
