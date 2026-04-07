"""Alinha StockBalance e read model físico diretamente a partir do ledger.

Uso:
  .\.venv\Scripts\python.exe repair_stock_balance_from_ledger.py --codigo 7891040004416 --codigo 7899772604560
  .\.venv\Scripts\python.exe repair_stock_balance_from_ledger.py --codigo 7891040004416 --apply
"""

from __future__ import annotations

import argparse
import os
import sys


os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from sqlalchemy import func

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, StockBalance, StockMovement, stock_balance_supports_read_model_ready
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.legacy_stock_normalizer import resolve_canonical_unit


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recompõe cache e read model físico a partir do ledger.")
    parser.add_argument("--codigo", action="append", required=True, help="Código do item a reparar. Pode repetir o argumento.")
    parser.add_argument("--apply", action="store_true", help="Aplica e faz commit. Sem este argumento roda em dry-run.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    app = create_app()
    with app.app_context():
        supports_ready = stock_balance_supports_read_model_ready()
        results: list[tuple[str, float, float, tuple[float, float], tuple[float, float]]] = []

        for codigo in [value.strip() for value in args.codigo if value and value.strip()]:
            item = db.session.get(Item, codigo)
            if item is None:
                print(f"[SKIP] {codigo} | item não encontrado")
                continue

            ledger_total = float(
                db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
                .filter(StockMovement.product_id == codigo)
                .scalar()
                or 0.0
            )
            balance = db.session.get(StockBalance, codigo)
            if balance is None:
                balance = StockBalance(product_id=codigo)
                db.session.add(balance)

            before_cache = float(balance.quantity_base or 0.0)
            before_physical = (float(item.estoque_embalagens or 0.0), float(item.estoque_unidades_soltas or 0.0))

            balance.quantity_base = ledger_total
            if supports_ready:
                balance.read_model_ready = True

            inventory_engine._sync_packaging_state_to_balance(
                item=item,
                quantity_base=ledger_total,
                unit_base=resolve_canonical_unit(item),
            )

            after_physical = (float(item.estoque_embalagens or 0.0), float(item.estoque_unidades_soltas or 0.0))
            results.append((codigo, before_cache, ledger_total, before_physical, after_physical))

        for codigo, before_cache, ledger_total, before_physical, after_physical in results:
            print(
                f"[REPAIR] {codigo} | cache {before_cache:g} -> {ledger_total:g} | "
                f"físico {before_physical} -> {after_physical}"
            )

        if args.apply:
            db.session.commit()
            print(f"Aplicação concluída. Itens reparados: {len(results)}.")
        else:
            db.session.rollback()
            print(f"Dry-run concluído. Itens avaliados: {len(results)}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())