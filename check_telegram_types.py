from datetime import datetime, timedelta
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification

app = create_app()
with app.app_context():
    since = datetime.utcnow() - timedelta(days=2)
    rows = (
        db.session.query(TelegramNotification.message_type, db.func.count(TelegramNotification.id))
        .filter(TelegramNotification.sent_at >= since)
        .group_by(TelegramNotification.message_type)
        .all()
    )
    print("Últimos 2 dias:")
    for msg_type, count in rows:
        print(msg_type, count)
