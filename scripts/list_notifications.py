from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification

app = create_app()
with app.app_context():
    nots = db.session.query(TelegramNotification).order_by(TelegramNotification.sent_at.desc()).limit(20).all()
    for n in nots:
        print(n.id, n.chat_id, n.message_type, n.status, n.error_message, n.sent_at)
