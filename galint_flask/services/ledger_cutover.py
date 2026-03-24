from __future__ import annotations

from dataclasses import dataclass

from ..extensions import db
from ..models import StockBalance, stock_balance_supports_read_model_ready
from .ledger_reconciliation import LedgerReconciliationService, ReconciliationResult, ledger_reconciliation_service


class LedgerCutoverError(ValueError):
    pass


@dataclass(slots=True)
class CutoverDecision:
    product_id: str
    classification: str
    activated: bool
    reason: str
    legacy_balance: float
    ledger_balance: float
    stock_balance: float


class LedgerCutoverService:
    """Ativa a leitura por StockBalance apenas para produtos reconciliados."""

    def __init__(self, reconciliation_service: LedgerReconciliationService | None = None):
        self._reconciliation_service = reconciliation_service or ledger_reconciliation_service

    def activate_product(
        self,
        product_id: str,
        *,
        allow_explainable: bool = False,
        force: bool = False,
        dry_run: bool = False,
    ) -> CutoverDecision:
        if not stock_balance_supports_read_model_ready():
            raise LedgerCutoverError(
                "Schema atual do banco não possui read_model_ready; cutover de leitura por ledger está indisponível nesta base."
            )
        result = self._reconciliation_service.reconcile_product(product_id)
        if not force and not self._is_eligible(result, allow_explainable=allow_explainable):
            return CutoverDecision(
                product_id=result.product_id,
                classification=result.classification,
                activated=False,
                reason="Produto não elegível para migração de leitura",
                legacy_balance=result.legacy_balance,
                ledger_balance=result.ledger_balance,
                stock_balance=result.stock_balance,
            )

        balance = db.session.get(StockBalance, result.product_id)
        if balance is None:
            balance = StockBalance()
            balance.product_id = result.product_id
            balance.quantity_base = float(result.stock_balance or 0.0)
            db.session.add(balance)
            db.session.flush()

        if dry_run:
            return CutoverDecision(
                product_id=result.product_id,
                classification=result.classification,
                activated=True,
                reason="Dry-run: produto elegível para ativação",
                legacy_balance=result.legacy_balance,
                ledger_balance=result.ledger_balance,
                stock_balance=result.stock_balance,
            )
        db.session.commit()
        return CutoverDecision(
            product_id=result.product_id,
            classification=result.classification,
            activated=True,
            reason="Leitura por StockBalance ativada",
            legacy_balance=result.legacy_balance,
            ledger_balance=result.ledger_balance,
            stock_balance=result.stock_balance,
        )

    def deactivate_product(self, product_id: str, *, dry_run: bool = False) -> CutoverDecision:
        if not stock_balance_supports_read_model_ready():
            raise LedgerCutoverError(
                "Schema atual do banco não possui read_model_ready; cutover de leitura por ledger está indisponível nesta base."
            )
        result = self._reconciliation_service.reconcile_product(product_id)
        balance = db.session.get(StockBalance, result.product_id)
        if balance is None:
            balance = StockBalance()
            balance.product_id = result.product_id
            balance.quantity_base = float(result.stock_balance or 0.0)
            db.session.add(balance)
            db.session.flush()

        if dry_run:
            return CutoverDecision(
                product_id=result.product_id,
                classification=result.classification,
                activated=False,
                reason="Dry-run: leitura seria revertida para legado",
                legacy_balance=result.legacy_balance,
                ledger_balance=result.ledger_balance,
                stock_balance=result.stock_balance,
            )
        db.session.commit()
        return CutoverDecision(
            product_id=result.product_id,
            classification=result.classification,
            activated=False,
            reason="Leitura revertida para legado",
            legacy_balance=result.legacy_balance,
            ledger_balance=result.ledger_balance,
            stock_balance=result.stock_balance,
        )

    def activate_batch(
        self,
        product_ids: list[str],
        *,
        allow_explainable: bool = False,
        force: bool = False,
        dry_run: bool = False,
    ) -> list[CutoverDecision]:
        decisions: list[CutoverDecision] = []
        for product_id in product_ids:
            decisions.append(
                self.activate_product(
                    product_id,
                    allow_explainable=allow_explainable,
                    force=force,
                    dry_run=dry_run,
                )
            )
        return decisions

    def eligible_products(self, *, allow_explainable: bool = False) -> list[ReconciliationResult]:
        results = self._reconciliation_service.reconcile_all()
        return [
            result
            for result in results
            if self._is_eligible(result, allow_explainable=allow_explainable)
        ]

    @staticmethod
    def _is_eligible(result: ReconciliationResult, *, allow_explainable: bool) -> bool:
        if result.classification == "divergencia_zero":
            return True
        if allow_explainable and result.classification == "divergencia_explicavel":
            return True
        return False


ledger_cutover_service = LedgerCutoverService()
