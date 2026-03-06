from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, TelegramNotification
from galint_flask.services.telegram_service import TelegramService

app = create_app()
with app.app_context():
    item = db.session.query(Item).first()
    if not item:
        print('No item found to test')
    else:
        print('Testing notify for item:', item.codigo_item, item.descricao)
        res = TelegramService.notify_item_now(item.codigo_item)
        print('Result:', res)
        nots = db.session.query(TelegramNotification).order_by(TelegramNotification.sent_at.desc()).limit(5).all()
        print('Last notifications:')
        for n in nots:
            print(n.id, n.chat_id, n.message_type, n.status, n.error_message, n.sent_at)
