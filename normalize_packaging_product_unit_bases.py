"""Normaliza ProductUnit base de itens embalados para a unidade canônica.

Uso:
  .\.venv\Scripts\python.exe normalize_packaging_product_unit_bases.py --dry-run
  .\.venv\Scripts\python.exe normalize_packaging_product_unit_bases.py --apply
  .\.venv\Scripts\python.exe normalize_packaging_product_unit_bases.py --apply --codigo 7891323088072
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass


os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, ProductDimension, ProductUnit, ProductUnitConversion
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.legacy_stock_normalizer import is_packaging_unit_code, resolve_canonical_unit, resolve_packaging_factor


UNIT_LABELS = {
    "kg": "Kg",
    "l": "Litro",
    "m": "Metro",
    "un": "Unidade",
}

UNIT_DIMENSIONS = {
    "kg": "mass",
    "l": "volume",
    "m": "length",
    "un": "unit",
}


@dataclass(slots=True)
class NormalizationResult:
    codigo: str
    changed: bool
    message: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normaliza bases canônicas de ProductUnit para itens embalados.")
    parser.add_argument("--codigo", action="append", help="Código específico a processar. Pode repetir o argumento.")
    parser.add_argument("--limit", type=int, default=0, help="Limita a quantidade de itens processados.")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o que seria alterado.")
    parser.add_argument("--apply", action="store_true", help="Aplica e faz commit das alterações.")
    return parser.parse_args()


def _ensure_dimension(item: Item, canonical_unit: str) -> None:
    dimension = UNIT_DIMENSIONS.get(canonical_unit)
    if not dimension:
        return
    existing = next(
        (
            row
            for row in (item.product_dimensions or [])
            if (row.dimension or "").strip().lower() == dimension
        ),
        None,
    )
    if existing is not None:
        existing.enabled = True
        return
    db.session.add(
        ProductDimension(
            product_id=item.codigo_item,
            dimension=dimension,
            enabled=True,
        )
    )


def _ensure_canonical_unit(item: Item, canonical_unit: str) -> ProductUnit:
    existing = next(
        (
            unit
            for unit in (item.product_units or [])
            if (unit.unit_code or "").strip().lower() == canonical_unit
        ),
        None,
    )
    if existing is not None:
        existing.active = True
        existing.unit_label = existing.unit_label or UNIT_LABELS.get(canonical_unit, canonical_unit.upper())
        existing.dimension = existing.dimension or UNIT_DIMENSIONS.get(canonical_unit)
        return existing

    created = ProductUnit(
        product_id=item.codigo_item,
        unit_code=canonical_unit,
        unit_label=UNIT_LABELS.get(canonical_unit, canonical_unit.upper()),
        dimension=UNIT_DIMENSIONS.get(canonical_unit),
        is_base=False,
        active=True,
    )
    db.session.add(created)
    item.product_units.append(created)
    return created


def _ensure_conversion(item: Item, from_unit: str, to_unit: str, factor: float) -> None:
    existing = next(
        (
            conversion
            for conversion in (item.product_unit_conversions or [])
            if (conversion.from_unit or "").strip().lower() == from_unit
            and (conversion.to_unit or "").strip().lower() == to_unit
        ),
        None,
    )
    if existing is not None:
        if float(existing.factor or 0.0) not in {0.0, factor}:
            raise ValueError(
                f"Conversão conflitante para {item.codigo_item}: {from_unit}->{to_unit} já existe com fator {existing.factor}"
            )
        existing.factor = factor
        existing.active = True
        return

    db.session.add(
        ProductUnitConversion(
            product_id=item.codigo_item,
            from_unit=from_unit,
            to_unit=to_unit,
            factor=factor,
            metadata_json={"source": "normalize_packaging_product_unit_bases"},
            active=True,
        )
    )


def _normalize_item(item: Item) -> NormalizationResult:
    active_base_units = [unit for unit in (item.product_units or []) if unit.is_base and unit.active]
    if len(active_base_units) != 1:
        return NormalizationResult(item.codigo_item, False, "ignorado: item sem base única ativa")

    packaging_base = active_base_units[0]
    packaging_code = (packaging_base.unit_code or "").strip().lower()
    if not is_packaging_unit_code(packaging_code):
        return NormalizationResult(item.codigo_item, False, "ignorado: base já é canônica")

    canonical_unit = (resolve_canonical_unit(item) or "").strip().lower()
    if not canonical_unit or is_packaging_unit_code(canonical_unit):
        return NormalizationResult(item.codigo_item, False, "ignorado: unidade canônica não resolvida")

    factor = float(resolve_packaging_factor(item) or 0.0)
    if factor <= 0.0:
        return NormalizationResult(item.codigo_item, False, "ignorado: fator de embalagem inválido")

    canonical_product_unit = _ensure_canonical_unit(item, canonical_unit)
    for unit in active_base_units:
        unit.is_base = False
    canonical_product_unit.is_base = True
    canonical_product_unit.active = True

    _ensure_dimension(item, canonical_unit)
    _ensure_conversion(item, packaging_code, canonical_unit, factor)

    try:
        inventory_engine.sync_packaging_read_model(product_id=item.codigo_item, commit=False)
    except Exception:
        pass

    return NormalizationResult(
        item.codigo_item,
        True,
        f"base {packaging_code} -> {canonical_unit}; conversão {packaging_code}->{canonical_unit}={factor:g}",
    )


def main() -> int:
    args = _parse_args()
    if args.apply and args.dry_run:
        print("Escolha apenas um modo: --dry-run ou --apply.")
        return 1
    dry_run = not args.apply or args.dry_run

    app = create_app()
    with app.app_context():
        query = Item.query.order_by(Item.codigo_item.asc())
        if args.codigo:
            query = query.filter(Item.codigo_item.in_([codigo.strip() for codigo in args.codigo if codigo and codigo.strip()]))

        processed = 0
        changed = 0
        results: list[NormalizationResult] = []
        for item in query.all():
            processed += 1
            result = _normalize_item(item)
            results.append(result)
            if result.changed:
                changed += 1
            if args.limit and processed >= args.limit:
                break

        for result in results:
            prefix = "CHANGE" if result.changed else "SKIP"
            print(f"[{prefix}] {result.codigo} | {result.message}")

        if dry_run:
            db.session.rollback()
            print(f"Dry-run concluído. Itens avaliados: {processed}. Alterações potenciais: {changed}.")
            return 0

        db.session.commit()
        print(f"Aplicação concluída. Itens avaliados: {processed}. Alterados: {changed}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())