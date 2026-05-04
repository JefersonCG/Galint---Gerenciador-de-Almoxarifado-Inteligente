"""Reaplica a normalizacao estrutural dos 27 pendentes da saida operacional.

Esta migracao reaproveita o caminho oficial de update do InventoryService para:
- normalizar a unidade base para a unidade operacional correta;
- persistir metadados de embalagem inferiveis;
- sincronizar conversoes, dimensoes e precos normalizados.
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
from galint_flask.services.inventory import inventory_service


TARGET_CODES: tuple[str, ...] = (
    "07892904021716",
    "07898936842022",
    "100L",
    "200L",
    "300L",
    "60L",
    "7891035919787",
    "7891738018954",
    "7892261000447",
    "7897432700676",
    "7897637118962",
    "7897637126240",
    "7897841947686",
    "7898180829107",
    "7898214962961",
    "7898729414320",
    "7898924601617",
    "7898936842060",
    "7899682763500",
    "789987456654002",
    "789987456654003",
    "789987456654004",
    "789987456654005",
    "78998745665421",
    "CABO-RG6-001",
    "FOOD12215",
    "UYLN30460",
)

TRACKED_FIELDS: tuple[str, ...] = (
    "unidade",
    "tipo_embalagem",
    "tipo_embalagem_novo",
    "grandeza_referencia",
    "litros_por_embalagem",
    "unidades_por_embalagem",
)


def _snapshot(item: Item) -> dict[str, object]:
    return {field: getattr(item, field, None) for field in TRACKED_FIELDS}


def apply_migration() -> dict[str, object]:
    changed_items: list[dict[str, object]] = []

    for codigo in TARGET_CODES:
        item = db.session.get(Item, codigo)
        if item is None:
            raise RuntimeError(f"Item {codigo} nao encontrado")

        before = _snapshot(item)
        inventory_service.update_item(
            codigo,
            {
                "codigo": codigo,
                "ultima_edicao_por": "migracao_unidades_operacionais_pendentes",
            },
        )

        item = db.session.get(Item, codigo)
        if item is None:
            raise RuntimeError(f"Item {codigo} nao encontrado apos a atualizacao")

        after = _snapshot(item)
        unidade_normalizada = str(after.get("unidade") or "").strip().lower()
        if unidade_normalizada != "unidade":
            raise RuntimeError(f"Item {codigo} continuou fora da unidade operacional apos a migracao")

        changed_items.append(
            {
                "codigo": codigo,
                "descricao": item.descricao,
                "changed_fields": [field for field in TRACKED_FIELDS if before.get(field) != after.get(field)],
                "before": before,
                "after": after,
            }
        )

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