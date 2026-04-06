from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import Entrada, InventarioEvento, Item, Saida, StockBalance, StockMovement, stock_balance_supports_read_model_ready
from .legacy_stock_normalizer import build_normalized_legacy_movements, resolve_canonical_unit

LEGACY_REBUILD_REFERENCE_TYPES = ("entrada", "saida", "inventario_evento", "legacy_movimento")


@dataclass(slots=True)
class BackfillSummary:
    processed_entries: int
    processed_exits: int
    processed_events: int
    skipped_existing: int
    skipped_missing_product: int
    balances_rebuilt: int
    read_models_preserved: int
    read_models_not_preserved: int


class LedgerBackfillService:
    """Migra registros legados para o novo ledger de forma idempotente."""

    def backfill(self, *, clear_balances: bool = False) -> BackfillSummary:
        processed_entries = 0
        processed_exits = 0
        processed_events = 0
        skipped_existing = 0
        skipped_missing_product = 0
        previously_ready_products = self._get_ready_products() if not clear_balances else set()

        if clear_balances:
            StockBalance.query.delete()
            db.session.flush()

        grouped_rows, missing_rows = self._group_legacy_rows()
        skipped_missing_product += missing_rows

        for product_id in sorted(grouped_rows):
            payload = grouped_rows[product_id]
            for movement in build_normalized_legacy_movements(
                payload["item"],
                entries=payload["entries"],
                exits=payload["exits"],
                events=payload["events"],
            ):
                created = self._ensure_movement(
                    product_id=product_id,
                    movement_type=movement.movement_type,
                    quantity=movement.quantity_base,
                    reference_type=movement.reference_type,
                    reference_id=movement.reference_id,
                    created_at=movement.created_at,
                    metadata=movement.metadata,
                    unit_base=movement.unit_base,
                )
                if created == "created":
                    if movement.reference_type == "entrada":
                        processed_entries += 1
                    elif movement.reference_type == "saida":
                        processed_exits += 1
                    else:
                        processed_events += 1
                elif created == "existing":
                    skipped_existing += 1
                else:
                    skipped_missing_product += 1

        balances_rebuilt = self.rebuild_balances()
        read_models_preserved, read_models_not_preserved = self._restore_ready_products(previously_ready_products)
        db.session.commit()
        return BackfillSummary(
            processed_entries=processed_entries,
            processed_exits=processed_exits,
            processed_events=processed_events,
            skipped_existing=skipped_existing,
            skipped_missing_product=skipped_missing_product,
            balances_rebuilt=balances_rebuilt,
            read_models_preserved=read_models_preserved,
            read_models_not_preserved=read_models_not_preserved,
        )

    def sync_restored_rows(
        self,
        *,
        entry_ids: list[int] | None = None,
        exit_ids: list[int] | None = None,
        event_ids: list[int] | None = None,
    ) -> BackfillSummary:
        processed_entries = 0
        processed_exits = 0
        processed_events = 0
        skipped_existing = 0
        skipped_missing_product = 0

        entries = self._query_rows_by_ids(Entrada, Entrada.id_entrada, entry_ids)
        exits = self._query_rows_by_ids(Saida, Saida.id_saida, exit_ids)
        events = self._query_rows_by_ids(InventarioEvento, InventarioEvento.id_evento, event_ids)
        touched_products = {
            (row.codigo_item or "").strip()
            for row in [*entries, *exits, *events]
            if getattr(row, "codigo_item", None)
        }
        previously_ready_products = self._get_ready_products().intersection(touched_products)
        grouped_rows, missing_rows = self._group_legacy_rows(product_ids=touched_products)
        skipped_missing_product += missing_rows

        for product_id in sorted(grouped_rows):
            payload = grouped_rows[product_id]
            for movement in build_normalized_legacy_movements(
                payload["item"],
                entries=payload["entries"],
                exits=payload["exits"],
                events=payload["events"],
            ):
                created = self._ensure_movement(
                    product_id=product_id,
                    movement_type=movement.movement_type,
                    quantity=movement.quantity_base,
                    reference_type=movement.reference_type,
                    reference_id=movement.reference_id,
                    created_at=movement.created_at,
                    metadata=movement.metadata,
                    unit_base=movement.unit_base,
                )
                if created == "created":
                    if movement.reference_type == "entrada":
                        processed_entries += 1
                    elif movement.reference_type == "saida":
                        processed_exits += 1
                    else:
                        processed_events += 1
                elif created == "existing":
                    skipped_existing += 1
                else:
                    skipped_missing_product += 1

        balances_rebuilt = self.rebuild_balances_for_products(touched_products)
        read_models_preserved, read_models_not_preserved = self._restore_ready_products(previously_ready_products)
        db.session.flush()
        return BackfillSummary(
            processed_entries=processed_entries,
            processed_exits=processed_exits,
            processed_events=processed_events,
            skipped_existing=skipped_existing,
            skipped_missing_product=skipped_missing_product,
            balances_rebuilt=balances_rebuilt,
            read_models_preserved=read_models_preserved,
            read_models_not_preserved=read_models_not_preserved,
        )

    def rebuild_products_from_legacy(
        self,
        product_ids: set[str] | list[str] | tuple[str, ...],
        *,
        clear_existing_movements: bool = True,
    ) -> BackfillSummary:
        normalized_product_ids = {
            (product_id or "").strip()
            for product_id in product_ids
            if (product_id or "").strip()
        }
        if not normalized_product_ids:
            return BackfillSummary(
                processed_entries=0,
                processed_exits=0,
                processed_events=0,
                skipped_existing=0,
                skipped_missing_product=0,
                balances_rebuilt=0,
                read_models_preserved=0,
                read_models_not_preserved=0,
            )

        processed_entries = 0
        processed_exits = 0
        processed_events = 0
        skipped_existing = 0
        skipped_missing_product = 0
        previously_ready_products = self._get_ready_products().intersection(normalized_product_ids)

        if clear_existing_movements:
            (
                StockMovement.query
                .filter(StockMovement.product_id.in_(sorted(normalized_product_ids)))
                .filter(StockMovement.reference_type.in_(LEGACY_REBUILD_REFERENCE_TYPES))
                .delete(synchronize_session=False)
            )
            db.session.flush()

        grouped_rows, missing_rows = self._group_legacy_rows(product_ids=normalized_product_ids)
        skipped_missing_product += missing_rows

        for product_id in sorted(grouped_rows):
            payload = grouped_rows[product_id]
            for movement in build_normalized_legacy_movements(
                payload["item"],
                entries=payload["entries"],
                exits=payload["exits"],
                events=payload["events"],
            ):
                created = self._ensure_movement(
                    product_id=product_id,
                    movement_type=movement.movement_type,
                    quantity=movement.quantity_base,
                    reference_type=movement.reference_type,
                    reference_id=movement.reference_id,
                    created_at=movement.created_at,
                    metadata=movement.metadata,
                    unit_base=movement.unit_base,
                )
                if created == "created":
                    if movement.reference_type == "entrada":
                        processed_entries += 1
                    elif movement.reference_type == "saida":
                        processed_exits += 1
                    else:
                        processed_events += 1
                elif created == "existing":
                    skipped_existing += 1
                else:
                    skipped_missing_product += 1

        balances_rebuilt = self.rebuild_balances_for_products(normalized_product_ids)
        read_models_preserved, read_models_not_preserved = self._restore_ready_products(previously_ready_products)
        db.session.flush()
        return BackfillSummary(
            processed_entries=processed_entries,
            processed_exits=processed_exits,
            processed_events=processed_events,
            skipped_existing=skipped_existing,
            skipped_missing_product=skipped_missing_product,
            balances_rebuilt=balances_rebuilt,
            read_models_preserved=read_models_preserved,
            read_models_not_preserved=read_models_not_preserved,
        )

    def rebuild_balances(self) -> int:
        totals = (
            db.session.query(
                StockMovement.product_id,
                func.coalesce(func.sum(StockMovement.quantity_base), 0.0),
            )
            .group_by(StockMovement.product_id)
            .all()
        )

        rebuilt = 0
        seen_products: set[str] = set()
        for product_id, total in totals:
            if not product_id:
                continue
            seen_products.add(product_id)
            balance = db.session.get(StockBalance, product_id)
            if balance is None:
                balance = StockBalance()
                balance.product_id = product_id
                db.session.add(balance)
            balance.quantity_base = float(total or 0.0)
            rebuilt += 1

        for balance in StockBalance.query.all():
            if balance.product_id not in seen_products:
                balance.quantity_base = 0.0
                rebuilt += 1

        db.session.flush()
        return rebuilt

    def rebuild_balances_for_products(self, product_ids: set[str] | list[str] | tuple[str, ...]) -> int:
        normalized_product_ids = {
            (product_id or "").strip()
            for product_id in product_ids
            if (product_id or "").strip()
        }
        if not normalized_product_ids:
            return 0

        totals = dict(
            db.session.query(
                StockMovement.product_id,
                func.coalesce(func.sum(StockMovement.quantity_base), 0.0),
            )
            .filter(StockMovement.product_id.in_(sorted(normalized_product_ids)))
            .group_by(StockMovement.product_id)
            .all()
        )

        rebuilt = 0
        for product_id in sorted(normalized_product_ids):
            balance = db.session.get(StockBalance, product_id)
            if balance is None:
                balance = StockBalance()
                balance.product_id = product_id
                db.session.add(balance)
            balance.quantity_base = float(totals.get(product_id, 0.0) or 0.0)
            rebuilt += 1

        db.session.flush()
        return rebuilt

    @staticmethod
    def _query_rows_by_ids(model: type[Entrada] | type[Saida] | type[InventarioEvento], pk_column: Any, row_ids: list[int] | None):
        normalized_ids = [int(row_id) for row_id in (row_ids or []) if row_id is not None]
        if not normalized_ids:
            return []
        return (
            model.query
            .filter(pk_column.in_(normalized_ids))
            .order_by(pk_column.asc())
            .all()
        )

    def _group_legacy_rows(self, *, product_ids: set[str] | list[str] | tuple[str, ...] | None = None) -> tuple[dict[str, dict[str, Any]], int]:
        normalized_product_ids = {
            (product_id or "").strip()
            for product_id in (product_ids or [])
            if (product_id or "").strip()
        }

        item_query = Item.query
        if normalized_product_ids:
            item_query = item_query.filter(Item.codigo_item.in_(sorted(normalized_product_ids)))
        item_cache = {item.codigo_item: item for item in item_query.all()}
        grouped_rows: dict[str, dict[str, Any]] = {
            codigo_item: {
                "item": item,
                "entries": [],
                "exits": [],
                "events": [],
            }
            for codigo_item, item in item_cache.items()
        }

        skipped_missing_product = 0

        entry_query = Entrada.query.order_by(Entrada.data_entrada.asc(), Entrada.id_entrada.asc())
        exit_query = Saida.query.order_by(Saida.data_saida.asc(), Saida.id_saida.asc())
        event_query = InventarioEvento.query.order_by(InventarioEvento.data_evento.asc(), InventarioEvento.id_evento.asc())
        if normalized_product_ids:
            entry_query = entry_query.filter(Entrada.codigo_item.in_(sorted(normalized_product_ids)))
            exit_query = exit_query.filter(Saida.codigo_item.in_(sorted(normalized_product_ids)))
            event_query = event_query.filter(InventarioEvento.codigo_item.in_(sorted(normalized_product_ids)))

        for entry in entry_query.all():
            codigo_item = (entry.codigo_item or "").strip()
            if codigo_item not in item_cache:
                skipped_missing_product += 1
                continue
            grouped_rows[codigo_item]["entries"].append(entry)

        for exit_row in exit_query.all():
            codigo_item = (exit_row.codigo_item or "").strip()
            if codigo_item not in item_cache:
                skipped_missing_product += 1
                continue
            grouped_rows[codigo_item]["exits"].append(exit_row)

        for event in event_query.all():
            codigo_item = (event.codigo_item or "").strip()
            if codigo_item not in item_cache:
                skipped_missing_product += 1
                continue
            grouped_rows[codigo_item]["events"].append(event)

        grouped_rows = {
            codigo_item: payload
            for codigo_item, payload in grouped_rows.items()
            if payload["entries"] or payload["exits"] or payload["events"]
        }
        return grouped_rows, skipped_missing_product

    def _get_ready_products(self) -> set[str]:
        if not stock_balance_supports_read_model_ready():
            return set()
        rows = (
            db.session.query(StockBalance.product_id)
            .filter(StockBalance.read_model_ready.is_(True))
            .all()
        )
        return {str(row[0]).strip() for row in rows if row and row[0]}

    def _restore_ready_products(self, product_ids: set[str]) -> tuple[int, int]:
        if not product_ids or not stock_balance_supports_read_model_ready():
            return 0, 0

        from .ledger_reconciliation import ledger_reconciliation_service

        preserved = 0
        not_preserved = 0
        for product_id in sorted(product_ids):
            balance = db.session.get(StockBalance, product_id)
            if balance is None:
                not_preserved += 1
                continue

            try:
                result = ledger_reconciliation_service.reconcile_product(product_id)
            except Exception:
                if hasattr(balance, "read_model_ready"):
                    balance.read_model_ready = False
                not_preserved += 1
                continue

            if result.classification in {"divergencia_zero", "divergencia_explicavel"}:
                if hasattr(balance, "read_model_ready"):
                    balance.read_model_ready = True
                preserved += 1
            else:
                if hasattr(balance, "read_model_ready"):
                    balance.read_model_ready = False
                not_preserved += 1

        db.session.flush()
        return preserved, not_preserved

    def _ensure_movement(
        self,
        *,
        product_id: str | None,
        movement_type: str,
        quantity: float,
        reference_type: str,
        reference_id: str,
        created_at: datetime | None,
        metadata: dict[str, Any],
        unit_base: str | None = None,
    ) -> str:
        product_id = (product_id or "").strip()
        if not product_id:
            return "missing_product"
        if quantity == 0:
            return "existing"

        if db.session.get(Item, product_id) is None:
            return "missing_product"

        existing = (
            StockMovement.query.filter_by(
                product_id=product_id,
                reference_type=reference_type,
                reference_id=reference_id,
            )
            .first()
        )
        if existing is not None:
            return "existing"

        movement = StockMovement()
        movement.product_id = product_id
        movement.movement_type = movement_type
        movement.quantity_base = float(quantity)
        movement.unit_base = (unit_base or self._resolve_unit_base(product_id) or "un").strip().lower()
        movement.reference_type = reference_type
        movement.reference_id = reference_id
        movement.metadata_json = {
            **metadata,
            "source": metadata.get("source") or "ledger_backfill",
            "user_id": metadata.get("user_id") or metadata.get("matricula"),
        }
        movement.created_at = created_at or datetime.utcnow()
        db.session.add(movement)
        db.session.flush()
        return "created"

    def _resolve_unit_base(self, product_id: str) -> str:
        item = Item.query.get(product_id)
        if item:
            return resolve_canonical_unit(item)
        return "un"


ledger_backfill_service = LedgerBackfillService()
