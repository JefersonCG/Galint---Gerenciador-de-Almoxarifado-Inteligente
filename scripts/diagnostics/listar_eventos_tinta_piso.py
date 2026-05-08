#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Busca todos eventos recentes da TINTA PISO."""

from app import app
from galint_flask.extensions import db
from galint_flask.models import InventarioEvento

if __name__ == '__main__':
    with app.app_context():
        print("="*80)
        print("EVENTOS RECENTES - TINTA PISO 7891323079407")
        print("="*80)
        
        eventos = (
            InventarioEvento.query
            .filter_by(codigo_item="7891323079407")
            .order_by(InventarioEvento.data_evento.desc())
            .limit(10)
            .all()
        )
        
        if not eventos:
            print("\nNenhum evento encontrado!")
        else:
            print(f"\nEncontrados {len(eventos)} eventos:\n")
            for ev in eventos:
                print(f"ID: {ev.id_evento}")
                print(f"  Data: {ev.data_evento}")
                print(f"  Tipo: {ev.tipo}")
                print(f"  Quantidade: {ev.quantidade}")
                print(f"  Descricao: {ev.descricao}")
                print()
        
        print("="*80)
