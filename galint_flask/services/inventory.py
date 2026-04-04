"""Inventory service bridging the legacy data model to Flask routes."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import json
import logging
import math
from time import monotonic
from typing import Any
from unicodedata import normalize as unicode_normalize

from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    DocumentoEntradaEstoque,
    DocumentoEntradaEstoqueItem,
    Entrada,
    EquipamentoReparo,
    FinanceLedgerEntry,
    FinanceSupplierPreference,
    InventarioEvento,
    Item,
    MaterialInventario,
    ProductDimension,
    StockBalance,
    StockMovement,
    ProductUnit,
    ProductUnitConversion,
    RetiradaFerramenta,
    Saida,
    TelegramOutbox,
    Usuario,
)
from .inventory_engine import (
    InventoryEngineError,
    InventoryOperationResult,
    PRE_CADASTRO_PENDING_EXIT_MESSAGE,
    inventory_engine,
)
from .admin_stock_audit_sqlite import log_admin_stock_adjustment
from .legacy_stock_normalizer import (
    is_packaging_unit_code,
    resolve_canonical_unit,
    resolve_packaging_factor,
    resolve_packaging_quantity_and_unit,
    uses_packaging_legacy_normalization,
)
from .operation_log_service import operation_log_service
from .price_normalization import infer_price_unit_for_item, normalize_item_price
from .unit_conversion_engine import UnitConversionError
from .balance_provider import balance_provider
from ..utils.lote_generator import generate_lote
from ..utils.barcode_generator import generate_barcode, get_barcode_path
from ..utils.time_service import TimeService

logger = logging.getLogger(__name__)

ADVANCED_DIMENSION_OPTIONS = ("unit", "mass", "volume", "length")

OPERATIONAL_ACTIVITY_OPTIONS: tuple[dict[str, str], ...] = (
    {"key": "piscina", "label": "Piscina e espelho d'agua"},
    {"key": "hidraulica", "label": "Manutencao hidraulica"},
    {"key": "eletrica", "label": "Manutencao eletrica"},
    {"key": "pintura_acabamento", "label": "Pintura e acabamento"},
    {"key": "jardins", "label": "Jardins e paisagismo"},
    {"key": "areas_comuns", "label": "Areas comuns e apoio"},
    {"key": "blocos_apartamentos", "label": "Blocos e apartamentos"},
    {"key": "limpeza", "label": "Limpeza operacional"},
    {"key": "uso_direto", "label": "Uso operacional direto"},
)
OPERATIONAL_ACTIVITY_LABELS = {
    row["key"]: row["label"]
    for row in OPERATIONAL_ACTIVITY_OPTIONS
}


def _normalize_operational_lookup(value: object) -> str:
    normalized = " ".join(str(value or "").strip().split()).lower()
    return unicode_normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")


_OPERATIONAL_ACTIVITY_ALIASES = {
    _normalize_operational_lookup(option["key"]): option["key"]
    for option in OPERATIONAL_ACTIVITY_OPTIONS
}
_OPERATIONAL_ACTIVITY_ALIASES.update(
    {
        _normalize_operational_lookup(option["label"]): option["key"]
        for option in OPERATIONAL_ACTIVITY_OPTIONS
    }
)


def normalize_operational_text(
    value: object,
    *,
    uppercase: bool = True,
    max_length: int | None = None,
) -> str | None:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return None
    if uppercase:
        normalized = normalized.upper()
    if max_length is not None:
        normalized = normalized[:max_length]
    return normalized


def normalize_operational_activity(value: object) -> str | None:
    lookup = _normalize_operational_lookup(value)
    if not lookup:
        return None
    return _OPERATIONAL_ACTIVITY_ALIASES.get(lookup)


def normalize_operational_context(
    *,
    activity: object = None,
    order: object = None,
    cost_center: object = None,
) -> dict[str, str | None]:
    return {
        "atividade_operacional": normalize_operational_activity(activity),
        "ordem_servico": normalize_operational_text(order, max_length=120),
        "centro_custo": normalize_operational_text(cost_center, max_length=120),
    }


def apply_operational_context(
    record: object,
    *,
    activity: object = None,
    order: object = None,
    cost_center: object = None,
) -> None:
    context = normalize_operational_context(
        activity=activity,
        order=order,
        cost_center=cost_center,
    )
    for attr_name, value in context.items():
        if hasattr(record, attr_name):
            setattr(record, attr_name, value)


def _normalize_advanced_dimension(value: object) -> str | None:
    raw = str(value or "").strip().lower()
    return raw if raw in ADVANCED_DIMENSION_OPTIONS else None


def _normalize_advanced_unit_settings(payload: object) -> dict[str, list[dict[str, object]]]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    dimensions: list[dict[str, object]] = []
    units: list[dict[str, object]] = []
    conversions: list[dict[str, object]] = []
    seen_dimensions: set[str] = set()
    seen_units: set[str] = set()

    for row in payload.get("dimensions") or []:
        if not isinstance(row, dict):
            continue
        dimension = _normalize_advanced_dimension(row.get("dimension"))
        if not dimension or dimension in seen_dimensions:
            continue
        seen_dimensions.add(dimension)
        dimensions.append({
            "dimension": dimension,
            "enabled": bool(row.get("enabled", True)),
        })

    for row in payload.get("units") or []:
        if not isinstance(row, dict):
            continue
        unit_code = str(row.get("unit_code") or "").strip().lower()
        unit_label = str(row.get("unit_label") or unit_code).strip()
        dimension = _normalize_advanced_dimension(row.get("dimension"))
        if not unit_code or not unit_label or not dimension or unit_code in seen_units:
            continue
        seen_units.add(unit_code)
        units.append({
            "unit_code": unit_code,
            "unit_label": unit_label,
            "dimension": dimension,
            "is_base": bool(row.get("is_base", False)),
            "active": bool(row.get("active", True)),
        })
        if dimension not in seen_dimensions:
            seen_dimensions.add(dimension)
            dimensions.append({"dimension": dimension, "enabled": True})

    if units and not any(bool(row.get("is_base")) for row in units):
        units[0]["is_base"] = True

    valid_unit_codes = {str(row["unit_code"]) for row in units}
    seen_conversions: set[tuple[str, str]] = set()
    for row in payload.get("conversions") or []:
        if not isinstance(row, dict):
            continue
        from_unit = str(row.get("from_unit") or "").strip().lower()
        to_unit = str(row.get("to_unit") or "").strip().lower()
        try:
            factor = float(row.get("factor") or 0)
        except (TypeError, ValueError):
            factor = 0.0
        key = (from_unit, to_unit)
        if (
            not from_unit
            or not to_unit
            or from_unit == to_unit
            or from_unit not in valid_unit_codes
            or to_unit not in valid_unit_codes
            or factor <= 0
            or key in seen_conversions
        ):
            continue
        seen_conversions.add(key)
        conversions.append({
            "from_unit": from_unit,
            "to_unit": to_unit,
            "factor": factor,
            "active": bool(row.get("active", True)),
        })

    return {
        "dimensions": dimensions,
        "units": units,
        "conversions": conversions,
    }


def _apply_advanced_unit_settings(item: Item, payload: object) -> None:
    normalized = _normalize_advanced_unit_settings(payload)

    item.product_dimensions[:] = []
    item.product_units[:] = []
    item.product_unit_conversions[:] = []
    db.session.flush()

    for row in normalized["dimensions"]:
        item.product_dimensions.append(
            ProductDimension(
                product_id=item.codigo_item,
                dimension=str(row["dimension"]),
                enabled=bool(row.get("enabled", True)),
            )
        )

    for row in normalized["units"]:
        item.product_units.append(
            ProductUnit(
                product_id=item.codigo_item,
                unit_code=str(row["unit_code"]),
                unit_label=str(row["unit_label"]),
                dimension=str(row["dimension"]),
                is_base=bool(row.get("is_base", False)),
                active=bool(row.get("active", True)),
            )
        )

    for row in normalized["conversions"]:
        item.product_unit_conversions.append(
            ProductUnitConversion(
                product_id=item.codigo_item,
                from_unit=str(row["from_unit"]),
                to_unit=str(row["to_unit"]),
                factor=float(row["factor"]),
                active=bool(row.get("active", True)),
            )
        )


def _coerce_price_value(value: object) -> float | None:
    if value in ("", None):
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _normalize_price_unit_value(value: object) -> str | None:
    raw = str(value or "").strip().lower()
    return raw or None


def _assign_normalized_item_price(item: Item, *, raw_price: object, kind: str, price_unit: object = None) -> None:
    if kind not in {"compra", "reposicao"}:
        raise ValueError("Tipo de preco invalido")

    raw_attr = f"preco_{kind}_unitario"
    base_attr = f"preco_{kind}_unitario_base"
    unit_attr = f"preco_{kind}_unidade_preco"
    factor_attr = f"preco_{kind}_fator_base"

    raw_value = _coerce_price_value(raw_price)
    if raw_value is None:
        setattr(item, raw_attr, None)
        setattr(item, base_attr, None)
        setattr(item, unit_attr, None)
        setattr(item, factor_attr, None)
        return

    resolved_price_unit = _normalize_price_unit_value(price_unit)
    if resolved_price_unit is None:
        resolved_price_unit = _normalize_price_unit_value(getattr(item, unit_attr, None))
    if resolved_price_unit is None:
        resolved_price_unit = infer_price_unit_for_item(item)

    try:
        normalized = normalize_item_price(
            item,
            unit_price=raw_value,
            price_unit=resolved_price_unit,
        )
    except Exception:
        fallback_price_unit = infer_price_unit_for_item(item)
        if fallback_price_unit != resolved_price_unit:
            try:
                normalized = normalize_item_price(
                    item,
                    unit_price=raw_value,
                    price_unit=fallback_price_unit,
                )
                resolved_price_unit = fallback_price_unit
            except Exception:
                normalized = None
        else:
            normalized = None

    setattr(item, raw_attr, raw_value)
    setattr(item, base_attr, float(normalized.unit_price_base) if normalized is not None else raw_value)
    setattr(item, unit_attr, normalized.price_unit if normalized is not None else resolved_price_unit)
    setattr(item, factor_attr, float(normalized.factor_to_base) if normalized is not None else 1.0)


@dataclass(slots=True)
class MovimentoPayload:
    codigo: str
    quantidade: float
    matricula: str | None = None
    nota_fiscal: str | None = None
    observacao: str | None = None
    local_servico: str | None = None
    atividade_operacional: str | None = None
    ordem_servico: str | None = None
    centro_custo: str | None = None
    modo_fracionado: bool = False
    tipo_produto: str | None = None
    densidade_aplicada: float | None = None
    fracao_numerador: int | None = None
    fracao_denominador: int | None = None
    quantidade_total_embalagem: float | None = None
    quantidade_retirada_em_litros: float | None = None
    quantidade_retirada_em_quilos: float | None = None
    quantidade_restante: float | None = None
    is_devolucao: bool = False
    em_embalagens: bool | None = None  # True = embalagens, False = unidades, None = item sem embalagem
    tipo_custodia: str = "temporaria"


ADMIN_BALANCE_ADJUSTMENT_TYPE = "ajuste_admin_saldo"
ADMIN_BALANCE_ADJUSTMENT_SOURCE = "admin_balance_portal"
ADMIN_BALANCE_DAILY_LIMIT = 4
ADMIN_BALANCE_PENDING_PRECADASTRO_MESSAGE = (
    "Ajuste administrativo bloqueado: este item está com pré-cadastro pendente. "
    "Finalize o pré-cadastro antes de corrigir o saldo."
)


class InventoryService:
    """Facade responsável por CRUD de itens e lançamentos de estoque."""

    def __init__(self) -> None:
        self._runtime_cache: dict[str, tuple[float, Any]] = {}

    @staticmethod
    def _as_positive_float(value: object) -> float:
        try:
            f = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return f

    def _get_cached(self, key: str) -> Any | None:
        cached = self._runtime_cache.get(key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at <= monotonic():
            self._runtime_cache.pop(key, None)
            return None
        return value

    def _set_cached(self, key: str, value: Any, *, ttl_seconds: float) -> Any:
        self._runtime_cache[key] = (monotonic() + ttl_seconds, value)
        return value

    def clear_runtime_cache(self, prefix: str | None = None) -> None:
        if prefix is None:
            self._runtime_cache.clear()
            return
        keys = [key for key in self._runtime_cache if key.startswith(prefix)]
        for key in keys:
            self._runtime_cache.pop(key, None)

    @staticmethod
    def _balance_close(left: float, right: float, *, tolerance: float = 1e-6) -> bool:
        return abs(float(left or 0.0) - float(right or 0.0)) <= tolerance

    @staticmethod
    def _reconciliation_label(classification: str) -> str:
        mapping = {
            "divergencia_zero": "Alinhado",
            "divergencia_explicavel": "Divergência explicável",
            "divergencia_critica": "Divergência crítica",
        }
        return mapping.get((classification or "").strip(), "Situação desconhecida")

    @staticmethod
    def _reconciliation_badge(classification: str) -> str:
        mapping = {
            "divergencia_zero": "success",
            "divergencia_explicavel": "warning",
            "divergencia_critica": "danger",
        }
        return mapping.get((classification or "").strip(), "secondary")

    @staticmethod
    def _admin_balance_day_bounds_utc(*, now_local: datetime | None = None) -> tuple[datetime, datetime, date]:
        current_local = now_local or TimeService.now_local()
        start_local = current_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
        start_utc = TimeService.to_utc(start_local).replace(tzinfo=None)
        end_utc = TimeService.to_utc(end_local).replace(tzinfo=None)
        return start_utc, end_utc, start_local.date()

    def get_admin_balance_daily_usage(self, codigo: str) -> dict[str, Any]:
        codigo_norm = _sanitize_codigo(codigo)
        if not codigo_norm:
            raise ValueError("Informe o código do item")

        start_utc, end_utc, local_date = self._admin_balance_day_bounds_utc()
        used = int(
            db.session.query(func.count(InventarioEvento.id_evento))
            .filter(
                InventarioEvento.tipo == ADMIN_BALANCE_ADJUSTMENT_TYPE,
                InventarioEvento.codigo_item == codigo_norm,
                InventarioEvento.data_evento >= start_utc,
                InventarioEvento.data_evento < end_utc,
            )
            .scalar()
            or 0
        )
        remaining = max(0, ADMIN_BALANCE_DAILY_LIMIT - used)
        return {
            "limit": ADMIN_BALANCE_DAILY_LIMIT,
            "used": used,
            "remaining": remaining,
            "exhausted": remaining <= 0,
            "local_date": local_date,
        }

    @staticmethod
    def _build_admin_balance_audit_details(
        *,
        item: Item | None,
        codigo: str | None,
        matricula: str | None,
        motivo: str | None,
        target_balance: float | None,
        audit_context: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        details = dict(audit_context or {})
        if item is not None:
            details.setdefault("codigo_item", item.codigo_item)
            details.setdefault("descricao_item", item.descricao)
        elif codigo:
            details.setdefault("codigo_item", codigo)
        if matricula:
            details.setdefault("user_id", matricula)
        if motivo is not None:
            details["reason"] = motivo
        if target_balance is not None:
            details["target_balance"] = float(target_balance)
        if error_message:
            details["error_message"] = error_message

        if before:
            details["displayed_balance_before"] = before.get("saldo_exibido")
            details["legacy_balance_before"] = before.get("legacy_balance")
            details["ledger_balance_before"] = before.get("ledger_balance")
            details["stock_balance_before"] = before.get("stock_balance")
            details["daily_limit"] = before.get("daily_limit")
            details["daily_used"] = before.get("daily_adjustments_used")
            details["daily_remaining"] = before.get("daily_adjustments_remaining")

        if after:
            details["displayed_balance_after"] = after.get("saldo_exibido")
            details["legacy_balance_after"] = after.get("legacy_balance")
            details["ledger_balance_after"] = after.get("ledger_balance")
            details["stock_balance_after"] = after.get("stock_balance")
            details["daily_limit"] = after.get("daily_limit", details.get("daily_limit"))
            details["daily_used"] = after.get("daily_adjustments_used", details.get("daily_used"))
            details["daily_remaining"] = after.get("daily_adjustments_remaining", details.get("daily_remaining"))

        if result:
            details["event_id"] = result.get("event_id")
            details["movement_id"] = result.get("movement_id")
            details["operation_log_id"] = result.get("operation_log_id")
            details["changed"] = bool(result.get("changed"))
            if result.get("message"):
                details["message"] = result.get("message")

        return details

    @classmethod
    def _log_admin_balance_audit(cls, *, action_result: str, details: dict[str, Any]) -> None:
        log_admin_stock_adjustment(
            action_type=ADMIN_BALANCE_ADJUSTMENT_TYPE,
            action_result=action_result,
            details=details,
        )

    def get_admin_balance_snapshot(self, codigo: str) -> dict[str, Any]:
        codigo_norm = _sanitize_codigo(codigo)
        if not codigo_norm:
            raise ValueError("Informe o código do item")

        item = Item.query.get(codigo_norm)
        if not item:
            raise ValueError("Item não encontrado")

        from .ledger_reconciliation import ledger_reconciliation_service

        reconciliation = ledger_reconciliation_service.reconcile_product(codigo_norm)
        balance_snapshot = balance_provider.get_balance(codigo_norm, item=item)
        daily_usage = self.get_admin_balance_daily_usage(codigo_norm)
        saldo_exibido = Item.normalize_balance_value(balance_snapshot.quantity_base)
        saldo_fisico = Item.normalize_balance_value(item.get_saldo_fisico_total())
        legacy_balance = Item.normalize_balance_value(reconciliation.legacy_balance)
        ledger_balance = Item.normalize_balance_value(reconciliation.ledger_balance)
        stock_balance = Item.normalize_balance_value(reconciliation.stock_balance)
        divergence_legacy_vs_ledger = Item.normalize_balance_value(reconciliation.divergence_legacy_vs_ledger)
        divergence_ledger_vs_cache = Item.normalize_balance_value(reconciliation.divergence_ledger_vs_cache)

        return {
            "codigo": item.codigo_item,
            "descricao": item.descricao,
            "categoria": item.categoria,
            "unidade": item.unidade,
            "saldo_exibido": saldo_exibido,
            "saldo_fisico": saldo_fisico,
            "saldo_display": item.get_saldo_fisico_display(),
            "explicacao_saldo": item.get_explicacao_saldo(),
            "source": balance_snapshot.source,
            "migrated": bool(balance_snapshot.migrated),
            "legacy_balance": legacy_balance,
            "ledger_balance": ledger_balance,
            "stock_balance": stock_balance,
            "divergence_legacy_vs_ledger": divergence_legacy_vs_ledger,
            "divergence_ledger_vs_cache": divergence_ledger_vs_cache,
            "classification": reconciliation.classification,
            "classification_label": self._reconciliation_label(reconciliation.classification),
            "classification_badge": self._reconciliation_badge(reconciliation.classification),
            "pre_cadastro_pendente": bool(getattr(item, "pre_cadastro_pendente", False)),
            "tipo_embalagem_novo": item.tipo_embalagem_novo,
            "unidades_por_embalagem": item.unidades_por_embalagem,
            "foto_path": item.foto_path,
            "daily_limit": daily_usage["limit"],
            "daily_adjustments_used": daily_usage["used"],
            "daily_adjustments_remaining": daily_usage["remaining"],
            "daily_limit_exhausted": daily_usage["exhausted"],
            "daily_reference_date": daily_usage["local_date"],
        }

    def list_recent_admin_balance_adjustments(self, limit: int = 12) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 12), 50))
        events = (
            InventarioEvento.query
            .filter(InventarioEvento.tipo == ADMIN_BALANCE_ADJUSTMENT_TYPE)
            .order_by(InventarioEvento.data_evento.desc())
            .limit(safe_limit)
            .all()
        )
        if not events:
            return []

        item_ids = sorted({str(event.codigo_item) for event in events if event.codigo_item})
        user_ids = sorted({str(event.matricula) for event in events if event.matricula})
        items_by_id = {
            item.codigo_item: item
            for item in Item.query.filter(Item.codigo_item.in_(item_ids)).all()
        } if item_ids else {}
        users_by_id = {
            user.matricula: user
            for user in Usuario.query.filter(Usuario.matricula.in_(user_ids)).all()
        } if user_ids else {}

        results: list[dict[str, Any]] = []
        for event in events:
            item = items_by_id.get(str(event.codigo_item or ""))
            user = users_by_id.get(str(event.matricula or ""))
            results.append({
                "id": event.id_evento,
                "codigo": event.codigo_item,
                "descricao_item": item.descricao if item else None,
                "matricula": event.matricula,
                "usuario_nome": user.nome if user else None,
                "quantidade": float(event.quantidade or 0.0),
                "descricao": event.descricao,
                "data_evento": event.data_evento,
            })
        return results

    def set_admin_absolute_balance(
        self,
        *,
        codigo: str,
        novo_saldo: float,
        matricula: str,
        motivo: str,
        notify: bool = True,
        audit_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audit_context_norm = dict(audit_context or {})
        codigo_norm = _sanitize_codigo(codigo)
        motivo_norm = str(motivo or "").strip()
        if not codigo_norm:
            message = "Informe o código do item"
            self._log_admin_balance_audit(
                action_result="validation_error",
                details=self._build_admin_balance_audit_details(
                    item=None,
                    codigo=codigo_norm or codigo,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=None,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message)

        try:
            target_balance = float(novo_saldo)
        except (TypeError, ValueError) as exc:
            message = "Saldo inválido"
            self._log_admin_balance_audit(
                action_result="validation_error",
                details=self._build_admin_balance_audit_details(
                    item=None,
                    codigo=codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=None,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message) from exc

        if math.isnan(target_balance) or math.isinf(target_balance):
            message = "Saldo inválido"
            self._log_admin_balance_audit(
                action_result="validation_error",
                details=self._build_admin_balance_audit_details(
                    item=None,
                    codigo=codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=None,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message)

        if target_balance < 0:
            message = "Saldo não pode ser negativo"
            self._log_admin_balance_audit(
                action_result="validation_error",
                details=self._build_admin_balance_audit_details(
                    item=None,
                    codigo=codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=target_balance,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message)
        if not motivo_norm:
            message = "Informe o motivo do ajuste administrativo"
            self._log_admin_balance_audit(
                action_result="validation_error",
                details=self._build_admin_balance_audit_details(
                    item=None,
                    codigo=codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=target_balance,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message)

        item = Item.query.get(codigo_norm)
        if not item:
            message = "Item não encontrado"
            self._log_admin_balance_audit(
                action_result="validation_error",
                details=self._build_admin_balance_audit_details(
                    item=None,
                    codigo=codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=target_balance,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message)
        if bool(getattr(item, "pre_cadastro_pendente", False)):
            self._log_admin_balance_audit(
                action_result="pre_cadastro_blocked",
                details=self._build_admin_balance_audit_details(
                    item=item,
                    codigo=codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=target_balance,
                    audit_context=audit_context_norm,
                    error_message=ADMIN_BALANCE_PENDING_PRECADASTRO_MESSAGE,
                ),
            )
            raise ValueError(ADMIN_BALANCE_PENDING_PRECADASTRO_MESSAGE)

        snapshot_before = self.get_admin_balance_snapshot(codigo_norm)
        legacy_before = float(snapshot_before["legacy_balance"])
        ledger_before = float(snapshot_before["ledger_balance"])
        stock_before = float(snapshot_before["stock_balance"])
        displayed_before = float(snapshot_before["saldo_exibido"])

        legacy_delta = target_balance - legacy_before
        ledger_delta = target_balance - ledger_before
        cache_needs_sync = not self._balance_close(stock_before, target_balance)

        unit_base = resolve_canonical_unit(item)
        adjustment_description = (
            f"Ajuste administrativo de saldo [{motivo_norm}]: "
            f"exibido {displayed_before:g} -> {target_balance:g}; "
            f"legado {legacy_before:g} -> {target_balance:g}; "
            f"ledger {ledger_before:g} -> {target_balance:g}; "
            f"cache {stock_before:g} -> {target_balance:g}"
        )

        if self._balance_close(legacy_delta, 0.0) and self._balance_close(ledger_delta, 0.0) and not cache_needs_sync:
            result = {
                "changed": False,
                "message": "Saldo já estava alinhado com o valor informado.",
                "before": snapshot_before,
                "after": snapshot_before,
            }
            self._log_admin_balance_audit(
                action_result="no_change",
                details=self._build_admin_balance_audit_details(
                    item=item,
                    codigo=codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=target_balance,
                    audit_context=audit_context_norm,
                    before=snapshot_before,
                    after=snapshot_before,
                    result=result,
                ),
            )
            return result

        if bool(snapshot_before.get("daily_limit_exhausted")):
            limit = int(snapshot_before.get("daily_limit") or ADMIN_BALANCE_DAILY_LIMIT)
            used = int(snapshot_before.get("daily_adjustments_used") or 0)
            reference_date = snapshot_before.get("daily_reference_date")
            if hasattr(reference_date, "strftime"):
                date_label = reference_date.strftime("%d/%m/%Y")
            else:
                date_label = str(reference_date or "hoje")
            message = (
                f"Limite diário atingido para este item em {date_label}. "
                f"Já foram feitos {used} ajustes administrativos e o máximo é {limit} por dia."
            )
            self._log_admin_balance_audit(
                action_result="daily_limit_blocked",
                details=self._build_admin_balance_audit_details(
                    item=item,
                    codigo=codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=target_balance,
                    audit_context=audit_context_norm,
                    before=snapshot_before,
                    error_message=message,
                ),
            )
            raise ValueError(message)

        event = None
        if not self._balance_close(legacy_delta, 0.0):
            event = InventarioEvento(
                codigo_item=item.codigo_item,
                matricula=matricula,
                tipo=ADMIN_BALANCE_ADJUSTMENT_TYPE,
                quantidade=float(legacy_delta),
                descricao=adjustment_description,
                data_evento=datetime.utcnow(),
            )
            db.session.add(event)

        movement = None
        operation_log_id: int | None = None
        if not self._balance_close(ledger_delta, 0.0):
            movement = StockMovement(
                product_id=item.codigo_item,
                movement_type="ajuste",
                quantity_base=float(ledger_delta),
                unit_base=unit_base,
                reference_type="admin_balance_override",
                reference_id=None,
                metadata_json={
                    "source": ADMIN_BALANCE_ADJUSTMENT_SOURCE,
                    "user_id": str(matricula or "").strip() or None,
                    "reason": motivo_norm,
                    "target_balance": target_balance,
                    "legacy_balance_before": legacy_before,
                    "ledger_balance_before": ledger_before,
                    "stock_balance_before": stock_before,
                    "displayed_balance_before": displayed_before,
                    "description": adjustment_description,
                },
                created_at=datetime.utcnow(),
            )
            db.session.add(movement)

            operation_log = operation_log_service.create_success_log(
                operation_type="ajuste",
                product_id=item.codigo_item,
                quantity_input=abs(float(ledger_delta)),
                quantity_base=float(ledger_delta),
                unit_input=unit_base,
                user_id=matricula,
                source=ADMIN_BALANCE_ADJUSTMENT_SOURCE,
                payload_json={
                    "target_balance": target_balance,
                    "legacy_balance_before": legacy_before,
                    "ledger_balance_before": ledger_before,
                    "stock_balance_before": stock_before,
                    "displayed_balance_before": displayed_before,
                    "legacy_delta": float(legacy_delta),
                    "ledger_delta": float(ledger_delta),
                    "reason": motivo_norm,
                    "description": adjustment_description,
                },
                created_at=movement.created_at,
                commit=False,
            )
            operation_log_id = operation_log.id

        balance = db.session.get(StockBalance, item.codigo_item)
        if balance is None:
            balance = StockBalance(product_id=item.codigo_item)
            db.session.add(balance)
        balance.quantity_base = target_balance

        inventory_engine._sync_packaging_state_to_balance(
            item=item,
            quantity_base=target_balance,
            unit_base=unit_base,
        )
        item.estoque_minimo = _calculate_min_stock(target_balance)

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            self._log_admin_balance_audit(
                action_result="error",
                details=self._build_admin_balance_audit_details(
                    item=item,
                    codigo=codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    target_balance=target_balance,
                    audit_context=audit_context_norm,
                    before=snapshot_before,
                    error_message=str(exc),
                ),
            )
            raise

        if notify:
            try:
                if event is not None:
                    from .notification_router import NotificationRouterService
                    NotificationRouterService.route_inventory_event(event.id_evento)
                elif operation_log_id is not None:
                    operation_log_service.notify_telegram(operation_log_id)
            except Exception:
                logger.exception("Falha ao notificar ajuste administrativo de saldo")

        snapshot_after = self.get_admin_balance_snapshot(codigo_norm)
        result = {
            "changed": True,
            "message": "Saldo administrativo ajustado com sucesso.",
            "before": snapshot_before,
            "after": snapshot_after,
            "event_id": event.id_evento if event is not None else None,
            "operation_log_id": operation_log_id,
            "movement_id": movement.id if movement is not None else None,
        }
        self._log_admin_balance_audit(
            action_result="success",
            details=self._build_admin_balance_audit_details(
                item=item,
                codigo=codigo_norm,
                matricula=matricula,
                motivo=motivo_norm,
                target_balance=target_balance,
                audit_context=audit_context_norm,
                before=snapshot_before,
                after=snapshot_after,
                result=result,
            ),
        )
        return result

    @staticmethod
    def _build_simple_balance_display(item: Item, saldo: float) -> str:
        normalized_balance = Item.normalize_balance_value(saldo)
        return f"{normalized_balance:g} {item.unidade or 'un'}"

    @staticmethod
    def _should_use_packaging_display(item: Item) -> bool:
        from ..services.embalagem_service import EmbalagemService

        return EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item)

    def _resolve_balances_in_bulk(self, items: list[Item]) -> dict[str, float]:
        snapshots = balance_provider.get_balances(
            [item.codigo_item for item in items if item.codigo_item],
            items_by_id={item.codigo_item: item for item in items if item.codigo_item},
        )
        return {
            product_id: Item.normalize_balance_value(snapshot.quantity_base)
            for product_id, snapshot in snapshots.items()
        }

    def get_material_return_pending(self, *, codigo: str, matricula: str) -> float:
        """Retorna quanto ainda pode ser devolvido (estornado) para um material.

        Regra:
        - O cálculo respeita a ordem cronológica dos movimentos para evitar que
          devoluções antigas ou entradas legadas anteriores reduzam retiradas feitas depois.
        - total_devolucoes considera:
          1) eventos tipo 'devolucao_material' (novo padrão)
          2) entradas legadas sem NF (rota antiga do mobile), para não permitir dupla devolução.
        """
        codigo_norm = (codigo or "").strip()
        matricula_norm = (matricula or "").strip()
        if not codigo_norm or not matricula_norm:
            return 0.0

        timeline: list[tuple[datetime, int, str, float, int]] = []

        saidas = (
            db.session.query(Saida.data_saida, Saida.quantidade, Saida.id_saida)
            .filter(Saida.codigo_item == codigo_norm, Saida.matricula == matricula_norm)
            .order_by(Saida.data_saida.asc(), Saida.id_saida.asc())
            .all()
        )
        for data_saida, quantidade, saida_id in saidas:
            timeline.append((data_saida or datetime.min, 0, "saida", self._as_positive_float(quantidade), int(saida_id or 0)))

        eventos = (
            db.session.query(InventarioEvento.data_evento, InventarioEvento.quantidade, InventarioEvento.id_evento)
            .filter(
                InventarioEvento.codigo_item == codigo_norm,
                InventarioEvento.matricula == matricula_norm,
                InventarioEvento.tipo == "devolucao_material",
            )
            .order_by(InventarioEvento.data_evento.asc(), InventarioEvento.id_evento.asc())
            .all()
        )
        for data_evento, quantidade, evento_id in eventos:
            timeline.append((data_evento or datetime.min, 1, "devolucao_material", self._as_positive_float(quantidade), int(evento_id or 0)))

        entradas_legado = (
            db.session.query(Entrada.data_entrada, Entrada.quantidade, Entrada.id_entrada)
            .filter(
                Entrada.codigo_item == codigo_norm,
                Entrada.matricula == matricula_norm,
                Entrada.nota_fiscal.is_(None),
            )
            .order_by(Entrada.data_entrada.asc(), Entrada.id_entrada.asc())
            .all()
        )
        for data_entrada, quantidade, entrada_id in entradas_legado:
            timeline.append((data_entrada or datetime.min, 2, "entrada_legado", self._as_positive_float(quantidade), int(entrada_id or 0)))

        timeline.sort(key=lambda row: (row[0], row[1], row[4]))

        pendente = 0.0
        for _, _, kind, quantidade, _ in timeline:
            if quantidade <= 0:
                continue
            if kind == "saida":
                pendente += quantidade
            else:
                pendente = max(pendente - quantidade, 0.0)

        return float(pendente)

    def registrar_devolucao_material(
        self,
        *,
        codigo: str,
        quantidade: float,
        matricula: str,
        observacao: str | None = None,
        commit: bool = True,
    ) -> InventarioEvento:
        """Registra devolução de material como um InventarioEvento.

        Importante:
        - Não cria Entrada (evita devolução virar 'adição' duplicada).
        - Bloqueia devolução acima do pendente por funcionário/item.
        """
        codigo_norm = (codigo or "").strip()
        matricula_norm = (matricula or "").strip()
        if not codigo_norm:
            raise ValueError("Código do item é obrigatório")
        if not matricula_norm:
            raise ValueError("Matrícula é obrigatória")

        quantidade_f = self._as_positive_float(quantidade)
        if quantidade_f <= 0:
            raise ValueError("Quantidade inválida")

        item = Item.query.get(codigo_norm)
        if not item:
            raise ValueError("Item não encontrado")

        categoria_text = (item.categoria or "").strip().lower()
        if "ferrament" in categoria_text:
            raise ValueError("Use a devolução de ferramentas para este item")

        pendente = self.get_material_return_pending(codigo=codigo_norm, matricula=matricula_norm)
        # Tolerância mínima para float.
        if pendente <= 1e-9:
            raise ValueError("Devolução não permitida: não há retirada pendente para este material.")
        if quantidade_f > pendente + 1e-9:
            raise ValueError(f"Devolução excede o pendente. Pendente: {pendente:g}")

        descricao_base = f"Devolução de Material: {item.descricao or 'Item'}"
        obs = (observacao or "").strip()
        descricao = f"{descricao_base} | {obs}" if obs else descricao_base

        payload = MovimentoPayload(
            codigo=item.codigo_item,
            quantidade=float(quantidade_f),
            matricula=matricula_norm,
            observacao=obs or None,
            is_devolucao=True,
        )
        ledger_result = self._mirror_payload_to_ledger(
            item=item,
            payload=payload,
            movement_type="devolucao",
            metadata={
                "reference_type": "inventario_evento",
                "legacy_event_type": "devolucao_material",
            },
        )

        evento = InventarioEvento(
            codigo_item=item.codigo_item,
            matricula=matricula_norm,
            tipo="devolucao_material",
            quantidade=float(quantidade_f),
            descricao=descricao,
            data_evento=datetime.utcnow(),
        )
        db.session.add(evento)
        db.session.flush()

        try:
            saldo_atualizado = float(item.get_saldo_atual() or 0.0)
        except Exception:
            saldo_atualizado = 0.0
        item.estoque_minimo = _calculate_min_stock(saldo_atualizado)

        if commit:
            db.session.commit()
            if ledger_result is not None:
                inventory_engine.record_operation_audit(ledger_result)
                operation_log_service.notify_telegram(ledger_result.operation_log_id)

        return evento

    @staticmethod
    def _normalize_tipo_custodia(value: str | None) -> str:
        raw = (value or "").strip().lower()
        if raw in {"permanente", "perm", "p"}:
            return "permanente"
        if raw in {"temporaria", "temporária", "diaria", "diária", "daily", "d"}:
            return "temporaria"
        return "temporaria"

    @staticmethod
    def _should_use_packaging_dual_write(
        item: Item,
        payload: MovimentoPayload | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not uses_packaging_legacy_normalization(item):
            return False
        if payload and payload.em_embalagens is True:
            return True
        if payload and payload.em_embalagens is False:
            return False
        reference_type = str((metadata or {}).get("reference_type") or "").strip().lower()
        return reference_type == "legacy_movimento"

    @staticmethod
    def _infer_dual_write_unit(
        item: Item,
        payload: MovimentoPayload | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if InventoryService._should_use_packaging_dual_write(item, payload, metadata):
            canonical_unit = resolve_canonical_unit(item)
            if canonical_unit:
                return canonical_unit

        if payload and payload.em_embalagens is True:
            tipo_emb = (item.tipo_embalagem_novo or "").strip().lower()
            if tipo_emb:
                return tipo_emb

        base_unit = next((unit for unit in item.product_units if unit.is_base and unit.active), None)
        if base_unit and base_unit.unit_code:
            return (base_unit.unit_code or "").strip().lower() or None

        unidade_item = (item.unidade or "").strip().lower()
        if unidade_item:
            return unidade_item

        return None

    @staticmethod
    def _resolve_packaging_dual_write(
        item: Item,
        quantity_value: float,
        payload: MovimentoPayload | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[float, str] | None:
        if not InventoryService._should_use_packaging_dual_write(item, payload, metadata):
            return None
        return resolve_packaging_quantity_and_unit(item, quantity_value)

    @staticmethod
    def _sync_packaging_balance_before_dual_write(
        item: Item,
        *,
        movement_type: str,
        quantity_base: float,
    ) -> None:
        from ..services.embalagem_service import EmbalagemService

        if not EmbalagemService.tem_embalagem(item):
            return

        current_total = float(EmbalagemService.calcular_estoque_total(item) or 0)
        movement_type_norm = (movement_type or "").strip().lower()
        if movement_type_norm == "saida":
            expected_before = current_total + quantity_base
        elif movement_type_norm in {"entrada", "devolucao"}:
            expected_before = current_total - quantity_base
        else:
            expected_before = current_total

        if expected_before < 0:
            expected_before = 0.0

        balance = db.session.get(StockBalance, item.codigo_item)
        if balance is None:
            balance = StockBalance()
            balance.product_id = item.codigo_item
            db.session.add(balance)

        current_balance = float(getattr(balance, "quantity_base", 0) or 0)
        if abs(current_balance - expected_before) <= 1e-6:
            return

        balance.quantity_base = expected_before
        if hasattr(balance, "read_model_ready"):
            balance.read_model_ready = True
        db.session.flush()

    def _mirror_payload_to_ledger(
        self,
        *,
        item: Item,
        payload: MovimentoPayload,
        movement_type: str,
        quantity: float | None = None,
        from_unit: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InventoryOperationResult | None:
        movement_type_norm = (movement_type or "").strip().lower()
        quantity_value = float(quantity if quantity is not None else payload.quantidade)
        if quantity_value == 0:
            return None

        packaging_resolution = self._resolve_packaging_dual_write(item, quantity_value, payload, metadata)
        if packaging_resolution is not None and from_unit is None:
            quantity_value, from_unit = packaging_resolution
            self._sync_packaging_balance_before_dual_write(
                item,
                movement_type=movement_type_norm,
                quantity_base=quantity_value,
            )

        unit_value = (from_unit or self._infer_dual_write_unit(item, payload, metadata) or "").strip().lower()
        if not unit_value:
            raise ValueError(f"Não foi possível inferir a unidade base para {item.codigo_item}")

        mirror_metadata = {
            "dual_write_active": True,
            "mirrored_from_legacy": True,
            "legacy_payload": {
                "nota_fiscal": payload.nota_fiscal,
                "observacao": payload.observacao,
                "local_servico": payload.local_servico,
                "atividade_operacional": payload.atividade_operacional,
                "ordem_servico": payload.ordem_servico,
                "centro_custo": payload.centro_custo,
                "matricula": payload.matricula,
                "em_embalagens": payload.em_embalagens,
                "modo_fracionado": payload.modo_fracionado,
                "tipo_custodia": payload.tipo_custodia,
            },
            **(metadata or {}),
        }

        if movement_type_norm == "entrada":
            return inventory_engine.register_entry(
                product_id=item.codigo_item,
                quantity=quantity_value,
                from_unit=unit_value,
                metadata=mirror_metadata,
                commit=False,
                write_audit=False,
            )
        if movement_type_norm == "saida":
            return inventory_engine.register_exit(
                product_id=item.codigo_item,
                quantity=quantity_value,
                from_unit=unit_value,
                metadata=mirror_metadata,
                commit=False,
                write_audit=False,
            )
        if movement_type_norm == "devolucao":
            return inventory_engine.register_return(
                product_id=item.codigo_item,
                quantity=abs(quantity_value),
                from_unit=unit_value,
                metadata=mirror_metadata,
                commit=False,
                write_audit=False,
            )
        if movement_type_norm == "ajuste":
            return inventory_engine.register_adjustment(
                product_id=item.codigo_item,
                quantity=quantity_value,
                from_unit=unit_value,
                metadata=mirror_metadata,
                commit=False,
                write_audit=False,
            )

        raise ValueError(f"Tipo de movimento não suportado pelo inventory_engine: {movement_type_norm}")

        return None

    def mirror_legacy_movement(
        self,
        *,
        product_id: str,
        movement_type: str,
        quantity: float,
        payload: MovimentoPayload | None = None,
        from_unit: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InventoryOperationResult | None:
        item = Item.query.get((product_id or "").strip())
        if not item:
            return None
        payload_value = payload or MovimentoPayload(codigo=item.codigo_item, quantidade=float(abs(quantity)))
        return self._mirror_payload_to_ledger(
            item=item,
            payload=payload_value,
            movement_type=movement_type,
            quantity=quantity,
            from_unit=from_unit,
            metadata=metadata,
        )

    @staticmethod
    def finalize_ledger_mirror(result: InventoryOperationResult | None) -> None:
        if result is None:
            return
        inventory_engine.record_operation_audit(result)

    def _bulk_saldos(self, codigos: list[str] | None = None) -> dict[str, float]:
        # Importante: evitar IN com listas enormes (pode estourar limite de parâmetros
        # e/ou degradar performance). Só aplicamos filtro quando a lista é pequena.
        filtro_codigos: set[str] | None = None
        if codigos:
            candidatos = {c for c in codigos if c}
            if 0 < len(candidatos) <= 500:
                filtro_codigos = candidatos

        entradas_q = (
            db.session.query(
                Entrada.codigo_item,
                func.coalesce(func.sum(Entrada.quantidade), 0).label("total_entrada"),
            )
            .filter(Entrada.codigo_item.isnot(None))
            .group_by(Entrada.codigo_item)
        )
        saidas_q = (
            db.session.query(
                Saida.codigo_item,
                func.coalesce(func.sum(Saida.quantidade), 0).label("total_saida"),
            )
            .filter(Saida.codigo_item.isnot(None))
            .group_by(Saida.codigo_item)
        )
        ajustes_q = (
            db.session.query(
                InventarioEvento.codigo_item,
                func.coalesce(func.sum(InventarioEvento.quantidade), 0).label("total_ajuste"),
            )
            .filter(InventarioEvento.codigo_item.isnot(None))
            .group_by(InventarioEvento.codigo_item)
        )

        if filtro_codigos is not None:
            entradas_q = entradas_q.filter(Entrada.codigo_item.in_(filtro_codigos))
            saidas_q = saidas_q.filter(Saida.codigo_item.in_(filtro_codigos))
            ajustes_q = ajustes_q.filter(InventarioEvento.codigo_item.in_(filtro_codigos))

        entradas = {codigo: float(total or 0) for codigo, total in entradas_q.all() if codigo}
        saidas = {codigo: float(total or 0) for codigo, total in saidas_q.all() if codigo}
        ajustes = {codigo: float(total or 0) for codigo, total in ajustes_q.all() if codigo}

        saldos: dict[str, float] = {}
        for codigo in set(entradas) | set(saidas) | set(ajustes):
            saldos[codigo] = entradas.get(codigo, 0.0) - saidas.get(codigo, 0.0) + ajustes.get(codigo, 0.0)
        return saldos

    def _sync_packaging_read_model_for_item(self, item: Item, *, commit: bool = False) -> bool:
        from ..services.embalagem_service import EmbalagemService

        if item is None or not EmbalagemService.tem_embalagem(item):
            return False

        try:
            return inventory_engine.sync_packaging_read_model(
                product_id=item.codigo_item,
                commit=commit,
            )
        except Exception:
            return False

    def search_items_for_autocomplete(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q or len(q) < 1:
            return []

        cache_key = f"search_items_for_autocomplete:{q.lower()}:{int(limit)}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]

        like = f"%{q}%"
        rows = (
            Item.query.filter(or_(Item.codigo_item.ilike(like), Item.descricao.ilike(like)))
            .order_by(Item.descricao)
            .limit(limit)
            .all()
        )

        from ..services.embalagem_service import EmbalagemService
        bulk_balances = self._resolve_balances_in_bulk(rows)
        results: list[dict[str, Any]] = []
        updated = False
        for item in rows:
            if EmbalagemService.tem_embalagem(item):
                if self._sync_packaging_read_model_for_item(item, commit=False):
                    updated = True
                try:
                    saldo = float(EmbalagemService.calcular_estoque_total(item) or 0.0)
                except Exception:
                    saldo = float(item.get_estoque_total_com_embalagens() or 0.0)
                saldo_display = item.get_saldo_fisico_display()
            else:
                saldo = float(bulk_balances.get(item.codigo_item, 0.0))
                saldo_display = self._build_simple_balance_display(item, saldo)
            results.append(
                {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "categoria": item.categoria,
                    "saldo": saldo,
                    "saldo_display": saldo_display,
                    "tipo_embalagem_novo": item.tipo_embalagem_novo,
                    "unidades_por_embalagem": item.unidades_por_embalagem,
                    "grandeza_referencia": item.grandeza_referencia,
                    "litros_por_embalagem": item.litros_por_embalagem,
                    "saldo_embalagens": item.estoque_embalagens,
                    "saldo_unidades_total": saldo,
                    "saldo_unidades_soltas": item.estoque_unidades_soltas,
                    "unidade": item.unidade,
                }
            )
        if updated:
            db.session.commit()
        return self._set_cached(cache_key, [dict(item) for item in results], ttl_seconds=3.0)

    def _has_active_tool_withdrawal(self, codigo_item: str, matricula: str | None) -> bool:
        """Retorna True se a matrícula já possui retirada ativa da mesma ferramenta."""
        if not codigo_item or not matricula:
            return False

        saidas = (
            db.session.query(Saida.id_saida, Saida.data_saida)
            .filter(
                Saida.codigo_item == codigo_item,
                Saida.matricula == matricula,
            )
            .order_by(Saida.data_saida.desc())
            .limit(50)
            .all()
        )

        if not saidas:
            return False

        tipos_fechamento = [
            "devolucao_ferramenta",
            "devolucao_material",
            "quebra_ferramenta",
            "reparo_ferramenta",
            "devolucao",
        ]

        for _, data_saida in saidas:
            devolucao = (
                db.session.query(InventarioEvento.id_evento)
                .filter(
                    InventarioEvento.codigo_item == codigo_item,
                    InventarioEvento.matricula == matricula,
                    InventarioEvento.tipo.in_(tipos_fechamento),
                    InventarioEvento.data_evento >= data_saida,
                )
                .first()
            )
            if not devolucao:
                return True

        return False

    def ensure_barcodes_for_all(self) -> dict[str, int]:
        stats = {
            "total": 0,
            "generated": 0,
            "skipped": 0,
            "failed": 0,
        }
        itens = Item.query.order_by(Item.codigo_item).all()
        for item in itens:
            stats["total"] += 1
            codigo = (item.codigo_item or "").strip()
            if not codigo:
                stats["failed"] += 1
                continue

            existing_path = item.barcode_image_path or get_barcode_path(codigo)
            if existing_path:
                if item.barcode_image_path != existing_path:
                    item.barcode_image_path = existing_path
                stats["skipped"] += 1
                continue

            try:
                barcode_path = generate_barcode(codigo, item.descricao)
                item.barcode_image_path = barcode_path
                stats["generated"] += 1
            except Exception:
                stats["failed"] += 1

        db.session.commit()
        return stats

    def list_items(self) -> list[dict[str, Any]]:
        cached = self._get_cached("list_items")
        if cached is not None:
            return [dict(item) for item in cached]

        itens = Item.query.order_by(Item.descricao).all()
        resultado: list[dict[str, Any]] = []
        atualizado = False
        from ..services.embalagem_service import EmbalagemService
        bulk_balances = self._resolve_balances_in_bulk(itens)

        def _safe_float_or_none(value: object) -> float | None:
            if value in ("", None):
                return None
            try:
                f = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
            if math.isnan(f) or math.isinf(f):
                return None
            return f

        def _resolve_stock_value_quantity(item: Item, *, saldo_total: float) -> float:
            quantity = float(saldo_total or 0.0)
            if quantity <= 0 or not EmbalagemService.tem_embalagem(item):
                return quantity

            base_unit = next((unit for unit in item.product_units if unit.is_base and unit.active and unit.unit_code), None)
            base_unit_code = str(getattr(base_unit, "unit_code", "") or "").strip().lower()
            if not base_unit_code or not is_packaging_unit_code(base_unit_code):
                return quantity

            packaging_factor = float(resolve_packaging_factor(item) or 0.0)
            if packaging_factor <= 1:
                return quantity

            embalagens = float(item.estoque_embalagens or 0.0)
            unidades_soltas = float(item.estoque_unidades_soltas or 0.0)
            return embalagens + (unidades_soltas / packaging_factor)

        def _calc_stock_total_value(item: Item, *, preco_unitario_base: float | None, saldo_total: float) -> float | None:
            if preco_unitario_base is None or preco_unitario_base <= 0:
                return None
            quantity_for_value = _resolve_stock_value_quantity(item, saldo_total=saldo_total)
            return quantity_for_value * preco_unitario_base

        for item in itens:
            if self._should_use_packaging_display(item):
                if self._sync_packaging_read_model_for_item(item, commit=False):
                    atualizado = True
                try:
                    saldo = float(item.get_saldo_fisico_total() or 0.0)
                except Exception:
                    db.session.rollback()
                    try:
                        saldo = float(EmbalagemService.calcular_estoque_total(item) or 0.0)
                    except Exception:
                        saldo = float(item.get_estoque_total_com_embalagens() or 0.0)
                saldo_display = item.get_saldo_fisico_display()
                explicacao_saldo = item.get_explicacao_saldo()
            else:
                saldo = float(bulk_balances.get(item.codigo_item, 0.0))
                saldo_display = self._build_simple_balance_display(item, saldo)
                explicacao_saldo = None
            minimo = _calculate_min_stock(saldo)
            if item.estoque_minimo != minimo:
                item.estoque_minimo = minimo
                atualizado = True

            preco_compra = _safe_float_or_none(getattr(item, "preco_compra_unitario", None))
            preco_compra_base = _safe_float_or_none(getattr(item, "preco_compra_unitario_base", None))
            preco_reposicao = _safe_float_or_none(getattr(item, "preco_reposicao_unitario", None))
            preco_reposicao_base = _safe_float_or_none(getattr(item, "preco_reposicao_unitario_base", None))
            valor_total_compra = _calc_stock_total_value(item, preco_unitario_base=preco_compra_base, saldo_total=saldo)
            valor_total_reposicao = _calc_stock_total_value(item, preco_unitario_base=preco_reposicao_base, saldo_total=saldo)
            
            resultado.append(
                {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "unidade": item.unidade,
                    "marca": item.marca,
                    "localizacao": item.localizacao,
                    "setor": item.setor,
                    "estoque_minimo": minimo,
                    "nota_fiscal": item.nota_fiscal,
                    "categoria": item.categoria,
                    "ultima_edicao_em": item.ultima_edicao_em.isoformat() if item.ultima_edicao_em else None,
                    "ultima_edicao_por": item.ultima_edicao_por,
                    "saldo": saldo,
                    "saldo_display": saldo_display,
                    "explicacao_saldo": explicacao_saldo,
                    "saldo_unidades_total": saldo,
                    "saldo_embalagens": item.estoque_embalagens,
                    "saldo_unidades_soltas": item.estoque_unidades_soltas,
                    "foto_path": item.foto_path,
                    "tipo_embalagem_novo": item.tipo_embalagem_novo,
                    "unidades_por_embalagem": item.unidades_por_embalagem,
                    "grandeza_referencia": item.grandeza_referencia,
                    "litros_por_embalagem": item.litros_por_embalagem,
                    "product_units": [
                        {
                            "unit_code": unit.unit_code,
                            "unit_label": unit.unit_label,
                            "dimension": unit.dimension,
                            "is_base": bool(unit.is_base),
                            "active": bool(unit.active),
                        }
                        for unit in sorted(item.product_units, key=lambda row: (not bool(row.is_base), (row.unit_code or ""), row.id or 0))
                    ],
                    "preco_compra_unitario": preco_compra,
                    "preco_compra_unitario_base": preco_compra_base,
                    "preco_compra_unidade_preco": getattr(item, "preco_compra_unidade_preco", None),
                    "preco_compra_fator_base": getattr(item, "preco_compra_fator_base", None),
                    "preco_compra_fonte": getattr(item, "preco_compra_fonte", None),
                    "preco_compra_documento": getattr(item, "preco_compra_documento", None),
                    "preco_compra_atualizado_em": item.preco_compra_atualizado_em.isoformat() if getattr(item, "preco_compra_atualizado_em", None) else None,
                    "preco_compra_atualizado_por": getattr(item, "preco_compra_atualizado_por", None),
                    "preco_reposicao_unitario": preco_reposicao,
                    "preco_reposicao_unitario_base": preco_reposicao_base,
                    "preco_reposicao_unidade_preco": getattr(item, "preco_reposicao_unidade_preco", None),
                    "preco_reposicao_fator_base": getattr(item, "preco_reposicao_fator_base", None),
                    "preco_reposicao_fonte": getattr(item, "preco_reposicao_fonte", None),
                    "preco_reposicao_uf": getattr(item, "preco_reposicao_uf", None),
                    "preco_reposicao_query": getattr(item, "preco_reposicao_query", None),
                    "preco_reposicao_url": getattr(item, "preco_reposicao_url", None),
                    "preco_reposicao_atualizado_em": item.preco_reposicao_atualizado_em.isoformat() if getattr(item, "preco_reposicao_atualizado_em", None) else None,
                    "preco_reposicao_atualizado_por": getattr(item, "preco_reposicao_atualizado_por", None),
                    "pre_cadastro_pendente": bool(getattr(item, "pre_cadastro_pendente", False)),
                    "pre_cadastro_origem": getattr(item, "pre_cadastro_origem", None),
                    "pre_cadastro_documento_item_id": getattr(item, "pre_cadastro_documento_item_id", None),
                    "pre_cadastro_criado_em": item.pre_cadastro_criado_em.isoformat() if getattr(item, "pre_cadastro_criado_em", None) else None,
                    "pre_cadastro_finalizado_em": item.pre_cadastro_finalizado_em.isoformat() if getattr(item, "pre_cadastro_finalizado_em", None) else None,
                    "valor_estoque_compra_total": valor_total_compra,
                    "valor_estoque_reposicao_total": valor_total_reposicao,
                }
            )
        if atualizado:
            db.session.commit()
        return self._set_cached("list_items", [dict(item) for item in resultado], ttl_seconds=5.0)

    def get_item(self, codigo: str) -> dict[str, Any] | None:
        item = Item.query.get(codigo)
        if not item:
            return None
        from ..services.embalagem_service import EmbalagemService
        packaging_synced = False
        if EmbalagemService.tem_embalagem(item):
            packaging_synced = self._sync_packaging_read_model_for_item(item, commit=False)
            try:
                saldo = float(EmbalagemService.calcular_estoque_total(item) or 0)
            except Exception:
                saldo = 0.0
        else:
            saldo = item.get_saldo_atual()
        minimo = _calculate_min_stock(saldo)
        if item.estoque_minimo != minimo:
            item.estoque_minimo = minimo
            packaging_synced = True
        if packaging_synced:
            db.session.commit()
        dados = item.to_dict(include_balance=True)
        latest_finance_entry = (
            FinanceLedgerEntry.query.filter(FinanceLedgerEntry.codigo_item == codigo)
            .order_by(FinanceLedgerEntry.data_lancamento.desc(), FinanceLedgerEntry.id.desc())
            .first()
        )
        if latest_finance_entry:
            dados.update(
                {
                    "finance_supplier_id": latest_finance_entry.fornecedor_id,
                    "finance_origem_valor": latest_finance_entry.origem_valor,
                    "finance_tipo_documento": latest_finance_entry.tipo_documento,
                    "finance_comprovacao_status": latest_finance_entry.comprovacao_status,
                    "finance_observacao": latest_finance_entry.observacao,
                }
            )
        dados["estoque_minimo"] = minimo
        dados["saldo"] = saldo
        return dados

    def create_item(self, payload: dict[str, Any]) -> str:
        codigo = _sanitize_codigo(payload.get("codigo") or payload.get("codigo_item"))
        if not codigo:
            raise ValueError("Código do item é obrigatório")

        # Verificar se item já existe
        item_existente = Item.query.get(codigo)
        
        # Processar data de entrada (blindada: sempre servidor)
        data_entrada = payload.get("data_entrada")
        if data_entrada:
            if isinstance(data_entrada, str):
                try:
                    data_entrada = datetime.strptime(data_entrada, '%Y-%m-%d').date()
                except ValueError:
                    data_entrada = None
        if not data_entrada:
            data_entrada = datetime.now().date()
        
        # Lote: manual quando informado, automático apenas quando solicitado
        auto_lote = bool(payload.get("gerar_lote_automatico"))
        lote = (payload.get("lote") or "").strip() or None
        if auto_lote:
            lote = generate_lote(datetime.combine(data_entrada, datetime.min.time()))
        
        # Se item existe, verificar se é o mesmo lote
        if item_existente:
            # Se o lote é igual (ou ambos vazios), é duplicata
            if (item_existente.lote or "") == (lote or ""):
                raise ValueError("Código já cadastrado com este lote. Use 'Registro de Entrada' para adicionar estoque.")
            else:
                # Lote diferente: registrar como nova entrada e atualizar dados do item
                # Campos estruturais de rastreabilidade são imutáveis após definidos.
                # Permitimos apenas o primeiro preenchimento (write-once) para manter
                # compatibilidade com bases antigas que tinham valores nulos.
                if not (item_existente.lote or "").strip() and lote:
                    item_existente.lote = lote
                item_existente.data_entrada = data_entrada
                
                # Atualizar datas de fabricação e validade se informadas
                data_fabricacao = payload.get("data_fabricacao")
                if data_fabricacao and isinstance(data_fabricacao, str):
                    try:
                        item_existente.data_fabricacao = datetime.strptime(data_fabricacao, '%Y-%m-%d').date()
                    except ValueError:
                        pass
                
                data_validade = payload.get("data_validade")
                if item_existente.data_validade is None and data_validade and isinstance(data_validade, str):
                    try:
                        item_existente.data_validade = datetime.strptime(data_validade, '%Y-%m-%d').date()
                    except ValueError:
                        pass

                # Foto: se foi enviada no formulário, persistir também.
                # (Antes, o fluxo de "lote diferente" ignorava foto_path.)
                if "foto_path" in payload:
                    nova_foto = payload.get("foto_path")
                    try:
                        if nova_foto and item_existente.foto_path and item_existente.foto_path != nova_foto:
                            from .item_foto_service import ItemFotoService

                            ItemFotoService.deletar_foto(item_existente.foto_path)
                    except Exception:
                        pass
                    item_existente.foto_path = nova_foto
                if "advanced_unit_settings" in payload:
                    _apply_advanced_unit_settings(item_existente, payload.get("advanced_unit_settings"))
                    _assign_normalized_item_price(item_existente, raw_price=item_existente.preco_compra_unitario, kind="compra")
                    _assign_normalized_item_price(item_existente, raw_price=item_existente.preco_reposicao_unitario, kind="reposicao")
                
                # Registrar entrada com a quantidade
                quantidade = payload.get("quantidade") or payload.get("saldo") or 0
                if quantidade and int(quantidade) > 0:
                    nota_fiscal = payload.get("nota_fiscal")

                    try:
                        from ..services.embalagem_service import embalagem_service

                        if embalagem_service.tem_embalagem(item_existente):
                            novas_emb, novas_soltas = embalagem_service.processar_entrada(
                                item_existente, float(quantidade), True
                            )
                            item_existente.estoque_embalagens = novas_emb
                            item_existente.estoque_unidades_soltas = novas_soltas
                    except Exception:
                        pass

                    entrada = Entrada(
                        codigo_item=codigo,
                        quantidade=int(quantidade),
                        nota_fiscal=nota_fiscal,
                        data_entrada=datetime.combine(data_entrada, datetime.min.time()),
                    )
                    db.session.add(entrada)
                
                db.session.commit()
                # Prefixo especial para indicar que foi atualização (entrada já registrada)
                return f"UPDATED:{codigo}"
        
        # Processar datas de fabricação e validade
        data_fabricacao = payload.get("data_fabricacao")
        if data_fabricacao and isinstance(data_fabricacao, str):
            try:
                data_fabricacao = datetime.strptime(data_fabricacao, '%Y-%m-%d').date()
            except ValueError:
                data_fabricacao = None
        
        data_validade = payload.get("data_validade")
        if data_validade and isinstance(data_validade, str):
            try:
                data_validade = datetime.strptime(data_validade, '%Y-%m-%d').date()
            except ValueError:
                data_validade = None

        data_emissao = payload.get("preco_compra_data_emissao")
        if data_emissao and isinstance(data_emissao, str):
            try:
                data_emissao = datetime.strptime(data_emissao, '%Y-%m-%d').date()
            except ValueError:
                data_emissao = None

        data_recebimento = payload.get("preco_compra_data_recebimento")
        if data_recebimento and isinstance(data_recebimento, str):
            try:
                data_recebimento = datetime.strptime(data_recebimento, '%Y-%m-%d').date()
            except ValueError:
                data_recebimento = None

        grandeza_referencia = payload.get("grandeza_referencia")
        if grandeza_referencia in ("", None):
            grandeza_referencia = None
        else:
            try:
                grandeza_referencia = float(grandeza_referencia)
            except (TypeError, ValueError):
                grandeza_referencia = None

        litros_por_embalagem = payload.get("litros_por_embalagem")
        if litros_por_embalagem in ("", None):
            litros_por_embalagem = None
        else:
            try:
                litros_por_embalagem = float(litros_por_embalagem)
            except (TypeError, ValueError):
                litros_por_embalagem = None

        # Novos campos de embalagem
        tipo_embalagem_novo = payload.get("tipo_embalagem_novo")
        if tipo_embalagem_novo in ("", None):
            tipo_embalagem_novo = None
        
        unidades_por_embalagem = payload.get("unidades_por_embalagem")
        if unidades_por_embalagem in ("", None):
            unidades_por_embalagem = None
        else:
            try:
                unidades_por_embalagem = float(unidades_por_embalagem)
            except (TypeError, ValueError):
                unidades_por_embalagem = None
        
        estoque_embalagens = payload.get("estoque_embalagens", 0)
        try:
            estoque_embalagens = float(estoque_embalagens)
        except (TypeError, ValueError):
            estoque_embalagens = 0
        
        estoque_unidades_soltas = payload.get("estoque_unidades_soltas", 0)
        try:
            estoque_unidades_soltas = float(estoque_unidades_soltas)
        except (TypeError, ValueError):
            estoque_unidades_soltas = 0

        preco_compra_unitario = _coerce_price_value(payload.get("preco_compra_unitario"))
        preco_reposicao_unitario = _coerce_price_value(payload.get("preco_reposicao_unitario"))

        item = Item(
            codigo_item=codigo,
            descricao=payload.get("descricao", ""),
            unidade=(payload.get("unidade") or "Unidade"),
            localizacao=payload.get("localizacao"),
            marca=payload.get("marca"),
            nota_fiscal=payload.get("nota_fiscal"),
            categoria=payload.get("categoria", "Material Elétrico"),
            setor=payload.get("categoria", "Material Elétrico"),
            numero_serie=payload.get("numero_serie"),
            modelo=payload.get("modelo"),
            # Novos campos de rastreabilidade
            data_entrada=data_entrada,
            lote=lote,
            data_fabricacao=data_fabricacao,
            data_validade=data_validade,
            tipo_embalagem=payload.get("tipo_embalagem"),
            grandeza_referencia=grandeza_referencia,
            litros_por_embalagem=litros_por_embalagem,
            # Sistema de embalagens
            tipo_embalagem_novo=tipo_embalagem_novo,
            unidades_por_embalagem=unidades_por_embalagem,
            estoque_embalagens=estoque_embalagens,
            estoque_unidades_soltas=estoque_unidades_soltas,
            # Campos de Equipamento
            voltagem=payload.get("voltagem"),
            amperagem=payload.get("amperagem"),
            local_instalacao=payload.get("local_instalacao"),
            # Foto do item
            foto_path=payload.get("foto_path"),
            # Financeiro
            preco_compra_unitario=preco_compra_unitario,
            preco_compra_fonte=payload.get("preco_compra_fonte"),
            preco_compra_documento=payload.get("preco_compra_documento"),
            preco_compra_chave_acesso=payload.get("preco_compra_chave_acesso"),
            preco_compra_data_emissao=data_emissao if payload.get("preco_compra_data_emissao") else None,
            preco_compra_data_recebimento=data_recebimento if payload.get("preco_compra_data_recebimento") else None,
            preco_compra_atualizado_em=payload.get("preco_compra_atualizado_em"),
            preco_compra_atualizado_por=payload.get("preco_compra_atualizado_por"),
            preco_reposicao_unitario=preco_reposicao_unitario,
            preco_reposicao_fonte=payload.get("preco_reposicao_fonte"),
            preco_reposicao_uf=payload.get("preco_reposicao_uf"),
            preco_reposicao_query=payload.get("preco_reposicao_query"),
            preco_reposicao_url=payload.get("preco_reposicao_url"),
            preco_reposicao_atualizado_em=payload.get("preco_reposicao_atualizado_em"),
            preco_reposicao_atualizado_por=payload.get("preco_reposicao_atualizado_por"),
            pre_cadastro_pendente=bool(payload.get("pre_cadastro_pendente", False)),
            pre_cadastro_origem=payload.get("pre_cadastro_origem"),
            pre_cadastro_documento_item_id=payload.get("pre_cadastro_documento_item_id"),
            pre_cadastro_criado_em=payload.get("pre_cadastro_criado_em"),
            pre_cadastro_finalizado_em=payload.get("pre_cadastro_finalizado_em"),
        )
        item.estoque_minimo = 0
        _assign_normalized_item_price(
            item,
            raw_price=preco_compra_unitario,
            kind="compra",
            price_unit=payload.get("preco_compra_unidade_preco"),
        )
        _assign_normalized_item_price(
            item,
            raw_price=preco_reposicao_unitario,
            kind="reposicao",
            price_unit=payload.get("preco_reposicao_unidade_preco"),
        )
        db.session.add(item)
        try:
            if "advanced_unit_settings" in payload:
                _apply_advanced_unit_settings(item, payload.get("advanced_unit_settings"))
                _assign_normalized_item_price(
                    item,
                    raw_price=item.preco_compra_unitario,
                    kind="compra",
                    price_unit=payload.get("preco_compra_unidade_preco"),
                )
                _assign_normalized_item_price(
                    item,
                    raw_price=item.preco_reposicao_unitario,
                    kind="reposicao",
                    price_unit=payload.get("preco_reposicao_unidade_preco"),
                )
            db.session.commit()
            
            # Gerar código de barras após salvar
            try:
                barcode_path = generate_barcode(codigo, item.descricao)
                item.barcode_image_path = barcode_path
                db.session.commit()
            except Exception as barcode_error:
                # Se falhar ao gerar barcode, apenas logar mas não reverter o item
                print(f"Aviso: Não foi possível gerar barcode para {codigo}: {barcode_error}")
                
        except IntegrityError as exc:
            db.session.rollback()
            raise ValueError("Não foi possível cadastrar o item") from exc
        return codigo

    def update_item(self, codigo: str, payload: dict[str, Any]) -> str:
        item = Item.query.get(codigo)
        if not item:
            raise ValueError("Item não encontrado")

        novo_codigo = _sanitize_codigo(payload.get("codigo") or codigo)
        if not novo_codigo:
            raise ValueError("Código do item é obrigatório")
        if novo_codigo != codigo and Item.query.get(novo_codigo):
            raise ValueError("Código já cadastrado")

        if novo_codigo != codigo:
            raise ValueError("Não é permitido alterar o código do item após criado. Crie um novo item.")

        item.descricao = payload.get("descricao", item.descricao)
        item.localizacao = payload.get("localizacao", item.localizacao)
        item.nota_fiscal = payload.get("nota_fiscal", item.nota_fiscal)
        categoria = payload.get("categoria")
        if categoria:
            item.categoria = categoria
            item.setor = categoria
        unidade = payload.get("unidade")
        if unidade:
            item.unidade = unidade
        marca = payload.get("marca")
        if marca is not None:
            item.marca = marca

        # Novos campos
        numero_serie = payload.get("numero_serie")
        if "numero_serie" in payload:  # Sempre atualizar se estiver no payload
            item.numero_serie = numero_serie
        modelo = payload.get("modelo")
        if "modelo" in payload:  # Sempre atualizar se estiver no payload
            item.modelo = modelo
        
        # Campos de rastreabilidade (data_entrada blindada; lote pode ser manual)
        data_entrada = payload.get("data_entrada")
        if data_entrada is not None:
            if isinstance(data_entrada, str):
                try:
                    item.data_entrada = datetime.strptime(data_entrada, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif isinstance(data_entrada, date):
                item.data_entrada = data_entrada
        elif item.data_entrada is None:
            item.data_entrada = datetime.now().date()

        auto_lote = bool(payload.get("gerar_lote_automatico"))
        lote_manual = (payload.get("lote") or "").strip() or None
        # Lote é write-once: só pode ser preenchido se estiver vazio.
        if not (item.lote or "").strip():
            if lote_manual:
                item.lote = lote_manual
            elif auto_lote and item.data_entrada:
                item.lote = generate_lote(datetime.combine(item.data_entrada, datetime.min.time()))
        
        data_fabricacao = payload.get("data_fabricacao")
        if data_fabricacao is not None:
            if isinstance(data_fabricacao, str):
                try:
                    item.data_fabricacao = datetime.strptime(data_fabricacao, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif isinstance(data_fabricacao, date):
                item.data_fabricacao = data_fabricacao
        
        data_validade = payload.get("data_validade")
        # data_validade é write-once: só pode ser preenchida se estiver nula.
        if item.data_validade is None and data_validade is not None:
            if isinstance(data_validade, str):
                try:
                    item.data_validade = datetime.strptime(data_validade, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif isinstance(data_validade, date):
                item.data_validade = data_validade
        
        tipo_embalagem = payload.get("tipo_embalagem")
        if tipo_embalagem is not None:
            item.tipo_embalagem = tipo_embalagem
        
        # Campos numéricos (suportar "limpar" quando o formulário troca de grandeza)
        if "grandeza_referencia" in payload:
            grandeza_referencia = payload.get("grandeza_referencia")
            if grandeza_referencia in (None, ""):
                item.grandeza_referencia = None
            else:
                try:
                    item.grandeza_referencia = float(grandeza_referencia)
                except (ValueError, TypeError):
                    pass

        if "litros_por_embalagem" in payload:
            litros_por_embalagem = payload.get("litros_por_embalagem")
            if litros_por_embalagem in (None, ""):
                item.litros_por_embalagem = None
            else:
                try:
                    item.litros_por_embalagem = float(litros_por_embalagem)
                except (ValueError, TypeError):
                    pass
        
        # Novos campos de embalagem
        tipo_embalagem_novo = payload.get("tipo_embalagem_novo")
        if tipo_embalagem_novo is not None:
            item.tipo_embalagem_novo = tipo_embalagem_novo if tipo_embalagem_novo else None
        
        if "unidades_por_embalagem" in payload:
            unidades_por_embalagem = payload.get("unidades_por_embalagem")
            if unidades_por_embalagem in (None, ""):
                item.unidades_por_embalagem = None
            else:
                try:
                    item.unidades_por_embalagem = float(unidades_por_embalagem)
                except (ValueError, TypeError):
                    item.unidades_por_embalagem = None
        
        estoque_embalagens = payload.get("estoque_embalagens")
        if estoque_embalagens is not None:
            try:
                item.estoque_embalagens = float(estoque_embalagens)
            except (ValueError, TypeError):
                item.estoque_embalagens = 0
        
        estoque_unidades_soltas = payload.get("estoque_unidades_soltas")
        if estoque_unidades_soltas is not None:
            try:
                item.estoque_unidades_soltas = float(estoque_unidades_soltas)
            except (ValueError, TypeError):
                item.estoque_unidades_soltas = 0
        
        # Histórico de Edição
        if "ultima_edicao_em" in payload:
            item.ultima_edicao_em = payload["ultima_edicao_em"]
        if "ultima_edicao_por" in payload:
            item.ultima_edicao_por = payload["ultima_edicao_por"]

        # Campos de Equipamento
        print(f"DEBUG - UPDATE SERVICE - Campos equipamento: voltagem={payload.get('voltagem')}, amperagem={payload.get('amperagem')}, local_instalacao={payload.get('local_instalacao')}")
        if "voltagem" in payload:
            item.voltagem = payload["voltagem"]
        if "amperagem" in payload:
            item.amperagem = payload["amperagem"]
        if "local_instalacao" in payload:
            item.local_instalacao = payload["local_instalacao"]

        # Foto do item
        if "foto_path" in payload:
            item.foto_path = payload["foto_path"]

        if "advanced_unit_settings" in payload:
            _apply_advanced_unit_settings(item, payload.get("advanced_unit_settings"))

        if "pre_cadastro_pendente" in payload:
            item.pre_cadastro_pendente = bool(payload.get("pre_cadastro_pendente"))
        if "pre_cadastro_origem" in payload:
            item.pre_cadastro_origem = payload.get("pre_cadastro_origem") or None
        if "pre_cadastro_documento_item_id" in payload:
            raw_documento_item_id = payload.get("pre_cadastro_documento_item_id")
            try:
                item.pre_cadastro_documento_item_id = int(raw_documento_item_id) if raw_documento_item_id not in (None, "") else None
            except (TypeError, ValueError):
                item.pre_cadastro_documento_item_id = None
        if "pre_cadastro_criado_em" in payload:
            item.pre_cadastro_criado_em = payload.get("pre_cadastro_criado_em")
        if "pre_cadastro_finalizado_em" in payload:
            item.pre_cadastro_finalizado_em = payload.get("pre_cadastro_finalizado_em")

        # Financeiro
        compra_keys = {
            "preco_compra_unitario",
            "preco_compra_unidade_preco",
            "preco_compra_fonte",
            "preco_compra_documento",
            "preco_compra_chave_acesso",
            "preco_compra_data_emissao",
            "preco_compra_data_recebimento",
        }
        if any(k in payload for k in compra_keys):
            if "preco_compra_unitario" in payload or "preco_compra_unidade_preco" in payload:
                _assign_normalized_item_price(
                    item,
                    raw_price=payload.get("preco_compra_unitario", item.preco_compra_unitario),
                    kind="compra",
                    price_unit=payload.get("preco_compra_unidade_preco"),
                )
            if "preco_compra_fonte" in payload:
                item.preco_compra_fonte = payload.get("preco_compra_fonte") or None
            if "preco_compra_documento" in payload:
                item.preco_compra_documento = payload.get("preco_compra_documento") or None
            if "preco_compra_chave_acesso" in payload:
                item.preco_compra_chave_acesso = payload.get("preco_compra_chave_acesso") or None
            if "preco_compra_data_emissao" in payload:
                raw_emissao = payload.get("preco_compra_data_emissao")
                if raw_emissao in (None, ""):
                    item.preco_compra_data_emissao = None
                elif isinstance(raw_emissao, str):
                    try:
                        item.preco_compra_data_emissao = datetime.strptime(raw_emissao, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                elif isinstance(raw_emissao, date):
                    item.preco_compra_data_emissao = raw_emissao
            if "preco_compra_data_recebimento" in payload:
                raw_recebimento = payload.get("preco_compra_data_recebimento")
                if raw_recebimento in (None, ""):
                    item.preco_compra_data_recebimento = None
                elif isinstance(raw_recebimento, str):
                    try:
                        item.preco_compra_data_recebimento = datetime.strptime(raw_recebimento, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                elif isinstance(raw_recebimento, date):
                    item.preco_compra_data_recebimento = raw_recebimento
            item.preco_compra_atualizado_em = payload.get("preco_compra_atualizado_em") or datetime.utcnow()
            item.preco_compra_atualizado_por = payload.get("preco_compra_atualizado_por") or payload.get("ultima_edicao_por")

        repos_keys = {
            "preco_reposicao_unitario",
            "preco_reposicao_unidade_preco",
            "preco_reposicao_fonte",
            "preco_reposicao_uf",
            "preco_reposicao_query",
            "preco_reposicao_url",
        }
        if any(k in payload for k in repos_keys):
            if "preco_reposicao_unitario" in payload or "preco_reposicao_unidade_preco" in payload:
                _assign_normalized_item_price(
                    item,
                    raw_price=payload.get("preco_reposicao_unitario", item.preco_reposicao_unitario),
                    kind="reposicao",
                    price_unit=payload.get("preco_reposicao_unidade_preco"),
                )
            if "preco_reposicao_fonte" in payload:
                item.preco_reposicao_fonte = payload.get("preco_reposicao_fonte") or None
            if "preco_reposicao_uf" in payload:
                item.preco_reposicao_uf = payload.get("preco_reposicao_uf") or None
            if "preco_reposicao_query" in payload:
                item.preco_reposicao_query = payload.get("preco_reposicao_query") or None
            if "preco_reposicao_url" in payload:
                item.preco_reposicao_url = payload.get("preco_reposicao_url") or None
            item.preco_reposicao_atualizado_em = payload.get("preco_reposicao_atualizado_em") or datetime.utcnow()
            item.preco_reposicao_atualizado_por = payload.get("preco_reposicao_atualizado_por") or payload.get("ultima_edicao_por")

        normalization_keys = {
            "unidade",
            "tipo_embalagem_novo",
            "unidades_por_embalagem",
            "grandeza_referencia",
            "litros_por_embalagem",
            "advanced_unit_settings",
        }
        if any(key in payload for key in normalization_keys):
            _assign_normalized_item_price(item, raw_price=item.preco_compra_unitario, kind="compra")
            _assign_normalized_item_price(item, raw_price=item.preco_reposicao_unitario, kind="reposicao")

        # Regenerar barcode se descrição mudou
        if payload.get("descricao") and item.descricao:
            try:
                barcode_path = generate_barcode(novo_codigo, item.descricao)
                item.barcode_image_path = barcode_path
            except Exception as barcode_error:
                print(f"Aviso: Não foi possível gerar barcode para {novo_codigo}: {barcode_error}")

        db.session.commit()
        return novo_codigo
        
    def delete_item(self, codigo: str) -> None:
        item = Item.query.get(codigo)
        if not item:
            raise ValueError("Item não encontrado")

        saidas_ids = [s.id_saida for s in Saida.query.filter_by(codigo_item=codigo).all()]
        entradas_ids = [e.id_entrada for e in Entrada.query.filter_by(codigo_item=codigo).all()]
        documento_ids = [
            row[0]
            for row in db.session.query(DocumentoEntradaEstoqueItem.documento_id)
            .filter(DocumentoEntradaEstoqueItem.codigo_item == codigo)
            .distinct()
            .all()
        ]

        if saidas_ids:
            TelegramOutbox.query.filter(TelegramOutbox.saida_id.in_(saidas_ids)).delete(
                synchronize_session=False
            )
            MaterialInventario.query.filter(MaterialInventario.saida_id.in_(saidas_ids)).delete(
                synchronize_session=False
            )

        if entradas_ids:
            TelegramOutbox.query.filter(TelegramOutbox.entrada_id.in_(entradas_ids)).delete(
                synchronize_session=False
            )

        FinanceSupplierPreference.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )
        FinanceLedgerEntry.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )
        DocumentoEntradaEstoqueItem.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )
        RetiradaFerramenta.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )
        EquipamentoReparo.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )

        if documento_ids:
            documentos_vazios = [
                documento_id
                for documento_id in documento_ids
                if not db.session.query(DocumentoEntradaEstoqueItem.id_documento_item)
                .filter(DocumentoEntradaEstoqueItem.documento_id == documento_id)
                .first()
            ]
            if documentos_vazios:
                DocumentoEntradaEstoque.query.filter(
                    DocumentoEntradaEstoque.id_documento.in_(documentos_vazios)
                ).delete(synchronize_session=False)

        # Agora pode excluir o item (cascade vai excluir saídas e entradas)
        db.session.delete(item)
        db.session.commit()
        

    def registrar_entrada(self, payload: MovimentoPayload, skip_notification: bool = False) -> Any:
        """Registra uma entrada de estoque.
        
        Args:
            payload: Dados da movimentação
            skip_notification: Se True, não envia notificação de entrada (usado quando notificação unificada já foi enviada)
            
        Returns:
            Objeto Entrada criado
        """
        return self._registrar_movimento(payload, is_entrada=True, skip_notification=skip_notification)

    def registrar_saida(self, payload: MovimentoPayload, *, skip_notification: bool = False) -> int:
        """Registra uma saída de estoque.
        
        Returns:
            ID da saída criada
        """
        movimento = self._registrar_movimento(payload, is_entrada=False, skip_notification=skip_notification)
        return getattr(movimento, 'id_saida', 0)

    def resumo_estoque(self) -> list[dict[str, Any]]:
        itens = Item.query.order_by(Item.setor, Item.descricao).all()
        resumo: list[dict[str, Any]] = []
        atualizado = False
        from ..services.embalagem_service import EmbalagemService
        for item in itens:
            try:
                saldo = float(item.get_saldo_fisico_total() or 0.0)
            except Exception:
                if EmbalagemService.tem_embalagem(item):
                    try:
                        saldo = float(EmbalagemService.calcular_estoque_total(item) or 0)
                    except Exception:
                        saldo = 0.0
                else:
                    saldo = float(item.get_saldo_atual() or 0.0)
            minimo = _calculate_min_stock(saldo)
            if item.estoque_minimo != minimo:
                item.estoque_minimo = minimo
                atualizado = True
            resumo.append(
                {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "setor": item.setor,
                    "marca": item.marca,
                    "estoque_minimo": minimo,
                    "saldo": saldo,
                    "status": "OK" if saldo > minimo else "Estoque baixo",
                }
            )
        if atualizado:
            db.session.commit()
        return resumo

    def dashboard_snapshot(self) -> dict[str, Any]:
        cached = self._get_cached("dashboard_snapshot")
        if cached is not None:
            return dict(cached)

        from ..services.embalagem_service import EmbalagemService

        def _normalize_unidade(value: str | None) -> str:
            return (value or "").strip().lower()

        def _is_unit(unidade: str | None) -> bool:
            u = _normalize_unidade(unidade)
            return u in ("un", "und", "unid", "unidade", "unidades")

        itens = Item.query.order_by(Item.setor, Item.descricao).all()
        resumo: list[dict[str, Any]] = []
        categorias: dict[str, dict[str, Any]] = {}
        total_quantity = 0.0
        atualizado = False
        bulk_balances = self._resolve_balances_in_bulk(itens)

        for item in itens:
            tem_embalagem = EmbalagemService.tem_embalagem(item)
            if tem_embalagem:
                try:
                    saldo_fisico = float(item.get_saldo_fisico_total() or 0.0)
                except Exception:
                    db.session.rollback()
                    try:
                        saldo_fisico = float(EmbalagemService.calcular_estoque_total(item) or 0.0)
                    except Exception:
                        saldo_fisico = float(item.get_estoque_total_com_embalagens() or 0.0)
            else:
                saldo_fisico = float(bulk_balances.get(item.codigo_item, 0.0))

            minimo = _calculate_min_stock(saldo_fisico)
            if item.estoque_minimo != minimo:
                item.estoque_minimo = minimo
                atualizado = True

            resumo.append(
                {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "setor": item.setor,
                    "marca": item.marca,
                    "estoque_minimo": minimo,
                    "saldo": saldo_fisico,
                    "status": "OK" if saldo_fisico > minimo else "Estoque baixo",
                }
            )

            saldo_categoria = float(item.estoque_embalagens or 0) if tem_embalagem else saldo_fisico
            total_quantity += float(item.estoque_embalagens or 0) if tem_embalagem else saldo_fisico

            categoria = item.categoria or "Sem categoria"
            categoria_resumo = categorias.setdefault(
                categoria,
                {
                    "categoria": categoria,
                    "total_itens": 0,
                    "saldo_total": 0.0,
                },
            )
            categoria_resumo["total_itens"] += 1
            if _is_unit(item.unidade):
                categoria_resumo["saldo_total"] += round(saldo_categoria)
            else:
                categoria_resumo["saldo_total"] += round(saldo_categoria, 1)

        if atualizado:
            db.session.commit()

        for categoria_resumo in categorias.values():
            categoria_resumo["saldo_total"] = round(categoria_resumo["saldo_total"], 1)

        snapshot = {
            "resumo": resumo,
            "total_quantity": int(round(total_quantity)),
            "category_summary": list(categorias.values()),
        }
        return self._set_cached("dashboard_snapshot", dict(snapshot), ttl_seconds=5.0)

    def list_notas_fiscais(self, limit: int = 100) -> list[dict[str, Any]]:
        cache_key = f"list_notas_fiscais:{int(limit)}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]

        from .finance_service import finance_service

        documentos = finance_service.list_stock_documents(limit=limit)
        registros = (
            Entrada.query.filter(Entrada.nota_fiscal.isnot(None))
            .order_by(Entrada.data_entrada.desc())
            .limit(max(limit * 5, limit))
            .all()
        )
        agrupadas = _agrupar_notas(registros)
        notas_por_numero: dict[str, dict[str, Any]] = {}

        for documento in documentos:
            numero = str(documento.get("numero_documento") or documento.get("nota_fiscal") or "").strip()
            if numero:
                notas_por_numero[numero] = documento

        for numero, nota_legada in agrupadas.items():
            if numero not in notas_por_numero:
                notas_por_numero[numero] = nota_legada

        notas = sorted(
            notas_por_numero.values(),
            key=lambda nota: nota.get("data") or datetime.min,
            reverse=True,
        )
        payload = notas[:limit]
        return self._set_cached(cache_key, [dict(item) for item in payload], ttl_seconds=8.0)

    def get_nota_fiscal(self, numero: str) -> dict[str, Any] | None:
        from .finance_service import finance_service

        numero = (numero or "").strip()
        if not numero:
            return None
        cache_key = f"get_nota_fiscal:{numero}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return dict(cached)

        documento = finance_service.get_stock_document_by_number(numero)
        if documento:
            return self._set_cached(cache_key, dict(documento), ttl_seconds=8.0)

        registros = (
            Entrada.query.filter(Entrada.nota_fiscal == numero)
            .order_by(Entrada.data_entrada.desc())
            .all()
        )
        if not registros:
            return None
        notas = _agrupar_notas(registros)
        nota = notas.get(numero)
        if nota is None:
            return None
        return self._set_cached(cache_key, dict(nota), ttl_seconds=8.0)

    def registrar_nota_fiscal(self, payload: MovimentoPayload) -> None:
        if not payload.nota_fiscal:
            raise ValueError("Informe a nota fiscal")
        self.registrar_entrada(payload)

    def list_entradas(self, limit: int = 100) -> list[dict[str, Any]]:
        registros = (
            Entrada.query.order_by(Entrada.data_entrada.desc()).limit(limit).all()
        )
        resultado: list[dict[str, Any]] = []
        for entrada in registros:
            resultado.append(
                {
                    "id": entrada.id_entrada,
                    "codigo": entrada.codigo_item,
                    "descricao": entrada.item.descricao if entrada.item else "",
                    "quantidade": entrada.quantidade,
                    "nota_fiscal": entrada.nota_fiscal,
                    "data": entrada.data_entrada,
                    "usuario": entrada.usuario.nome if entrada.usuario else entrada.matricula,
                    "matricula": entrada.usuario.matricula if entrada.usuario else entrada.matricula,
                    "categoria": entrada.item.categoria if entrada.item else None,
                }
            )
        return resultado

    def list_saidas(self, limit: int = 100) -> list[dict[str, Any]]:
        registros = Saida.query.order_by(Saida.data_saida.desc()).limit(limit).all()
        resultado: list[dict[str, Any]] = []
        for saida in registros:
            resultado.append(
                {
                    "id": saida.id_saida,
                    "codigo": saida.codigo_item,
                    "descricao": saida.item.descricao if saida.item else "",
                    "quantidade": saida.quantidade,
                    "data": saida.data_saida,
                    "observacao": saida.observacao,
                    "usuario": saida.usuario.nome if saida.usuario else saida.matricula,
                    "matricula": saida.usuario.matricula if saida.usuario else saida.matricula,
                    "tipo_produto": saida.tipo_produto,
                    "densidade_aplicada": saida.densidade_aplicada,
                    "fracao_numerador": saida.fracao_numerador,
                    "fracao_denominador": saida.fracao_denominador,
                    "quantidade_total_embalagem": saida.quantidade_total_embalagem,
                    "quantidade_retirada_em_litros": saida.quantidade_retirada_em_litros,
                    "quantidade_retirada_em_quilos": saida.quantidade_retirada_em_quilos,
                    "quantidade_restante": saida.quantidade_restante,
                    "usou_fracao": bool(saida.usou_fracao),
                    "atividade_operacional": getattr(saida, "atividade_operacional", None),
                    "ordem_servico": getattr(saida, "ordem_servico", None),
                    "centro_custo": getattr(saida, "centro_custo", None),
                }
            )
        return resultado

    def list_saidas_fracionadas(self, limit: int = 200) -> list[dict[str, Any]]:
        registros = (
            Saida.query.filter(
                or_(Saida.usou_fracao.is_(True), Saida.fracao_denominador.isnot(None))
            )
            .order_by(Saida.data_saida.desc())
            .limit(limit)
            .all()
        )
        resultado: list[dict[str, Any]] = []
        for saida in registros:
            resultado.append(
                {
                    "id": saida.id_saida,
                    "codigo": saida.codigo_item,
                    "descricao": saida.item.descricao if saida.item else "",
                    "quantidade": saida.quantidade,
                    "data": saida.data_saida,
                    "observacao": saida.observacao,
                    "usuario": saida.usuario.nome if saida.usuario else saida.matricula,
                    "matricula": saida.usuario.matricula if saida.usuario else saida.matricula,
                    "tipo_produto": saida.tipo_produto,
                    "densidade_aplicada": saida.densidade_aplicada,
                    "fracao_numerador": saida.fracao_numerador,
                    "fracao_denominador": saida.fracao_denominador,
                    "quantidade_total_embalagem": saida.quantidade_total_embalagem,
                    "quantidade_retirada_em_litros": saida.quantidade_retirada_em_litros,
                    "quantidade_retirada_em_quilos": saida.quantidade_retirada_em_quilos,
                    "quantidade_restante": saida.quantidade_restante,
                    "usou_fracao": bool(saida.usou_fracao),
                    "atividade_operacional": getattr(saida, "atividade_operacional", None),
                    "ordem_servico": getattr(saida, "ordem_servico", None),
                    "centro_custo": getattr(saida, "centro_custo", None),
                }
            )
        return resultado

    def list_saidas_por_usuario(
        self,
        matricula: str,
        *,
        limit: int | None = 200,
        data_inicial: datetime | None = None,
        data_final: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Retorna as saídas vinculadas a um usuário específico."""
        matricula = (matricula or "").strip()
        if not matricula:
            return []

        consulta = Saida.query.filter(Saida.matricula == matricula).order_by(Saida.data_saida.desc())
        if data_inicial:
            consulta = consulta.filter(Saida.data_saida >= data_inicial)
        if data_final:
            consulta = consulta.filter(Saida.data_saida <= data_final)
        if limit is not None:
            consulta = consulta.limit(limit)

        registros = consulta.all()
        historico: list[dict[str, Any]] = []
        for saida in registros:
            historico.append(
                {
                    "id": saida.id_saida,
                    "codigo": saida.codigo_item,
                    "descricao": saida.item.descricao if saida.item else "",
                    "quantidade": saida.quantidade,
                    "data": saida.data_saida,
                    "observacao": saida.observacao,
                    "usuario": saida.usuario.nome if saida.usuario else saida.matricula,
                    "matricula": saida.matricula,
                    "atividade_operacional": getattr(saida, "atividade_operacional", None),
                    "ordem_servico": getattr(saida, "ordem_servico", None),
                    "centro_custo": getattr(saida, "centro_custo", None),
                }
            )
        return historico

    def list_movements_feed(self, limit: int = 100) -> list[dict[str, Any]]:
        entradas = self.list_entradas(limit=limit)
        saidas = self.list_saidas(limit=limit)
        feed = [
            {
                "tipo": "Entrada",
                **entrada,
            }
            for entrada in entradas
        ]
        feed.extend(
            {
                "tipo": "Saída",
                **saida,
            }
            for saida in saidas
        )
        feed.sort(key=lambda registro: registro.get("data") or datetime.min, reverse=True)
        return feed[:limit]

    def list_item_movements(self, codigo: str, limit: int = 20) -> list[dict[str, Any]]:
        codigo_norm = (codigo or "").strip()
        if not codigo_norm:
            return []

        entradas = (
            Entrada.query
            .filter(Entrada.codigo_item == codigo_norm)
            .order_by(Entrada.data_entrada.desc())
            .limit(limit)
            .all()
        )
        saidas = (
            Saida.query
            .filter(Saida.codigo_item == codigo_norm)
            .order_by(Saida.data_saida.desc())
            .limit(limit)
            .all()
        )

        movimentos: list[dict[str, Any]] = []

        for entrada in entradas:
            movimentos.append(
                {
                    "id": entrada.id_entrada,
                    "tipo": "Entrada",
                    "quantidade": float(entrada.quantidade or 0),
                    "data": entrada.data_entrada,
                    "responsavel": entrada.usuario.nome if entrada.usuario else (entrada.matricula or "-"),
                }
            )

        for saida in saidas:
            movimentos.append(
                {
                    "id": saida.id_saida,
                    "tipo": "Saída",
                    "quantidade": float(saida.quantidade or 0),
                    "data": saida.data_saida,
                    "responsavel": saida.usuario.nome if saida.usuario else (saida.matricula or "-"),
                }
            )

        movimentos.sort(key=lambda registro: registro.get("data") or datetime.min, reverse=True)
        return movimentos[:limit]

    def total_quantity(self) -> int:
        from ..services.embalagem_service import EmbalagemService

        total = 0.0
        for item in Item.query.all():
            if EmbalagemService.tem_embalagem(item):
                total += float(item.estoque_embalagens or 0)
            else:
                total += float(item.get_saldo_atual() or 0)
        return int(round(total))

    def total_quantity_internal(self) -> int:
        from ..services.embalagem_service import EmbalagemService

        total = 0.0
        for item in Item.query.all():
            if EmbalagemService.tem_embalagem(item):
                total += float(item.get_saldo_fisico_total() or 0)
            else:
                total += float(item.get_saldo_atual() or 0)
        return int(round(total))

    def category_summary(self) -> list[dict[str, Any]]:
        from ..services.embalagem_service import EmbalagemService

        def _normalize_unidade(value: str | None) -> str:
            return (value or "").strip().lower()

        def _is_unit(unidade: str | None) -> bool:
            u = _normalize_unidade(unidade)
            return u in ("un", "und", "unid", "unidade", "unidades")

        categorias: dict[str, dict[str, Any]] = {}
        for item in Item.query.order_by(Item.categoria, Item.descricao).all():
            categoria = item.categoria or "Sem categoria"
            resumo = categorias.setdefault(
                categoria,
                {
                    "categoria": categoria,
                    "total_itens": 0,
                    "saldo_total": 0.0,
                },
            )
            resumo["total_itens"] += 1
            if EmbalagemService.tem_embalagem(item):
                saldo = float(item.estoque_embalagens or 0)
            else:
                saldo = float(item.get_saldo_atual() or 0)
            
            # Se for unidade, soma como inteiro; senão, soma normalmente mas arredonda
            if _is_unit(item.unidade):
                resumo["saldo_total"] += round(saldo)
            else:
                resumo["saldo_total"] += round(saldo, 1)
        
        # Arredondar todos os totais para eliminar problemas de float
        for resumo in categorias.values():
            resumo["saldo_total"] = round(resumo["saldo_total"], 1)
        
        return list(categorias.values())

    def adjust_item_balance(
        self,
        *,
        codigo: str,
        novo_saldo: float,
        matricula: str,
        nota_fiscal: str | None = None,
        tipo: str | None = None,
        descricao: str | None = None,
    ) -> None:
        if novo_saldo < 0:
            raise ValueError("Saldo não pode ser negativo")
        item = Item.query.get(codigo)
        if not item:
            raise ValueError("Item não encontrado")
        saldo_atual = item.get_saldo_atual()
        delta = novo_saldo - saldo_atual
        if delta == 0:
            return

        descricao_base = "Ajuste manual de estoque"
        if saldo_atual == 0:
            descricao_base = "Saldo inicial configurado"

        descricao_final = descricao or descricao_base
        tipo_final = tipo or "ajuste_estoque"

        descricao_evento = f"{descricao_final}: de {saldo_atual} para {novo_saldo}"
        if nota_fiscal:
            descricao_evento = f"{descricao_evento} (NF: {nota_fiscal})"

        # Evitar eventos duplicados na mesma janela de tempo.
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=60)
            existe_duplicado = (
                InventarioEvento.query
                .filter(InventarioEvento.codigo_item == codigo)
                .filter(InventarioEvento.matricula == matricula)
                .filter(InventarioEvento.tipo == tipo_final)
                .filter(InventarioEvento.descricao == descricao_evento)
                .filter(InventarioEvento.data_evento >= cutoff)
                .first()
            )
            if existe_duplicado:
                return
        except Exception:
            pass

        payload = MovimentoPayload(
            codigo=codigo,
            quantidade=abs(float(delta)),
            matricula=matricula,
            nota_fiscal=nota_fiscal,
            observacao=descricao_evento,
        )
        ledger_result = self._mirror_payload_to_ledger(
            item=item,
            payload=payload,
            movement_type="ajuste",
            quantity=float(delta),
            metadata={
                "reference_type": "inventario_evento",
                "legacy_event_type": tipo_final,
                "legacy_description": descricao_evento,
            },
        )

        evento = InventarioEvento(
            codigo_item=codigo,
            matricula=matricula,
            tipo=tipo_final,
            quantidade=delta,
            descricao=descricao_evento,
        )

        db.session.add(evento)
        item.estoque_minimo = _calculate_min_stock(novo_saldo)
        
        db.session.commit()
        if ledger_result is not None:
            inventory_engine.record_operation_audit(ledger_result)
            operation_log_service.notify_telegram(ledger_result.operation_log_id)

    def report_low_stock(self) -> list[dict[str, Any]]:
        return [item for item in self.resumo_estoque() if item["saldo"] <= item["estoque_minimo"]]

    def report_inventory_events(self, tipo: str, limit: int = 500) -> list[dict[str, Any]]:
        tipo = (tipo or "").strip().lower()
        if not tipo:
            return []
        registros = (
            InventarioEvento.query.filter(InventarioEvento.tipo.ilike(f"%{tipo}%"))
            .order_by(InventarioEvento.data_evento.desc())
            .limit(limit)
            .all()
        )
        resultado: list[dict[str, Any]] = []
        for evento in registros:
            resultado.append(
                {
                    "data": evento.data_evento,
                    "codigo": evento.codigo_item,
                    "tipo": evento.tipo,
                    "quantidade": evento.quantidade,
                    "responsavel": evento.matricula,
                    "descricao": evento.descricao,
                }
            )
        return resultado

    def generate_report_csv(self, tipo: str) -> tuple[str, list[str], list[list[Any]]]:
        """Gera os dados para um relatório em formato CSV."""
        tipo = (tipo or "").strip().lower()
        if tipo == "falta":
            dados = self.report_low_stock()
            headers = ["codigo", "descricao", "setor", "saldo", "estoque_minimo"]
            rows = [[item.get(h, "") for h in headers] for item in dados]
            return "produtos-em-falta", headers, rows
        if tipo in {"perda", "perdas"}:
            dados = self.report_inventory_events("perda")
            headers = ["data", "codigo", "tipo", "quantidade", "responsavel", "descricao"]
            rows = [[
                registro["data"].isoformat() if registro.get("data") else "",
                registro.get("codigo", ""),
                registro.get("tipo", ""),
                registro.get("quantidade", 0),
                registro.get("responsavel", ""),
                registro.get("descricao", ""),
            ] for registro in dados]
            return "produtos-com-perda", headers, rows
        if tipo in {"avariado", "avariados", "avaria"}:
            dados = self.report_inventory_events("avari")
            headers = ["data", "codigo", "tipo", "quantidade", "responsavel", "descricao"]
            rows = [[
                registro["data"].isoformat() if registro.get("data") else "",
                registro.get("codigo", ""),
                registro.get("tipo", ""),
                registro.get("quantidade", 0),
                registro.get("responsavel", ""),
                registro.get("descricao", ""),
            ] for registro in dados]
            return "produtos-avariados", headers, rows
        raise ValueError("Tipo de relatório inválido")

    def _registrar_movimento(self, payload: MovimentoPayload, *, is_entrada: bool, skip_notification: bool = False) -> Any:
        """Registra uma movimentação de estoque (entrada ou saída).
        
        Returns:
            Objeto Entrada ou Saida criado
        """
        if payload.quantidade <= 0:
            raise ValueError("Quantidade precisa ser positiva")

        item = Item.query.get(payload.codigo)
        if not item:
            raise ValueError("Item não encontrado")

        if not is_entrada and bool(getattr(item, "pre_cadastro_pendente", False)):
            raise ValueError(PRE_CADASTRO_PENDING_EXIT_MESSAGE)

        categoria_text = (item.categoria or "").lower()
        if not is_entrada and "ferrament" in categoria_text:
            if self._has_active_tool_withdrawal(payload.codigo, payload.matricula):
                raise ValueError(
                    "Retirada bloqueada: este funcionário já possui esta ferramenta em aberto. "
                    "Faça a devolução antes de nova retirada."
                )

        # Verificar se o item usa sistema de embalagens
        from ..services.embalagem_service import EmbalagemService, embalagem_service
        tem_embalagem = embalagem_service.tem_embalagem(item)

        # Contexto de saldo para notificação (evita divergências de unidades no Telegram)
        telegram_balance_before: float | None = None
        telegram_balance_after: float | None = None
        telegram_balance_unit: str | None = None

        if not is_entrada:
            # Corrigir unidade quando confundida com tipo_embalagem_novo
            unidade_item = item.unidade or "un"
            tipo_emb = (item.tipo_embalagem_novo or "").lower().strip()
            
            # Se a unidade está igual ao tipo de embalagem, inferir a unidade correta
            if unidade_item.lower().strip() == tipo_emb:
                if tipo_emb == "rolo":
                    telegram_balance_unit = "metros"
                elif tipo_emb in ("lata", "balde", "bombona"):
                    # Para lata/balde/bombona, usar a unidade de referência (L ou KG)
                    if item.litros_por_embalagem and float(item.litros_por_embalagem) > 0:
                        telegram_balance_unit = "L"
                    elif item.grandeza_referencia and float(item.grandeza_referencia) > 0:
                        telegram_balance_unit = "KG"
                    else:
                        telegram_balance_unit = "un"
                elif tipo_emb in ("pacote", "caixa", "fardo"):
                    telegram_balance_unit = "un"
                elif tipo_emb == "litro":
                    telegram_balance_unit = "L"
                else:
                    telegram_balance_unit = "un"
            else:
                telegram_balance_unit = unidade_item
            
            if tem_embalagem and payload.em_embalagens is not None:
                try:
                    telegram_balance_before = float(EmbalagemService.calcular_estoque_total(item) or 0)
                except Exception:
                    telegram_balance_before = None
            else:
                try:
                    telegram_balance_before = float(item.get_saldo_atual() or 0)
                except Exception:
                    telegram_balance_before = None
        
        # Processar embalagens ANTES de verificar saldo ou criar movimento
        if tem_embalagem and payload.em_embalagens is not None:
            # Itens antigos podem ter saldo legado, mas estoque novo ainda não inicializado.
            # Sincroniza de forma conservadora antes de processar a operação.
            try:
                EmbalagemService.tentar_sincronizar_estoque_de_legacy(item)
            except Exception:
                pass

            if is_entrada:
                # Entrada/Devolução
                novas_emb, novas_soltas = embalagem_service.processar_entrada(
                    item, payload.quantidade, payload.em_embalagens
                )
                item.estoque_embalagens = novas_emb
                item.estoque_unidades_soltas = novas_soltas
            else:
                # Saída
                novas_emb, novas_soltas, sucesso = embalagem_service.processar_saida(
                    item, payload.quantidade, payload.em_embalagens
                )
                if not sucesso:
                    raise ValueError("Saldo insuficiente para a saída solicitada")
                item.estoque_embalagens = novas_emb
                item.estoque_unidades_soltas = novas_soltas

                # Saldo após a saída (em UNIDADES totais) para notificação
                try:
                    telegram_balance_after = float(EmbalagemService.calcular_estoque_total(item) or 0)
                except Exception:
                    telegram_balance_after = None

        # Validação de saldo para itens sem embalagem
        if not tem_embalagem and not is_entrada:
            saldo_atual = item.get_saldo_atual()
            if payload.quantidade > saldo_atual:
                raise ValueError("Saldo insuficiente para a saída solicitada")

        ledger_result = self._mirror_payload_to_ledger(
            item=item,
            payload=payload,
            movement_type="devolucao" if is_entrada and payload.is_devolucao else ("entrada" if is_entrada else "saida"),
            metadata={
                "reference_type": "legacy_movimento",
                "legacy_model": "Entrada" if is_entrada else "Saida",
            },
        )

        movimento_cls = Entrada if is_entrada else Saida
        movimento = movimento_cls(
            codigo_item=payload.codigo,
            matricula=payload.matricula,
            quantidade=payload.quantidade,
        )
        # Se o payload tiver observação e o modelo de movimento aceitar, persista-a
        if getattr(movimento.__class__, 'observacao', None) is not None and payload.observacao:
            try:
                movimento.observacao = payload.observacao
            except Exception:
                # Proteção genérica caso o mapeamento de coluna não exista em runtime
                pass
        if is_entrada:
            movimento.nota_fiscal = payload.nota_fiscal  # type: ignore[attr-defined]
        else:
            # Persistir metadados da operação fracionada quando aplicável
            if getattr(movimento.__class__, "usou_fracao", None) is not None:
                movimento.usou_fracao = bool(payload.modo_fracionado)
            if payload.modo_fracionado:
                for attr_name, value in (
                    ("tipo_produto", payload.tipo_produto),
                    ("densidade_aplicada", payload.densidade_aplicada),
                    ("fracao_numerador", payload.fracao_numerador),
                    ("fracao_denominador", payload.fracao_denominador),
                    ("quantidade_total_embalagem", payload.quantidade_total_embalagem),
                    ("quantidade_retirada_em_litros", payload.quantidade_retirada_em_litros),
                    ("quantidade_retirada_em_quilos", payload.quantidade_retirada_em_quilos),
                    ("quantidade_restante", payload.quantidade_restante),
                ):
                    if value is not None and hasattr(movimento, attr_name):
                        setattr(movimento, attr_name, value)
            
            # Persistir local_servico se for saída
            if not is_entrada and payload.local_servico and hasattr(movimento, "local_servico"):
                movimento.local_servico = payload.local_servico

            apply_operational_context(
                movimento,
                activity=payload.atividade_operacional,
                order=payload.ordem_servico,
                cost_center=payload.centro_custo,
            )
            
            # Persistir tipo_custodia se for saída
            if not is_entrada and hasattr(movimento, "tipo_custodia"):
                movimento.tipo_custodia = self._normalize_tipo_custodia(getattr(payload, "tipo_custodia", None))

        db.session.add(movimento)
        db.session.flush()
        if ledger_result is not None:
            movement_id = getattr(movimento, "id_entrada", None) if is_entrada else getattr(movimento, "id_saida", None)
            if movement_id is not None:
                ledger_result.metadata["reference_id"] = str(movement_id)
        db.session.refresh(item)
        saldo_atualizado = item.get_saldo_atual()
        item.estoque_minimo = _calculate_min_stock(saldo_atualizado)
        db.session.commit()
        if ledger_result is not None:
            inventory_engine.record_operation_audit(ledger_result)
            if not skip_notification:
                operation_log_service.notify_telegram(ledger_result.operation_log_id)
        
        # Verificar e gerar relatório automático a cada 1000 entradas (apenas para entradas)
        if is_entrada:
            try:
                from ..services.entrada_report_service import entrada_report_service
                entrada_report_service.check_e_gerar_relatorio()
            except Exception as e:
                # Não bloquear a operação por falha no relatório automático
                logger.warning(f"Erro ao verificar relatório automático de entradas: {e}")

        # Retornar o objeto movimento criado
        return movimento


