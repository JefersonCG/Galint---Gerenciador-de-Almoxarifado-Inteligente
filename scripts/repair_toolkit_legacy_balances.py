from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from sqlalchemy import func

os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Entrada, InventarioEvento, Item, Saida, StockBalance, StockMovement
from galint_flask.services.ledger_backfill_normalized import LEGACY_REBUILD_REFERENCE_TYPES, ledger_backfill_service
from galint_flask.services.legacy_stock_normalizer import ignore_packaging_metadata_for_stock

TOLERANCE = 1e-6


@dataclass(slots=True)
class RepairSnapshot:
    codigo_item: str
    descricao: str
    legacy_balance: float
    ledger_balance: float
    cache_balance: float
    movement_count: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconstrói saldos legados de jogos/kits de ferramentas que estavam multiplicando pecas internas."
    )
    parser.add_argument("--codes", nargs="*", help="Códigos específicos para filtrar")
    parser.add_argument("--apply", action="store_true", help="Aplica a reconstrução no banco")
    return parser.parse_args()


def _normalize_codes(codes: list[str] | None) -> list[str]:
    return sorted({str(code or "").strip() for code in (codes or []) if str(code or "").strip()})


def _resolve_items(codes: list[str]) -> list[Item]:
    query = Item.query.order_by(Item.codigo_item.asc())
    if codes:
        query = query.filter(Item.codigo_item.in_(codes))
    return [item for item in query.all() if ignore_packaging_metadata_for_stock(item)]


def _legacy_balance(codigo_item: str) -> float:
    entradas = float(
        db.session.query(func.coalesce(func.sum(Entrada.quantidade), 0.0))
        .filter(Entrada.codigo_item == codigo_item)
        .scalar()
        or 0.0
    )
    saidas = float(
        db.session.query(func.coalesce(func.sum(Saida.quantidade), 0.0))
        .filter(Saida.codigo_item == codigo_item)
        .scalar()
        or 0.0
    )
    eventos = float(
        db.session.query(func.coalesce(func.sum(InventarioEvento.quantidade), 0.0))
        .filter(InventarioEvento.codigo_item == codigo_item)
        .scalar()
        or 0.0
    )
    return entradas - saidas + eventos


def _ledger_balance(codigo_item: str) -> float:
    return float(
        db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
        .filter(StockMovement.product_id == codigo_item)
        .scalar()
        or 0.0
    )


def _movement_count(codigo_item: str) -> int:
    return int(
        db.session.query(StockMovement.id)
        .filter(StockMovement.product_id == codigo_item)
        .count()
    )


def _build_snapshot(item: Item) -> RepairSnapshot:
    balance = db.session.get(StockBalance, item.codigo_item)
    return RepairSnapshot(
        codigo_item=item.codigo_item,
        descricao=item.descricao or item.codigo_item,
        legacy_balance=_legacy_balance(item.codigo_item),
        ledger_balance=_ledger_balance(item.codigo_item),
        cache_balance=float(getattr(balance, "quantity_base", 0.0) or 0.0),
        movement_count=_movement_count(item.codigo_item),
    )


def _print_snapshots(title: str, snapshots: list[RepairSnapshot]) -> None:
    print(title)
    print(f"Itens alvo: {len(snapshots)}")
    for snapshot in snapshots:
        print(
            f"{snapshot.codigo_item} | legado={snapshot.legacy_balance:g} | "
            f"ledger={snapshot.ledger_balance:g} | cache={snapshot.cache_balance:g} | "
            f"movimentos={snapshot.movement_count} | {snapshot.descricao}"
        )


def _count_rebuild_rows(codes: list[str]) -> int:
    if not codes:
        return 0
    return int(
        db.session.query(StockMovement.id)
        .filter(StockMovement.product_id.in_(codes))
        .filter(StockMovement.reference_type.in_(LEGACY_REBUILD_REFERENCE_TYPES))
        .count()
    )


def _has_divergence(snapshot: RepairSnapshot) -> bool:
    return (
        abs(snapshot.legacy_balance - snapshot.ledger_balance) > TOLERANCE
        or abs(snapshot.ledger_balance - snapshot.cache_balance) > TOLERANCE
    )


def main() -> int:
    args = _parse_args()
    app = create_app()

    with app.app_context():
        codes = _normalize_codes(args.codes)
        items = _resolve_items(codes)
        if not items:
            print("Nenhum kit de ferramenta com metadata de pecas internas foi encontrado.")
            return 0

        snapshots_before = [_build_snapshot(item) for item in items]
        inconsistent_codes = {
            snapshot.codigo_item
            for snapshot in snapshots_before
            if _has_divergence(snapshot)
        }
        items = [item for item in items if item.codigo_item in inconsistent_codes]
        snapshots_before = [snapshot for snapshot in snapshots_before if snapshot.codigo_item in inconsistent_codes]
        if not snapshots_before:
            print("Nenhum kit de ferramenta com metadata interna apresentou divergencia real entre legado, ledger e cache.")
            return 0

        _print_snapshots("ANTES DA RECONSTRUCAO", snapshots_before)

        if not args.apply:
            print(f"\nMovimentos legados a recriar: {_count_rebuild_rows([item.codigo_item for item in items])}")
            print("Use --apply para reconstruir o ledger desses itens a partir das tabelas legadas.")
            return 0

        summary = ledger_backfill_service.rebuild_products_from_legacy([item.codigo_item for item in items])
        db.session.commit()

        print(
            "\nREBUILD EXECUTADO | "
            f"entradas={summary.processed_entries} saidas={summary.processed_exits} eventos={summary.processed_events} "
            f"saldos={summary.balances_rebuilt}"
        )

        snapshots_after = [_build_snapshot(item) for item in items]
        _print_snapshots("\nDEPOIS DA RECONSTRUCAO", snapshots_after)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())