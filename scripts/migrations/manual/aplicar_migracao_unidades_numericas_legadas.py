"""Normaliza itens com unidade numerica legada para uma unidade base valida.

Esta migracao ataca apenas os 7 codigos auditados na revisao manual de 2026-05-04.
Ela reaproveita a mesma heuristica do InventoryService para evitar manter valores
como 0, 1, 2, 4, 6, 9 ou 12 no campo de unidade.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item
from galint_flask.services.inventory import InventoryService


TARGET_CODES: tuple[str, ...] = (
    "0216A008",
    "7896038108244",
    "7896231701129",
    "7897613520529",
    "7897826107937",
    "7898056460076",
    "7899036387024",
)

TRACKED_FIELDS: tuple[str, ...] = (
    "unidade",
    "tipo_embalagem",
    "tipo_embalagem_novo",
    "grandeza_referencia",
    "litros_por_embalagem",
    "unidades_por_embalagem",
)


def _is_numeric_legacy(value: object) -> bool:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return False
    try:
        float(raw)
    except (TypeError, ValueError):
        return False
    return True


def apply_migration() -> dict[str, object]:
    changed_items: list[dict[str, object]] = []

    for codigo in TARGET_CODES:
        item = db.session.get(Item, codigo)
        if item is None:
            raise RuntimeError(f"Item {codigo} nao encontrado")

        before = {field: getattr(item, field, None) for field in TRACKED_FIELDS}
        normalized = InventoryService._hydrate_missing_packaging_metadata({}, current_item=item)

        for field in TRACKED_FIELDS:
            if field in normalized and normalized[field] != getattr(item, field, None):
                setattr(item, field, normalized[field])

        after = {field: getattr(item, field, None) for field in TRACKED_FIELDS}
        if _is_numeric_legacy(after.get("unidade")):
            raise RuntimeError(f"Item {codigo} continuou com unidade numerica apos a normalizacao")

        changed_fields = [field for field in TRACKED_FIELDS if before.get(field) != after.get(field)]
        changed_items.append(
            {
                "codigo": codigo,
                "descricao": item.descricao,
                "changed_fields": changed_fields,
                "before": before,
                "after": after,
            }
        )

    db.session.commit()
    return {
        "total": len(changed_items),
        "changed": changed_items,
    }


def main() -> int:
    app = create_app()
    with app.app_context():
        result = apply_migration()
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())