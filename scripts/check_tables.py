from galint_flask import create_app

app = create_app()

with app.app_context():
    from galint_flask.models import TelegramConfig

    try:
        print("config count", TelegramConfig.query.count())
    except Exception as exc:
        import traceback

        traceback.print_exc()
