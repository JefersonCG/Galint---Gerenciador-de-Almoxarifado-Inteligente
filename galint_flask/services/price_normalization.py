from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..models import Item
from .legacy_stock_normalizer import ignore_packaging_metadata_for_stock, resolve_canonical_unit, resolve_packaging_factor
from .unit_conversion_engine import ConversionResult, UnitConversionError, unit_conversion_engine

_ROUND_PRICE = 8
_ROUND_QUANTITY = 8


@dataclass(slots=True, frozen=True)
class NormalizedLineValue:
    quantity_input: float
    quantity_unit: str
    quantity_base: float
    unit_base: str
    unit_price_input: float | None
    unit_price_base: float | None
    total_value: float | None
    price_unit: str
    factor_to_base: float
    conversion: ConversionResult


@dataclass(slots=True, frozen=True)
class NormalizedStoredPrice:
    unit_price_input: float
    unit_price_base: float
    price_unit: str
    unit_base: str
    factor_to_base: float
    conversion: ConversionResult


def _coerce_positive_or_zero(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _resolve_unit(value: str | None, *, fallback: str) -> str:
    normalized = (value or "").strip().lower()
    return normalized or fallback


def _normalize_unit_key(value: str | None) -> str:
    normalized = unit_conversion_engine._normalize_unit_code(value)
    if normalized:
        return normalized
    return _resolve_unit(value, fallback="")


def _infer_packaging_document_unit(item: Item) -> str | None:
    packaging_unit = (item.tipo_embalagem_novo or "").strip().lower()
    packaging_factor = float(resolve_packaging_factor(item) or 0.0)
    if packaging_unit and packaging_factor > 0 and not ignore_packaging_metadata_for_stock(item):
        return packaging_unit
    return None


def infer_document_quantity_unit_for_item(item: Item) -> str:
    packaging_unit = _infer_packaging_document_unit(item)
    if packaging_unit:
        return packaging_unit
    return _resolve_unit(item.unidade, fallback=resolve_canonical_unit(item))


def infer_price_unit_for_item(item: Item) -> str:
    return infer_document_quantity_unit_for_item(item)


def should_autofix_packaged_document_unit(
    item: Item,
    *,
    current_unit: str | None,
    quantity: float | None,
    quantity_base: float | None,
) -> bool:
    packaging_unit = _infer_packaging_document_unit(item)
    if not packaging_unit:
        return False

    packaging_key = _normalize_unit_key(packaging_unit)
    canonical_key = _normalize_unit_key(resolve_canonical_unit(item))
    current_key = _normalize_unit_key(current_unit)
    packaging_factor = float(resolve_packaging_factor(item) or 0.0)

    if not packaging_key or not canonical_key or not current_key:
        return False
    if current_key != canonical_key or current_key == packaging_key:
        return False
    if packaging_factor <= 1.0 or ignore_packaging_metadata_for_stock(item):
        return False

    quantity_value = _coerce_positive_or_zero(quantity)
    if quantity_value is None or quantity_value <= 0:
        return False

    quantity_base_value = _coerce_positive_or_zero(quantity_base)
    if quantity_base_value is None:
        return True
    return abs(float(quantity_base_value) - float(quantity_value)) <= 1e-6


def normalize_quantity_for_item(
    item: Item,
    *,
    quantity: float,
    from_unit: str | None = None,
) -> ConversionResult:
    if not item or not item.codigo_item:
        raise UnitConversionError("Produto não encontrado para normalização de quantidade")
    quantity_unit = _resolve_unit(from_unit, fallback=infer_document_quantity_unit_for_item(item))
    return unit_conversion_engine.convert_item_to_base(item, quantity, quantity_unit)


def normalize_document_line(
    item: Item,
    *,
    quantity: float,
    quantity_unit: str | None = None,
    unit_price: float | None = None,
    total_price: float | None = None,
    price_unit: str | None = None,
) -> NormalizedLineValue:
    quantity_value = float(quantity)
    quantity_conversion = normalize_quantity_for_item(
        item,
        quantity=quantity_value,
        from_unit=quantity_unit,
    )
    resolved_quantity_unit = _resolve_unit(quantity_unit, fallback=infer_document_quantity_unit_for_item(item))
    resolved_price_unit = _resolve_unit(price_unit, fallback=resolved_quantity_unit)
    price_conversion = normalize_quantity_for_item(
        item,
        quantity=1.0,
        from_unit=resolved_price_unit,
    )
    factor_to_base = float(price_conversion.quantity_base or 0.0)
    if factor_to_base <= 0:
        factor_to_base = 1.0

    raw_unit_price = _coerce_positive_or_zero(unit_price)
    raw_total = _coerce_positive_or_zero(total_price)
    if raw_total is None and raw_unit_price is not None:
        raw_total = round(raw_unit_price * quantity_value, 2)

    unit_price_base: float | None = None
    if raw_total is not None and float(quantity_conversion.quantity_base or 0.0) > 0:
        unit_price_base = round(raw_total / float(quantity_conversion.quantity_base), _ROUND_PRICE)
    elif raw_unit_price is not None:
        unit_price_base = round(raw_unit_price / factor_to_base, _ROUND_PRICE)

    return NormalizedLineValue(
        quantity_input=quantity_value,
        quantity_unit=resolved_quantity_unit,
        quantity_base=round(float(quantity_conversion.quantity_base or 0.0), _ROUND_QUANTITY),
        unit_base=(quantity_conversion.unit_base or resolve_canonical_unit(item) or "un").strip().lower(),
        unit_price_input=raw_unit_price,
        unit_price_base=unit_price_base,
        total_value=raw_total,
        price_unit=resolved_price_unit,
        factor_to_base=round(factor_to_base, _ROUND_QUANTITY),
        conversion=quantity_conversion,
    )


def normalize_item_price(
    item: Item,
    *,
    unit_price: float,
    price_unit: str | None = None,
) -> NormalizedStoredPrice:
    raw_unit_price = _coerce_positive_or_zero(unit_price)
    if raw_unit_price is None:
        raise ValueError("Preço informado inválido")

    resolved_price_unit = _resolve_unit(price_unit, fallback=infer_price_unit_for_item(item))
    price_conversion = normalize_quantity_for_item(
        item,
        quantity=1.0,
        from_unit=resolved_price_unit,
    )
    factor_to_base = float(price_conversion.quantity_base or 0.0)
    if factor_to_base <= 0:
        factor_to_base = 1.0

    return NormalizedStoredPrice(
        unit_price_input=raw_unit_price,
        unit_price_base=round(raw_unit_price / factor_to_base, _ROUND_PRICE),
        price_unit=resolved_price_unit,
        unit_base=(price_conversion.unit_base or resolve_canonical_unit(item) or "un").strip().lower(),
        factor_to_base=round(factor_to_base, _ROUND_QUANTITY),
        conversion=price_conversion,
    )