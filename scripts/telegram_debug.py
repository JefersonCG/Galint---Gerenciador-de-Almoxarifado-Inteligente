from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService
from galint_flask.extensions import db
from galint_flask.models import Usuario, TelegramUser, TelegramConfig, InventarioEvento, Entrada, TelegramNotification

app = create_app()
with app.app_context():
    print('Telegram enabled:', TelegramService.is_enabled())
    cfg = TelegramService.get_config()
    print('TelegramConfig:', {'enabled': bool(cfg.enabled) if cfg else None, 'has_token': bool(cfg.bot_token) if cfg else None})

    admins = db.session.query(Usuario).filter(Usuario.is_admin == 1).all()
    print('\nAdministradores cadastrados:')
    for a in admins:
        tu = db.session.query(TelegramUser).filter_by(matricula=a.matricula).first()
        print(f'- {a.matricula} | {a.nome} | is_admin={a.is_admin} | telegram: {tu.chat_id if tu else None} enabled={tu.enabled if tu else None}')

    tus = db.session.query(TelegramUser).all()
    print('\nTelegram users table:')
    for t in tus:
        print(f'- matricula={t.matricula} chat_id={t.chat_id} celular={t.celular} enabled={t.enabled}')

    print('\nÚltimas InventarioEvento (10):')
    evs = db.session.query(InventarioEvento).order_by(InventarioEvento.data_evento.desc()).limit(10).all()
    for e in evs:
        print(f'- id={e.id_evento} codigo={e.codigo_item} quantidade={e.quantidade} matricula={e.matricula} tipo={e.tipo} data={e.data_evento}')

    print('\nÚltimas Entradas (10):')
    entradas = db.session.query(Entrada).order_by(Entrada.data_entrada.desc()).limit(10).all()
    for ent in entradas:
        print(f'- id={ent.id_entrada} codigo={ent.codigo_item} quantidade={ent.quantidade} matricula={ent.matricula} data={ent.data_entrada}')

    print('\nÚltimas telegram_notifications (10):')
    nots = db.session.query(TelegramNotification).order_by(TelegramNotification.sent_at.desc()).limit(10).all()
    for n in nots:
        print(f'- id={n.id} chat_id={n.chat_id} type={n.message_type} status={n.status} sent_at={n.sent_at} err={n.error_message}')
