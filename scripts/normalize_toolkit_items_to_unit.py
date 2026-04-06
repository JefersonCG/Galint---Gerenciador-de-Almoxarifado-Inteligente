from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from galint_flask import create_app
from galint_flask.models import Item
from galint_flask.services.inventory import InventoryService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Converte jogos/kits de Ferramentas para semântica de unidade e limpa metadados de embalagem."
    )
    parser.add_argument("--codes", nargs="*", help="Codigos especificos para filtrar")
    parser.add_argument("--apply", action="store_true", help="Aplica a correcao no banco")
    return parser.parse_args()


def _normalized_codes(values: list[str] | None) -> set[str]:
    return {str(value or "").strip() for value in (values or []) if str(value or "").strip()}


def _matching_items(codes: set[str]) -> list[Item]:
    query = Item.query.order_by(Item.codigo_item.asc())
    if codes:
        query = query.filter(Item.codigo_item.in_(sorted(codes)))
    return [item for item in query.all() if InventoryService._should_force_toolkit_unit_semantics({}, current_item=item)]


def _print_item(item: Item) -> None:
    print(
        f"{item.codigo_item} | unidade={item.unidade or '-'} | "
        f"tipo={item.tipo_embalagem_novo or '-'} | unid_por={item.unidades_por_embalagem or '-'} | "
        f"emb={float(item.estoque_embalagens or 0):g} | soltas={float(item.estoque_unidades_soltas or 0):g} | {item.descricao}"
    )


def main() -> int:
    args = _parse_args()
    app = create_app()
    codes = _normalized_codes(args.codes)

    with app.app_context():
        items = _matching_items(codes)
        if not items:
            print("Nenhum item com semantica de kit de ferramenta foi encontrado.")
            return 0

        print("ANTES")
        for item in items:
            _print_item(item)

        if not args.apply:
            print("\nUse --apply para salvar a normalizacao como Unidade.")
            return 0

        changed = 0
        for item in items:
            if InventoryService._apply_toolkit_unit_semantics(item):
                changed += 1

        from galint_flask.extensions import db

        db.session.commit()

        print(f"\nITENS AJUSTADOS: {changed}")
        refreshed = _matching_items(codes)
        print("\nDEPOIS")
        for item in refreshed:
            _print_item(item)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())