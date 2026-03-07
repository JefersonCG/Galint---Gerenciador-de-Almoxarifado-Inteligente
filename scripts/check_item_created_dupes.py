import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# Evitar side-effects ao inicializar app (scheduler/polling/etc.)
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification, TelegramOutbox


def _short(text: str | None, max_len: int = 140) -> str:
    t = (text or "").replace("\r", " ").replace("\n", " | ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def main() -> None:
    limit = 80
    within_minutes = 180

    if len(sys.argv) >= 2:
        try:
            limit = int(sys.argv[1])
        except Exception:
            limit = 80

    if len(sys.argv) >= 3:
        try:
            within_minutes = int(sys.argv[2])
        except Exception:
            within_minutes = 180

    app = create_app()
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(minutes=within_minutes)

        out_rows = (
            db.session.query(TelegramOutbox)
            .filter(TelegramOutbox.message_type == "item_created")
            .filter(TelegramOutbox.created_at >= cutoff)
            .order_by(TelegramOutbox.id.desc())
            .limit(limit)
            .all()
        )

        print(
            f"Outbox item_created (últimos {within_minutes} min, limit={limit}): {len(out_rows)}"
        )
        key_counts = Counter((str(r.chat_id), str(r.idempotency_key)) for r in out_rows)
        dup_keys = [(k, c) for k, c in key_counts.items() if c > 1]
        if dup_keys:
            print("DUPLICADOS por (chat_id, idempotency_key):")
            for (chat_id, key), c in sorted(dup_keys, key=lambda x: -x[1]):
                print(f"- chat_id={chat_id} count={c} key={key}")
        else:
            print("Sem duplicidade por idempotency_key nesse recorte.")

        text_counts = Counter((str(r.chat_id), str(r.message_text)) for r in out_rows)
        dup_text = [(k, c) for k, c in text_counts.items() if c > 1]
        if dup_text:
            print("DUPLICADOS por (chat_id, message_text):")
            for (chat_id, _text), c in sorted(dup_text, key=lambda x: -x[1])[:20]:
                print(f"- chat_id={chat_id} count={c} text={_short(_text)}")

        print("\nÚltimas linhas (outbox):")
        for r in out_rows[:20]:
            print(
                f"- outbox_id={r.id} created_at={r.created_at} chat_id={r.chat_id} status={r.status} "
                f"attempts={getattr(r, 'attempt_count', None)} key={r.idempotency_key} :: {_short(r.message_text)}"
            )

        notif_rows = (
            db.session.query(TelegramNotification)
            .filter(TelegramNotification.message_type == "item_created")
            .filter(TelegramNotification.sent_at >= cutoff)
            .order_by(TelegramNotification.id.desc())
            .limit(limit)
            .all()
        )

        print(
            f"\nNotifications item_created (últimos {within_minutes} min, limit={limit}): {len(notif_rows)}"
        )
        notif_text_counts = Counter((str(n.chat_id), str(n.message_text)) for n in notif_rows)
        notif_dup = [(k, c) for k, c in notif_text_counts.items() if c > 1]
        if notif_dup:
            print("DUPLICADOS no histórico por (chat_id, message_text):")
            for (chat_id, _text), c in sorted(notif_dup, key=lambda x: -x[1])[:20]:
                print(f"- chat_id={chat_id} count={c} text={_short(_text)}")
        else:
            print("Sem duplicidade evidente no histórico nesse recorte.")

        print("\nÚltimas linhas (histórico):")
        for n in notif_rows[:20]:
            print(
                f"- notif_id={n.id} sent_at={n.sent_at} chat_id={n.chat_id} status={n.status} err={_short(n.error_message, 60)} :: {_short(n.message_text)}"
            )


if __name__ == "__main__":
    main()
