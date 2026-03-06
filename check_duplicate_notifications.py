"""Script para verificar notificações duplicadas no banco de dados."""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification, TelegramOutbox
from datetime import datetime, timedelta

app = create_app()

with app.app_context():
    # Verificar últimas 2 horas
    cutoff = datetime.utcnow() - timedelta(hours=2)
    
    print("\n" + "=" * 120)
    print("VERIFICAÇÃO DE NOTIFICAÇÕES DUPLICADAS")
    print("=" * 120)
    
    # Últimas notificações
    notifs = (
        db.session.query(
            TelegramNotification.id,
            TelegramNotification.chat_id,
            TelegramNotification.saida_id,
            TelegramNotification.message_type,
            TelegramNotification.status,
            TelegramNotification.sent_at
        )
        .filter(
            TelegramNotification.sent_at >= cutoff,
            TelegramNotification.saida_id.isnot(None)
        )
        .order_by(TelegramNotification.sent_at.desc())
        .limit(50)
        .all()
    )
    
    print(f"\nÚltimas {len(notifs)} notificações (últimas 2 horas):")
    print("-" * 120)
    for n in notifs:
        print(f"ID={n.id:4} | chat_id={n.chat_id:15} | saida_id={n.saida_id:5} | type={n.message_type:20} | status={n.status:8} | sent={n.sent_at}")
    
    # Buscar duplicatas
    print("\n" + "=" * 120)
    print("BUSCANDO DUPLICATAS (mesmo chat_id + saida_id)")
    print("=" * 120)
    
    dups = (
        db.session.query(
            TelegramNotification.chat_id,
            TelegramNotification.saida_id,
            db.func.count(TelegramNotification.id).label('qtd')
        )
        .filter(
            TelegramNotification.sent_at >= cutoff,
            TelegramNotification.saida_id.isnot(None)
        )
        .group_by(
            TelegramNotification.chat_id,
            TelegramNotification.saida_id
        )
        .having(db.func.count(TelegramNotification.id) > 1)
        .all()
    )
    
    if dups:
        print(f"\n❌ ENCONTRADAS {len(dups)} DUPLICATAS:\n")
        for d in dups:
            print(f"  chat_id={d.chat_id} | saida_id={d.saida_id} | quantidade={d.qtd}")
            
            # Mostrar detalhes de cada duplicata
            details = (
                db.session.query(TelegramNotification)
                .filter_by(chat_id=d.chat_id, saida_id=d.saida_id)
                .filter(TelegramNotification.sent_at >= cutoff)
                .order_by(TelegramNotification.sent_at)
                .all()
            )
            
            for idx, detail in enumerate(details, 1):
                print(f"    {idx}. ID={detail.id} | status={detail.status} | sent={detail.sent_at} | type={detail.message_type}")
            print()
    else:
        print("\n✅ NENHUMA DUPLICATA ENCONTRADA!\n")
    
    # Verificar outbox também
    print("=" * 120)
    print("VERIFICANDO OUTBOX (idempotency_key)")
    print("=" * 120)
    
    outbox_dups = (
        db.session.query(
            TelegramOutbox.idempotency_key,
            db.func.count(TelegramOutbox.id).label('qtd')
        )
        .filter(TelegramOutbox.created_at >= cutoff)
        .group_by(TelegramOutbox.idempotency_key)
        .having(db.func.count(TelegramOutbox.id) > 1)
        .all()
    )
    
    if outbox_dups:
        print(f"\n❌ ENCONTRADAS {len(outbox_dups)} DUPLICATAS NO OUTBOX (PROBLEMA COM IDEMPOTÊNCIA!):\n")
        for od in outbox_dups:
            print(f"  idempotency_key={od.idempotency_key} | quantidade={od.qtd}")
    else:
        print("\n✅ NENHUMA DUPLICATA NO OUTBOX (idempotência funcionando corretamente)\n")
    
    print("=" * 120)
