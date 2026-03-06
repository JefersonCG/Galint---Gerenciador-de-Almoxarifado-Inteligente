import os
import sys

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item


def main() -> None:
    terms = sys.argv[1:]
    if not terms:
        print("Uso: python scripts/find_items_by_description.py <termo1> [termo2] ...")
        return

    app = create_app()
    with app.app_context():
        for term in terms:
            term = (term or "").strip()
            if not term:
                continue
            matches = (
                db.session.query(Item)
                .filter(Item.descricao.ilike(f"%{term}%"))
                .order_by(Item.descricao.asc())
                .limit(30)
                .all()
            )
            print(f"\nTermo: {term} -> {len(matches)} match(es)")
            for it in matches:
                print(f"- {it.codigo_item}: {it.descricao}")


if __name__ == "__main__":
    main()
