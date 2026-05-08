from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramOutbox

app = create_app()

with app.app_context():
    total = db.session.query(TelegramOutbox).count()
    pending = db.session.query(TelegramOutbox).filter(TelegramOutbox.status == 'pending').count()
    failed = db.session.query(TelegramOutbox).filter(TelegramOutbox.status == 'failed').count()
    sent = db.session.query(TelegramOutbox).filter(TelegramOutbox.status == 'sent').count()
    print(f"Total={total} Pending={pending} Sent={sent} Failed={failed}")

    recent = db.session.query(TelegramOutbox).order_by(TelegramOutbox.id.desc()).limit(5).all()
    for r in recent:
        print(r.id, r.status, r.chat_id, r.message_type, r.available_at, r.attempt_count, r.last_error)
