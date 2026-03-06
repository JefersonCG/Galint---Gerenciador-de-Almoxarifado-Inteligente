import os
import sys

# Evitar threads em background (scheduler/polling)
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService
from galint_flask.extensions import db
from galint_flask.models import TelegramUser, Usuario


def main() -> None:
    app = create_app()
    with app.app_context():
        admins = (
            db.session.query(TelegramUser)
            .join(Usuario, TelegramUser.matricula == Usuario.matricula)
            .filter(TelegramUser.enabled == True, Usuario.is_admin == 1)
            .all()
        )
        print("admins:", len(admins))
        results = []
        for adm in admins:
            res = TelegramService.send_message(adm.chat_id, "✅ Teste GALINT: mensagem de verificação")
            results.append({"chat_id": adm.chat_id, **res})
        print(results)


if __name__ == "__main__":
    main()
