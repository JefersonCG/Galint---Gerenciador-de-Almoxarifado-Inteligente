#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnostica o item TINTA PISO PREMIUM BRANCA 3.6L."""

from app import app
from galint_flask.extensions import db
from galint_flask.models import Item, InventarioEvento

if __name__ == '__main__':
    with app.app_context():
        print("="*80)
        print("DIAGNOSTICO - TINTA PISO PREMIUM BRANCA 3.6L")
        print("="*80)
        
        item = Item.query.filter_by(codigo_item="7891323879497").first()
        if not item:
            print("\nItem nao encontrado!")
            exit(1)
        
        print(f"\nCodigo: {item.codigo_item}")
        print(f"Descricao: {item.descricao}")
        print(f"Unidade: '{item.unidade}'")
        print(f"Categoria: {item.categoria}")
        
        print(f"\nEstoque ATUAL:")
        print(f"  - estoque_embalagens: {item.estoque_embalagens}")
        print(f"  - estoque_unidades_soltas: {item.estoque_unidades_soltas}")
        print(f"  - tipo_embalagem_novo: {item.tipo_embalagem_novo}")
        print(f"  - unidades_por_embalagem: {item.unidades_por_embalagem}")
        print(f"  - litros_por_embalagem: {item.litros_por_embalagem}")
        print(f"  - get_saldo_atual(): {item.get_saldo_atual()}")
        
        print(f"\nEstoque CORRETO deveria ser:")
        print(f"  - estoque_embalagens: 1 (1 lata fechada)")
        print(f"  - estoque_unidades_soltas: 3.6 (3.6 litros soltos)")
        print(f"  - Total: (1 x 3.6) + 3.6 = 7.2 litros")
        
        # Verificar ultimos eventos
        eventos = (
            InventarioEvento.query
            .filter_by(codigo_item="7891323879497")
            .order_by(InventarioEvento.data_evento.desc())
            .limit(5)
            .all()
        )
        
        if eventos:
            print(f"\nUltimos {len(eventos)} eventos de inventario:")
            for i, ev in enumerate(eventos, 1):
                print(f"\n  {i}. ID: {ev.id_evento}")
                print(f"     Data: {ev.data_evento}")
                print(f"     Tipo: {ev.tipo}")
                print(f"     Quantidade: {ev.quantidade}")
                print(f"     Descricao: '{ev.descricao}'")
        
        # Testar formatacao
        try:
            from galint_flask.services.embalagem_service import EmbalagemService
            print(f"\nFormatacao EmbalagemService:")
            print(f"  - tem_embalagem: {EmbalagemService.tem_embalagem(item)}")
            print(f"  - calcular_estoque_total: {EmbalagemService.calcular_estoque_total(item)}")
            print(f"  - formatar_estoque: {EmbalagemService.formatar_estoque(item)}")
        except Exception as e:
            print(f"\nERRO ao formatar: {e}")
        
        print("\n" + "="*80)
