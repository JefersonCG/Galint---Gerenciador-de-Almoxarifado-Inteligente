from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification

app = create_app()
with app.app_context():
    total = db.session.query(TelegramNotification).count()
    print("Total notifications:", total)
    recent = db.session.query(TelegramNotification).order_by(TelegramNotification.id.desc()).limit(10).all()
    for n in recent:
        print(n.id, n.status, n.message_type, n.chat_id, n.recipient_name, n.sent_at, n.error_message)
