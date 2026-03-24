from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func

from ..extensions import db
from ..models import Entrada, InventarioEvento, Item, Saida, StockBalance, stock_balance_supports_read_model_ready


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
    def get_balance(product_id: str) -> BalanceSnapshot:
        product_id = (product_id or "").strip()
        if not product_id:
            raise ValueError("product_id é obrigatório")

        item = Item.query.get(product_id)
        if not item:
            raise ValueError("Produto não encontrado")

        if BalanceProvider.is_product_migrated(product_id):
            balance = StockBalance.query.get(product_id)
            quantity = float(balance.quantity_base if balance else 0.0)
            unit_base = BalanceProvider._resolve_unit_base(item)
            return BalanceSnapshot(
                product_id=product_id,
                quantity_base=quantity,
                unit_base=unit_base,
                source="stock_balance",
                migrated=True,
            )

        quantity = BalanceProvider._get_legacy_balance(product_id)
        unit_base = BalanceProvider._resolve_unit_base(item)
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
        base_unit = next((unit for unit in item.product_units if unit.is_base and unit.active), None)
        if base_unit:
            return base_unit.unit_code
        return (item.unidade or "").strip() or None


balance_provider = BalanceProvider()
