from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func

from ..extensions import db
from ..models import Entrada, InventarioEvento, Item, Saida, StockBalance, stock_balance_supports_read_model_ready
from .legacy_stock_normalizer import resolve_canonical_unit, resolve_packaging_factor


@dataclass(slots=True)
class BalanceSnapshot:
    product_id: str
    quantity_base: float
    unit_base: str | None
    source: str
    migrated: bool


class BalanceProvider:
    """Centraliza leitura de saldo durante a migração para ledger."""

    @staticmethod
    def _should_prefer_stock_balance_for_nf_origin(item: Item | None, balance: StockBalance | None) -> bool:
        if item is None or balance is None:
            return False
        origem = (getattr(item, "pre_cadastro_origem", "") or "").strip().lower()
        if origem != "nf":
            return False
        try:
            canonical_unit = (resolve_canonical_unit(item) or "").strip().lower()
            packaging_factor = float(resolve_packaging_factor(item) or 0.0)
            if (
                canonical_unit in {"un", "par"}
                and 0 < packaging_factor <= 1.0
                and BalanceProvider._has_legacy_history(item.codigo_item)
            ):
                return False
        except Exception:
            pass
        return True

    @staticmethod
    def get_balances(product_ids: list[str], *, items_by_id: dict[str, Item] | None = None) -> dict[str, BalanceSnapshot]:
        normalized_ids = []
        seen_ids: set[str] = set()
        for raw_product_id in product_ids:
            product_id = (raw_product_id or "").strip()
            if product_id and product_id not in seen_ids:
                seen_ids.add(product_id)
                normalized_ids.append(product_id)

        if not normalized_ids:
            return {}

        item_lookup = dict(items_by_id or {})
        missing_ids = [product_id for product_id in normalized_ids if product_id not in item_lookup]
        if missing_ids:
            rows = Item.query.filter(Item.codigo_item.in_(missing_ids)).all()
            item_lookup.update({item.codigo_item: item for item in rows if item.codigo_item})

        balance_rows = {
            row.product_id: row
            for row in StockBalance.query.filter(StockBalance.product_id.in_(normalized_ids)).all()
        }

        migrated_ids: set[str] = set()
        if stock_balance_supports_read_model_ready():
            migrated_ids = {
                product_id
                for product_id, row in balance_rows.items()
                if bool(getattr(row, "read_model_ready", False))
            }

        migrated_ids.update(
            product_id
            for product_id, row in balance_rows.items()
            if BalanceProvider._should_prefer_stock_balance_for_nf_origin(item_lookup.get(product_id), row)
        )

        legacy_candidate_ids = [product_id for product_id in normalized_ids if product_id not in migrated_ids]
        legacy_history_ids: set[str] = set()
        legacy_balances: dict[str, float] = {}

        if legacy_candidate_ids:
            for model in (Entrada, Saida, InventarioEvento):
                rows = (
                    db.session.query(model.codigo_item)
                    .filter(model.codigo_item.in_(legacy_candidate_ids))
                    .distinct()
                    .all()
                )
                legacy_history_ids.update(codigo for (codigo,) in rows if codigo)

            if legacy_history_ids:
                entradas = {
                    codigo: float(total or 0.0)
                    for codigo, total in (
                        db.session.query(
                            Entrada.codigo_item,
                            func.coalesce(func.sum(Entrada.quantidade), 0.0),
                        )
                        .filter(Entrada.codigo_item.in_(legacy_history_ids))
                        .group_by(Entrada.codigo_item)
                        .all()
                    )
                    if codigo
                }
                saidas = {
                    codigo: float(total or 0.0)
                    for codigo, total in (
                        db.session.query(
                            Saida.codigo_item,
                            func.coalesce(func.sum(Saida.quantidade), 0.0),
                        )
                        .filter(Saida.codigo_item.in_(legacy_history_ids))
                        .group_by(Saida.codigo_item)
                        .all()
                    )
                    if codigo
                }
                ajustes = {
                    codigo: float(total or 0.0)
                    for codigo, total in (
                        db.session.query(
                            InventarioEvento.codigo_item,
                            func.coalesce(func.sum(InventarioEvento.quantidade), 0.0),
                        )
                        .filter(InventarioEvento.codigo_item.in_(legacy_history_ids))
                        .group_by(InventarioEvento.codigo_item)
                        .all()
                    )
                    if codigo
                }

                for product_id in legacy_history_ids:
                    legacy_balances[product_id] = (
                        entradas.get(product_id, 0.0)
                        - saidas.get(product_id, 0.0)
                        + ajustes.get(product_id, 0.0)
                    )

        snapshots: dict[str, BalanceSnapshot] = {}
        for product_id in normalized_ids:
            item = item_lookup.get(product_id)
            unit_base = BalanceProvider._resolve_unit_base(item) if item else None

            if product_id in migrated_ids:
                balance = balance_rows.get(product_id)
                snapshots[product_id] = BalanceSnapshot(
                    product_id=product_id,
                    quantity_base=float(balance.quantity_base if balance else 0.0),
                    unit_base=unit_base,
                    source="stock_balance",
                    migrated=True,
                )
                continue

            if product_id in legacy_history_ids:
                snapshots[product_id] = BalanceSnapshot(
                    product_id=product_id,
                    quantity_base=float(legacy_balances.get(product_id, 0.0)),
                    unit_base=unit_base,
                    source="legacy",
                    migrated=False,
                )
                continue

            balance = balance_rows.get(product_id)
            if balance is not None:
                snapshots[product_id] = BalanceSnapshot(
                    product_id=product_id,
                    quantity_base=float(balance.quantity_base or 0.0),
                    unit_base=unit_base,
                    source="stock_balance_pending_cutover",
                    migrated=False,
                )
                continue

            snapshots[product_id] = BalanceSnapshot(
                product_id=product_id,
                quantity_base=0.0,
                unit_base=unit_base,
                source="legacy",
                migrated=False,
            )

        return snapshots

    @staticmethod
    def _has_legacy_history(product_id: str) -> bool:
        product_id = (product_id or "").strip()
        if not product_id:
            return False
        return bool(
            db.session.query(Entrada.codigo_item)
            .filter(Entrada.codigo_item == product_id)
            .first()
            or db.session.query(Saida.codigo_item)
            .filter(Saida.codigo_item == product_id)
            .first()
            or db.session.query(InventarioEvento.codigo_item)
            .filter(InventarioEvento.codigo_item == product_id)
            .first()
        )

    @staticmethod
    def is_product_migrated(product_id: str) -> bool:
        product_id = (product_id or "").strip()
        if not product_id:
            return False
        if not stock_balance_supports_read_model_ready():
            return False
        return (
            db.session.query(StockBalance.product_id)
            .filter(
                StockBalance.product_id == product_id,
                StockBalance.read_model_ready.is_(True),
            )
            .first()
            is not None
        )

    @staticmethod
    def get_balance(product_id: str, *, item: Item | None = None) -> BalanceSnapshot:
        product_id = (product_id or "").strip()
        if not product_id:
            raise ValueError("product_id é obrigatório")

        item = item or Item.query.get(product_id)
        if not item:
            raise ValueError("Produto não encontrado")

        balance = StockBalance.query.get(product_id)
        if BalanceProvider.is_product_migrated(product_id) or BalanceProvider._should_prefer_stock_balance_for_nf_origin(item, balance):
            quantity = float(balance.quantity_base if balance else 0.0)
            unit_base = BalanceProvider._resolve_unit_base(item)
            return BalanceSnapshot(
                product_id=product_id,
                quantity_base=quantity,
                unit_base=unit_base,
                source="stock_balance" if BalanceProvider.is_product_migrated(product_id) else "stock_balance_nf_origin",
                migrated=BalanceProvider.is_product_migrated(product_id),
            )

        quantity = BalanceProvider._get_legacy_balance(product_id)
        unit_base = BalanceProvider._resolve_unit_base(item)
        if not BalanceProvider._has_legacy_history(product_id):
            if balance is not None:
                return BalanceSnapshot(
                    product_id=product_id,
                    quantity_base=float(balance.quantity_base or 0.0),
                    unit_base=unit_base,
                    source="stock_balance_pending_cutover",
                    migrated=False,
                )
        return BalanceSnapshot(
            product_id=product_id,
            quantity_base=quantity,
            unit_base=unit_base,
            source="legacy",
            migrated=False,
        )

    @staticmethod
    def _get_legacy_balance(product_id: str) -> float:
        entradas = (
            db.session.query(func.coalesce(func.sum(Entrada.quantidade), 0.0))
            .filter(Entrada.codigo_item == product_id)
            .scalar()
        )
        saidas = (
            db.session.query(func.coalesce(func.sum(Saida.quantidade), 0.0))
            .filter(Saida.codigo_item == product_id)
            .scalar()
        )
        ajustes = (
            db.session.query(func.coalesce(func.sum(InventarioEvento.quantidade), 0.0))
            .filter(InventarioEvento.codigo_item == product_id)
            .scalar()
        )
        return float(entradas or 0.0) - float(saidas or 0.0) + float(ajustes or 0.0)

    @staticmethod
    def _resolve_unit_base(item: Item) -> str | None:
        canonical_unit = resolve_canonical_unit(item)
        if canonical_unit:
            return canonical_unit

        base_unit = next((unit for unit in item.product_units if unit.is_base and unit.active), None)
        if base_unit:
            return base_unit.unit_code
        return (item.unidade or "").strip() or None


balance_provider = BalanceProvider()
