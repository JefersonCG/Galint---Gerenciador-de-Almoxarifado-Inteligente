from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Item, StockBalance, StockMovement
from .balance_provider import balance_provider
from .legacy_stock_normalizer import is_packaging_unit_code, resolve_canonical_unit, resolve_packaging_factor
from .operation_log_service import operation_log_service
from .unit_conversion_engine import ConversionResult, UnitConversionEngine, unit_conversion_engine


class InventoryEngineError(ValueError):
    pass


PRE_CADASTRO_PENDING_EXIT_MESSAGE = (
    "Saída bloqueada: este item está com pré-cadastro pendente. "
    "Finalize o pré-cadastro antes de registrar a saída."
)


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
    operation_log_id: int | None
    dual_write_applied: bool
    metadata: dict[str, Any]


class InventoryEngine:
    """Novo núcleo transacional de estoque em paralelo ao legado."""

    _UNIT_ALIASES = {
        "unidade": "un",
        "unidades": "un",
        "pc": "un",
        "pcs": "un",
        "pca": "un",
        "pca.": "un",
        "peca": "un",
        "pecas": "un",
        "peça": "un",
        "peças": "un",
        "litro": "l",
        "litros": "l",
        "metro": "m",
        "metros": "m",
        "quilo": "kg",
        "quilos": "kg",
        "caixas": "caixa",
        "pacotes": "pacote",
        "fardos": "fardo",
        "rolos": "rolo",
        "latas": "lata",
        "baldes": "balde",
        "bombonas": "bombona",
        "sacos": "saco",
    }

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
        return self._execute_operation(
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
        return self._execute_operation(
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
        return self._execute_operation(
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
        return self._execute_operation(
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
        operation_log_service.attach_audit_metadata(
            result.operation_log_id,
            {
                "movement_id": result.movement_id,
                "movement_type": result.movement_type,
                "quantity_base": result.quantity_base,
                "unit_base": result.unit_base,
                "balance_before": result.balance_before,
                "balance_after": result.balance_after,
                "conversion_path": list(result.metadata.get("conversion_path") or []),
                "factor_applied": float(result.metadata.get("factor_applied") or 1.0),
                "reference_id": result.metadata.get("reference_id"),
            },
        )

    def sync_packaging_read_model(
        self,
        *,
        product_id: str,
        commit: bool = True,
    ) -> bool:
        product_id = (product_id or "").strip()
        if not product_id:
            raise InventoryEngineError("product_id é obrigatório")

        item = db.session.get(Item, product_id)
        if item is None:
            raise InventoryEngineError("Produto não encontrado")

        balance_snapshot = balance_provider.get_balance(product_id, item=item)
        sync_unit_base = self._resolve_packaging_sync_unit_base(
            item=item,
            fallback_unit_base=balance_snapshot.unit_base,
        )
        changed = self._sync_packaging_state_to_balance(
            item=item,
            quantity_base=float(balance_snapshot.quantity_base or 0.0),
            unit_base=sync_unit_base,
        )
        if changed:
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        return changed

    @staticmethod
    def _resolve_packaging_sync_unit_base(*, item: Item, fallback_unit_base: str | None) -> str | None:
        canonical_unit = resolve_canonical_unit(item)
        if canonical_unit:
            return canonical_unit
        return fallback_unit_base

    @classmethod
    def _normalize_unit_code(cls, value: str | None) -> str:
        raw = (value or "").strip().lower()
        if not raw:
            return ""
        return cls._UNIT_ALIASES.get(raw, raw)

    @classmethod
    def _ensure_canonical_movement_unit(cls, *, item: Item, unit_base: str) -> None:
        resolved_unit = cls._normalize_unit_code(unit_base)
        if not resolved_unit:
            raise InventoryEngineError("Movimento sem unidade base canônica resolvida")
        if is_packaging_unit_code(resolved_unit):
            raise InventoryEngineError(
                f"Movimento operacional com unit_base de embalagem não é permitido: {resolved_unit}"
            )

        canonical_unit = cls._normalize_unit_code(resolve_canonical_unit(item))
        if canonical_unit and resolved_unit != canonical_unit:
            raise InventoryEngineError(
                f"Movimento operacional fora da unidade canônica do item: unit_base={resolved_unit}, canonical={canonical_unit}"
            )

    @classmethod
    def _is_packaging_input_unit(cls, item: Item, from_unit: str | None) -> bool:
        unit_code = cls._normalize_unit_code(from_unit)
        if not unit_code:
            return False

        packaging_units = {
            cls._normalize_unit_code(item.tipo_embalagem_novo),
            cls._normalize_unit_code(item.unidade),
        }
        packaging_units.update(
            cls._normalize_unit_code(unit.unit_code)
            for unit in item.product_units
            if unit.active and unit.unit_code
        )
        packaging_units = {unit for unit in packaging_units if unit and is_packaging_unit_code(unit)}
        return unit_code in packaging_units or is_packaging_unit_code(unit_code)

    @classmethod
    def _decompose_packaging_balance(
        cls,
        *,
        item: Item,
        quantity_base: float,
        unit_base: str | None,
    ) -> tuple[float, float]:
        quantity_value = max(float(quantity_base or 0.0), 0.0)
        if quantity_value <= 1e-6:
            return 0.0, 0.0

        unit_code = cls._normalize_unit_code(unit_base)
        if unit_code and is_packaging_unit_code(unit_code):
            factor = float(resolve_packaging_factor(item) or 0.0)
            if factor <= 0:
                return quantity_value, 0.0

            embalagens_inteiras = float(math.floor(quantity_value + 1e-9))
            fracao_embalagem = quantity_value - embalagens_inteiras
            if abs(fracao_embalagem) <= 1e-6:
                fracao_embalagem = 0.0

            unidades_soltas = fracao_embalagem * factor
            unidades_soltas_round = round(unidades_soltas)
            if abs(unidades_soltas - unidades_soltas_round) <= 1e-6:
                unidades_soltas = float(unidades_soltas_round)
            if unidades_soltas >= factor - 1e-6:
                embalagens_inteiras += 1.0
                unidades_soltas = 0.0
            if abs(unidades_soltas) <= 1e-6:
                unidades_soltas = 0.0
            return embalagens_inteiras, float(unidades_soltas)

        factor = float(resolve_packaging_factor(item) or 0.0)
        if factor <= 0:
            return quantity_value, 0.0

        embalagens = float(math.floor((quantity_value + 1e-9) / factor))
        unidades_soltas = quantity_value - (embalagens * factor)
        if abs(unidades_soltas) <= 1e-6:
            unidades_soltas = 0.0
        if unidades_soltas < 0 and abs(unidades_soltas) <= 1e-6:
            unidades_soltas = 0.0
        return embalagens, float(unidades_soltas)

    @classmethod
    def _sync_packaging_state_to_balance(
        cls,
        *,
        item: Item,
        quantity_base: float,
        unit_base: str | None,
    ) -> bool:
        from .embalagem_service import EmbalagemService

        if not EmbalagemService.tem_embalagem(item):
            return False

        embalagens, unidades_soltas = cls._decompose_packaging_balance(
            item=item,
            quantity_base=quantity_base,
            unit_base=unit_base,
        )
        current_embalagens = float(item.estoque_embalagens or 0.0)
        current_soltas = float(item.estoque_unidades_soltas or 0.0)
        if abs(current_embalagens - embalagens) <= 1e-6 and abs(current_soltas - unidades_soltas) <= 1e-6:
            return False

        item.estoque_embalagens = embalagens
        item.estoque_unidades_soltas = unidades_soltas
        return True

    def _sync_packaging_read_model_before_operation(
        self,
        *,
        item: Item,
        movement_type: str,
        balance_delta_sign: int,
        quantity_input: float,
        from_unit: str,
        balance_before: float,
        unit_base: str | None,
        metadata: dict[str, Any],
    ) -> None:
        from .embalagem_service import EmbalagemService

        if metadata.get("mirrored_from_legacy"):
            return
        if not EmbalagemService.tem_embalagem(item):
            return

        self._sync_packaging_state_to_balance(
            item=item,
            quantity_base=balance_before,
            unit_base=unit_base,
        )

        em_embalagens = self._is_packaging_input_unit(item, from_unit)
        movement_type_norm = (movement_type or "").strip().lower()

        if movement_type_norm in {"entrada", "devolucao"} or (
            movement_type_norm == "ajuste" and balance_delta_sign >= 0
        ):
            novas_embalagens, novas_unidades_soltas = EmbalagemService.processar_entrada(
                item,
                float(quantity_input),
                em_embalagens,
            )
        elif movement_type_norm == "saida" or (
            movement_type_norm == "ajuste" and balance_delta_sign < 0
        ):
            novas_embalagens, novas_unidades_soltas, sucesso = EmbalagemService.processar_saida(
                item,
                float(quantity_input),
                em_embalagens,
            )
            if not sucesso:
                raise InventoryEngineError("Saldo insuficiente para concluir a operação")
        else:
            return

        item.estoque_embalagens = novas_embalagens
        item.estoque_unidades_soltas = novas_unidades_soltas

    def _execute_operation(
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
        try:
            return self._register_movement(
                product_id=product_id,
                quantity=quantity,
                from_unit=from_unit,
                movement_type=movement_type,
                balance_delta_sign=balance_delta_sign,
                metadata=metadata,
                commit=commit,
                write_audit=write_audit,
            )
        except Exception as exc:
            try:
                db.session.rollback()
            except Exception:
                pass
            self._record_operation_error(
                product_id=product_id,
                quantity=quantity,
                from_unit=from_unit,
                movement_type=movement_type,
                metadata=metadata,
                error=exc,
            )
            raise

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

        item = db.session.get(Item, product_id)
        if item is None:
            raise InventoryEngineError("Produto não encontrado")

        movement_type_norm = (movement_type or "").strip().lower()
        if movement_type_norm == "saida" and bool(getattr(item, "pre_cadastro_pendente", False)):
            raise InventoryEngineError(PRE_CADASTRO_PENDING_EXIT_MESSAGE)

        conversion = self._conversion_engine.convert_item_to_base(item, quantity, from_unit)
        self._ensure_canonical_movement_unit(item=item, unit_base=conversion.unit_base)
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
        movement_source = str(
            payload_metadata.get("source")
            or payload_metadata.get("origin")
            or payload_metadata.get("channel")
            or "inventory_engine"
        )
        movement_user_id = payload_metadata.get("user_id") or payload_metadata.get("matricula")
        movement.metadata_json = {
            **payload_metadata,
            "source": movement_source,
            "user_id": str(movement_user_id) if movement_user_id not in {None, ""} else None,
            "input_quantity": float(quantity),
            "input_unit": from_unit,
            "conversion_path": conversion.conversion_path,
            "factor_applied": conversion.factor_applied,
        }
        movement.created_at = datetime.now(timezone.utc).replace(tzinfo=None)

        self._sync_packaging_read_model_before_operation(
            item=item,
            movement_type=movement_type,
            balance_delta_sign=balance_delta_sign,
            quantity_input=float(quantity),
            from_unit=from_unit,
            balance_before=balance_before,
            unit_base=conversion.unit_base,
            metadata=payload_metadata,
        )

        dual_write_applied = bool(payload_metadata.get("dual_write_active", False))
        operation_log_id: int | None = None
        try:
            db.session.add(movement)
            balance = db.session.get(StockBalance, product_id)
            if balance is None:
                balance = StockBalance()
                balance.product_id = product_id
                db.session.add(balance)
            balance.quantity_base = balance_after
            db.session.flush()
            operation_log = operation_log_service.create_success_log(
                operation_type=operation_log_service.normalize_operation_type(movement_type, quantity_base=quantity_delta),
                product_id=product_id,
                quantity_input=float(quantity),
                quantity_base=float(quantity_delta),
                unit_input=from_unit,
                user_id=str(movement_user_id) if movement_user_id not in {None, ""} else None,
                source=movement_source,
                payload_json={
                    **payload_metadata,
                    "movement_type": movement_type,
                    "unit_base": conversion.unit_base,
                    "input_quantity": float(quantity),
                    "input_unit": from_unit,
                    "quantity_delta": float(quantity_delta),
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                    "conversion_path": conversion.conversion_path,
                    "factor_applied": conversion.factor_applied,
                },
                created_at=movement.created_at,
                commit=False,
            )
            operation_log_id = operation_log.id
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
            operation_log_id=operation_log_id,
            dual_write_applied=dual_write_applied,
            metadata={
                **payload_metadata,
                "conversion_path": conversion.conversion_path,
                "factor_applied": conversion.factor_applied,
            },
        )

    def _record_operation_error(
        self,
        *,
        product_id: str,
        quantity: float,
        from_unit: str,
        movement_type: str,
        metadata: dict[str, Any] | None,
        error: Exception,
    ) -> None:
        try:
            operation_log_service.create_error_log(
                requested_operation_type=movement_type,
                product_id=(product_id or "").strip() or None,
                quantity_input=float(quantity) if quantity is not None else None,
                unit_input=(from_unit or "").strip() or None,
                user_id=(str((metadata or {}).get("user_id") or (metadata or {}).get("matricula") or "").strip() or None),
                source=str((metadata or {}).get("source") or (metadata or {}).get("origin") or (metadata or {}).get("channel") or "inventory_engine"),
                payload_json=dict(metadata or {}),
                error_message=str(error),
            )
        except Exception:
            return

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
