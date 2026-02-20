import os
import sys

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification


CODES = [
    "7897765925692",  # FITA DUPLA FACE
    "7908089600414",  # LUVA PVC 46cm
    "7891260028346",  # LIQUIBASE COMPLEMENTO PAREDES 18L
    "7891260456989",  # MASSA CORRIDA PRÉ PINTURA
]


def main() -> None:
    app = create_app()
    with app.app_context():
        for code in CODES:
            res = TelegramService.notify_item_created(code)
            print(code, res)

        last = (
            db.session.query(TelegramNotification)
            .filter(TelegramNotification.message_type == "item_created")
            .order_by(TelegramNotification.sent_at.desc())
            .limit(10)
            .all()
        )
        print("--- last 10 item_created ---")
        for n in last:
            print(n.id, n.sent_at, n.chat_id, n.status, (n.error_message or ""))


if __name__ == "__main__":
    main()
