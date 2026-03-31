from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import Entrada, InventarioEvento, Item, Saida, StockBalance, StockMovement
from .legacy_stock_normalizer import build_normalized_legacy_movements


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

        legacy_balance = self._legacy_balance(item)
        ledger_balance = self._ledger_balance(item.codigo_item)
        cache_balance = self._cache_balance(item.codigo_item)
        document_only_balance = self._document_only_balance(item.codigo_item)

        divergence_legacy_vs_ledger = ledger_balance - legacy_balance
        divergence_ledger_vs_cache = cache_balance - ledger_balance
        classification = self._classify(
            divergence_legacy_vs_ledger,
            divergence_ledger_vs_cache,
            document_only_balance=document_only_balance,
        )

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
                "document_only_balance": document_only_balance,
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

    def _legacy_balance(self, item: Item) -> float:
        return float(sum(movement.quantity_base for movement in build_normalized_legacy_movements(item)))

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

    def _document_only_balance(self, product_id: str) -> float:
        total = (
            db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
            .filter(StockMovement.product_id == product_id)
            .filter(StockMovement.reference_type == "entrada_documento_item")
            .scalar()
        )
        return float(total or 0.0)

    def _classify(
        self,
        divergence_legacy_vs_ledger: float,
        divergence_ledger_vs_cache: float,
        *,
        document_only_balance: float = 0.0,
    ) -> str:
        if abs(divergence_legacy_vs_ledger) <= self.TOLERANCE and abs(divergence_ledger_vs_cache) <= self.TOLERANCE:
            return "divergencia_zero"
        if (
            abs(divergence_ledger_vs_cache) <= self.TOLERANCE
            and abs(divergence_legacy_vs_ledger - document_only_balance) <= self.TOLERANCE
        ):
            return "divergencia_explicavel"
        if abs(divergence_legacy_vs_ledger) <= 1.0 and abs(divergence_ledger_vs_cache) <= 1.0:
            return "divergencia_explicavel"
        return "divergencia_critica"


ledger_reconciliation_service = LedgerReconciliationService()