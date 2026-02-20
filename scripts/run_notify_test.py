from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification

app = create_app()
with app.app_context():
    # replace with id observed in debug output
    entrada_id = 114
    print('Calling notify_inventory_event for id', entrada_id)
    res = TelegramService.notify_inventory_event(entrada_id)
    print('Result:', res)
    print('Latest telegram_notifications:')
    for n in db.session.query(TelegramNotification).order_by(TelegramNotification.sent_at.desc()).limit(10).all():
        print('-', n.id, n.chat_id, n.message_type, n.status, n.error_message, n.sent_at)
