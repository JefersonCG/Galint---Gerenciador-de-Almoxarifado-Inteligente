from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import Entrada, InventarioEvento, Item, Saida, StockBalance, StockMovement


@dataclass(slots=True)
class ReconciliationResult:
    product_id: str
    description: str
    legacy_balance: float
    ledger_balance: float
    stock_balance: float
    divergence_legacy_vs_ledger: float
    divergence_ledger_vs_cache: float
    classification: str
    details: dict[str, Any]


class LedgerReconciliationService:
    TOLERANCE = 1e-6

    def reconcile_product(self, product_id: str) -> ReconciliationResult:
        item = Item.query.get((product_id or "").strip())
        if not item:
            raise ValueError("Produto não encontrado")

        legacy_balance = self._legacy_balance(item.codigo_item)
        ledger_balance = self._ledger_balance(item.codigo_item)
        cache_balance = self._cache_balance(item.codigo_item)

        divergence_legacy_vs_ledger = ledger_balance - legacy_balance
        divergence_ledger_vs_cache = cache_balance - ledger_balance
        classification = self._classify(divergence_legacy_vs_ledger, divergence_ledger_vs_cache)

        return ReconciliationResult(
            product_id=item.codigo_item,
            description=item.descricao,
            legacy_balance=legacy_balance,
            ledger_balance=ledger_balance,
            stock_balance=cache_balance,
            divergence_legacy_vs_ledger=divergence_legacy_vs_ledger,
            divergence_ledger_vs_cache=divergence_ledger_vs_cache,
            classification=classification,
            details={
                "unidade": item.unidade,
                "tipo_embalagem_novo": item.tipo_embalagem_novo,
                "estoque_embalagens": item.estoque_embalagens,
                "estoque_unidades_soltas": item.estoque_unidades_soltas,
            },
        )

    def reconcile_all(self) -> list[ReconciliationResult]:
        results: list[ReconciliationResult] = []
        for item in Item.query.order_by(Item.codigo_item.asc()).all():
            results.append(self.reconcile_product(item.codigo_item))
        return results

    def summarize(self) -> dict[str, Any]:
        results = self.reconcile_all()
        summary = {
            "total": len(results),
            "divergencia_zero": 0,
            "divergencia_explicavel": 0,
            "divergencia_critica": 0,
        }
        for result in results:
            if result.classification == "divergencia_zero":
                summary["divergencia_zero"] += 1
            elif result.classification == "divergencia_explicavel":
                summary["divergencia_explicavel"] += 1
            else:
                summary["divergencia_critica"] += 1
        return summary

    def _legacy_balance(self, product_id: str) -> float:
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

    def _ledger_balance(self, product_id: str) -> float:
        total = (
            db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
            .filter(StockMovement.product_id == product_id)
            .scalar()
        )
        return float(total or 0.0)

    def _cache_balance(self, product_id: str) -> float:
        balance = db.session.get(StockBalance, product_id)
        if balance is None:
            return 0.0
        return float(balance.quantity_base or 0.0)

    def _classify(self, divergence_legacy_vs_ledger: float, divergence_ledger_vs_cache: float) -> str:
        if abs(divergence_legacy_vs_ledger) <= self.TOLERANCE and abs(divergence_ledger_vs_cache) <= self.TOLERANCE:
            return "divergencia_zero"
        if abs(divergence_legacy_vs_ledger) <= 1.0 and abs(divergence_ledger_vs_cache) <= 1.0:
            return "divergencia_explicavel"
        return "divergencia_critica"


ledger_reconciliation_service = LedgerReconciliationService()