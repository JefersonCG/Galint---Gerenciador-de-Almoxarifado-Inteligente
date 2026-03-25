from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import Entrada, InventarioEvento, Item, ProductUnit, Saida, StockBalance, StockMovement, stock_balance_supports_read_model_ready


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

        for entry in Entrada.query.order_by(Entrada.data_entrada.asc(), Entrada.id_entrada.asc()).all():
            created = self._ensure_movement(
                product_id=entry.codigo_item,
                movement_type="entrada",
                quantity=float(entry.quantidade or 0),
                reference_type="entrada",
                reference_id=str(entry.id_entrada),
                created_at=entry.data_entrada,
                metadata={
                    "legacy_table": "entradas",
                    "matricula": entry.matricula,
                    "nota_fiscal": entry.nota_fiscal,
                },
            )
            if created == "created":
                processed_entries += 1
            elif created == "existing":
                skipped_existing += 1
            else:
                skipped_missing_product += 1

        for exit_row in Saida.query.order_by(Saida.data_saida.asc(), Saida.id_saida.asc()).all():
            created = self._ensure_movement(
                product_id=exit_row.codigo_item,
                movement_type="saida",
                quantity=-float(exit_row.quantidade or 0),
                reference_type="saida",
                reference_id=str(exit_row.id_saida),
                created_at=exit_row.data_saida,
                metadata={
                    "legacy_table": "saidas",
                    "matricula": exit_row.matricula,
                    "observacao": exit_row.observacao,
                    "local_servico": exit_row.local_servico,
                    "tipo_custodia": getattr(exit_row, "tipo_custodia", None),
                },
            )
            if created == "created":
                processed_exits += 1
            elif created == "existing":
                skipped_existing += 1
            else:
                skipped_missing_product += 1

        for event in (
            InventarioEvento.query
            .order_by(InventarioEvento.data_evento.asc(), InventarioEvento.id_evento.asc())
            .all()
        ):
            movement_type = self._classify_event_type(event.tipo)
            created = self._ensure_movement(
                product_id=event.codigo_item,
                movement_type=movement_type,
                quantity=float(event.quantidade or 0),
                reference_type="inventario_evento",
                reference_id=str(event.id_evento),
                created_at=event.data_evento,
                metadata={
                    "legacy_table": "inventario_eventos",
                    "legacy_event_type": event.tipo,
                    "matricula": event.matricula,
                    "descricao": event.descricao,
                },
            )
            if created == "created":
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

        for entry in entries:
            created = self._ensure_movement(
                product_id=entry.codigo_item,
                movement_type="entrada",
                quantity=float(entry.quantidade or 0),
                reference_type="entrada",
                reference_id=str(entry.id_entrada),
                created_at=entry.data_entrada,
                metadata={
                    "legacy_table": "entradas",
                    "matricula": entry.matricula,
                    "nota_fiscal": entry.nota_fiscal,
                    "source": "restore_backup_json",
                    "user_id": entry.matricula,
                },
            )
            if created == "created":
                processed_entries += 1
            elif created == "existing":
                skipped_existing += 1
            else:
                skipped_missing_product += 1

        for exit_row in exits:
            created = self._ensure_movement(
                product_id=exit_row.codigo_item,
                movement_type="saida",
                quantity=-float(exit_row.quantidade or 0),
                reference_type="saida",
                reference_id=str(exit_row.id_saida),
                created_at=exit_row.data_saida,
                metadata={
                    "legacy_table": "saidas",
                    "matricula": exit_row.matricula,
                    "observacao": exit_row.observacao,
                    "local_servico": exit_row.local_servico,
                    "tipo_custodia": getattr(exit_row, "tipo_custodia", None),
                    "source": "restore_backup_json",
                    "user_id": exit_row.matricula,
                },
            )
            if created == "created":
                processed_exits += 1
            elif created == "existing":
                skipped_existing += 1
            else:
                skipped_missing_product += 1

        for event in events:
            movement_type = self._classify_event_type(event.tipo)
            created = self._ensure_movement(
                product_id=event.codigo_item,
                movement_type=movement_type,
                quantity=float(event.quantidade or 0),
                reference_type="inventario_evento",
                reference_id=str(event.id_evento),
                created_at=event.data_evento,
                metadata={
                    "legacy_table": "inventario_eventos",
                    "legacy_event_type": event.tipo,
                    "matricula": event.matricula,
                    "descricao": event.descricao,
                    "source": "restore_backup_json",
                    "user_id": event.matricula,
                },
            )
            if created == "created":
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
                not_preserved += 1
                continue

            if result.classification in {"divergencia_zero", "divergencia_explicavel"}:
                preserved += 1
            else:
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
        movement.unit_base = self._resolve_unit_base(product_id)
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
        base_unit = (
            ProductUnit.query.filter_by(product_id=product_id, is_base=True, active=True)
            .order_by(ProductUnit.id.asc())
            .first()
        )
        if base_unit and base_unit.unit_code:
            return (base_unit.unit_code or "").strip().lower()
        item = Item.query.get(product_id)
        if item and item.unidade:
            return (item.unidade or "").strip().lower()
        if item and item.tipo_embalagem_novo:
            return (item.tipo_embalagem_novo or "").strip().lower()
        return "un"

    @staticmethod
    def _classify_event_type(event_type: str | None) -> str:
        raw = (event_type or "").strip().lower()
        if raw.startswith("devolucao"):
            return "devolucao"
        if "ajuste" in raw:
            return "ajuste"
        if raw in {"quebra_ferramenta", "reparo_ferramenta", "perda"}:
            return "ajuste"
        return "ajuste"


ledger_backfill_service = LedgerBackfillService()