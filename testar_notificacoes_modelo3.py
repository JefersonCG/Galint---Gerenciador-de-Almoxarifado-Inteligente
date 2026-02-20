"""Script para testar as novas notificações de devolução e retirada"""
from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService
from galint_flask.models import Saida, Entrada, InventarioEvento, Item, Usuario
from galint_flask.extensions import db
from datetime import datetime, timedelta

app = create_app()

with app.app_context():
    print("=" * 60)
    print("TESTE DE NOTIFICAÇÕES - MODELO 3")
    print("=" * 60)
    
    # Teste 1: Buscar uma devolução recente (evento de inventário)
    print("\n1️⃣ TESTANDO NOTIFICAÇÃO DE DEVOLUÇÃO...")
    print("-" * 60)
    
    evento_devolucao = (
        InventarioEvento.query
        .filter(InventarioEvento.descricao.ilike('%devolução%'))
        .order_by(InventarioEvento.data_evento.desc())
        .first()
    )
    
    if evento_devolucao:
        item = db.session.get(Item, evento_devolucao.codigo_item) if evento_devolucao.codigo_item else None
        
        print(f"✓ Evento encontrado: ID {evento_devolucao.id_evento}")
        print(f"  - Item: {item.descricao if item else 'N/D'}")
        print(f"  - Data: {evento_devolucao.data_evento}")
        print(f"  - Quantidade: {evento_devolucao.quantidade}")
        print("\n📱 NOTIFICAÇÃO FORMATADA:")
        print("-" * 60)
        
        msg = TelegramService.format_devolucao_message(evento_devolucao, item)
        print(msg)
        print("-" * 60)
    else:
        print("❌ Nenhuma devolução encontrada no banco")
    
    # Teste 2: Buscar uma retirada recente
    print("\n\n2️⃣ TESTANDO NOTIFICAÇÃO DE RETIRADA...")
    print("-" * 60)
    
    saida_recente = (
        Saida.query
        .join(Saida.item)
        .join(Saida.usuario)
        .filter(Item.categoria.ilike('%ferramenta%'))
        .order_by(Saida.data_saida.desc())
        .first()
    )
    
    if saida_recente and saida_recente.item and saida_recente.usuario:
        print(f"✓ Retirada encontrada: ID {saida_recente.id_saida}")
        print(f"  - Item: {saida_recente.item.descricao}")
        print(f"  - Funcionário: {saida_recente.usuario.nome}")
        print(f"  - Data: {saida_recente.data_saida}")
        print(f"  - Quantidade: {saida_recente.quantidade}")
        print("\n📱 NOTIFICAÇÃO FORMATADA (Usuário):")
        print("-" * 60)
        
        msg_user = TelegramService.format_withdrawal_message_user(
            saida_recente, 
            saida_recente.usuario, 
            saida_recente.item
        )
        print(msg_user)
        print("-" * 60)
        
        print("\n📱 NOTIFICAÇÃO FORMATADA (Supervisor):")
        print("-" * 60)
        
        msg_supervisor = TelegramService.format_withdrawal_message_supervisor(
            saida_recente, 
            saida_recente.usuario, 
            saida_recente.item
        )
        print(msg_supervisor)
        print("-" * 60)
    else:
        print("❌ Nenhuma retirada de ferramenta encontrada")
    
    print("\n" + "=" * 60)
    print("✅ TESTES CONCLUÍDOS!")
    print("=" * 60)
