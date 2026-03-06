import os
import sys
from typing import Iterable

# Evitar threads em background em script
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, TelegramNotification
from galint_flask.services.telegram_service import TelegramService


DEFAULT_TERMS = [
    "fita dupla face",
    "luva pvc 46cm",
    "liquibase 18l",
    "massa corrida pre pintura",
]


def _find_items(terms: Iterable[str], *, per_term_limit: int = 5) -> list[Item]:
    found: list[Item] = []
    seen_codes: set[str] = set()

    for term in terms:
        term = (term or "").strip()
        if not term:
            continue
        matches = (
            db.session.query(Item)
            .filter(Item.descricao.ilike(f"%{term}%"))
            .order_by(Item.descricao.asc())
            .limit(per_term_limit)
            .all()
        )
        print(f"Termo: {term} -> {len(matches)} match(es)")
        for it in matches:
            code = str(getattr(it, "codigo_item", ""))
            desc = str(getattr(it, "descricao", ""))
            print(f"  - {code}: {desc}")
            if code and code not in seen_codes:
                found.append(it)
                seen_codes.add(code)

    return found


def main() -> None:
    app = create_app()
    with app.app_context():
        items = _find_items(DEFAULT_TERMS, per_term_limit=5)
        if not items:
            print("Nenhum item encontrado para os termos informados.")
            return

        sent = 0
        failed = 0
        for it in items:
            code = str(it.codigo_item)
            desc = str(it.descricao)
            res = TelegramService.notify_item_created(code)
            if res.get("sent"):
                sent += 1
            if res.get("failed"):
                failed += 1
            print("---")
            print("Enviando:", code, "|", desc)
            print("Resultado:", res)

        # Mostrar últimas notificações geradas (item_created)
        last = (
            db.session.query(TelegramNotification)
            .filter(TelegramNotification.message_type == "item_created")
            .order_by(TelegramNotification.sent_at.desc())
            .limit(20)
            .all()
        )
        print("\nResumo:")
        print("Itens processados:", len(items), "sent_calls:", sent, "failed_calls:", failed)
        print("Últimas 20 item_created:")
        for n in last:
            err = (n.error_message or "").replace("\n", " ")
            if len(err) > 140:
                err = err[:140] + "..."
            print(n.id, n.sent_at, n.chat_id, n.status, err)


if __name__ == "__main__":
    main()
