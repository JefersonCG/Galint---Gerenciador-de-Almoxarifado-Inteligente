import os
import sys
from datetime import datetime, timedelta

# Evitar threads de background em script
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification


def main() -> None:
    app = create_app()
    with app.app_context():
        now = datetime.now()
        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1)

        nots = (
            db.session.query(TelegramNotification)
            .filter(TelegramNotification.sent_at >= start)
            .filter(TelegramNotification.sent_at < end)
            .order_by(TelegramNotification.sent_at.desc())
            .all()
        )

        print("Hoje (", start, ") total:", len(nots))
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for n in nots:
            msg_type = str(getattr(n, "message_type", ""))
            status = str(getattr(n, "status", ""))
            by_type[msg_type] = by_type.get(msg_type, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1

        print("Por tipo:", by_type)
        print("Por status:", by_status)
        print("--- últimos 30 ---")
        for n in nots[:30]:
            err = (n.error_message or "").replace("\n", " ")
            if len(err) > 160:
                err = err[:160] + "..."
            print(n.id, n.sent_at, n.message_type, n.status, err)


if __name__ == "__main__":
    main()
