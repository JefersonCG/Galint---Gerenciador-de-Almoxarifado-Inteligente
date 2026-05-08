"""Teste de retirada de ferramenta."""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, Usuario, Saida, TelegramNotification
from galint_flask.services.telegram_service import TelegramService
from datetime import datetime

app = create_app()
with app.app_context():
    # Buscar todas as ferramentas
    items = db.session.query(Item).filter(
        Item.categoria.ilike('%ferramenta%')
    ).limit(10).all()
    
    # Encontrar uma com saldo > 0
    item = None
    for i in items:
        if i.get_saldo_atual() > 0:
            item = i
            break
    
    if not item:
        print("NAO FOI ENCONTRADA NENHUMA FERRAMENTA EM ESTOQUE")
    else:
        print(f"Item: {item.descricao}")
        print(f"Categoria: {item.categoria}")
        print(f"Saldo: {item.get_saldo_atual()}")
        
        # Buscar usuário admin
        usuario = db.session.query(Usuario).filter_by(is_admin=1).first()
        
        if usuario:
            print(f"Usuario: {usuario.nome}")
            
            # Criar retirada
            saida = Saida(
                codigo_item=item.codigo_item,
                quantidade=1,
                matricula=usuario.matricula,
                data_saida=datetime.now(),
                observacao="TESTE DE NOTIFICACAO FERRAMENTA"
            )
            
            db.session.add(saida)
            db.session.commit()
            
            print(f"Saida criada: {saida.id_saida}")
            
            # Notificar
            result = TelegramService.notify_withdrawal(saida.id_saida)
            print(f"Notificacao enviada: {result}")
            
            # Buscar ultima notificacao
            notif = db.session.query(TelegramNotification).order_by(
                TelegramNotification.sent_at.desc()
            ).first()
            
            if notif:
                print("\n" + "="*70)
                print(notif.message_text)
                print("="*70)
                
                if "RETIRADA DE FERRAMENTA" in notif.message_text:
                    print("\n✅ TITULO CORRETO: RETIRADA DE FERRAMENTA")
                else:
                    print("\n❌ TITULO INCORRETO (deveria ser RETIRADA DE FERRAMENTA)")

