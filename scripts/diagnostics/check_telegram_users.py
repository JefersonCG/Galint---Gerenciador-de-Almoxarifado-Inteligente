from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramUser

app = create_app()
with app.app_context():
    users = db.session.query(TelegramUser).order_by(TelegramUser.id).all()
    for u in users:
        prefs = u.notification_preferences
        nome = u.usuario.nome if u.usuario else None
        print(u.id, nome, u.chat_id, u.enabled, 'prefs' if prefs else 'no_prefs')
