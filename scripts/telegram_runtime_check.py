import os
import sys

# Evitar que o create_app() inicie scheduler/polling e mantenha o processo preso.
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

# Ensure project root is importable
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramConfig, TelegramUser, TelegramNotification, Usuario


def main() -> None:
    app = create_app()
    with app.app_context():
        cfg = TelegramConfig.query.first()
        print("TelegramConfig exists:", bool(cfg))
        if cfg:
            print("enabled:", getattr(cfg, "enabled", None))
            token = getattr(cfg, "bot_token", None)
            print("bot_token set:", bool(token))
            print("bot_token prefix:", (token[:10] + "...") if token else None)
            print(
                "flags:",
                {
                    "notify_on_withdrawal": getattr(cfg, "notify_on_withdrawal", None),
                    "notify_supervisors": getattr(cfg, "notify_supervisors", None),
                    "alert_enabled": getattr(cfg, "alert_enabled", None),
                    "low_stock_enabled": getattr(cfg, "low_stock_enabled", None),
                },
            )

        admins = (
            db.session.query(TelegramUser)
            .join(Usuario, TelegramUser.matricula == Usuario.matricula)
            .filter(TelegramUser.enabled == True, Usuario.is_admin == 1)
            .all()
        )
        print("Admin users:", len(admins))
        if admins:
            a = admins[0]
            print("First admin:", {"id": a.id, "enabled": a.enabled, "chat_id": a.chat_id})

        last = TelegramNotification.query.order_by(TelegramNotification.sent_at.desc()).first()
        print("Last notification exists:", bool(last))
        if last:
            print(
                "Last notif:",
                {
                    "sent_at": str(last.sent_at),
                    "type": last.message_type,
                    "status": last.status,
                    "error": last.error_message,
                },
            )


if __name__ == "__main__":
    main()
