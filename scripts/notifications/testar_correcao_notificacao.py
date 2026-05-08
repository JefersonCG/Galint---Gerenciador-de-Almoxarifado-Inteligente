#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Testa a formatacao corrigida da notificacao do evento 663."""

from app import app
from galint_flask.extensions import db
from galint_flask.models import InventarioEvento, Item
from galint_flask.services.telegram_service import TelegramService

if __name__ == '__main__':
    with app.app_context():
        print("="*80)
        print("TESTE DE FORMATACAO CORRIGIDA - EVENTO 663")
        print("="*80)
        
        evento = db.session.get(InventarioEvento, 663)
        if not evento:
            print("\nEvento 663 nao encontrado!")
            exit(1)
        
        item = db.session.get(Item, evento.codigo_item) if evento.codigo_item else None
        
        print(f"\nEvento #{evento.id_evento}")
        print(f"Descricao: {evento.descricao}")
        print(f"Quantidade: {evento.quantidade}")
        print(f"Codigo item: {evento.codigo_item}")
        
        if item:
            print(f"\nItem:")
            print(f"  Descricao: {item.descricao}")
            print(f"  Embalagens: {item.estoque_embalagens}")
            print(f"  Soltas: {item.estoque_unidades_soltas}")
        
        print("\n" + "="*80)
        print("MENSAGEM FORMATADA:")
        print("="*80)
        
        message_text, message_type, is_devolucao = TelegramService.format_inventory_event_message(
            evento, item
        )
        
        # Salvar em arquivo UTF-8 para evitar erro de encoding
        with open("teste_notificacao_output.txt", "w", encoding="utf-8") as f:
            f.write(message_text)
        
        print("\nMensagem salva em: teste_notificacao_output.txt")
        
        # Verificar se contem "52 Lata"
        if "52 Lata" in message_text:
            print("\nERRO: Ainda mostra '52 Lata'!")
        elif "2 lata" in message_text.lower() or "2 Lata" in message_text:
            print("\nSUCESSO: Mostra quantidade correta de latas (2)!")
        elif "52 litros" in message_text.lower() or "52L" in message_text:
            print("\nSUCESSO: Mostra total em litros!")
        else:
            print("\nINFO: Verificar manualmente o arquivo teste_notificacao_output.txt")
