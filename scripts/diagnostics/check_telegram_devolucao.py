from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification

app = create_app()
with app.app_context():
    rows = (
        db.session.query(TelegramNotification.message_type, db.func.count(TelegramNotification.id))
        .filter(TelegramNotification.message_type.ilike('%devolucao%'))
        .group_by(TelegramNotification.message_type)
        .all()
    )
    print(rows)
