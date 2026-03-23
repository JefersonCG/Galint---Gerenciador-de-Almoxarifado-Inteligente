from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import StockBalance, StockMovement
from .balance_provider import balance_provider
from .unit_conversion_engine import ConversionResult, UnitConversionEngine, unit_conversion_engine


class InventoryEngineError(ValueError):
    pass


@dataclass(slots=True)
class InventoryOperationResult:
    product_id: str
    movement_type: str
    quantity_input: float
    unit_input: str
    quantity_base: float
    unit_base: str
    balance_before: float
    balance_after: float
    movement_id: int
    dual_write_applied: bool
    metadata: dict[str, Any]


class InventoryEngine:
    """Novo núcleo transacional de estoque em paralelo ao legado."""

    def __init__(self, conversion_engine: UnitConversionEngine | None = None):
        self._conversion_engine = conversion_engine or unit_conversion_engine

    def register_entry(
        self,
        *,
        product_id: str,
        quantity: float,
        from_unit: str,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
        write_audit: bool = True,
    ) -> InventoryOperationResult:
        return self._register_movement(
            product_id=product_id,
            quantity=quantity,
            from_unit=from_unit,
            movement_type="entrada",
            balance_delta_sign=1,
            metadata=metadata,
            commit=commit,
            write_audit=write_audit,
        )

    def register_exit(
        self,
        *,
        product_id: str,
        quantity: float,
        from_unit: str,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
        write_audit: bool = True,
    ) -> InventoryOperationResult:
        return self._register_movement(
            product_id=product_id,
            quantity=quantity,
            from_unit=from_unit,
            movement_type="saida",
            balance_delta_sign=-1,
            metadata=metadata,
            commit=commit,
            write_audit=write_audit,
        )

    def register_adjustment(
        self,
        *,
        product_id: str,
        quantity: float,
        from_unit: str,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
        write_audit: bool = True,
    ) -> InventoryOperationResult:
        adjustment_sign = -1 if float(quantity) < 0 else 1
        return self._register_movement(
            product_id=product_id,
            quantity=abs(float(quantity)),
            from_unit=from_unit,
            movement_type="ajuste",
            balance_delta_sign=adjustment_sign,
            metadata=metadata,
            commit=commit,
            write_audit=write_audit,
        )

    def register_return(
        self,
        *,
        product_id: str,
        quantity: float,
        from_unit: str,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
        write_audit: bool = True,
    ) -> InventoryOperationResult:
        return self._register_movement(
            product_id=product_id,
            quantity=quantity,
            from_unit=from_unit,
            movement_type="devolucao",
            balance_delta_sign=1,
            metadata=metadata,
            commit=commit,
            write_audit=write_audit,
        )

    def record_operation_audit(self, result: InventoryOperationResult) -> None:
        conversion = ConversionResult(
            quantity_base=result.quantity_base,
            unit_base=result.unit_base,
            conversion_path=list(result.metadata.get("conversion_path") or []),
            factor_applied=float(result.metadata.get("factor_applied") or 1.0),
            metadata={},
        )
        self._write_conversion_audit(
            product_id=result.product_id,
            quantity=result.quantity_input,
            from_unit=result.unit_input,
            conversion=conversion,
            source=result.movement_type,
            metadata=result.metadata,
        )

    def _register_movement(
        self,
        *,
        product_id: str,
        quantity: float,
        from_unit: str,
        movement_type: str,
        balance_delta_sign: int,
        metadata: dict[str, Any] | None,
        commit: bool,
        write_audit: bool,
    ) -> InventoryOperationResult:
        payload_metadata = dict(metadata or {})
        product_id = (product_id or "").strip()
        if not product_id:
            raise InventoryEngineError("product_id é obrigatório")

        conversion = self._conversion_engine.convert_to_base(product_id, quantity, from_unit)
        balance_snapshot = balance_provider.get_balance(product_id)
        balance_before = float(balance_snapshot.quantity_base)
        quantity_delta = float(conversion.quantity_base) * float(balance_delta_sign)
        balance_after = balance_before + quantity_delta
        if balance_after < 0:
            raise InventoryEngineError("Saldo insuficiente para concluir a operação")

        movement = StockMovement()
        movement.product_id = product_id
        movement.movement_type = movement_type
        movement.quantity_base = quantity_delta
        movement.unit_base = conversion.unit_base
        movement.reference_type = str(payload_metadata.get("reference_type") or "inventory_engine")
        movement.reference_id = (
            str(payload_metadata.get("reference_id"))
            if payload_metadata.get("reference_id") is not None
            else None
        )
        movement.metadata_json = {
            **payload_metadata,
            "input_quantity": float(quantity),
            "input_unit": from_unit,
            "conversion_path": conversion.conversion_path,
            "factor_applied": conversion.factor_applied,
        }
        movement.created_at = datetime.now(timezone.utc).replace(tzinfo=None)

        dual_write_applied = bool(payload_metadata.get("dual_write_active", False))
        try:
            db.session.add(movement)
            balance = db.session.get(StockBalance, product_id)
            if balance is None:
                balance = StockBalance()
                balance.product_id = product_id
                balance.read_model_ready = False
                db.session.add(balance)
            balance.quantity_base = balance_after
            db.session.flush()
            if commit:
                db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise InventoryEngineError("Falha de concorrência ou integridade ao atualizar saldo") from exc
        except Exception:
            db.session.rollback()
            raise

        if write_audit:
            self._write_conversion_audit(
                product_id=product_id,
                quantity=quantity,
                from_unit=from_unit,
                conversion=conversion,
                source=movement_type,
                metadata=payload_metadata,
            )

        return InventoryOperationResult(
            product_id=product_id,
            movement_type=movement_type,
            quantity_input=float(quantity),
            unit_input=from_unit,
            quantity_base=float(conversion.quantity_base),
            unit_base=conversion.unit_base,
            balance_before=balance_before,
            balance_after=balance_after,
            movement_id=int(movement.id),
            dual_write_applied=dual_write_applied,
            metadata={
                **payload_metadata,
                "conversion_path": conversion.conversion_path,
                "factor_applied": conversion.factor_applied,
            },
        )

    def _write_conversion_audit(
        self,
        *,
        product_id: str,
        quantity: float,
        from_unit: str,
        conversion: ConversionResult,
        source: str,
        metadata: dict[str, Any],
    ) -> None:
        try:
            db_path = Path(__file__).resolve().parents[2] / "instance" / "conversion_logs.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversion_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        product_id TEXT NOT NULL,
                        input_unit TEXT NOT NULL,
                        input_quantity REAL NOT NULL,
                        output_quantity_base REAL NOT NULL,
                        output_unit_base TEXT NOT NULL,
                        conversion_path TEXT NOT NULL,
                        factor_applied REAL NOT NULL,
                        metadata_json TEXT NULL,
                        source TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO conversion_logs (
                        timestamp,
                        product_id,
                        input_unit,
                        input_quantity,
                        output_quantity_base,
                        output_unit_base,
                        conversion_path,
                        factor_applied,
                        metadata_json,
                        source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        product_id,
                        from_unit,
                        float(quantity),
                        float(conversion.quantity_base),
                        conversion.unit_base,
                        json.dumps(conversion.conversion_path, ensure_ascii=True),
                        float(conversion.factor_applied),
                        json.dumps(metadata, ensure_ascii=True),
                        source,
                    ),
                )
                connection.commit()
            finally:
                connection.close()
        except Exception:
            return


inventory_engine = InventoryEngine()
