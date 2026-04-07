"""Relabela movimentos históricos cuja quantidade já está canônica, mas a unidade ficou errada.

Uso:
  .\.venv\Scripts\python.exe relabel_mismatched_canonical_movements.py --dry-run --codigo 7898936842060
  .\.venv\Scripts\python.exe relabel_mismatched_canonical_movements.py --apply --codigo 7898936842060
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sys
from dataclasses import dataclass


os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from sqlalchemy import func

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, StockBalance, StockMovement, stock_balance_supports_read_model_ready
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.legacy_stock_normalizer import is_packaging_unit_code, resolve_canonical_unit


@dataclass(slots=True)
class RelabelResult:
    product_id: str
    movement_id: int
    unit_before: str
    unit_after: str
    reason: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relabela movimentos históricos com unit_base canônica errada.")
    parser.add_argument("--codigo", action="append", help="Código do item a processar. Pode repetir o argumento.")
    parser.add_argument("--movement-id", action="append", type=int, help="ID específico do movimento a processar.")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o que seria alterado.")
    parser.add_argument("--apply", action="store_true", help="Aplica e faz commit das alterações.")
    return parser.parse_args()


def _normalize_unit(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "unidade": "un",
        "unidades": "un",
        "quilo": "kg",
        "quilos": "kg",
        "litro": "l",
        "litros": "l",
        "metro": "m",
        "metros": "m",
    }
    return aliases.get(raw, raw)


def _should_relabel(item: Item, movement: StockMovement) -> tuple[bool, str]:
    canonical_unit = _normalize_unit(resolve_canonical_unit(item))
    current_unit = _normalize_unit(movement.unit_base)
    metadata = movement.metadata_json or {}

    if not canonical_unit:
        return False, "canonical_unit_unresolved"
    if not current_unit or current_unit == canonical_unit:
        return False, "already_canonical"
    if is_packaging_unit_code(current_unit):
        return False, "packaging_unit_requires_other_tool"
    if str(metadata.get("source") or "").strip().lower() != "ledger_backfill":
        return False, "unsupported_source"
    if not bool(metadata.get("normalized_from_packaging")):
        return False, "not_packaging_backfill"
    return True, "packaging_backfill_label_only"


def _rebuild_product_state(product_id: str) -> None:
    supports_ready = stock_balance_supports_read_model_ready()
    ledger_total = float(
        db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
        .filter(StockMovement.product_id == product_id)
        .scalar()
        or 0.0
    )
    item = db.session.get(Item, product_id)
    if item is None:
        return

    balance = db.session.get(StockBalance, product_id)
    if balance is None:
        balance = StockBalance(product_id=product_id)
        db.session.add(balance)
    balance.quantity_base = ledger_total
    if supports_ready:
        balance.read_model_ready = True

    inventory_engine._sync_packaging_state_to_balance(
        item=item,
        quantity_base=ledger_total,
        unit_base=resolve_canonical_unit(item),
    )


def main() -> int:
    args = _parse_args()
    if args.apply and args.dry_run:
        print("Escolha apenas um modo: --dry-run ou --apply.")
        return 1
    dry_run = not args.apply or args.dry_run

    app = create_app()
    with app.app_context():
        query = StockMovement.query.order_by(StockMovement.product_id.asc(), StockMovement.id.asc())
        if args.codigo:
            codes = [value.strip() for value in args.codigo if value and value.strip()]
            query = query.filter(StockMovement.product_id.in_(codes))
        if args.movement_id:
            query = query.filter(StockMovement.id.in_(args.movement_id))

        changed: list[RelabelResult] = []
        touched_products: set[str] = set()
        for movement in query.all():
            item = db.session.get(Item, movement.product_id)
            if item is None:
                continue
            should_relabel, reason = _should_relabel(item, movement)
            if not should_relabel:
                continue

            canonical_unit = _normalize_unit(resolve_canonical_unit(item))
            unit_before = _normalize_unit(movement.unit_base)
            metadata = dict(movement.metadata_json or {})
            metadata["repair_canonical_unit_relabel"] = {
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "source": "relabel_mismatched_canonical_movements",
                "unit_base_before": unit_before,
                "unit_base_after": canonical_unit,
                "reason": reason,
            }
            metadata["canonical_unit"] = canonical_unit
            movement.unit_base = canonical_unit
            movement.metadata_json = metadata
            changed.append(
                RelabelResult(
                    product_id=item.codigo_item,
                    movement_id=int(movement.id),
                    unit_before=unit_before,
                    unit_after=canonical_unit,
                    reason=reason,
                )
            )
            touched_products.add(item.codigo_item)

        for product_id in sorted(touched_products):
            _rebuild_product_state(product_id)

        for entry in changed:
            print(
                f"[CHANGE] {entry.product_id} | movimento {entry.movement_id} | "
                f"{entry.unit_before} -> {entry.unit_after} | {entry.reason}"
            )

        if dry_run:
            db.session.rollback()
            print(f"Dry-run concluído. Movimentos alteráveis: {len(changed)}. Produtos afetados: {len(touched_products)}.")
            return 0

        db.session.commit()
        print(f"Aplicação concluída. Movimentos alterados: {len(changed)}. Produtos afetados: {len(touched_products)}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())