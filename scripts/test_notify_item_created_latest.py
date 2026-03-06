import os
import sys

# Evitar threads de background em script
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, TelegramNotification
from galint_flask.services.telegram_service import TelegramService


def main() -> None:
    app = create_app()
    with app.app_context():
        # Pega um item existente só para testar o envio do template de "criado"
        item = db.session.query(Item).order_by(Item.codigo_item.desc()).first()
        if not item:
            print("No item found")
            return

        print("Testing notify_item_created for:", item.codigo_item, item.descricao)
        res = TelegramService.notify_item_created(item.codigo_item)
        print("Result:", res)

        nots = (
            db.session.query(TelegramNotification)
            .order_by(TelegramNotification.sent_at.desc())
            .limit(5)
            .all()
        )
        print("Last notifications:")
        for n in nots:
            print(n.id, n.chat_id, n.message_type, n.status, n.error_message, n.sent_at)


if __name__ == "__main__":
    main()
