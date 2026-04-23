"""Normaliza movimentos históricos gravados com unit_base de embalagem.

Uso:
  .\.venv\Scripts\python.exe normalize_packaging_stock_movements.py --dry-run
  .\.venv\Scripts\python.exe normalize_packaging_stock_movements.py --apply
  .\.venv\Scripts\python.exe normalize_packaging_stock_movements.py --apply --codigo 7891323088072
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
from galint_flask.services.legacy_stock_normalizer import (
    is_packaging_unit_code,
    resolve_canonical_unit,
    resolve_packaging_factor,
    uses_packaging_legacy_normalization,
)


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


@dataclass(slots=True)
class MovementNormalization:
    product_id: str
    movement_id: int
    quantity_before: float
    unit_before: str
    quantity_after: float
    unit_after: str
    reason: str


@dataclass(slots=True)
class MovementSkip:
    product_id: str
    movement_id: int
    quantity_before: float
    unit_before: str
    reason: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normaliza movimentos históricos com unit_base de embalagem.")
    parser.add_argument("--codigo", action="append", help="Código do item a processar. Pode repetir o argumento.")
    parser.add_argument("--movement-id", action="append", type=int, help="ID específico do movimento a processar. Pode repetir o argumento.")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o que seria alterado.")
    parser.add_argument("--apply", action="store_true", help="Aplica e faz commit das alterações.")
    return parser.parse_args()


def _resolve_corrected_quantity(movement: StockMovement, *, packaging_factor: float) -> tuple[float, str] | None:
    metadata = movement.metadata_json or {}
    input_quantity = metadata.get("input_quantity")
    try:
        quantity_before = float(movement.quantity_base or 0.0)
    except (TypeError, ValueError):
        return None

    sign = -1.0 if quantity_before < 0 else 1.0
    magnitude = abs(quantity_before)

    if not _should_multiply_quantity(movement, packaging_factor=packaging_factor, magnitude=magnitude):
        return sign * magnitude, "unit_label_only"

    try:
        input_quantity_value = abs(float(input_quantity)) if input_quantity not in (None, "") else None
    except (TypeError, ValueError):
        input_quantity_value = None

    if input_quantity_value is not None and input_quantity_value > 0:
        return sign * input_quantity_value * packaging_factor, "input_quantity_x_packaging_factor"

    return sign * magnitude * packaging_factor, "quantity_base_x_packaging_factor"


def _should_multiply_quantity(movement: StockMovement, *, packaging_factor: float, magnitude: float) -> bool:
    metadata = movement.metadata_json or {}
    source = str(metadata.get("source") or "").strip().lower()
    reference_type = str(movement.reference_type or "").strip().lower()

    if packaging_factor <= 0.0:
        return False
    if source == "documento_fiscal" or reference_type == "entrada_documento_item":
        return True
    if source == "ledger_backfill" and reference_type in {"entrada", "saida", "inventario_evento"}:
        return True
    if packaging_factor < 1.0:
        return True
    if magnitude >= packaging_factor:
        return False
    return True


def _normalize_movement(item: Item, movement: StockMovement) -> MovementNormalization | MovementSkip | None:
    canonical_unit = _normalize_unit(resolve_canonical_unit(item))
    packaging_factor = float(resolve_packaging_factor(item) or 0.0)
    unit_before = _normalize_unit(movement.unit_base)
    quantity_before = float(movement.quantity_base or 0.0)
    item_unit = _normalize_unit(getattr(item, "unidade", None))
    looks_like_legacy_operational_unit = (
        uses_packaging_legacy_normalization(item)
        and bool(item_unit)
        and unit_before == item_unit
        and unit_before != canonical_unit
    )

    def skipped(reason: str) -> MovementSkip:
        return MovementSkip(
            product_id=item.codigo_item,
            movement_id=int(movement.id),
            quantity_before=quantity_before,
            unit_before=unit_before,
            reason=reason,
        )

    if not canonical_unit or is_packaging_unit_code(canonical_unit):
        return skipped("canonical_unit_unresolved")
    if not unit_before or (not is_packaging_unit_code(unit_before) and not looks_like_legacy_operational_unit):
        return None
    if packaging_factor <= 0.0:
        return skipped("packaging_factor_unresolved")

    corrected = _resolve_corrected_quantity(movement, packaging_factor=packaging_factor)
    if corrected is None:
        return skipped("corrected_quantity_unresolved")

    quantity_after, reason = corrected
    if abs(quantity_before - quantity_after) <= 1e-9 and unit_before == canonical_unit:
        return None

    metadata = dict(movement.metadata_json or {})
    metadata["repair_packaging_unit_base"] = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "source": "normalize_packaging_stock_movements",
        "quantity_base_before": quantity_before,
        "unit_base_before": unit_before,
        "quantity_base_after": quantity_after,
        "unit_base_after": canonical_unit,
        "reason": reason,
        "packaging_factor": packaging_factor,
    }
    metadata["factor_applied"] = packaging_factor
    metadata["conversion_path"] = [
        {
            "from_unit": unit_before,
            "to_unit": canonical_unit,
            "factor": packaging_factor,
            "source": "historical_packaging_movement_normalization",
        }
    ]

    movement.quantity_base = quantity_after
    movement.unit_base = canonical_unit
    movement.metadata_json = metadata

    return MovementNormalization(
        product_id=item.codigo_item,
        movement_id=int(movement.id),
        quantity_before=quantity_before,
        unit_before=unit_before,
        quantity_after=quantity_after,
        unit_after=canonical_unit,
        reason=reason,
    )


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
            codigos = [value.strip() for value in args.codigo if value and value.strip()]
            query = query.filter(StockMovement.product_id.in_(codigos))
        if args.movement_id:
            query = query.filter(StockMovement.id.in_(args.movement_id))

        changed: list[MovementNormalization] = []
        skipped: list[MovementSkip] = []
        touched_products: set[str] = set()
        for movement in query.all():
            item = db.session.get(Item, movement.product_id)
            if item is None:
                continue
            normalized = _normalize_movement(item, movement)
            if normalized is None:
                continue
            if isinstance(normalized, MovementSkip):
                skipped.append(normalized)
                continue
            changed.append(normalized)
            touched_products.add(normalized.product_id)

        for product_id in sorted(touched_products):
            _rebuild_product_state(product_id)

        for entry in changed:
            print(
                f"[CHANGE] {entry.product_id} | movimento {entry.movement_id} | "
                f"{entry.quantity_before:g} {entry.unit_before} -> {entry.quantity_after:g} {entry.unit_after} | {entry.reason}"
            )

        for entry in skipped:
            print(
                f"[SKIP] {entry.product_id} | movimento {entry.movement_id} | "
                f"{entry.quantity_before:g} {entry.unit_before} | {entry.reason}"
            )

        if dry_run:
            db.session.rollback()
            print(
                f"Dry-run concluído. Movimentos candidatos: {len(changed)}. "
                f"Produtos afetados: {len(touched_products)}. Ignorados: {len(skipped)}."
            )
            return 0

        db.session.commit()
        print(
            f"Aplicação concluída. Movimentos alterados: {len(changed)}. "
            f"Produtos afetados: {len(touched_products)}. Ignorados: {len(skipped)}."
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())