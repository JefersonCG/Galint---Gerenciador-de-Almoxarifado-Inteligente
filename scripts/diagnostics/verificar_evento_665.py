#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verifica o evento 665 da TINTA PISO."""

from app import app
from galint_flask.extensions import db
from galint_flask.models import Item, InventarioEvento
from galint_flask.services.telegram_service import TelegramService

if __name__ == '__main__':
    with app.app_context():
        print("="*80)
        print("DIAGNOSTICO EVENTO 665 - TINTA PISO")
        print("="*80)
        
        evento = db.session.get(InventarioEvento, 665)
        if not evento:
            print("\nEvento 665 nao encontrado!")
            exit(1)
        
        item = db.session.get(Item, evento.codigo_item)
        
        print(f"\nEvento #{evento.id_evento}")
        print(f"Codigo item: {evento.codigo_item}")
        print(f"Descricao: {evento.descricao}")
        print(f"Quantidade: {evento.quantidade}")
        
        if item:
            print(f"\nItem:")
            print(f"  Descricao: {item.descricao}")
            print(f"  Embalagens: {item.estoque_embalagens}")
            print(f"  Soltas: {item.estoque_unidades_soltas}")
            print(f"  litros_por_embalagem: {item.litros_por_embalagem}")
            print(f"  get_saldo_atual(): {item.get_saldo_atual()}")
        
        print("\n" + "="*80)
        print("MENSAGEM FORMATADA:")
        print("="*80)
        
        message_text, message_type, is_devolucao = TelegramService.format_inventory_event_message(
            evento, item
        )
        
        # Salvar em arquivo
        with open("evento_665_output.txt", "w", encoding="utf-8") as f:
            f.write(f"Descricao do evento: {evento.descricao}\n\n")
            f.write("="*80 + "\n")
            f.write(message_text)
        
        print("\nMensagem salva em: evento_665_output.txt")
        
        # Analise da descricao
        import re
        all_matches = list(re.finditer(
            r"de\s+([0-9]+(?:\.[0-9]+)?)\s+para\s+([0-9]+(?:\.[0-9]+)?)",
            evento.descricao,
        ))
        
        print(f"\nMatches encontrados na descricao: {len(all_matches)}")
        for i, m in enumerate(all_matches, 1):
            print(f"  {i}. de {m.group(1)} para {m.group(2)}")
        
        # Verificar se detecta ajuste_em_embalagens
        ajuste_em_emb = "saldo em embalagens" in evento.descricao.lower()
        print(f"\najuste_em_embalagens: {ajuste_em_emb}")
        
        if "3 Lata" in message_text or "3 lata" in message_text:
            print("\nERRO: Mensagem mostra '3 Lata'!")
        elif "1 lata" in message_text.lower():
            print("\nSUCESSO: Mensagem mostra '1 lata'!")
        
        print("\n" + "="*80)
