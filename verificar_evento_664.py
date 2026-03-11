#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verifica evento 664."""

from app import app
from galint_flask.extensions import db
from galint_flask.models import Item, InventarioEvento
from galint_flask.services.telegram_service import TelegramService

if __name__ == '__main__':
    with app.app_context():
        print("="*80)
        print("EVENTO 664 - TINTA PISO")
        print("="*80)
        
        evento = db.session.get(InventarioEvento, 664)
        if not evento:
            print("\nEvento 664 nao encontrado!")
            exit(1)
        
        item = db.session.get(Item, evento.codigo_item)
        
        print(f"\nEvento #{evento.id_evento}")
        print(f"Descricao: {evento.descricao}")
        print(f"Quantidade: {evento.quantidade}")
        
        if item:
            print(f"\nItem ANTES do evento 665:")
            print(f"  OBS: Este evento aconteceu primeiro (12:27), depois veio o 665 (13:49)")
            print(f"  Embalagens ATUAIS: {item.estoque_embalagens}")
            print(f"  Soltas ATUAIS: {item.estoque_unidades_soltas}")
        
        # Simular como estava antes do evento 665
        # Evento 665: quantidade 2.6, descricao "de 1.0 para 3.6"
        # Entao ANTES do 665, o item tinha saldo_atual = 1.0
        # Evento 664 tambem tem "de 1.0 para 3.6", ou seja teria que estar em 1.0 ANTES
        # Mas isso nao faz sentido se os 2 eventos sao identicos...
        
        # Vou formatar a mensagem do 664
        message_text, message_type, is_devolucao = TelegramService.format_inventory_event_message(
            evento, item
        )
        
        with open("evento_664_output.txt", "w", encoding="utf-8") as f:
            f.write(message_text)
        
        print("\nMensagem formatada salva em: evento_664_output.txt")
        
        if "3 Lata" in message_text or "3 lata" in message_text:
            print("\nERRO ENCONTRADO: Mensagem mostra '3 Lata'!")
            print("Este eh o evento que gerou a notificacao errada!")
        elif "1 lata" in message_text.lower():
            print("\nMensagem mostra '1 lata' (correto)")
