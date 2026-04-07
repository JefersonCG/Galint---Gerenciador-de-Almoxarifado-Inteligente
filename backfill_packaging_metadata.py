"""Backfill seguro de metadados de embalagem para itens com histórico em unidade de embalagem.

Uso:
  .\.venv\Scripts\python.exe backfill_packaging_metadata.py --dry-run
  .\.venv\Scripts\python.exe backfill_packaging_metadata.py --apply
  .\.venv\Scripts\python.exe backfill_packaging_metadata.py --apply --codigo 7896155116405
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace


os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, StockMovement
from galint_flask.services.inventory import InventoryService
from galint_flask.services.legacy_stock_normalizer import is_packaging_unit_code, resolve_canonical_unit, resolve_packaging_factor


PACKAGING_UNITS = ("balde", "bombona", "caixa", "fardo", "lata", "pacote", "rolo", "saco")
BACKFILL_FIELDS = (
    "tipo_embalagem_novo",
    "litros_por_embalagem",
    "grandeza_referencia",
    "unidades_por_embalagem",
    "unidade",
)


@dataclass(slots=True)
class BackfillPlan:
    codigo_item: str
    changed: bool
    message: str
    changes: dict[str, object]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill de metadados de embalagem a partir do histórico.")
    parser.add_argument("--codigo", action="append", help="Código do item a processar. Pode repetir o argumento.")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o que seria alterado.")
    parser.add_argument("--apply", action="store_true", help="Aplica e faz commit das alterações.")
    return parser.parse_args()


def _target_codes(explicit_codes: list[str] | None) -> list[str]:
    normalized_codes = sorted({str(code or "").strip() for code in (explicit_codes or []) if str(code or "").strip()})
    if normalized_codes:
        return normalized_codes

    rows = (
        db.session.query(StockMovement.product_id)
        .filter(StockMovement.unit_base.in_(PACKAGING_UNITS))
        .distinct()
        .order_by(StockMovement.product_id.asc())
        .all()
    )
    return [str(row[0]).strip() for row in rows if row and str(row[0]).strip()]


def _build_probe(item: Item, changes: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        codigo_item=item.codigo_item,
        descricao=item.descricao,
        categoria=item.categoria,
        marca=item.marca,
        unidade=changes.get("unidade", item.unidade),
        tipo_embalagem_novo=changes.get("tipo_embalagem_novo", item.tipo_embalagem_novo),
        litros_por_embalagem=changes.get("litros_por_embalagem", item.litros_por_embalagem),
        grandeza_referencia=changes.get("grandeza_referencia", item.grandeza_referencia),
        unidades_por_embalagem=changes.get("unidades_por_embalagem", item.unidades_por_embalagem),
        product_units=getattr(item, "product_units", []) or [],
    )


def _plan_item(item: Item) -> BackfillPlan:
    hydrated = InventoryService._hydrate_missing_packaging_metadata({}, current_item=item)
    changes: dict[str, object] = {}
    for field in BACKFILL_FIELDS:
        proposed = hydrated.get(field)
        if proposed in (None, ""):
            continue
        current = getattr(item, field, None)
        if str(proposed) == str(current):
            continue
        changes[field] = proposed

    if not changes:
        return BackfillPlan(item.codigo_item, False, "sem alteração inferida", {})

    probe = _build_probe(item, changes)
    canonical_unit = str(resolve_canonical_unit(probe) or "").strip().lower()
    packaging_factor = float(resolve_packaging_factor(probe) or 0.0)
    if not canonical_unit or is_packaging_unit_code(canonical_unit):
        return BackfillPlan(item.codigo_item, False, "unidade canônica não resolvida após inferência", {})
    if packaging_factor <= 0.0:
        return BackfillPlan(item.codigo_item, False, "fator de embalagem não resolvido após inferência", {})

    message = ", ".join(f"{field}={value}" for field, value in changes.items())
    return BackfillPlan(item.codigo_item, True, message, changes)


def main() -> int:
    args = _parse_args()
    if args.apply and args.dry_run:
        print("Escolha apenas um modo: --dry-run ou --apply.")
        return 1
    dry_run = not args.apply or args.dry_run

    app = create_app()
    with app.app_context():
        codes = _target_codes(args.codigo)
        changed = 0
        planned: list[BackfillPlan] = []
        for code in codes:
            item = db.session.get(Item, code)
            if item is None:
                continue
            plan = _plan_item(item)
            planned.append(plan)
            prefix = "CHANGE" if plan.changed else "SKIP"
            print(f"[{prefix}] {code} | {plan.message}")
            if not plan.changed:
                continue
            changed += 1
            if dry_run:
                continue
            for field, value in plan.changes.items():
                setattr(item, field, value)

        if dry_run:
            db.session.rollback()
            print(f"Dry-run concluído. Itens avaliados: {len(planned)}. Alterações potenciais: {changed}.")
            return 0

        db.session.commit()
        print(f"Aplicação concluída. Itens avaliados: {len(planned)}. Alterados: {changed}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())