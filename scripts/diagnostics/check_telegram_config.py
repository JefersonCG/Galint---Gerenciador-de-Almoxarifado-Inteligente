from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramConfig

app = create_app()
with app.app_context():
    cfg = db.session.query(TelegramConfig).first()
    print("config:", bool(cfg))
    if cfg:
        print("enabled", cfg.enabled)
        print("notify_on_withdrawal", cfg.notify_on_withdrawal)
        print("notify_supervisors", cfg.notify_supervisors)
        print("alert_enabled", cfg.alert_enabled)
