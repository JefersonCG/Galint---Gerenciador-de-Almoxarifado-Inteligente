import os
import sys

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python scripts/telegram_notifications_for_item.py <codigo_item> [limit]")
        return

    codigo = (sys.argv[1] or "").strip()
    limit = 30
    if len(sys.argv) >= 3:
        try:
            limit = int(sys.argv[2])
        except Exception:
            limit = 30

    app = create_app()
    with app.app_context():
        q = (
            db.session.query(TelegramNotification)
            .filter(TelegramNotification.message_text.ilike(f"%{codigo}%"))
            .order_by(TelegramNotification.id.desc())
            .limit(limit)
        )
        rows = q.all()

        print(f"Notificações contendo codigo={codigo}: {len(rows)}")
        for n in rows:
            msg = (n.message_text or "").replace("\r", " ").replace("\n", " | ")
            if len(msg) > 180:
                msg = msg[:180] + "..."
            print(
                f"- id={n.id} type={n.message_type} status={n.status} chat_id={n.chat_id} sent_at={n.sent_at} err={n.error_message} :: {msg}"
            )


if __name__ == "__main__":
    main()
