from types import SimpleNamespace
from unittest.mock import patch

from galint_flask.services.telegram_service import TelegramService


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)


def _adm(chat_id, nome, matricula):
    return SimpleNamespace(
        chat_id=str(chat_id),
        matricula=matricula,
        usuario=SimpleNamespace(nome=nome),
    )


def run():
    rows = [
        _adm("100", "ANDERSON", "1"),
        _adm("200", "RONALDO", "2"),
        _adm("300", "RAPHAEL", "3"),
    ]

    with patch.object(TelegramService, "_privileged_users_query", return_value=_FakeQuery(rows)):
        recipients = TelegramService._withdrawal_recipients(exclude_chat_ids={"200"})

    assert recipients == [
        {"chat_id": "100", "recipient_name": "Admin: ANDERSON", "target": "admin"},
        {"chat_id": "300", "recipient_name": "Admin: RAPHAEL", "target": "admin"},
    ], recipients

    print("OK: destinatários de retirada incluem todos os privilegiados ativos")


if __name__ == "__main__":
    run()