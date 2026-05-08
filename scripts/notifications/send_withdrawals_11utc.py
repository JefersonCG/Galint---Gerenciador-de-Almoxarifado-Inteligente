from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService

app = create_app()

saida_ids = [414, 415, 416, 417, 418]

with app.app_context():
    for saida_id in saida_ids:
        res = TelegramService.notify_withdrawal(saida_id, force_single=True)
        print(saida_id, res)