inventory_service = InventoryService()


def _sanitize_codigo(codigo: str | None) -> str:
    if not codigo:
        return ""
    codigo = codigo.strip()
    if not codigo:
        return ""
    return codigo


def _calculate_min_stock(quantity: float) -> int:
    if quantity <= 0:
        return 0
    return max(1, math.ceil(quantity * 0.05))


def _append_usuario(nota: dict[str, Any], entrada: Entrada) -> None:
    usuarios: set[str] = nota.setdefault("usuarios", set())  # type: ignore[assignment]
    nome = (entrada.usuario.nome if entrada.usuario else entrada.matricula) or ""
    if nome:
        usuarios.add(nome)


def _normalizar_usuarios(nota: dict[str, Any]) -> None:
    raw = nota.get("usuarios")
    if isinstance(raw, set):
        nota["usuarios"] = sorted(raw)


def _agrupar_notas(registros: Iterable[Entrada]) -> dict[str, dict[str, Any]]:
    notas: dict[str, dict[str, Any]] = {}
    for entrada in registros:
        numero = (entrada.nota_fiscal or "").strip()
        if not numero:
            continue
        nota = notas.get(numero)
        if nota is None:
            nota = {
                "nota_fiscal": numero,
                "data": entrada.data_entrada,
                "itens": [],
                "total_itens": 0,
                "total_quantidade": 0,
                "usuarios": set(),
            }
            notas[numero] = nota
        else:
            data_atual = nota.get("data")
            if entrada.data_entrada and (data_atual is None or entrada.data_entrada > data_atual):
                nota["data"] = entrada.data_entrada
        item_info = {
            "id": entrada.id_entrada,
            "codigo": entrada.codigo_item,
            "descricao": entrada.item.descricao if entrada.item else "",
            "quantidade": entrada.quantidade,
        }
        nota["itens"].append(item_info)  # type: ignore[index]
        _append_usuario(nota, entrada)
    for nota in notas.values():
        nota["total_itens"] = len(nota["itens"])  # type: ignore[index]
        nota["total_quantidade"] = sum(item.get("quantidade", 0) for item in nota["itens"])  # type: ignore[index]
        _normalizar_usuarios(nota)
    return notas
