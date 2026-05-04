"""Inventory service bridging the legacy data model to Flask routes."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from difflib import SequenceMatcher
import json
import logging
import math
import re
import secrets
from time import monotonic
from types import SimpleNamespace
from typing import Any
from unicodedata import normalize as unicode_normalize

from flask import has_app_context
from sqlalchemy import or_, func, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

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
    OperationLog,
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
    infer_packaging_measure,
    ignore_packaging_metadata_for_stock,
    is_packaging_unit_code,
    resolve_canonical_unit,
    resolve_packaging_factor,
    resolve_packaging_quantity_and_unit,
    uses_packaging_legacy_normalization,
)
from .operation_log_service import operation_log_service
from .price_normalization import (
    infer_document_quantity_unit_for_item,
    infer_price_unit_for_item,
    normalize_document_line,
    normalize_item_price,
    should_autofix_packaged_document_unit,
)
from .unit_conversion_engine import UnitConversionError, unit_conversion_engine
from .balance_provider import balance_provider
from .category_catalog import category_catalog_service
from .material_return_metadata import format_material_return_actor_label
from ..utils.lote_generator import generate_lote
from ..utils.barcode_generator import generate_barcode, get_barcode_path
from ..utils.time_service import TimeService

logger = logging.getLogger(__name__)

ADVANCED_DIMENSION_OPTIONS = ("unit", "mass", "volume", "length")
ACTIVE_TOOL_WITHDRAWAL_STATUSES = ("em_uso", "atrasada", "para_reparo")
OPEN_TOOL_REPAIR_STATUSES = ("aguardando_orcamento", "em_reparo")
TOOL_EXIT_CHANNELS = {"ferramenta", "ferramentas", "custodia", "tool_custody", "central_kits"}
FRACTIONAL_EXIT_CHANNELS = {"fracionado", "saida_fracionada", "saida-fracionada"}

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

BASE_ITEM_UNIT_OPTIONS: tuple[str, ...] = ("Unidade", "Par", "Metro", "Quilo", "Litro")
_BASE_ITEM_UNIT_LABEL_BY_CODE = {
    "un": "Unidade",
    "par": "Par",
    "m": "Metro",
    "kg": "Quilo",
    "l": "Litro",
}
_BASE_ITEM_STORAGE_CODE_BY_LABEL = {
    "Unidade": "unidade",
    "Par": "par",
    "Metro": "metro",
    "Quilo": "quilo",
    "Litro": "litro",
}
_ADVANCED_DIMENSION_BY_CANONICAL_UNIT = {
    "un": "unit",
    "par": "unit",
    "m": "length",
    "kg": "mass",
    "l": "volume",
}
_BASE_ITEM_UNIT_ALIASES = {
    "un": "Unidade",
    "und": "Unidade",
    "pc": "Unidade",
    "pcs": "Unidade",
    "pca": "Unidade",
    "pca.": "Unidade",
    "peca": "Unidade",
    "pecas": "Unidade",
    "peça": "Unidade",
    "peças": "Unidade",
    "unidade": "Unidade",
    "unidades": "Unidade",
    "par": "Par",
    "pares": "Par",
    "m": "Metro",
    "metro": "Metro",
    "metros": "Metro",
    "kg": "Quilo",
    "quilo": "Quilo",
    "quilos": "Quilo",
    "kilo": "Quilo",
    "kilos": "Quilo",
    "l": "Litro",
    "lt": "Litro",
    "lts": "Litro",
    "litro": "Litro",
    "litros": "Litro",
}


def normalize_base_item_unit(value: object, *, fallback: str | None = None) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return fallback
    return _BASE_ITEM_UNIT_ALIASES.get(raw, fallback)


def ensure_base_item_unit(value: object, *, fallback: str = "Unidade") -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    normalized = normalize_base_item_unit(raw)
    if normalized:
        return normalized
    raise ValueError("Unidade base invalida. Use apenas Unidade, Par, Metro, Quilo ou Litro.")


def resolve_item_base_unit_label(item_like: Any, *, fallback: str = "Unidade") -> str:
    if item_like is None:
        return fallback

    if isinstance(item_like, dict):
        d = dict(item_like)
        if isinstance(d.get("product_units"), list):
            d["product_units"] = [
                SimpleNamespace(**u) if isinstance(u, dict) else u
                for u in d["product_units"]
            ]
        probe = SimpleNamespace(**d)
    else:
        probe = item_like

    canonical_unit = _BASE_ITEM_UNIT_LABEL_BY_CODE.get((resolve_canonical_unit(probe) or "").strip().lower())
    if canonical_unit:
        return canonical_unit

    if isinstance(item_like, dict):
        normalized = normalize_base_item_unit(item_like.get("unidade"))
        if normalized:
            return normalized
    else:
        normalized = normalize_base_item_unit(getattr(item_like, "unidade", None))
        if normalized:
            return normalized

    return fallback


def _normalize_dashboard_lookup(value: object) -> str:
    normalized = " ".join(str(value or "").strip().split()).lower()
    normalized = unicode_normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


_DASHBOARD_CATEGORY_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "material-eletrico",
        "label": "Material Elétrico",
        "route": "Material Elétrico",
        "aliases": (
            "material elétrico",
            "material eletrico",
            "materiais elétricos",
            "materiais eletricos",
        ),
    },
    {
        "key": "material-hidraulico",
        "label": "Material Hidráulico",
        "route": "Material Hidráulico",
        "aliases": (
            "material hidráulico",
            "material hidraulico",
            "materiais hidráulicos",
            "materiais hidraulicos",
        ),
    },
    {
        "key": "materiais-limpeza",
        "label": "Materiais de Limpeza",
        "route": "Materiais de Limpeza",
        "aliases": (
            "materiais de limpeza",
            "material de limpeza",
            "limpeza",
        ),
    },
    {
        "key": "mat-pintura-drywall",
        "label": "Mat. Pintura e Drywall",
        "route": "Mat. Pintura e Drywall",
        "aliases": (
            "mat. pintura e drywall",
            "mat pintura e drywall",
            "material pintura",
            "material pintura e drywall",
            "material de pintura drywall",
            "material de pintura/drywall",
            "material pintura/drywall",
            "material pintura e drywal",
            "material pintura",
            "material de pintura",
            "drywall",
        ),
    },
    {
        "key": "ferramentas",
        "label": "Ferramentas",
        "route": "Ferramentas",
        "aliases": (
            "ferramenta",
            "ferramentas",
        ),
    },
    {
        "key": "equipamento",
        "label": "Equipamentos",
        "route": "Equipamento",
        "aliases": (
            "equipamento",
            "equipamentos",
            "equipamentos maquinas",
            "equipamentos/maquinas",
            "equipamentos/máquinas",
        ),
    },
    {
        "key": "equipamento-ti",
        "label": "Equipamentos T.I",
        "route": "Equipamentos T.I",
        "aliases": (
            "equipamento de ti",
            "equipamentos de ti",
            "equipamento ti",
            "equipamentos ti",
            "equipamento t i",
            "equipamentos t i",
            "equipamentos t.i",
            "equipamento t.i",
            "equipamento de informatica",
            "equipamento de informática",
            "equipamentos de informatica",
            "equipamentos de informática",
        ),
    },
    {
        "key": "material-construcao",
        "label": "Material Construção",
        "route": "Material Construção",
        "aliases": (
            "material construção",
            "material construcao",
            "material de construção",
            "material de construcao",
            "construcao civil",
        ),
    },
    {
        "key": "material-ep",
        "label": "Material de EP",
        "route": "Material de EP",
        "aliases": (
            "material de ep",
            "material de e.p.",
            "epi",
            "epis",
            "equipamento de protecao",
            "equipamento de proteção",
        ),
    },
    {
        "key": "material-piscina",
        "label": "Material Piscina",
        "route": "Material Piscina",
        "aliases": (
            "material piscina",
            "materiais piscina",
            "materiais de piscina",
            "material de piscina",
            "piscina",
        ),
    },
    {
        "key": "material-uso-geral",
        "label": "Material/Uso geral",
        "route": "Material/Uso geral",
        "aliases": (
            "material/uso geral",
            "material uso geral",
            "uso geral",
        ),
    },
    {
        "key": "sem-categoria",
        "label": "Sem categoria",
        "route": "Sem categoria",
        "aliases": (
            "sem categoria",
        ),
    },
)

_DASHBOARD_CATEGORY_ORDER = {
    row["key"]: index
    for index, row in enumerate(_DASHBOARD_CATEGORY_DEFINITIONS)
}

_DASHBOARD_CATEGORY_LOOKUP: dict[str, dict[str, Any]] = {}
for _dashboard_category in _DASHBOARD_CATEGORY_DEFINITIONS:
    for _dashboard_alias in _dashboard_category["aliases"]:
        _DASHBOARD_CATEGORY_LOOKUP[_normalize_dashboard_lookup(_dashboard_alias)] = _dashboard_category
    _DASHBOARD_CATEGORY_LOOKUP.setdefault(
        _normalize_dashboard_lookup(_dashboard_category["label"]),
        _dashboard_category,
    )
    _DASHBOARD_CATEGORY_LOOKUP.setdefault(
        _normalize_dashboard_lookup(_dashboard_category["route"]),
        _dashboard_category,
    )

_DASHBOARD_UNIT_DEFINITIONS: tuple[dict[str, str], ...] = (
    {"key": "unidade", "label": "Unidade", "short_label": "un"},
    {"key": "litro", "label": "Litro", "short_label": "L"},
    {"key": "kg", "label": "Kg", "short_label": "kg"},
    {"key": "metro", "label": "Metro", "short_label": "m"},
)

_DASHBOARD_UNIT_ORDER = {
    row["key"]: index
    for index, row in enumerate(_DASHBOARD_UNIT_DEFINITIONS)
}

_DASHBOARD_UNIT_LOOKUP = {
    "un": "unidade",
    "und": "unidade",
    "unid": "unidade",
    "unidade": "unidade",
    "unidades": "unidade",
    "l": "litro",
    "lt": "litro",
    "lts": "litro",
    "litro": "litro",
    "litros": "litro",
    "kg": "kg",
    "quilo": "kg",
    "quilos": "kg",
    "m": "metro",
    "mt": "metro",
    "mts": "metro",
    "metro": "metro",
    "metros": "metro",
}


def _resolve_dashboard_category_meta(value: object) -> dict[str, str]:
    raw_value = " ".join(str(value or "").strip().split()) or "Sem categoria"
    normalized = _normalize_dashboard_lookup(raw_value)
    category_meta = _DASHBOARD_CATEGORY_LOOKUP.get(normalized)
    if category_meta is not None:
        return {
            "key": str(category_meta["key"]),
            "label": str(category_meta["label"]),
            "route": str(category_meta["route"]),
        }
    fallback_key = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "sem-categoria"
    return {
        "key": fallback_key,
        "label": raw_value,
        "route": raw_value,
    }


def _resolve_dashboard_unit_key(value: object) -> str:
    normalized = _normalize_dashboard_lookup(value)
    if not normalized:
        return "unidade"
    return _DASHBOARD_UNIT_LOOKUP.get(normalized, "unidade")


def _round_dashboard_balance(unit_key: str, value: float) -> float:
    if unit_key == "unidade":
        return float(round(value))
    return round(value, 1)


def _new_dashboard_unit_map() -> dict[str, dict[str, Any]]:
    return {
        row["key"]: {
            "key": row["key"],
            "label": row["label"],
            "short_label": row["short_label"],
            "count": 0,
            "saldo_total": 0.0,
        }
        for row in _DASHBOARD_UNIT_DEFINITIONS
    }


def _accumulate_dashboard_category_summary(
    categorias: dict[str, dict[str, Any]],
    *,
    categoria_value: object,
    unidade_value: object,
    saldo_categoria: float,
    photo_path: str | None = None,
) -> None:
    category_meta = _resolve_dashboard_category_meta(categoria_value)
    raw_category = " ".join(str(categoria_value or "").strip().split()) or category_meta["route"]
    category_key = category_meta["key"]
    category_summary = categorias.setdefault(
        category_key,
        {
            "category_key": category_key,
            "categoria": category_meta["label"],
            "route_categoria": raw_category,
            "source_categories": set(),
            "total_itens": 0,
            "saldo_total": 0.0,
            "_order": _DASHBOARD_CATEGORY_ORDER.get(category_key, 999),
            "_unit_map": _new_dashboard_unit_map(),
            "_photo_paths": [],
        },
    )
    category_summary["source_categories"].add(raw_category)
    if raw_category == category_meta["route"] or category_summary.get("route_categoria") == category_meta["label"]:
        category_summary["route_categoria"] = raw_category

    normalized_photo_path = str(photo_path or "").strip()
    if normalized_photo_path and normalized_photo_path not in category_summary["_photo_paths"]:
        category_summary["_photo_paths"].append(normalized_photo_path)

    unit_key = _resolve_dashboard_unit_key(unidade_value)
    rounded_balance = _round_dashboard_balance(unit_key, float(saldo_categoria or 0.0))

    category_summary["total_itens"] += 1
    category_summary["saldo_total"] += rounded_balance

    unit_summary = category_summary["_unit_map"][unit_key]
    unit_summary["count"] += 1
    unit_summary["saldo_total"] += rounded_balance


def _finalize_dashboard_category_summary(categorias: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    fallback_order_base = len(_DASHBOARD_CATEGORY_ORDER)
    for fallback_index, summary in enumerate(categorias.values()):
        total_itens = int(summary.get("total_itens") or 0)
        unit_breakdown: list[dict[str, Any]] = []
        for unit_meta in _DASHBOARD_UNIT_DEFINITIONS:
            unit_summary = summary["_unit_map"][unit_meta["key"]]
            if int(unit_summary.get("count") or 0) <= 0:
                continue
            unit_breakdown.append(
                {
                    "key": unit_meta["key"],
                    "label": unit_meta["label"],
                    "short_label": unit_meta["short_label"],
                    "count": int(unit_summary.get("count") or 0),
                    "saldo_total": _round_dashboard_balance(
                        unit_meta["key"],
                        float(unit_summary.get("saldo_total") or 0.0),
                    ),
                    "share_pct": round(
                        (float(unit_summary.get("count") or 0) / float(total_itens)) * 100,
                        1,
                    ) if total_itens else 0.0,
                }
            )
        unit_breakdown.sort(
            key=lambda entry: (
                _DASHBOARD_UNIT_ORDER.get(str(entry.get("key")), 999),
                -int(entry.get("count") or 0),
            )
        )
        dominant_unit = max(
            unit_breakdown,
            key=lambda entry: (int(entry.get("count") or 0), float(entry.get("saldo_total") or 0.0)),
            default=None,
        )
        summaries.append(
            {
                "category_key": summary["category_key"],
                "categoria": summary["categoria"],
                "route_categoria": summary.get("route_categoria") or summary["categoria"],
                "source_categories": sorted(str(value) for value in summary.get("source_categories") or []),
                "photo_paths": list(summary.get("_photo_paths") or []),
                "total_itens": total_itens,
                "saldo_total": round(float(summary.get("saldo_total") or 0.0), 1),
                "unit_breakdown": unit_breakdown,
                "unit_mix_label": " • ".join(
                    f"{entry['count']} {entry['short_label']}"
                    for entry in unit_breakdown
                ),
                "dominant_unit": dominant_unit.get("label") if dominant_unit else None,
                "dominant_unit_key": dominant_unit.get("key") if dominant_unit else None,
                "has_data": total_itens > 0,
                "_order": summary.get("_order", fallback_order_base + fallback_index),
            }
        )
    summaries.sort(
        key=lambda entry: (
            int(entry.get("_order") or fallback_order_base),
            -int(entry.get("total_itens") or 0),
            str(entry.get("categoria") or "").lower(),
        )
    )
    for summary in summaries:
        summary.pop("_order", None)
    return summaries

MATERIAL_RETURN_UNIT_ALIASES = {
    "l": "litro",
    "lt": "litro",
    "lts": "litro",
    "litro": "litro",
    "litros": "litro",
    "kg": "quilo",
    "quilo": "quilo",
    "quilos": "quilo",
    "m": "metro",
    "mt": "metro",
    "mts": "metro",
    "metro": "metro",
    "metros": "metro",
    "par": "par",
    "pares": "par",
    "un": "unidade",
    "und": "unidade",
    "pc": "unidade",
    "pcs": "unidade",
    "pca": "unidade",
    "pca.": "unidade",
    "peca": "unidade",
    "pecas": "unidade",
    "peça": "unidade",
    "peças": "unidade",
    "unid": "unidade",
    "unidade": "unidade",
    "unidades": "unidade",
}

MATERIAL_RETURN_UNIT_META = {
    "litro": {
        "unit_display": "L",
        "unit_label": "Litro",
        "allow_decimal": True,
        "input_step": 0.001,
        "input_min": 0.001,
    },
    "quilo": {
        "unit_display": "kg",
        "unit_label": "Kg",
        "allow_decimal": True,
        "input_step": 0.001,
        "input_min": 0.001,
    },
    "par": {
        "unit_display": "par",
        "unit_label": "Par",
        "allow_decimal": False,
        "input_step": 1,
        "input_min": 1,
    },
    "metro": {
        "unit_display": "m",
        "unit_label": "Metro",
        "allow_decimal": True,
        "input_step": 0.001,
        "input_min": 0.001,
    },
    "unidade": {
        "unit_display": "un",
        "unit_label": "Unidade",
        "allow_decimal": False,
        "input_step": 1,
        "input_min": 1,
    },
}

MATERIAL_RETURN_FRACTIONABLE_PACKAGING_TYPES = {
    "lata",
    "balde",
    "bombona",
    "caixa",
    "fardo",
    "litro",
    "pacote",
    "rolo",
    "saco",
}

MATERIAL_RETURN_LIQUID_HINTS = (
    "tinta",
    "resina",
    "verniz",
    "solvente",
    "thinner",
    "selador",
    "impermeabilizante",
    "esmalte",
)

MATERIAL_RETURN_WEIGHT_HINTS = (
    "massa",
    "argamassa",
    "rejunte",
    "cloro",
    "cimento",
    "gesso",
)

MATERIAL_RETURN_LIQUID_MEASURE_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(l|lt|lts|litro|litros)\b")
MATERIAL_RETURN_WEIGHT_MEASURE_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(kg|quilo|quilos)\b")


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


_EQUIVALENT_ITEM_STOPWORDS = frozenset(
    {
        "a",
        "as",
        "com",
        "da",
        "das",
        "de",
        "do",
        "dos",
        "e",
        "em",
        "na",
        "nas",
        "no",
        "nos",
        "para",
        "por",
        "sem",
    }
)
_EQUIVALENT_ITEM_PRESENTATION_TOKENS = frozenset(
    {
        "balde",
        "bombona",
        "caixa",
        "fardo",
        "frasco",
        "galao",
        "garrafa",
        "kit",
        "lata",
        "pacote",
        "refil",
        "rolo",
        "saco",
        "unidade",
    }
)
_EQUIVALENT_ITEM_MEASURE_RE = re.compile(
    r"^\d+(?:[\.,]\d+)?(?:mm|cm|m|ml|l|lt|lts|litro|litros|g|gr|kg|un|und|pct|pc|cx|x)?$"
)


def _coerce_truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "yes", "sim"}
    return bool(value)


def _normalize_equivalent_text(value: object) -> str:
    normalized = _normalize_operational_lookup(value)
    if not normalized:
        return ""
    normalized = normalized.replace("/", " ").replace("-", " ")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return " ".join(normalized.split())


def _extract_equivalent_tokens(value: object) -> list[str]:
    tokens: list[str] = []
    for token in _normalize_equivalent_text(value).split():
        if len(token) <= 1:
            continue
        if token in _EQUIVALENT_ITEM_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _strip_equivalent_presentation_tokens(value: object) -> str:
    kept_tokens: list[str] = []
    for token in _normalize_equivalent_text(value).split():
        if token in _EQUIVALENT_ITEM_PRESENTATION_TOKENS:
            continue
        if _EQUIVALENT_ITEM_MEASURE_RE.match(token):
            continue
        kept_tokens.append(token)
    return " ".join(kept_tokens)


def _sequence_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return float(SequenceMatcher(None, left, right).ratio())


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


def _normalize_unit_code_key(value: object) -> str:
    return unit_conversion_engine._normalize_unit_code(str(value or "").strip().lower())


def _storage_unit_code_from_canonical(value: object, *, fallback: str = "unidade") -> str:
    canonical = _normalize_unit_code_key(value)
    label = _BASE_ITEM_UNIT_LABEL_BY_CODE.get(canonical)
    if label:
        return _BASE_ITEM_STORAGE_CODE_BY_LABEL.get(label, fallback)

    normalized_label = normalize_base_item_unit(value)
    if normalized_label:
        return _BASE_ITEM_STORAGE_CODE_BY_LABEL.get(normalized_label, fallback)

    raw = str(value or "").strip().lower()
    return raw or fallback


def _resolve_advanced_dimension_for_unit(value: object) -> str:
    canonical = _normalize_unit_code_key(value)
    return _ADVANCED_DIMENSION_BY_CANONICAL_UNIT.get(canonical, "unit")


def _sync_packaging_conversion_graph(item: Item) -> None:
    packaging_unit_raw = str(getattr(item, "tipo_embalagem_novo", None) or "").strip().lower()
    if not packaging_unit_raw or ignore_packaging_metadata_for_stock(item):
        return

    try:
        packaging_factor = float(resolve_packaging_factor(item) or 0.0)
    except (TypeError, ValueError):
        packaging_factor = 0.0
    if packaging_factor <= 0:
        return

    packaging_key = _normalize_unit_code_key(packaging_unit_raw)
    base_key = _normalize_unit_code_key(resolve_canonical_unit(item) or getattr(item, "unidade", None))
    if not packaging_key or not base_key or packaging_key == base_key:
        return

    base_label = resolve_item_base_unit_label(item, fallback="Unidade")
    base_dimension = _resolve_advanced_dimension_for_unit(base_key)
    packaging_dimension = base_dimension
    packaging_label = packaging_unit_raw.capitalize()

    base_unit = next(
        (
            row for row in item.product_units
            if _normalize_unit_code_key(getattr(row, "unit_code", None)) == base_key
        ),
        None,
    )
    if base_unit is None:
        base_unit = ProductUnit(
            product_id=item.codigo_item,
            unit_code=_storage_unit_code_from_canonical(base_key, fallback="unidade"),
            unit_label=base_label,
            dimension=base_dimension,
            is_base=True,
            active=True,
        )
        item.product_units.append(base_unit)
    else:
        base_unit.active = True
        base_unit.is_base = True
        if not str(base_unit.unit_code or "").strip():
            base_unit.unit_code = _storage_unit_code_from_canonical(base_key, fallback="unidade")
        if not str(base_unit.unit_label or "").strip():
            base_unit.unit_label = base_label
        if base_dimension and base_unit.dimension != base_dimension:
            base_unit.dimension = base_dimension

    packaging_unit = next(
        (
            row for row in item.product_units
            if _normalize_unit_code_key(getattr(row, "unit_code", None)) == packaging_key
        ),
        None,
    )
    if packaging_unit is None:
        packaging_unit = ProductUnit(
            product_id=item.codigo_item,
            unit_code=packaging_unit_raw,
            unit_label=packaging_label,
            dimension=packaging_dimension,
            is_base=False,
            active=True,
        )
        item.product_units.append(packaging_unit)
    else:
        packaging_unit.active = True
        if packaging_unit.is_base:
            packaging_unit.is_base = False
        if not str(packaging_unit.unit_code or "").strip():
            packaging_unit.unit_code = packaging_unit_raw
        if not str(packaging_unit.unit_label or "").strip():
            packaging_unit.unit_label = packaging_label
        if packaging_dimension and packaging_unit.dimension != packaging_dimension:
            packaging_unit.dimension = packaging_dimension

    existing_dimensions = {
        str(row.dimension or "").strip().lower(): row
        for row in item.product_dimensions
    }
    for dimension in {base_dimension, packaging_dimension}:
        if not dimension:
            continue
        dimension_row = existing_dimensions.get(dimension)
        if dimension_row is None:
            item.product_dimensions.append(
                ProductDimension(
                    product_id=item.codigo_item,
                    dimension=dimension,
                    enabled=True,
                )
            )
        else:
            dimension_row.enabled = True

    matching_conversions = [
        row
        for row in item.product_unit_conversions
        if _normalize_unit_code_key(getattr(row, "from_unit", None)) == packaging_key
        and _normalize_unit_code_key(getattr(row, "to_unit", None)) == base_key
    ]
    if matching_conversions:
        primary_conversion = matching_conversions[0]
        primary_conversion.from_unit = packaging_unit.unit_code
        primary_conversion.to_unit = base_unit.unit_code
        primary_conversion.factor = packaging_factor
        primary_conversion.active = True
        metadata = dict(primary_conversion.metadata_json or {})
        metadata["source"] = "packaging_metadata_sync"
        primary_conversion.metadata_json = metadata
        for duplicate in matching_conversions[1:]:
            duplicate.active = False
    else:
        item.product_unit_conversions.append(
            ProductUnitConversion(
                product_id=item.codigo_item,
                from_unit=packaging_unit.unit_code,
                to_unit=base_unit.unit_code,
                factor=packaging_factor,
                metadata_json={"source": "packaging_metadata_sync"},
                active=True,
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


def _price_field_matches(current: object, expected: float | None, *, tolerance: float = 1e-8) -> bool:
    current_value = _coerce_price_value(current)
    if expected is None:
        return current_value is None
    if current_value is None:
        return False
    return abs(float(current_value) - float(expected)) <= tolerance


def _price_unit_matches(current: object, expected: str | None) -> bool:
    return _normalize_price_unit_value(current) == _normalize_price_unit_value(expected)


def _resolve_effective_historical_line_units(
    item: Item,
    *,
    quantity: float,
    quantity_base: object,
    quantity_unit: object,
    price_unit: object,
) -> tuple[str, str]:
    stored_quantity_unit = _normalize_price_unit_value(quantity_unit) or ""
    effective_quantity_unit = stored_quantity_unit
    should_refresh_document_unit = not effective_quantity_unit

    if not should_refresh_document_unit and should_autofix_packaged_document_unit(
        item,
        current_unit=effective_quantity_unit,
        quantity=quantity,
        quantity_base=quantity_base,
    ):
        should_refresh_document_unit = True

    if should_refresh_document_unit:
        effective_quantity_unit = infer_document_quantity_unit_for_item(item)

    effective_quantity_unit = effective_quantity_unit or infer_document_quantity_unit_for_item(item)
    stored_price_unit = _normalize_price_unit_value(price_unit)
    if should_refresh_document_unit and (not stored_price_unit or stored_price_unit == stored_quantity_unit):
        effective_price_unit = effective_quantity_unit
    else:
        effective_price_unit = stored_price_unit or effective_quantity_unit

    return effective_quantity_unit, effective_price_unit


def _normalize_historical_item_price_row(
    item: Item,
    row: DocumentoEntradaEstoqueItem | FinanceLedgerEntry,
    *,
    raw_value: float,
) -> dict[str, float | str] | None:
    quantity = _coerce_price_value(getattr(row, "quantidade", None))
    if quantity is None or quantity <= 0:
        return None

    historical_raw = _coerce_price_value(getattr(row, "valor_unitario", None))
    if historical_raw is None:
        total_value = _coerce_price_value(getattr(row, "valor_total", None))
        if total_value is not None and quantity > 0:
            historical_raw = round(float(total_value) / float(quantity), 8)

    if historical_raw is None or abs(float(historical_raw) - float(raw_value)) > 1e-6:
        return None

    quantity_unit, price_unit = _resolve_effective_historical_line_units(
        item,
        quantity=float(quantity),
        quantity_base=getattr(row, "quantidade_base", None),
        quantity_unit=getattr(row, "unidade_quantidade", None),
        price_unit=getattr(row, "unidade_preco", None),
    )

    try:
        normalized = normalize_document_line(
            item,
            quantity=float(quantity),
            quantity_unit=quantity_unit,
            unit_price=float(historical_raw),
            total_price=_coerce_price_value(getattr(row, "valor_total", None)),
            price_unit=price_unit,
        )
    except Exception:
        return None

    unit_price_base = _coerce_price_value(normalized.unit_price_base)
    factor_to_base = _coerce_price_value(normalized.factor_to_base) or 1.0
    if unit_price_base is None or unit_price_base <= 0:
        return None

    return {
        "unit_price_base": float(unit_price_base),
        "price_unit": normalized.price_unit,
        "factor_to_base": float(factor_to_base),
    }


def _resolve_historical_item_price_proof(item: Item, *, raw_value: float) -> dict[str, float | str] | None:
    code = str(getattr(item, "codigo_item", "") or "").strip()
    if not code or raw_value <= 0:
        return None
    if not has_app_context():
        return None

    packaging_factor = float(resolve_packaging_factor(item) or 0.0)
    if packaging_factor <= 1 or ignore_packaging_metadata_for_stock(item):
        return None

    document_rows = (
        DocumentoEntradaEstoqueItem.query
        .filter(DocumentoEntradaEstoqueItem.codigo_item == code)
        .order_by(DocumentoEntradaEstoqueItem.id_documento_item.desc())
        .limit(25)
        .all()
    )
    for row in document_rows:
        proof = _normalize_historical_item_price_row(item, row, raw_value=raw_value)
        if proof is not None:
            return proof

    finance_rows = (
        FinanceLedgerEntry.query
        .filter(FinanceLedgerEntry.codigo_item == code)
        .order_by(FinanceLedgerEntry.id.desc())
        .limit(25)
        .all()
    )
    for row in finance_rows:
        proof = _normalize_historical_item_price_row(item, row, raw_value=raw_value)
        if proof is not None:
            return proof

    return None


def _reconcile_normalized_item_price(item: Item, *, kind: str) -> bool:
    if kind not in {"compra", "reposicao"}:
        raise ValueError("Tipo de preco invalido")

    raw_attr = f"preco_{kind}_unitario"
    base_attr = f"preco_{kind}_unitario_base"
    unit_attr = f"preco_{kind}_unidade_preco"
    factor_attr = f"preco_{kind}_fator_base"

    raw_value = _coerce_price_value(getattr(item, raw_attr, None))
    if raw_value is None:
        changed = False
        for attr_name in (base_attr, unit_attr, factor_attr):
            if getattr(item, attr_name, None) is not None:
                setattr(item, attr_name, None)
                changed = True
        return changed

    stored_unit = _normalize_price_unit_value(getattr(item, unit_attr, None))
    candidates = []
    tried_units: set[str | None] = set()
    for candidate_unit in (stored_unit, infer_price_unit_for_item(item)):
        if candidate_unit in tried_units:
            continue
        tried_units.add(candidate_unit)
        try:
            normalized = normalize_item_price(item, unit_price=raw_value, price_unit=candidate_unit)
            candidates.append(normalized)
        except Exception:
            continue

    if not candidates:
        return False

    normalized = candidates[0]
    if len(candidates) > 1:
        historical_proof = _resolve_historical_item_price_proof(item, raw_value=raw_value)
        if historical_proof is not None:
            for candidate in candidates:
                if (
                    _price_field_matches(candidate.unit_price_base, historical_proof.get("unit_price_base"))
                    and _price_unit_matches(candidate.price_unit, str(historical_proof.get("price_unit") or ""))
                    and _price_field_matches(candidate.factor_to_base, historical_proof.get("factor_to_base"))
                ):
                    normalized = candidate
                    break

    expected_base = float(normalized.unit_price_base)
    expected_unit = normalized.price_unit
    expected_factor = float(normalized.factor_to_base)
    changed = False

    if not _price_field_matches(getattr(item, base_attr, None), expected_base):
        setattr(item, base_attr, expected_base)
        changed = True

    if not _price_unit_matches(getattr(item, unit_attr, None), expected_unit):
        setattr(item, unit_attr, expected_unit)
        changed = True

    if not _price_field_matches(getattr(item, factor_attr, None), expected_factor):
        setattr(item, factor_attr, expected_factor)
        changed = True

    return changed


def _reconcile_normalized_item_prices(item: Item) -> bool:
    changed = False
    for kind in ("compra", "reposicao"):
        if _reconcile_normalized_item_price(item, kind=kind):
            changed = True
    return changed


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
    canal_saida: str | None = None


ADMIN_BALANCE_ADJUSTMENT_TYPE = "ajuste_admin_saldo"
ADMIN_BALANCE_ADJUSTMENT_SOURCE = "admin_balance_portal"
ADMIN_ITEM_CODE_CHANGE_TYPE = "ajuste_admin_codigo"
ADMIN_ITEM_CODE_CHANGE_SOURCE = "admin_code_portal"
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
    def _should_force_toolkit_unit_semantics(
        payload: dict[str, Any] | None,
        *,
        current_item: Item | None = None,
    ) -> bool:
        payload_data = dict(payload or {})
        probe = SimpleNamespace(
            categoria=payload_data.get("categoria", getattr(current_item, "categoria", None)),
            descricao=payload_data.get("descricao", getattr(current_item, "descricao", None)),
            unidade=payload_data.get("unidade", getattr(current_item, "unidade", None)),
            tipo_embalagem=payload_data.get("tipo_embalagem", getattr(current_item, "tipo_embalagem", None)),
            tipo_embalagem_novo=payload_data.get("tipo_embalagem_novo", getattr(current_item, "tipo_embalagem_novo", None)),
            unidades_por_embalagem=payload_data.get("unidades_por_embalagem", getattr(current_item, "unidades_por_embalagem", None)),
            grandeza_referencia=payload_data.get("grandeza_referencia", getattr(current_item, "grandeza_referencia", None)),
            litros_por_embalagem=payload_data.get("litros_por_embalagem", getattr(current_item, "litros_por_embalagem", None)),
            product_units=getattr(current_item, "product_units", []) or [],
            product_unit_conversions=getattr(current_item, "product_unit_conversions", []) or [],
        )
        return ignore_packaging_metadata_for_stock(probe)

    @staticmethod
    def _normalize_toolkit_registration_payload(
        payload: dict[str, Any] | None,
        *,
        current_item: Item | None = None,
    ) -> dict[str, Any]:
        normalized_payload = dict(payload or {})
        if not InventoryService._should_force_toolkit_unit_semantics(normalized_payload, current_item=current_item):
            return normalized_payload

        normalized_payload["unidade"] = "Unidade"
        normalized_payload["tipo_embalagem"] = None
        normalized_payload["tipo_embalagem_novo"] = None
        normalized_payload["unidades_por_embalagem"] = None
        normalized_payload["grandeza_referencia"] = None
        normalized_payload["litros_por_embalagem"] = None
        normalized_payload["estoque_embalagens"] = 0.0
        normalized_payload["estoque_unidades_soltas"] = 0.0
        return normalized_payload

    @staticmethod
    def _apply_toolkit_unit_semantics(item: Item) -> bool:
        if item is None or not InventoryService._should_force_toolkit_unit_semantics({}, current_item=item):
            return False

        changed = False
        target_values = {
            "unidade": "Unidade",
            "tipo_embalagem": None,
            "tipo_embalagem_novo": None,
            "unidades_por_embalagem": None,
            "grandeza_referencia": None,
            "litros_por_embalagem": None,
            "estoque_embalagens": 0.0,
            "estoque_unidades_soltas": 0.0,
        }
        for field_name, target_value in target_values.items():
            current_value = getattr(item, field_name)
            if current_value != target_value:
                setattr(item, field_name, target_value)
                changed = True
        return changed

    @staticmethod
    def _as_positive_float(value: object) -> float:
        try:
            f = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return f

    @staticmethod
    def _hydrate_missing_packaging_metadata(
        payload: dict[str, Any] | None,
        *,
        current_item: Item | None = None,
    ) -> dict[str, Any]:
        normalized_payload = dict(payload or {})
        piece_like_keywords = (
            "aspirador",
            "caixa passagem",
            "caixa sif",
            "desempenadeira",
            "disjuntor",
            "dobradica",
            "espatula",
            "escova",
            "grampo",
            "iluminacao de emergencia",
            "interruptor",
            "jogo",
            "kit",
            "lampada",
            "led",
            "luminaria",
            "modulo",
            "mola aerea",
            "nivel",
            "painel",
            "parafuso",
            "peneira",
            "placa",
            "rabixo",
            "ralo",
            "refletor",
            "respirador",
            "tampa",
            "tampo",
            "temporizador",
            "tomada",
        )
        liquid_keywords = (
            "acetinado",
            "aditivo",
            "esmalte",
            "fosco",
            "impermeabilizante",
            "resina",
            "selador",
            "solvente",
            "thinner",
            "tinta",
            "toque",
            "vedalit",
            "verniz",
        )
        weight_keywords = (
            "argamassa",
            "cloro",
            "cimento",
            "ecopoxi",
            "gesso",
            "manta",
            "massa",
            "quartzo",
            "rejunte",
        )

        def _normalize_packaging_type(value: object) -> str | None:
            raw = str(value or "").strip().lower()
            aliases = {
                "lata": "lata",
                "latas": "lata",
                "balde": "balde",
                "baldes": "balde",
                "bombona": "bombona",
                "bombonas": "bombona",
                "caixa": "caixa",
                "caixas": "caixa",
                "pacote": "pacote",
                "pacotes": "pacote",
                "fardo": "fardo",
                "fardos": "fardo",
                "rolo": "rolo",
                "rolos": "rolo",
                "saco": "saco",
                "sacos": "saco",
                "litro": "litro",
                "litros": "litro",
            }
            normalized = aliases.get(raw)
            if normalized and is_packaging_unit_code(normalized):
                return normalized
            return None

        def _normalize_legacy_lookup_text(*parts: object) -> str:
            joined = " ".join(str(part or "").strip().lower() for part in parts if str(part or "").strip())
            normalized = unicode_normalize("NFKD", joined).encode("ascii", "ignore").decode("ascii")
            return re.sub(r"[^a-z0-9]+", " ", normalized).strip()

        def _parse_positive_numeric_legacy(value: object) -> float:
            raw = str(value or "").strip().replace(",", ".")
            if not raw:
                return 0.0
            try:
                parsed = float(raw)
            except (TypeError, ValueError):
                return 0.0
            if math.isnan(parsed) or math.isinf(parsed) or parsed <= 0:
                return 0.0
            return parsed

        def _infer_unit_only_from_numeric_legacy(*, descricao: object, categoria: object) -> str | None:
            lookup_text = _normalize_legacy_lookup_text(descricao, categoria)
            if not lookup_text:
                return None
            if "material de ep" in lookup_text and "luva" in lookup_text:
                return "Par"
            if any(keyword in lookup_text for keyword in piece_like_keywords):
                return "Unidade"
            return None

        def _infer_measure_from_numeric_legacy(*, legacy_value: float, descricao: object, categoria: object) -> tuple[float, str] | None:
            if legacy_value <= 0:
                return None
            lookup_text = _normalize_legacy_lookup_text(descricao, categoria)
            if any(keyword in lookup_text for keyword in liquid_keywords):
                return legacy_value, "l"
            if any(keyword in lookup_text for keyword in weight_keywords):
                return legacy_value, "kg"
            return None

        def _infer_packaging_type_from_measure(*, inferred_unit: str, descricao: object, categoria: object) -> str | None:
            text = " ".join(
                part.strip().lower()
                for part in (str(descricao or ""), str(categoria or ""))
                if str(part or "").strip()
            )
            if inferred_unit == "m":
                return "rolo"
            if inferred_unit == "l":
                return "lata"
            if inferred_unit == "kg":
                if any(keyword in text for keyword in ("textura", "graffiato", "grafiato", "massa", "cloro", "manta")):
                    return "balde"
                if any(keyword in text for keyword in ("argamassa", "rejunte", "rejuntamento", "cimento", "gesso", "quartzo")):
                    return "saco"
            return None

        inferred_packaging_type = _normalize_packaging_type(
            normalized_payload.get("tipo_embalagem_novo", getattr(current_item, "tipo_embalagem_novo", None))
        )
        if inferred_packaging_type is None:
            inferred_packaging_type = _normalize_packaging_type(
                normalized_payload.get("unidade", getattr(current_item, "unidade", None))
            )
            if inferred_packaging_type is not None and normalized_payload.get("tipo_embalagem_novo") in (None, ""):
                normalized_payload["tipo_embalagem_novo"] = inferred_packaging_type

        probe = SimpleNamespace(
            descricao=normalized_payload.get("descricao", getattr(current_item, "descricao", None)),
            categoria=normalized_payload.get("categoria", getattr(current_item, "categoria", None)),
            marca=normalized_payload.get("marca", getattr(current_item, "marca", None)),
            unidade=normalized_payload.get("unidade", getattr(current_item, "unidade", None)),
            tipo_embalagem_novo=normalized_payload.get("tipo_embalagem_novo", getattr(current_item, "tipo_embalagem_novo", None)),
            litros_por_embalagem=normalized_payload.get("litros_por_embalagem", getattr(current_item, "litros_por_embalagem", None)),
            grandeza_referencia=normalized_payload.get("grandeza_referencia", getattr(current_item, "grandeza_referencia", None)),
            unidades_por_embalagem=normalized_payload.get("unidades_por_embalagem", getattr(current_item, "unidades_por_embalagem", None)),
            product_units=getattr(current_item, "product_units", []) or [],
        )
        unidade_atual = str(normalized_payload.get("unidade", getattr(current_item, "unidade", None)) or "").strip().lower()
        unidade_numerica = False
        if unidade_atual:
            try:
                float(unidade_atual.replace(",", "."))
                unidade_numerica = True
            except ValueError:
                unidade_numerica = False
        legacy_numeric_value = _parse_positive_numeric_legacy(unidade_atual) if unidade_numerica else 0.0
        inferred_measure = infer_packaging_measure(probe)
        if inferred_measure is None and unidade_numerica:
            inferred_measure = _infer_measure_from_numeric_legacy(
                legacy_value=legacy_numeric_value,
                descricao=probe.descricao,
                categoria=probe.categoria,
            )
        if inferred_measure is None:
            unidade_base_fallback = resolve_item_base_unit_label(current_item, fallback="Unidade") if current_item is not None else "Unidade"
            if inferred_packaging_type is not None and (
                unidade_atual in {"", "un", "und", "unidade", "unidades"}
                or is_packaging_unit_code(unidade_atual)
            ):
                normalized_payload["unidade"] = unidade_base_fallback
            if unidade_numerica:
                inferred_unit_only = _infer_unit_only_from_numeric_legacy(
                    descricao=probe.descricao,
                    categoria=probe.categoria,
                )
                if inferred_unit_only and normalized_payload.get("unidade") in (None, ""):
                    normalized_payload["unidade"] = inferred_unit_only
                elif inferred_unit_only and current_item is not None and normalized_payload.get("unidade", getattr(current_item, "unidade", None)) == getattr(current_item, "unidade", None):
                    normalized_payload["unidade"] = inferred_unit_only
                elif normalized_payload.get("unidade") in (None, ""):
                    normalized_payload["unidade"] = "Unidade"
                elif current_item is not None and normalized_payload.get("unidade", getattr(current_item, "unidade", None)) == getattr(current_item, "unidade", None):
                    normalized_payload["unidade"] = "Unidade"
            return normalized_payload

        inferred_value, inferred_unit = inferred_measure
        if inferred_packaging_type is None:
            inferred_packaging_type = _infer_packaging_type_from_measure(
                inferred_unit=inferred_unit,
                descricao=probe.descricao,
                categoria=probe.categoria,
            )
            if inferred_packaging_type is not None and normalized_payload.get("tipo_embalagem_novo") in (None, ""):
                normalized_payload["tipo_embalagem_novo"] = inferred_packaging_type

        if inferred_unit == "l" and normalized_payload.get("litros_por_embalagem") in (None, ""):
            normalized_payload["litros_por_embalagem"] = inferred_value
        elif inferred_unit == "kg" and normalized_payload.get("grandeza_referencia") in (None, ""):
            normalized_payload["grandeza_referencia"] = inferred_value
        elif inferred_unit == "m" and normalized_payload.get("grandeza_referencia") in (None, ""):
            normalized_payload["grandeza_referencia"] = inferred_value
        elif inferred_unit == "un" and normalized_payload.get("unidades_por_embalagem") in (None, ""):
            normalized_payload["unidades_por_embalagem"] = inferred_value

        tipo_embalagem = str(
            normalized_payload.get("tipo_embalagem_novo", getattr(current_item, "tipo_embalagem_novo", None)) or ""
        ).strip().lower()
        unidade_base_fallback = resolve_item_base_unit_label(current_item, fallback="Unidade") if current_item is not None else "Unidade"
        inferred_base_label = _BASE_ITEM_UNIT_LABEL_BY_CODE.get((inferred_unit or "").strip().lower())
        if tipo_embalagem and (
            unidade_atual in {"", "un", "und", "unidade", "unidades"}
            or unidade_numerica
            or is_packaging_unit_code(unidade_atual)
        ):
            normalized_payload["unidade"] = inferred_base_label or unidade_base_fallback
        elif unidade_numerica and inferred_base_label:
            normalized_payload["unidade"] = inferred_base_label
        else:
            normalized_payload["unidade"] = ensure_base_item_unit(
                normalized_payload.get("unidade"),
                fallback=unidade_base_fallback,
            )

        return normalized_payload

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
            "exhausted": False,
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

    @staticmethod
    def _build_admin_code_change_audit_details(
        *,
        item: Item | None,
        codigo_anterior: str | None,
        codigo_novo: str | None,
        matricula: str | None,
        motivo: str | None,
        audit_context: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        details = dict(audit_context or {})
        codigo_antigo_norm = _sanitize_codigo(codigo_anterior)
        codigo_novo_norm = _sanitize_codigo(codigo_novo)

        if item is not None:
            details.setdefault("descricao_item", item.descricao)
        details["codigo_item"] = codigo_novo_norm or codigo_antigo_norm or details.get("codigo_item")
        details["codigo_item_anterior"] = codigo_antigo_norm or None
        details["codigo_item_novo"] = codigo_novo_norm or None

        if matricula:
            details.setdefault("user_id", matricula)
        if motivo is not None:
            details["reason"] = str(motivo or "").strip() or None
        if error_message:
            details["error_message"] = error_message

        if before:
            details["displayed_balance_before"] = before.get("saldo_exibido")
            details["legacy_balance_before"] = before.get("legacy_balance")
            details["ledger_balance_before"] = before.get("ledger_balance")
            details["stock_balance_before"] = before.get("stock_balance")

        if after:
            details["displayed_balance_after"] = after.get("saldo_exibido")
            details["legacy_balance_after"] = after.get("legacy_balance")
            details["ledger_balance_after"] = after.get("ledger_balance")
            details["stock_balance_after"] = after.get("stock_balance")

        if result:
            details["changed"] = bool(result.get("changed"))
            details["codigo_item_anterior"] = result.get("codigo_anterior") or details.get("codigo_item_anterior")
            details["codigo_item_novo"] = result.get("codigo_atual") or details.get("codigo_item_novo")
            if result.get("message"):
                details["message"] = result.get("message")
            if result.get("updated_tables") is not None:
                details["updated_tables"] = result.get("updated_tables")

        return details

    @classmethod
    def _log_admin_code_change_audit(cls, *, action_result: str, details: dict[str, Any]) -> None:
        log_admin_stock_adjustment(
            action_type=ADMIN_ITEM_CODE_CHANGE_TYPE,
            action_result=action_result,
            details=details,
        )

    @staticmethod
    def _parse_optional_admin_target_balance(value: Any) -> float | None:
        raw = str(value or "").strip().replace(",", ".")
        if not raw:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Informe um saldo válido") from exc

    @staticmethod
    def _admin_balance_unit_meta(unit_code: str | None) -> dict[str, Any]:
        normalized = str(unit_code or "un").strip().lower() or "un"
        mapping = {
            "l": {
                "code": "l",
                "label": "Litro",
                "display": "L",
                "plural": "litros",
                "step": "0.001",
                "allow_decimal": True,
            },
            "kg": {
                "code": "kg",
                "label": "Quilo",
                "display": "kg",
                "plural": "kg",
                "step": "0.001",
                "allow_decimal": True,
            },
            "m": {
                "code": "m",
                "label": "Metro",
                "display": "m",
                "plural": "metros",
                "step": "0.001",
                "allow_decimal": True,
            },
            "par": {
                "code": "par",
                "label": "Par",
                "display": "par",
                "plural": "pares",
                "step": "1",
                "allow_decimal": False,
            },
            "un": {
                "code": "un",
                "label": "Unidade interna",
                "display": "un",
                "plural": "unidades internas",
                "step": "1",
                "allow_decimal": False,
            },
        }
        return dict(mapping.get(normalized, mapping["un"]))

    @classmethod
    def _parse_admin_balance_component(
        cls,
        value: Any,
        *,
        label: str,
        allow_blank: bool,
        allow_decimal: bool,
    ) -> float | None:
        raw = str(value or "").strip().replace(",", ".")
        if not raw:
            if allow_blank:
                return None
            raise ValueError(f"Informe {label.lower()}")

        try:
            parsed = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Informe {label.lower()} válida") from exc

        if math.isnan(parsed) or math.isinf(parsed):
            raise ValueError(f"Informe {label.lower()} válida")
        if parsed < 0:
            raise ValueError(f"{label} não pode ser negativa")
        if not allow_decimal and not cls._balance_close(parsed, round(parsed)):
            raise ValueError(f"{label} deve ser inteira")
        return float(round(parsed)) if not allow_decimal else float(parsed)

    @classmethod
    def _build_admin_balance_input_context(cls, *, item: Any, current_balance: float) -> dict[str, Any]:
        canonical_unit_code = str(resolve_canonical_unit(item) or "un").strip().lower() or "un"
        unit_meta = cls._admin_balance_unit_meta(canonical_unit_code)
        packaging_type = str(getattr(item, "tipo_embalagem_novo", None) or "").strip().lower()
        packaging_factor = Item.normalize_balance_value(resolve_packaging_factor(item) or 0.0)
        supports_packaging = bool(packaging_type and packaging_factor > 0)

        if hasattr(item, "get_nome_embalagem"):
            package_name = str(item.get_nome_embalagem() or "embalagem")
        else:
            package_name = packaging_type or "embalagem"
        if hasattr(item, "get_nome_embalagem_plural"):
            package_plural = str(item.get_nome_embalagem_plural() or "embalagens")
        else:
            package_plural = f"{package_name}s" if package_name and not package_name.endswith("s") else (package_name or "embalagens")

        normalized_balance = Item.normalize_balance_value(current_balance)
        estimated_packages = 0
        estimated_internal_remainder = normalized_balance
        if supports_packaging and packaging_factor > 0 and normalized_balance >= 0:
            estimated_packages = max(0, int(math.floor((normalized_balance + 1e-6) / packaging_factor)))
            estimated_internal_remainder = Item.normalize_balance_value(normalized_balance - (estimated_packages * packaging_factor))
            if not unit_meta.get("allow_decimal"):
                estimated_internal_remainder = float(round(estimated_internal_remainder))

        package_content_display = None
        if supports_packaging:
            package_content_display = f"{packaging_factor:g} {unit_meta['display']} por {package_name}"

        default_mode = "packages_plus_internal" if supports_packaging else "direct"
        return {
            "supports_packaging": supports_packaging,
            "package_type": packaging_type or None,
            "package_name": package_name,
            "package_plural": package_plural,
            "package_factor": packaging_factor,
            "package_content_display": package_content_display,
            "internal_unit_code": unit_meta["code"],
            "internal_unit_label": unit_meta["label"],
            "internal_unit_display": unit_meta["display"],
            "internal_unit_plural": unit_meta["plural"],
            "internal_step": unit_meta["step"],
            "internal_allow_decimal": bool(unit_meta["allow_decimal"]),
            "estimated_packages": estimated_packages,
            "estimated_internal_remainder": estimated_internal_remainder,
            "current_balance": normalized_balance,
            "default_mode": default_mode,
        }

    @classmethod
    def build_admin_balance_input_fallback(cls, preview: dict[str, Any] | None) -> dict[str, Any]:
        snapshot = dict(preview or {})
        raw_unit = str(snapshot.get("unidade") or "").strip().lower()
        if raw_unit in {"kg", "quilo", "quilos"}:
            unit_code = "kg"
        elif raw_unit in {"l", "lt", "litro", "litros"}:
            unit_code = "l"
        elif raw_unit in {"m", "metro", "metros"}:
            unit_code = "m"
        elif raw_unit in {"par", "pares"}:
            unit_code = "par"
        else:
            unit_code = "un"

        unit_meta = cls._admin_balance_unit_meta(unit_code)
        current_balance = cls._parse_optional_admin_target_balance(snapshot.get("saldo_exibido"))
        normalized_balance = Item.normalize_balance_value(current_balance or 0.0)

        return {
            "supports_packaging": False,
            "package_type": None,
            "package_name": "embalagem",
            "package_plural": "embalagens",
            "package_factor": 0.0,
            "package_content_display": None,
            "internal_unit_code": unit_meta["code"],
            "internal_unit_label": unit_meta["label"],
            "internal_unit_display": unit_meta["display"],
            "internal_unit_plural": unit_meta["plural"],
            "internal_step": unit_meta["step"],
            "internal_allow_decimal": bool(unit_meta["allow_decimal"]),
            "estimated_packages": 0,
            "estimated_internal_remainder": normalized_balance,
            "current_balance": normalized_balance,
            "default_mode": "direct",
        }

    @classmethod
    def _resolve_admin_target_balance_from_inputs(
        cls,
        *,
        item: Any,
        raw_target_balance: Any,
        adjustment_payload: dict[str, Any] | None = None,
    ) -> tuple[float | None, dict[str, Any]]:
        payload = dict(adjustment_payload or {})
        mode = str(payload.get("admin_balance_mode") or "").strip().lower()
        if not mode:
            parsed = cls._parse_optional_admin_target_balance(raw_target_balance)
            return parsed, {}

        context = cls._build_admin_balance_input_context(item=item, current_balance=0.0)
        supports_packaging = bool(context.get("supports_packaging"))
        packaging_factor = float(context.get("package_factor") or 0.0)
        allow_decimal = bool(context.get("internal_allow_decimal"))
        result_context: dict[str, Any] = {"admin_balance_mode": mode}

        if mode == "direct":
            direct_value = payload.get("admin_balance_direct_value")
            parsed = cls._parse_optional_admin_target_balance(direct_value if str(direct_value or "").strip() else raw_target_balance)
            return parsed, result_context

        if mode == "packages":
            if not supports_packaging:
                raise ValueError("Este item não possui embalagem configurada para ajuste por quantidade de embalagens")
            packages = cls._parse_admin_balance_component(
                payload.get("admin_balance_packaging_quantity"),
                label="Quantidade de embalagens",
                allow_blank=False,
                allow_decimal=False,
            )
            target = float(packages or 0.0) * packaging_factor
            result_context.update({
                "package_quantity": packages,
                "package_factor": packaging_factor,
                "target_balance": target,
            })
            return target, result_context

        if mode == "packages_plus_internal":
            if not supports_packaging:
                raise ValueError("Este item não possui embalagem configurada para ajuste por embalagens e saldo interno")
            packages = cls._parse_admin_balance_component(
                payload.get("admin_balance_packaging_quantity"),
                label="Quantidade de embalagens",
                allow_blank=True,
                allow_decimal=False,
            )
            internal = cls._parse_admin_balance_component(
                payload.get("admin_balance_internal_extra"),
                label=f"Quantidade em {context['internal_unit_label']}",
                allow_blank=True,
                allow_decimal=allow_decimal,
            )
            if packages is None and internal is None:
                raise ValueError("Informe a quantidade de embalagens, a sobra interna ou ambos")
            target = (float(packages or 0.0) * packaging_factor) + float(internal or 0.0)
            result_context.update({
                "package_quantity": packages,
                "internal_extra": internal,
                "package_factor": packaging_factor,
                "target_balance": target,
            })
            return target, result_context

        if mode == "internal_only":
            internal = cls._parse_admin_balance_component(
                payload.get("admin_balance_internal_only_value"),
                label=f"Quantidade em {context['internal_unit_label']}",
                allow_blank=False,
                allow_decimal=allow_decimal,
            )
            result_context.update({
                "internal_value": internal,
                "target_balance": internal,
            })
            return internal, result_context

        raise ValueError("Modo de ajuste administrativo inválido")

    def _get_item_code_reference_columns(self) -> list[tuple[str, str]]:
        inspector = inspect(db.engine)
        reference_columns: list[tuple[str, str]] = []
        for table_name in sorted(inspector.get_table_names()):
            column_names = {str(column.get("name")) for column in inspector.get_columns(table_name)}
            for candidate in ("codigo_item", "product_id"):
                if candidate in column_names:
                    reference_columns.append((table_name, candidate))
        return reference_columns

    def change_item_code_admin(
        self,
        *,
        codigo_atual: str,
        novo_codigo: str,
        matricula: str,
        motivo: str,
        audit_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audit_context_norm = dict(audit_context or {})
        codigo_atual_norm = _sanitize_codigo(codigo_atual)
        novo_codigo_norm = _sanitize_codigo(novo_codigo)
        motivo_norm = str(motivo or "").strip()

        if not codigo_atual_norm:
            message = "Informe o código atual do item"
            self._log_admin_code_change_audit(
                action_result="validation_error",
                details=self._build_admin_code_change_audit_details(
                    item=None,
                    codigo_anterior=codigo_atual,
                    codigo_novo=novo_codigo,
                    matricula=matricula,
                    motivo=motivo_norm,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message)

        if not novo_codigo_norm:
            message = "Informe o novo código de barras"
            self._log_admin_code_change_audit(
                action_result="validation_error",
                details=self._build_admin_code_change_audit_details(
                    item=None,
                    codigo_anterior=codigo_atual_norm,
                    codigo_novo=novo_codigo,
                    matricula=matricula,
                    motivo=motivo_norm,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message)

        if not motivo_norm:
            message = "Informe o motivo da alteração do código de barras"
            self._log_admin_code_change_audit(
                action_result="validation_error",
                details=self._build_admin_code_change_audit_details(
                    item=None,
                    codigo_anterior=codigo_atual_norm,
                    codigo_novo=novo_codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message)

        item = Item.query.get(codigo_atual_norm)
        if not item:
            message = "Item não encontrado"
            self._log_admin_code_change_audit(
                action_result="validation_error",
                details=self._build_admin_code_change_audit_details(
                    item=None,
                    codigo_anterior=codigo_atual_norm,
                    codigo_novo=novo_codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    audit_context=audit_context_norm,
                    error_message=message,
                ),
            )
            raise ValueError(message)

        if bool(getattr(item, "pre_cadastro_pendente", False)):
            self._log_admin_code_change_audit(
                action_result="pre_cadastro_blocked",
                details=self._build_admin_code_change_audit_details(
                    item=item,
                    codigo_anterior=codigo_atual_norm,
                    codigo_novo=novo_codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    audit_context=audit_context_norm,
                    error_message=ADMIN_BALANCE_PENDING_PRECADASTRO_MESSAGE,
                ),
            )
            raise ValueError(ADMIN_BALANCE_PENDING_PRECADASTRO_MESSAGE)

        snapshot_before = self.get_admin_balance_snapshot(codigo_atual_norm)
        if novo_codigo_norm == codigo_atual_norm:
            result = {
                "changed": False,
                "codigo_anterior": codigo_atual_norm,
                "codigo_atual": codigo_atual_norm,
                "message": "O item já está com esse código de barras.",
            }
            self._log_admin_code_change_audit(
                action_result="no_change",
                details=self._build_admin_code_change_audit_details(
                    item=item,
                    codigo_anterior=codigo_atual_norm,
                    codigo_novo=novo_codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    audit_context=audit_context_norm,
                    before=snapshot_before,
                    after=snapshot_before,
                    result=result,
                ),
            )
            return result

        if Item.query.get(novo_codigo_norm):
            message = "Código já cadastrado"
            self._log_admin_code_change_audit(
                action_result="validation_error",
                details=self._build_admin_code_change_audit_details(
                    item=item,
                    codigo_anterior=codigo_atual_norm,
                    codigo_novo=novo_codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    audit_context=audit_context_norm,
                    before=snapshot_before,
                    error_message=message,
                ),
            )
            raise ValueError(message)

        reference_columns = self._get_item_code_reference_columns()
        trigger_tables = sorted({table_name for table_name, _ in reference_columns})
        updated_tables: dict[str, int] = {}
        timestamp_now = datetime.utcnow()

        try:
            for table_name in trigger_tables:
                db.session.execute(text(f'ALTER TABLE "{table_name}" DISABLE TRIGGER ALL'))

            for table_name, column_name in reference_columns:
                if table_name == "itens":
                    continue
                result = db.session.execute(
                    text(f'UPDATE "{table_name}" SET "{column_name}" = :novo_codigo WHERE "{column_name}" = :codigo_atual'),
                    {"novo_codigo": novo_codigo_norm, "codigo_atual": codigo_atual_norm},
                )
                updated_tables[table_name] = int(result.rowcount or 0)

            db.session.execute(
                text(
                    'UPDATE "itens" '
                    'SET "codigo_item" = :novo_codigo, "ultima_edicao_em" = :ultima_edicao_em, "ultima_edicao_por" = :ultima_edicao_por '
                    'WHERE "codigo_item" = :codigo_atual'
                ),
                {
                    "novo_codigo": novo_codigo_norm,
                    "codigo_atual": codigo_atual_norm,
                    "ultima_edicao_em": timestamp_now,
                    "ultima_edicao_por": matricula,
                },
            )

            db.session.expire_all()
            item_atualizado = Item.query.get(novo_codigo_norm)
            if item_atualizado is None:
                raise ValueError("Falha ao localizar o item após atualizar o código")

            try:
                barcode_path = generate_barcode(novo_codigo_norm, item_atualizado.descricao)
                item_atualizado.barcode_image_path = barcode_path
            except Exception as barcode_error:
                logger.warning("Não foi possível regenerar barcode administrativo para %s: %s", novo_codigo_norm, barcode_error)
                item_atualizado.barcode_image_path = get_barcode_path(novo_codigo_norm) or item_atualizado.barcode_image_path

            item_atualizado.ultima_edicao_em = timestamp_now
            item_atualizado.ultima_edicao_por = matricula

            for table_name in reversed(trigger_tables):
                db.session.execute(text(f'ALTER TABLE "{table_name}" ENABLE TRIGGER ALL'))

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            self._log_admin_code_change_audit(
                action_result="error",
                details=self._build_admin_code_change_audit_details(
                    item=item,
                    codigo_anterior=codigo_atual_norm,
                    codigo_novo=novo_codigo_norm,
                    matricula=matricula,
                    motivo=motivo_norm,
                    audit_context=audit_context_norm,
                    before=snapshot_before,
                    error_message=str(exc),
                ),
            )
            raise

        self.clear_runtime_cache("search_items_for_autocomplete")
        self.clear_runtime_cache("list_items")
        self.clear_runtime_cache("dashboard_snapshot")

        snapshot_after = self.get_admin_balance_snapshot(novo_codigo_norm)
        result = {
            "changed": True,
            "codigo_anterior": codigo_atual_norm,
            "codigo_atual": novo_codigo_norm,
            "updated_tables": {key: value for key, value in updated_tables.items() if value},
            "message": "Código de barras alterado com sucesso.",
            "before": snapshot_before,
            "after": snapshot_after,
        }
        self._log_admin_code_change_audit(
            action_result="success",
            details=self._build_admin_code_change_audit_details(
                item=Item.query.get(novo_codigo_norm),
                codigo_anterior=codigo_atual_norm,
                codigo_novo=novo_codigo_norm,
                matricula=matricula,
                motivo=motivo_norm,
                audit_context=audit_context_norm,
                before=snapshot_before,
                after=snapshot_after,
                result=result,
            ),
        )
        return result

    def apply_admin_item_adjustments(
        self,
        *,
        codigo_atual: str,
        novo_codigo: str | None,
        novo_saldo: Any,
        adjustment_payload: dict[str, Any] | None = None,
        matricula: str,
        motivo: str,
        audit_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        codigo_atual_norm = _sanitize_codigo(codigo_atual)
        if not codigo_atual_norm:
            raise ValueError("Informe o código do item")

        motivo_norm = str(motivo or "").strip()
        novo_codigo_norm = _sanitize_codigo(novo_codigo) or codigo_atual_norm
        audit_context_norm = dict(audit_context or {})
        current_item = Item.query.get(codigo_atual_norm)
        if not current_item:
            raise ValueError("Item não encontrado")

        target_balance, target_context = self._resolve_admin_target_balance_from_inputs(
            item=current_item,
            raw_target_balance=novo_saldo,
            adjustment_payload=adjustment_payload,
        )
        audit_context_norm.update(target_context)

        code_audit_context = dict(audit_context_norm)
        code_audit_context["codigo_item_anterior"] = codigo_atual_norm
        code_audit_context["codigo_item_novo"] = novo_codigo_norm or None
        if motivo_norm:
            code_audit_context["reason"] = motivo_norm

        balance_audit_context = dict(audit_context_norm)
        if motivo_norm:
            balance_audit_context["reason"] = motivo_norm
        if target_balance is not None:
            balance_audit_context["target_balance"] = target_balance

        mensagens: list[str] = []
        houve_alteracao = False
        codigo_final = codigo_atual_norm
        code_result: dict[str, Any] | None = None
        balance_result: dict[str, Any] | None = None

        if novo_codigo_norm != codigo_atual_norm:
            code_result = self.change_item_code_admin(
                codigo_atual=codigo_atual_norm,
                novo_codigo=novo_codigo_norm,
                matricula=matricula,
                motivo=motivo_norm,
                audit_context=code_audit_context,
            )
            codigo_final = str(code_result.get("codigo_atual") or codigo_final)
            if code_result.get("message"):
                mensagens.append(str(code_result.get("message")))
            houve_alteracao = bool(code_result.get("changed")) or houve_alteracao

        if target_balance is not None:
            snapshot = self.get_admin_balance_snapshot(codigo_final)
            saldo_atual = float(snapshot.get("saldo_exibido") or 0.0)
            if not self._balance_close(saldo_atual, target_balance):
                balance_result = self.set_admin_absolute_balance(
                    codigo=codigo_final,
                    novo_saldo=target_balance,
                    matricula=matricula,
                    motivo=motivo_norm,
                    audit_context=balance_audit_context,
                )
                if balance_result.get("message"):
                    mensagens.append(str(balance_result.get("message")))
                houve_alteracao = bool(balance_result.get("changed")) or houve_alteracao

        if not mensagens:
            mensagens.append("Nenhuma alteração adicional era necessária.")

        return {
            "changed": houve_alteracao,
            "codigo_anterior": codigo_atual_norm,
            "codigo_atual": codigo_final,
            "message": " ".join(mensagens),
            "code_result": code_result,
            "balance_result": balance_result,
        }

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
        admin_balance_input = self._build_admin_balance_input_context(item=item, current_balance=saldo_exibido)

        return {
            "codigo": item.codigo_item,
            "descricao": item.descricao,
            "categoria": item.categoria,
            "marca": item.marca,
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
            "admin_balance_input": admin_balance_input,
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
        unit_text = str(item.unidade or "un").strip()
        unit_key = unit_text.lower()
        is_single_unit = abs(normalized_balance - 1.0) <= 1e-6
        if unit_key in {"un", "unidade", "unidades"}:
            unit_text = "unidade" if is_single_unit else "unidades"
        elif unit_key in {"par", "pares"}:
            unit_text = "par" if is_single_unit else "pares"
        return f"{normalized_balance:g} {unit_text}"

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

    @staticmethod
    def _normalize_material_return_unit_code(value: str | None) -> str:
        raw = (value or "").strip().lower()
        if not raw:
            return ""
        return MATERIAL_RETURN_UNIT_ALIASES.get(raw, "")

    @classmethod
    def _build_material_return_unit_meta(cls, unit_code: str) -> dict[str, Any]:
        normalized = cls._normalize_material_return_unit_code(unit_code) or "unidade"
        meta = MATERIAL_RETURN_UNIT_META.get(normalized, MATERIAL_RETURN_UNIT_META["unidade"])
        return {
            "unit_code": normalized,
            "unit_display": str(meta["unit_display"]),
            "unit_label": str(meta["unit_label"]),
            "allow_decimal": bool(meta["allow_decimal"]),
            "input_step": meta["input_step"],
            "input_min": meta["input_min"],
        }

    @staticmethod
    def _build_material_return_lookup_text(*values: object) -> str:
        parts = [_normalize_operational_lookup(value) for value in values]
        return " ".join(part for part in parts if part).strip()

    @staticmethod
    def _material_return_text_prefers_liquid_unit(text: str) -> bool:
        return bool(
            text
            and MATERIAL_RETURN_LIQUID_MEASURE_RE.search(text)
            and any(keyword in text for keyword in MATERIAL_RETURN_LIQUID_HINTS)
        )

    @staticmethod
    def _material_return_text_prefers_weight_unit(text: str) -> bool:
        return bool(
            text
            and MATERIAL_RETURN_WEIGHT_MEASURE_RE.search(text)
            and any(keyword in text for keyword in MATERIAL_RETURN_WEIGHT_HINTS)
        )

    def _resolve_material_return_primary_unit_code(self, item: Item) -> str:
        tipo_embalagem = _normalize_operational_lookup(getattr(item, "tipo_embalagem_novo", None))
        unidade_item = self._normalize_material_return_unit_code(getattr(item, "unidade", None))
        litros_por_embalagem = self._as_positive_float(getattr(item, "litros_por_embalagem", None))
        grandeza_referencia = self._as_positive_float(getattr(item, "grandeza_referencia", None))
        unidades_por_embalagem = self._as_positive_float(getattr(item, "unidades_por_embalagem", None))
        lookup_text = self._build_material_return_lookup_text(
            getattr(item, "categoria", None),
            getattr(item, "descricao", None),
        )

        product_units = sorted(
            getattr(item, "product_units", []) or [],
            key=lambda row: (
                self._normalize_material_return_unit_code(getattr(row, "unit_code", None)) == "unidade",
                not bool(getattr(row, "is_base", False)),
                (getattr(row, "unit_code", None) or ""),
                getattr(row, "id", 0) or 0,
            ),
        )
        for unit in product_units:
            if not bool(getattr(unit, "active", False)):
                continue
            normalized = self._normalize_material_return_unit_code(getattr(unit, "unit_code", None))
            if normalized in {"litro", "quilo", "metro"}:
                return normalized

        if litros_por_embalagem > 0 or self._material_return_text_prefers_liquid_unit(lookup_text):
            return "litro"

        if tipo_embalagem == "rolo" and unidades_por_embalagem > 0:
            return "metro"

        canonical_unit = self._normalize_material_return_unit_code(resolve_canonical_unit(item))
        if canonical_unit:
            return canonical_unit

        if grandeza_referencia > 0 or self._material_return_text_prefers_weight_unit(lookup_text):
            return "quilo"

        if tipo_embalagem in {"pacote", "caixa", "fardo", "saco"}:
            return "unidade"

        if tipo_embalagem in MATERIAL_RETURN_FRACTIONABLE_PACKAGING_TYPES and unidade_item in {"litro", "quilo", "metro"}:
            return unidade_item

        if unidade_item:
            return unidade_item

        for unit in product_units:
            normalized = self._normalize_material_return_unit_code(getattr(unit, "unit_code", None))
            if normalized:
                return normalized

        return "unidade"

    def get_material_return_unit_options(self, *, item: Item | None = None, codigo: str | None = None) -> list[dict[str, Any]]:
        item_model = item
        if item_model is None:
            codigo_norm = (codigo or "").strip()
            if not codigo_norm:
                return []
            item_model = Item.query.get(codigo_norm)
        if item_model is None:
            return []

        options: list[dict[str, Any]] = []
        seen_units: set[str] = set()

        def add_option(raw_unit: str | None) -> None:
            normalized = self._normalize_material_return_unit_code(raw_unit)
            if not normalized or normalized in seen_units:
                return
            seen_units.add(normalized)
            options.append(self._build_material_return_unit_meta(normalized))

        add_option(self._resolve_material_return_primary_unit_code(item_model))
        if not options:
            add_option("unidade")

        return options

    def _get_default_material_return_unit_code(self, item: Item) -> str:
        options = self.get_material_return_unit_options(item=item)
        if not options:
            return "unidade"
        return str(options[0].get("unit_code") or "unidade")

    @classmethod
    def _extract_material_return_unit_from_text(cls, text: str | None) -> str:
        normalized = " ".join(str(text or "").strip().lower().split())
        if not normalized:
            return ""

        explicit_marker = re.search(r"retorno_unit\s*=\s*([a-zç]+)", normalized)
        if explicit_marker:
            return cls._normalize_material_return_unit_code(explicit_marker.group(1))

        for pattern in (
            r"retirada fracionada:\s*[\d.,]+\s*([a-zç]+)",
            r"devolvido:\s*[\d.,]+\s*([a-zç]+)",
            r"unidade:\s*([a-zç]+)",
        ):
            match = re.search(pattern, normalized)
            if match:
                parsed = cls._normalize_material_return_unit_code(match.group(1))
                if parsed:
                    return parsed
        return ""

    def _convert_material_quantity_between_units(
        self,
        *,
        item: Item,
        quantity: float,
        from_unit: str,
        to_unit: str,
    ) -> float:
        quantity_value = self._as_positive_float(quantity)
        if quantity_value <= 0:
            return 0.0

        from_raw = (from_unit or "").strip().lower()
        to_raw = (to_unit or "").strip().lower()
        from_code = self._normalize_material_return_unit_code(from_raw) or from_raw
        to_code = self._normalize_material_return_unit_code(to_raw) or to_raw

        if not from_code or not to_code:
            return 0.0
        if from_code == to_code:
            return quantity_value

        try:
            quantity_base = float(unit_conversion_engine.convert_item_to_base(item, quantity_value, from_code).quantity_base)
            target_factor = float(unit_conversion_engine.convert_item_to_base(item, 1.0, to_code).quantity_base)
            if target_factor <= 0:
                return 0.0
            return quantity_base / target_factor
        except UnitConversionError:
            return 0.0

    def _resolve_saida_pending_quantity(
        self,
        *,
        item: Item,
        saida: Saida,
        target_unit: str,
        default_unit: str,
    ) -> float:
        quantity_l = self._as_positive_float(getattr(saida, "quantidade_retirada_em_litros", None))
        quantity_kg = self._as_positive_float(getattr(saida, "quantidade_retirada_em_quilos", None))

        if target_unit == "litro" and quantity_l > 0:
            return quantity_l
        if target_unit == "quilo" and quantity_kg > 0:
            return quantity_kg
        if quantity_l > 0:
            return self._convert_material_quantity_between_units(
                item=item,
                quantity=quantity_l,
                from_unit="litro",
                to_unit=target_unit,
            )
        if quantity_kg > 0:
            return self._convert_material_quantity_between_units(
                item=item,
                quantity=quantity_kg,
                from_unit="quilo",
                to_unit=target_unit,
            )

        quantity_value = self._as_positive_float(saida.quantidade)
        if quantity_value <= 0:
            return 0.0

        observed_unit = self._extract_material_return_unit_from_text(getattr(saida, "observacao", None))
        if observed_unit:
            converted = self._convert_material_quantity_between_units(
                item=item,
                quantity=quantity_value,
                from_unit=observed_unit,
                to_unit=target_unit,
            )
            if converted > 0:
                return converted

        packaging_unit = (getattr(item, "tipo_embalagem_novo", None) or getattr(item, "unidade", None) or "").strip().lower()
        if packaging_unit and is_packaging_unit_code(packaging_unit):
            converted = self._convert_material_quantity_between_units(
                item=item,
                quantity=quantity_value,
                from_unit=packaging_unit,
                to_unit=target_unit,
            )
            if converted > 0:
                return converted

        converted = self._convert_material_quantity_between_units(
            item=item,
            quantity=quantity_value,
            from_unit=default_unit,
            to_unit=target_unit,
        )
        if converted > 0:
            return converted
        return quantity_value if default_unit == target_unit else 0.0

    def _build_material_return_timeline(
        self,
        *,
        codigo: str,
        matricula: str,
        end_datetime: datetime | None = None,
    ) -> list[tuple[datetime, int, str, Any, int]]:
        timeline: list[tuple[datetime, int, str, Any, int]] = []

        saidas_query = (
            Saida.query
            .filter(Saida.codigo_item == codigo, Saida.matricula == matricula)
            .order_by(Saida.data_saida.asc(), Saida.id_saida.asc())
        )
        if end_datetime is not None:
            saidas_query = saidas_query.filter(Saida.data_saida <= end_datetime)
        for saida in saidas_query.all():
            timeline.append((saida.data_saida or datetime.min, 0, "saida", saida, int(saida.id_saida or 0)))

        eventos_query = (
            InventarioEvento.query
            .filter(
                InventarioEvento.codigo_item == codigo,
                InventarioEvento.matricula == matricula,
                InventarioEvento.tipo == "devolucao_material",
            )
            .order_by(InventarioEvento.data_evento.asc(), InventarioEvento.id_evento.asc())
        )
        if end_datetime is not None:
            eventos_query = eventos_query.filter(InventarioEvento.data_evento <= end_datetime)
        for evento in eventos_query.all():
            timeline.append((evento.data_evento or datetime.min, 1, "devolucao_material", evento, int(evento.id_evento or 0)))

        entradas_query = (
            Entrada.query
            .filter(
                Entrada.codigo_item == codigo,
                Entrada.matricula == matricula,
                Entrada.nota_fiscal.is_(None),
            )
            .order_by(Entrada.data_entrada.asc(), Entrada.id_entrada.asc())
        )
        if end_datetime is not None:
            entradas_query = entradas_query.filter(Entrada.data_entrada <= end_datetime)
        for entrada in entradas_query.all():
            timeline.append((entrada.data_entrada or datetime.min, 2, "entrada_legado", entrada, int(entrada.id_entrada or 0)))

        timeline.sort(key=lambda row: (row[0], row[1], row[4]))
        return timeline

    def _calculate_material_return_pending_from_timeline(
        self,
        *,
        item: Item,
        timeline: list[tuple[datetime, int, str, Any, int]],
        target_unit: str,
        default_unit: str,
        window_start: datetime | None = None,
    ) -> float:
        pending_before_window = 0.0
        pending_in_window = 0.0

        for event_datetime, _order_index, kind, row, _reference_id in timeline:
            quantidade = 0.0
            if kind == "saida":
                quantidade = self._resolve_saida_pending_quantity(
                    item=item,
                    saida=row,
                    target_unit=target_unit,
                    default_unit=default_unit,
                )
            elif kind == "devolucao_material":
                source_unit = self._extract_material_return_unit_from_text(getattr(row, "descricao", None)) or default_unit
                quantidade = self._convert_material_quantity_between_units(
                    item=item,
                    quantity=self._as_positive_float(getattr(row, "quantidade", 0.0)),
                    from_unit=source_unit,
                    to_unit=target_unit,
                )
            else:
                quantidade = self._convert_material_quantity_between_units(
                    item=item,
                    quantity=self._as_positive_float(getattr(row, "quantidade", 0.0)),
                    from_unit=default_unit,
                    to_unit=target_unit,
                )

            if quantidade <= 0:
                continue

            within_window = window_start is None or event_datetime >= window_start
            if kind == "saida":
                if within_window:
                    pending_in_window += quantidade
                else:
                    pending_before_window += quantidade
                continue

            remaining = quantidade
            if pending_before_window > 0:
                abatido_historico = min(pending_before_window, remaining)
                pending_before_window -= abatido_historico
                remaining -= abatido_historico

            if remaining > 0:
                pending_in_window = max(pending_in_window - remaining, 0.0)

        total_pending = pending_in_window if window_start is not None else (pending_before_window + pending_in_window)
        return float(round(total_pending, 3))

    def get_material_return_pending(self, *, codigo: str, matricula: str, unit_code: str | None = None) -> float:
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

        item = Item.query.get(codigo_norm)
        if item is None:
            return 0.0

        default_unit = self._get_default_material_return_unit_code(item)
        target_unit = self._normalize_material_return_unit_code(unit_code) or default_unit

        timeline = self._build_material_return_timeline(
            codigo=codigo_norm,
            matricula=matricula_norm,
        )
        return self._calculate_material_return_pending_from_timeline(
            item=item,
            timeline=timeline,
            target_unit=target_unit,
            default_unit=default_unit,
            window_start=None,
        )

    def get_material_return_pending_in_window(
        self,
        *,
        codigo: str,
        matricula: str,
        start_datetime: datetime,
        end_datetime: datetime,
        unit_code: str | None = None,
    ) -> float:
        codigo_norm = (codigo or "").strip()
        matricula_norm = (matricula or "").strip()
        if not codigo_norm or not matricula_norm:
            return 0.0
        if start_datetime is None or end_datetime is None or start_datetime > end_datetime:
            return 0.0

        item = Item.query.get(codigo_norm)
        if item is None:
            return 0.0

        default_unit = self._get_default_material_return_unit_code(item)
        target_unit = self._normalize_material_return_unit_code(unit_code) or default_unit
        timeline = self._build_material_return_timeline(
            codigo=codigo_norm,
            matricula=matricula_norm,
            end_datetime=end_datetime,
        )
        return self._calculate_material_return_pending_from_timeline(
            item=item,
            timeline=timeline,
            target_unit=target_unit,
            default_unit=default_unit,
            window_start=start_datetime,
        )

    def get_latest_material_return_holder(
        self,
        *,
        codigo: str,
        unit_code: str | None = None,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> dict[str, Any] | None:
        codigo_norm = (codigo or "").strip()
        if not codigo_norm:
            return None
        if start_datetime is not None and end_datetime is not None and start_datetime > end_datetime:
            return None

        item = Item.query.get(codigo_norm)
        if item is None:
            return None

        default_unit = self._get_default_material_return_unit_code(item)
        target_unit = self._normalize_material_return_unit_code(unit_code) or default_unit
        query = Saida.query.filter(Saida.codigo_item == codigo_norm)
        if start_datetime is not None:
            query = query.filter(Saida.data_saida >= start_datetime)
        if end_datetime is not None:
            query = query.filter(Saida.data_saida <= end_datetime)

        seen_users: set[str] = set()
        for saida in query.order_by(Saida.data_saida.desc(), Saida.id_saida.desc()).all():
            retirada_matricula = str(saida.matricula or "").strip()
            if not retirada_matricula or retirada_matricula in seen_users:
                continue
            seen_users.add(retirada_matricula)

            if start_datetime is not None and end_datetime is not None:
                pendente = self.get_material_return_pending_in_window(
                    codigo=codigo_norm,
                    matricula=retirada_matricula,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    unit_code=target_unit,
                )
            else:
                pendente = self.get_material_return_pending(
                    codigo=codigo_norm,
                    matricula=retirada_matricula,
                    unit_code=target_unit,
                )
            if pendente <= 1e-9:
                continue

            usuario = saida.usuario or Usuario.query.get(retirada_matricula)
            nome_usuario = getattr(usuario, "nome", None) or None
            return {
                "matricula": retirada_matricula,
                "nome": nome_usuario,
                "label": format_material_return_actor_label(nome=nome_usuario, matricula=retirada_matricula),
                "pendente": float(round(pendente, 3)),
                "ultima_saida_em": saida.data_saida,
                "ultima_saida_label": TimeService.format_local(saida.data_saida),
                "local_servico": (saida.local_servico or "").strip() or None,
                "atividade_operacional": getattr(saida, "atividade_operacional", None),
                "saida_id": getattr(saida, "id_saida", None),
            }

        return None

    @staticmethod
    def _normalize_express_material_return_scope(scope: str | None) -> str:
        raw = (scope or "").strip().lower()
        if raw in {"fracionada", "fracionado", "fractional"}:
            return "fracionada"
        if raw in {"padrao", "saida", "comum", "material", "materiais", "regular", "normal"}:
            return "padrao"
        return "todos"

    @classmethod
    def _matches_express_material_return_scope(cls, saida: Saida, scope: str | None) -> bool:
        normalized_scope = cls._normalize_express_material_return_scope(scope)
        uses_fraction = bool(getattr(saida, "usou_fracao", False))
        if normalized_scope == "fracionada":
            return uses_fraction
        if normalized_scope == "padrao":
            return not uses_fraction
        return True

    def list_express_material_return_collaborators(
        self,
        *,
        start_datetime: datetime,
        end_datetime: datetime,
        scope: str = "todos",
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        scope_norm = self._normalize_express_material_return_scope(scope)
        if start_datetime is None or end_datetime is None or start_datetime > end_datetime:
            return []

        registros = (
            Saida.query
            .filter(
                Saida.data_saida >= start_datetime,
                Saida.data_saida <= end_datetime,
            )
            .order_by(Saida.data_saida.desc(), Saida.id_saida.desc())
            .all()
        )

        latest_by_matricula: dict[str, dict[str, Any]] = {}
        for saida in registros:
            matricula_norm = str(saida.matricula or "").strip()
            if not matricula_norm or matricula_norm in latest_by_matricula:
                continue
            if not self._matches_express_material_return_scope(saida, scope_norm):
                continue

            item_model = saida.item or Item.query.get(saida.codigo_item)
            if item_model is None:
                continue

            categoria_norm = str(item_model.categoria or "").strip().lower()
            if "ferrament" in categoria_norm:
                continue

            latest_by_matricula[matricula_norm] = {
                "usuario": saida.usuario or Usuario.query.get(matricula_norm),
                "ultima_saida_em": saida.data_saida,
                "local_servico": (saida.local_servico or "").strip() or None,
                "atividade_operacional": getattr(saida, "atividade_operacional", None),
            }

        collaborators: list[dict[str, Any]] = []
        for matricula_norm, info in latest_by_matricula.items():
            items = self.list_express_material_return_candidates(
                matricula=matricula_norm,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                limit=80,
                scope=scope_norm,
            )
            if not items:
                continue

            usuario = info.get("usuario")
            nome_usuario = getattr(usuario, "nome", None) or None
            preview_items = [
                str(item.get("descricao") or item.get("codigo") or "").strip()
                for item in items[:2]
                if str(item.get("descricao") or item.get("codigo") or "").strip()
            ]

            collaborators.append(
                {
                    "matricula": matricula_norm,
                    "nome": nome_usuario,
                    "label": format_material_return_actor_label(nome=nome_usuario, matricula=matricula_norm),
                    "total_items": len(items),
                    "preview_items": preview_items,
                    "ultima_saida_label": TimeService.format_local(info.get("ultima_saida_em")) if info.get("ultima_saida_em") else None,
                    "local_servico": info.get("local_servico"),
                    "atividade_operacional": info.get("atividade_operacional"),
                }
            )
            if len(collaborators) >= max(1, int(limit or 0)):
                break

        return collaborators

    def list_express_material_return_candidates(
        self,
        *,
        matricula: str,
        start_datetime: datetime,
        end_datetime: datetime,
        limit: int = 80,
        scope: str = "todos",
    ) -> list[dict[str, Any]]:
        matricula_norm = (matricula or "").strip()
        scope_norm = self._normalize_express_material_return_scope(scope)
        if not matricula_norm or start_datetime is None or end_datetime is None or start_datetime > end_datetime:
            return []

        registros = (
            Saida.query
            .filter(
                Saida.matricula == matricula_norm,
                Saida.data_saida >= start_datetime,
                Saida.data_saida <= end_datetime,
            )
            .order_by(Saida.data_saida.desc(), Saida.id_saida.desc())
            .all()
        )

        agrupados: dict[str, dict[str, Any]] = {}
        for saida in registros:
            codigo_item = (saida.codigo_item or "").strip()
            if not codigo_item:
                continue
            if not self._matches_express_material_return_scope(saida, scope_norm):
                continue

            item_model = saida.item or Item.query.get(codigo_item)
            if item_model is None:
                continue

            categoria_norm = str(item_model.categoria or "").strip().lower()
            if "ferrament" in categoria_norm:
                continue

            default_unit = self._get_default_material_return_unit_code(item_model)
            quantidade_retirada = self._resolve_saida_pending_quantity(
                item=item_model,
                saida=saida,
                target_unit=default_unit,
                default_unit=default_unit,
            )
            if quantidade_retirada <= 0:
                continue

            bucket = agrupados.get(codigo_item)
            if bucket is None:
                bucket = {
                    "codigo": codigo_item,
                    "descricao": item_model.descricao or codigo_item,
                    "categoria": item_model.categoria,
                    "marca": item_model.marca,
                    "local_servico": saida.local_servico,
                    "atividade_operacional": getattr(saida, "atividade_operacional", None),
                    "unidade_codigo": default_unit,
                    "unidade_meta": self._build_material_return_unit_meta(default_unit),
                    "unidades_opcoes": self.get_material_return_unit_options(item=item_model),
                    "retirado_hoje": 0.0,
                    "ultima_saida_em": saida.data_saida,
                    "modo_fracionado": bool(getattr(saida, "usou_fracao", False)),
                }
                agrupados[codigo_item] = bucket

            bucket["retirado_hoje"] = float(bucket.get("retirado_hoje") or 0.0) + quantidade_retirada
            ultima_saida_em = bucket.get("ultima_saida_em")
            if not ultima_saida_em or (saida.data_saida and saida.data_saida > ultima_saida_em):
                bucket["ultima_saida_em"] = saida.data_saida
                bucket["local_servico"] = saida.local_servico
                bucket["atividade_operacional"] = getattr(saida, "atividade_operacional", None)
                bucket["modo_fracionado"] = bool(getattr(saida, "usou_fracao", False))

        candidatos: list[dict[str, Any]] = []
        for codigo_item, bucket in agrupados.items():
            unidade_codigo = str(bucket.get("unidade_codigo") or "unidade")
            pendente_hoje = self.get_material_return_pending_in_window(
                codigo=codigo_item,
                matricula=matricula_norm,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                unit_code=unidade_codigo,
            )
            if pendente_hoje <= 1e-9:
                continue

            unidade_meta = dict(bucket.get("unidade_meta") or self._build_material_return_unit_meta(unidade_codigo))
            retirado_hoje = float(bucket.get("retirado_hoje") or 0.0)
            ultima_saida_em = bucket.get("ultima_saida_em")
            candidatos.append(
                {
                    "codigo": codigo_item,
                    "descricao": bucket.get("descricao"),
                    "categoria": bucket.get("categoria"),
                    "marca": bucket.get("marca"),
                    "local_servico": bucket.get("local_servico"),
                    "atividade_operacional": bucket.get("atividade_operacional"),
                    "retirado_hoje": float(round(retirado_hoje, 3)),
                    "retirado_hoje_display": f"{round(retirado_hoje, 3):g} {unidade_meta.get('unit_display')}",
                    "pendente_hoje": float(round(pendente_hoje, 3)),
                    "pendente_hoje_display": f"{round(pendente_hoje, 3):g} {unidade_meta.get('unit_display')}",
                    "devolucao_unidade_codigo": unidade_codigo,
                    "devolucao_unidade_exibicao": unidade_meta.get("unit_display"),
                    "devolucao_unidade_label": unidade_meta.get("unit_label"),
                    "devolucao_unidades_opcoes": bucket.get("unidades_opcoes") or [unidade_meta],
                    "modo_fracionado": bool(bucket.get("modo_fracionado")),
                    "ultima_saida_em": TimeService.isoformat_utc(ultima_saida_em),
                    "ultima_saida_label": TimeService.format_local(ultima_saida_em),
                }
            )

        candidatos.sort(
            key=lambda row: (row.get("ultima_saida_em") or "", row.get("descricao") or "", row.get("codigo") or ""),
            reverse=True,
        )
        return candidatos[:limit]

    def registrar_devolucao_material(
        self,
        *,
        codigo: str,
        quantidade: float,
        matricula: str | None = None,
        retirada_matricula: str | None = None,
        devolvido_por_matricula: str | None = None,
        from_unit: str | None = None,
        observacao: str | None = None,
        commit: bool = True,
    ) -> InventarioEvento:
        """Registra devolução de material como um InventarioEvento.

        Importante:
        - Não cria Entrada (evita devolução virar 'adição' duplicada).
        - Bloqueia devolução acima do pendente por funcionário/item.
        - Permite separar o colaborador que retirou do colaborador que está devolvendo.
        """
        codigo_norm = (codigo or "").strip()
        matricula_legado = (matricula or "").strip()
        retirada_matricula_norm = (retirada_matricula or matricula_legado).strip()
        devolvido_por_matricula_norm = (devolvido_por_matricula or matricula_legado).strip()
        if not codigo_norm:
            raise ValueError("Código do item é obrigatório")

        quantidade_f = self._as_positive_float(quantidade)
        if quantidade_f <= 0:
            raise ValueError("Quantidade inválida")

        item = Item.query.get(codigo_norm)
        if not item:
            raise ValueError("Item não encontrado")

        categoria_text = (item.categoria or "").strip().lower()
        if "ferrament" in categoria_text:
            raise ValueError("Use a devolução de ferramentas para este item")

        default_unit = self._get_default_material_return_unit_code(item)
        selected_unit = self._normalize_material_return_unit_code(from_unit) or default_unit
        unit_options = self.get_material_return_unit_options(item=item)
        valid_units = {str(option.get("unit_code") or "") for option in unit_options}
        if selected_unit not in valid_units:
            raise ValueError("Unidade de devolução inválida para este item.")

        if not retirada_matricula_norm:
            retirada_info = self.get_latest_material_return_holder(
                codigo=codigo_norm,
                unit_code=selected_unit,
            )
            if not retirada_info:
                raise ValueError("Devolução não permitida: não há retirada pendente para este material.")
            retirada_matricula_norm = str(retirada_info.get("matricula") or "").strip()

        if not devolvido_por_matricula_norm:
            raise ValueError("Informe quem está devolvendo o material.")

        unit_meta = self._build_material_return_unit_meta(selected_unit)
        pendente = self.get_material_return_pending(
            codigo=codigo_norm,
            matricula=retirada_matricula_norm,
            unit_code=selected_unit,
        )
        # Tolerância mínima para float.
        if pendente <= 1e-9:
            raise ValueError("Devolução não permitida: não há retirada pendente para este material.")
        if quantidade_f > pendente + 1e-9:
            raise ValueError(
                f"Devolução excede o pendente. Pendente: {pendente:g} {unit_meta['unit_display']}"
            )

        quantidade_legacy = self._convert_material_quantity_between_units(
            item=item,
            quantity=quantidade_f,
            from_unit=selected_unit,
            to_unit=default_unit,
        )
        if quantidade_legacy <= 0:
            raise ValueError("Não foi possível converter a unidade informada para registrar a devolução.")

        retirante_usuario = Usuario.query.get(retirada_matricula_norm)
        devolvedor_usuario = Usuario.query.get(devolvido_por_matricula_norm)
        retirante_label = format_material_return_actor_label(
            nome=getattr(retirante_usuario, "nome", None),
            matricula=retirada_matricula_norm,
        )
        devolvedor_label = format_material_return_actor_label(
            nome=getattr(devolvedor_usuario, "nome", None),
            matricula=devolvido_por_matricula_norm,
        )

        descricao_base = f"Devolução de Material: {item.descricao or 'Item'}"
        obs = (observacao or "").strip()
        detalhes_devolucao = f"Devolvido: {quantidade_f:g} {unit_meta['unit_display']} | retorno_unit={selected_unit}"
        descricao = " | ".join(
            part
            for part in (
                descricao_base,
                detalhes_devolucao,
                f"Retirado por: {retirante_label}" if retirante_label else None,
                f"Devolvido por: {devolvedor_label}" if devolvedor_label else None,
                obs,
            )
            if part
        )

        payload = MovimentoPayload(
            codigo=item.codigo_item,
            quantidade=float(quantidade_f),
            matricula=devolvido_por_matricula_norm,
            observacao=obs or None,
            is_devolucao=True,
        )
        ledger_result = self._mirror_payload_to_ledger(
            item=item,
            payload=payload,
            movement_type="devolucao",
            from_unit=selected_unit,
            metadata={
                "reference_type": "inventario_evento",
                "legacy_event_type": "devolucao_material",
                "return_unit": selected_unit,
                "withdrawer_matricula": retirada_matricula_norm,
                "returner_matricula": devolvido_por_matricula_norm,
            },
        )

        evento = InventarioEvento(
            codigo_item=item.codigo_item,
            matricula=retirada_matricula_norm,
            tipo="devolucao_material",
            quantidade=float(quantidade_legacy),
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
    def _normalize_exit_channel(value: str | None, payload: MovimentoPayload | None = None) -> str:
        raw = (value or "").strip().lower()
        if not raw and payload and payload.modo_fracionado:
            raw = "fracionado"
        if not raw:
            raw = "materiais"
        normalized = unicode_normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
        return normalized.replace(" ", "_")

    @staticmethod
    def _is_tool_item(item: Item | None) -> bool:
        if item is None:
            return False
        return "ferrament" in str(getattr(item, "categoria", "") or "").lower()

    @staticmethod
    def _is_mass_or_volume_item(item: Item | None) -> bool:
        if item is None:
            return False
        canonical_unit = (resolve_canonical_unit(item) or "").strip().lower()
        if canonical_unit in {"kg", "l"}:
            return True
        unidade = str(getattr(item, "unidade", "") or "").strip().lower()
        if normalize_base_item_unit(unidade) in {"Quilo", "Litro"}:
            return True
        if InventoryService._as_positive_float(getattr(item, "litros_por_embalagem", None)) > 0:
            return True
        grandeza = InventoryService._as_positive_float(getattr(item, "grandeza_referencia", None))
        return grandeza > 0 and any(token in unidade for token in ("kg", "quilo", "litro", "lt"))

    @staticmethod
    def _fractional_payload_unit(item: Item, payload: MovimentoPayload) -> str | None:
        if not payload.modo_fracionado:
            return None
        if InventoryService._as_positive_float(payload.quantidade_retirada_em_litros) > 0:
            return "l"
        if InventoryService._as_positive_float(payload.quantidade_retirada_em_quilos) > 0:
            return "kg"
        if payload.em_embalagens is False:
            canonical_unit = (resolve_canonical_unit(item) or "").strip().lower()
            return canonical_unit or None
        return None

    @staticmethod
    def _package_factor_for_operational_policy(item: Item) -> float:
        factor = InventoryService._as_positive_float(resolve_packaging_factor(item))
        if factor > 0:
            return factor
        canonical_unit = (resolve_canonical_unit(item) or "").strip().lower()
        if canonical_unit == "l":
            return InventoryService._as_positive_float(getattr(item, "litros_por_embalagem", None))
        if canonical_unit == "kg":
            return InventoryService._as_positive_float(getattr(item, "grandeza_referencia", None))
        return 0.0

    @staticmethod
    def _is_full_package_exit(item: Item, payload: MovimentoPayload) -> bool:
        if payload.em_embalagens is True:
            return True

        try:
            quantity_value, unit_value = InventoryService._resolve_ledger_input_for_mirror(
                item,
                payload,
                metadata={"reference_type": "legacy_movimento"},
            )
            quantity_base = float(
                unit_conversion_engine.convert_item_to_base(item, quantity_value, unit_value).quantity_base or 0.0
            )
        except Exception:
            quantity_base = InventoryService._as_positive_float(getattr(payload, "quantidade", None))

        if quantity_base <= 0:
            return False

        package_factor = InventoryService._package_factor_for_operational_policy(item)
        if package_factor <= 0:
            return math.isclose(quantity_base, round(quantity_base), rel_tol=0.0, abs_tol=1e-6)

        package_count = quantity_base / package_factor
        return math.isclose(package_count, round(package_count), rel_tol=0.0, abs_tol=1e-6)

    def validate_exit_payload_policy(self, item: Item, payload: MovimentoPayload) -> None:
        channel = self._normalize_exit_channel(getattr(payload, "canal_saida", None), payload)
        is_tool = self._is_tool_item(item)

        if is_tool:
            if payload.modo_fracionado or channel in FRACTIONAL_EXIT_CHANNELS:
                raise ValueError("Ferramentas não podem sair no fracionado. Use o fluxo de Ferramentas/Custódia.")
            if channel not in TOOL_EXIT_CHANNELS:
                raise ValueError("Ferramentas só podem sair pelo fluxo de Ferramentas/Custódia.")
            return

        if payload.modo_fracionado or channel in FRACTIONAL_EXIT_CHANNELS:
            if payload.is_devolucao:
                raise ValueError("Devolução não é registrada pelo fracionado.")
            fractional_unit = self._fractional_payload_unit(item, payload)
            if fractional_unit not in {"kg", "l", "m"}:
                raise ValueError("Saída fracionada aceita apenas materiais em kg, litros ou metros.")
            if fractional_unit in {"kg", "l"} and not self._is_mass_or_volume_item(item):
                raise ValueError("Este item não pertence à régua de fracionado em kg/L.")
            return

        if self._is_mass_or_volume_item(item) and not self._is_full_package_exit(item, payload):
            raise ValueError(
                "Materiais em kg/L no fluxo comum só podem sair por embalagem completa/total da NF. "
                "Use Saída Fracionada para retirar 3 kg, 2 kg, 1,5 kg, 1 L, 2 L ou 1,5 L."
            )

    @staticmethod
    def _should_use_packaging_dual_write(
        item: Item,
        payload: MovimentoPayload | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        packaging_factor = float(resolve_packaging_factor(item) or 0.0)
        if packaging_factor <= 1.0 or ignore_packaging_metadata_for_stock(item):
            return False

        base_unit = next((unit for unit in item.product_units if unit.is_base and unit.active), None)
        base_unit_code = (base_unit.unit_code or "").strip().lower() if base_unit and base_unit.unit_code else ""
        has_packaging_based_unit_config = bool(base_unit_code and is_packaging_unit_code(base_unit_code))

        if not uses_packaging_legacy_normalization(item) and not has_packaging_based_unit_config:
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

        if payload and payload.em_embalagens is False:
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
        packaging_factor = float(resolve_packaging_factor(item) or 0.0)
        canonical_unit = resolve_canonical_unit(item)
        if packaging_factor <= 1.0 or not canonical_unit:
            return None
        if payload and payload.em_embalagens is True:
            return float(quantity_value) * packaging_factor, canonical_unit
        return resolve_packaging_quantity_and_unit(item, quantity_value)

    @staticmethod
    def _resolve_fractional_dual_write(
        item: Item,
        quantity_value: float,
        payload: MovimentoPayload | None = None,
    ) -> tuple[float, str] | None:
        if not payload or not payload.modo_fracionado:
            return None

        retirada_litros = InventoryService._as_positive_float(payload.quantidade_retirada_em_litros)
        if retirada_litros > 0:
            return retirada_litros, "l"

        retirada_quilos = InventoryService._as_positive_float(payload.quantidade_retirada_em_quilos)
        if retirada_quilos > 0:
            return retirada_quilos, "kg"

        if payload.em_embalagens is False:
            canonical_unit = resolve_canonical_unit(item)
            if canonical_unit:
                return float(quantity_value), canonical_unit

        return None

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

    @staticmethod
    def _resolve_ledger_input_for_mirror(
        item: Item,
        payload: MovimentoPayload,
        *,
        quantity: float | None = None,
        from_unit: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[float, str]:
        quantity_value = float(quantity if quantity is not None else payload.quantidade)
        fractional_resolution = InventoryService._resolve_fractional_dual_write(item, quantity_value, payload)
        if fractional_resolution is not None and from_unit is None:
            quantity_value, from_unit = fractional_resolution

        packaging_resolution = InventoryService._resolve_packaging_dual_write(item, quantity_value, payload, metadata)
        if packaging_resolution is not None and from_unit is None:
            quantity_value, from_unit = packaging_resolution

        unit_value = (from_unit or InventoryService._infer_dual_write_unit(item, payload, metadata) or "").strip().lower()
        if not unit_value:
            raise ValueError(f"Não foi possível inferir a unidade base para {item.codigo_item}")

        return quantity_value, unit_value

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

        quantity_value, unit_value = self._resolve_ledger_input_for_mirror(
            item,
            payload,
            quantity=quantity_value,
            from_unit=from_unit,
            metadata=metadata,
        )

        if bool((metadata or {}).get("legacy_state_pre_applied")):
            quantity_base_preview = float(
                unit_conversion_engine.convert_item_to_base(item, quantity_value, unit_value).quantity_base
            )
            self._sync_packaging_balance_before_dual_write(
                item,
                movement_type=movement_type_norm,
                quantity_base=quantity_base_preview,
            )

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
                "canal_saida": payload.canal_saida,
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
        try:
            movement = db.session.get(StockMovement, getattr(result, "movement_id", None))
            if movement is not None:
                reference_id = result.metadata.get("reference_id")
                reference_type = result.metadata.get("reference_type")
                if reference_id is not None and str(getattr(movement, "reference_id", "") or "") != str(reference_id):
                    movement.reference_id = str(reference_id)
                if reference_type and str(getattr(movement, "reference_type", "") or "") != str(reference_type):
                    movement.reference_type = str(reference_type)
        except Exception as exc:
            logger.warning(
                "Falha ao sincronizar reference_id/reference_type no StockMovement %s: %s",
                getattr(result, "movement_id", None),
                exc,
            )
        try:
            inventory_engine.sync_packaging_read_model(
                product_id=result.product_id,
                commit=True,
            )
        except Exception as exc:
            logger.warning(
                "Falha ao sincronizar read model de embalagem para %s apos espelhamento: %s",
                result.product_id,
                exc,
            )
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

    @staticmethod
    def _is_tool_category(category: Any) -> bool:
        return "ferrament" in str(category or "").strip().lower()

    @staticmethod
    def _format_availability_quantity(value: float) -> str:
        quantity = float(value or 0.0)
        if abs(quantity - round(quantity)) <= 1e-6:
            return str(int(round(quantity)))
        return f"{quantity:.2f}".rstrip("0").rstrip(".")

    def _build_tool_availability_state(self, codes: Iterable[str]) -> dict[str, dict[str, Any]]:
        normalized_codes = [str(code or "").strip() for code in codes if str(code or "").strip()]
        if not normalized_codes:
            return {}

        state: dict[str, dict[str, Any]] = {
            code: {
                "reserved_quantity": 0.0,
                "repair_quantity": 0.0,
                "has_open_repair": False,
            }
            for code in normalized_codes
        }

        reserved_rows = (
            db.session.query(
                RetiradaFerramenta.codigo_item,
                func.coalesce(func.sum(RetiradaFerramenta.quantidade), 0),
            )
            .filter(RetiradaFerramenta.codigo_item.in_(normalized_codes))
            .filter(RetiradaFerramenta.status.in_(ACTIVE_TOOL_WITHDRAWAL_STATUSES))
            .group_by(RetiradaFerramenta.codigo_item)
            .all()
        )
        for codigo_item, quantidade in reserved_rows:
            state.setdefault(codigo_item, {}).update({"reserved_quantity": float(quantidade or 0.0)})

        repair_rows = (
            db.session.query(
                RetiradaFerramenta.codigo_item,
                func.coalesce(func.sum(RetiradaFerramenta.quantidade), 0),
            )
            .filter(RetiradaFerramenta.codigo_item.in_(normalized_codes))
            .filter(RetiradaFerramenta.status == "para_reparo")
            .group_by(RetiradaFerramenta.codigo_item)
            .all()
        )
        for codigo_item, quantidade in repair_rows:
            state.setdefault(codigo_item, {}).update({"repair_quantity": float(quantidade or 0.0)})

        open_repair_codes = {
            str(codigo_item or "").strip()
            for (codigo_item,) in (
                db.session.query(EquipamentoReparo.codigo_item)
                .filter(EquipamentoReparo.codigo_item.in_(normalized_codes))
                .filter(EquipamentoReparo.status.in_(OPEN_TOOL_REPAIR_STATUSES))
                .distinct()
                .all()
            )
            if str(codigo_item or "").strip()
        }
        for codigo_item in open_repair_codes:
            state.setdefault(codigo_item, {}).update({"has_open_repair": True})

        return state

    def _apply_withdrawal_availability(
        self,
        item: Item,
        payload: dict[str, Any],
        *,
        tool_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        saldo_total = float(payload.get("saldo") or 0.0)
        reserved_quantity = 0.0
        repair_quantity = 0.0
        has_open_repair = False
        available_quantity = max(0.0, saldo_total)
        unavailable_reason: str | None = None
        unavailable_detail: str | None = None

        if self._is_tool_category(payload.get("categoria") or getattr(item, "categoria", None)):
            snapshot = tool_state or {}
            reserved_quantity = float(snapshot.get("reserved_quantity") or 0.0)
            repair_quantity = float(snapshot.get("repair_quantity") or 0.0)
            has_open_repair = bool(snapshot.get("has_open_repair"))
            available_quantity = max(0.0, saldo_total - reserved_quantity)

            if has_open_repair or repair_quantity > 1e-6:
                unavailable_reason = "Ferramenta em reparo"
                unavailable_detail = "Ferramenta indisponível para retirada enquanto houver reparo aberto."
            elif available_quantity <= 1e-6:
                unavailable_reason = "Sem saldo disponível"
                if reserved_quantity > 1e-6 and saldo_total > 1e-6:
                    unavailable_detail = (
                        f"Estoque físico atual: {self._format_availability_quantity(saldo_total)}. "
                        "Toda a disponibilidade já está comprometida em uso, atraso ou custódia."
                    )
                else:
                    unavailable_detail = "Ferramenta sem saldo disponível para retirada."
        elif available_quantity <= 1e-6:
            unavailable_reason = "Estoque zerado"
            unavailable_detail = "Item sem saldo disponível para retirada."

        payload.update(
            {
                "saldo_disponivel": available_quantity,
                "saldo_disponivel_display": self._format_availability_quantity(available_quantity),
                "reserved_quantity": reserved_quantity,
                "repair_quantity": repair_quantity,
                "has_open_repair": has_open_repair,
                "is_available": unavailable_reason is None,
                "unavailable_reason": unavailable_reason,
                "unavailable_detail": unavailable_detail,
            }
        )
        return payload

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
            Item.query.filter(
                or_(
                    Item.codigo_item.ilike(like),
                    Item.descricao.ilike(like),
                    Item.marca.ilike(like),
                )
            )
            .order_by(Item.descricao)
            .limit(limit)
            .all()
        )

        from ..services.embalagem_service import EmbalagemService
        bulk_balances = self._resolve_balances_in_bulk(rows)
        tool_states = self._build_tool_availability_state(
            item.codigo_item for item in rows if self._is_tool_category(item.categoria)
        )
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
            payload = {
                "codigo": item.codigo_item,
                "descricao": item.descricao,
                "categoria": item.categoria,
                "marca": item.marca,
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
            results.append(
                self._apply_withdrawal_availability(
                    item,
                    payload,
                    tool_state=tool_states.get(item.codigo_item),
                )
            )
        if updated:
            db.session.commit()
        return self._set_cached(cache_key, [dict(item) for item in results], ttl_seconds=3.0)

    def find_equivalent_item_candidates(
        self,
        payload: dict[str, Any],
        *,
        limit: int = 5,
        exclude_codigo: str | None = None,
    ) -> list[dict[str, Any]]:
        descricao_raw = str(payload.get("descricao") or "").strip()
        if not descricao_raw:
            return []

        descricao_norm = _normalize_equivalent_text(descricao_raw)
        descricao_base = _strip_equivalent_presentation_tokens(descricao_raw)
        reference_text = descricao_base or descricao_norm
        reference_tokens = _extract_equivalent_tokens(reference_text) or _extract_equivalent_tokens(descricao_raw)
        if len(reference_text) < 4 or not reference_tokens:
            return []

        codigo = _sanitize_codigo(payload.get("codigo") or payload.get("codigo_item"))
        exclude_codigo_norm = _sanitize_codigo(exclude_codigo) or codigo or None
        marca_raw = str(payload.get("marca") or "").strip()
        categoria_raw = str(payload.get("categoria") or "").strip()
        unidade_raw = str(payload.get("unidade") or "").strip()
        tipo_embalagem_raw = str(payload.get("tipo_embalagem_novo") or "").strip()

        search_conditions = [Item.descricao.ilike(f"%{token}%") for token in reference_tokens[:4]]
        if marca_raw:
            search_conditions.append(Item.marca.ilike(f"%{marca_raw}%"))

        if not search_conditions:
            return []

        query = Item.query
        if exclude_codigo_norm:
            query = query.filter(Item.codigo_item != exclude_codigo_norm)

        rows = (
            query.filter(or_(*search_conditions))
            .order_by(func.lower(Item.descricao).asc(), Item.codigo_item.asc())
            .limit(max(int(limit or 5) * 12, 40))
            .all()
        )

        if not rows:
            return []

        normalized_brand = _normalize_equivalent_text(marca_raw)
        normalized_category = _normalize_equivalent_text(categoria_raw)
        normalized_packaging = _normalize_equivalent_text(tipo_embalagem_raw or unidade_raw)
        reference_token_set = set(reference_tokens)
        candidates: list[dict[str, Any]] = []

        for item in rows:
            candidate_description = str(item.descricao or "").strip()
            candidate_norm = _normalize_equivalent_text(candidate_description)
            candidate_base = _strip_equivalent_presentation_tokens(candidate_description)
            candidate_reference = candidate_base or candidate_norm
            candidate_tokens = set(_extract_equivalent_tokens(candidate_reference) or _extract_equivalent_tokens(candidate_description))
            if not candidate_reference or not candidate_tokens:
                continue

            desc_ratio = _sequence_similarity(descricao_norm, candidate_norm)
            base_ratio = _sequence_similarity(reference_text, candidate_reference)
            token_overlap = len(reference_token_set & candidate_tokens) / max(len(reference_token_set), len(candidate_tokens), 1)

            candidate_brand = _normalize_equivalent_text(item.marca)
            candidate_category = _normalize_equivalent_text(item.categoria)
            candidate_packaging = _normalize_equivalent_text((item.tipo_embalagem_novo or item.unidade or ""))

            same_brand = bool(normalized_brand and candidate_brand and normalized_brand == candidate_brand)
            same_category = bool(normalized_category and candidate_category and normalized_category == candidate_category)
            packaging_changed = bool(normalized_packaging and candidate_packaging and normalized_packaging != candidate_packaging)
            presentation_changed = bool(base_ratio >= 0.82 and descricao_norm != candidate_norm)

            score = (desc_ratio * 0.34) + (base_ratio * 0.38) + (token_overlap * 0.18)
            if same_brand:
                score += 0.06
            if same_category:
                score += 0.03
            if presentation_changed:
                score += 0.04
            if packaging_changed:
                score += 0.02

            if score < 0.63 and base_ratio < 0.78 and not (same_brand and token_overlap >= 0.5):
                continue

            signals: list[str] = []
            if base_ratio >= 0.9:
                signals.append("descricao-base praticamente igual")
            elif base_ratio >= 0.82:
                signals.append("descricao-base muito parecida")
            elif desc_ratio >= 0.72:
                signals.append("descricao parecida")
            if same_brand:
                signals.append("mesma marca")
            if same_category:
                signals.append("mesma categoria")
            if presentation_changed or packaging_changed:
                signals.append("embalagem ou apresentacao diferente")
            if codigo and item.codigo_item != codigo:
                signals.append("codigo de barras diferente")
            if item.foto_path:
                signals.append("foto pronta para reaproveitar")

            candidates.append(
                {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "marca": item.marca,
                    "categoria": item.categoria,
                    "localizacao": item.localizacao,
                    "unidade": item.unidade,
                    "tipo_embalagem_novo": item.tipo_embalagem_novo,
                    "unidades_por_embalagem": item.unidades_por_embalagem,
                    "foto_path": item.foto_path,
                    "score": round(score, 4),
                    "score_percent": max(1, min(99, int(round(score * 100)))),
                    "same_brand": same_brand,
                    "same_category": same_category,
                    "presentation_changed": presentation_changed,
                    "packaging_changed": packaging_changed,
                    "signals": signals[:5],
                }
            )

        candidates.sort(
            key=lambda row: (
                float(row.get("score") or 0),
                1 if row.get("same_brand") else 0,
                1 if row.get("same_category") else 0,
                str(row.get("descricao") or "").lower(),
            ),
            reverse=True,
        )
        return candidates[: max(int(limit or 5), 1)]

    def _apply_equivalent_item_reuse(self, payload: dict[str, Any], *, codigo: str) -> dict[str, Any]:
        action = str(payload.get("equivalent_item_action") or "").strip().lower()
        if action != "reuse_metadata":
            return payload

        source_code = _sanitize_codigo(payload.get("equivalent_item_source_code"))
        if not source_code or source_code == codigo:
            return payload

        source_item = Item.query.get(source_code)
        if source_item is None:
            return payload

        if _coerce_truthy(payload.get("equivalent_item_reuse_brand")) and source_item.marca:
            payload["marca"] = source_item.marca
        if _coerce_truthy(payload.get("equivalent_item_reuse_category")) and source_item.categoria:
            payload["categoria"] = source_item.categoria
        if _coerce_truthy(payload.get("equivalent_item_reuse_location")) and source_item.localizacao:
            payload["localizacao"] = source_item.localizacao

        should_reuse_photo = (
            _coerce_truthy(payload.get("equivalent_item_reuse_photo"))
            and not payload.get("foto_path")
            and not payload.get("foto_url")
            and bool(source_item.foto_path)
        )
        if should_reuse_photo:
            try:
                from .item_foto_service import ItemFotoService

                payload["foto_path"] = ItemFotoService.duplicar_foto_para_item(source_item.foto_path, codigo)
            except Exception:
                logger.exception(
                    "Falha ao duplicar foto de item equivalente (origem=%s, destino=%s)",
                    source_code,
                    codigo,
                )

        return payload

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

    def generate_unique_internal_barcode_code(self, *, prefix: str = "2", max_attempts: int = 200) -> str:
        prefix_norm = re.sub(r"\D", "", str(prefix or "2"))[:1] or "2"

        for _ in range(max_attempts):
            body = f"{secrets.randbelow(10 ** 10):010d}"
            base_digits = prefix_norm + body
            codigo = base_digits + self._calculate_upc_check_digit(base_digits)
            if Item.query.get(codigo) is None:
                return codigo

        raise ValueError("Não foi possível gerar um novo código de barras único")

    @staticmethod
    def _calculate_upc_check_digit(base_digits: str) -> str:
        digits = [int(char) for char in str(base_digits or "") if char.isdigit()]
        if len(digits) != 11:
            raise ValueError("O código base deve ter 11 dígitos para gerar um código de barras de 12 dígitos")

        odd_sum = sum(digits[::2])
        even_sum = sum(digits[1::2])
        checksum = (10 - ((odd_sum * 3 + even_sum) % 10)) % 10
        return str(checksum)

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

        def _is_seeded_nf_pre_registration(item: Item, *, saldo_total: float) -> bool:
            if not bool(getattr(item, "pre_cadastro_pendente", False)):
                return False

            origem_pre_cadastro = (getattr(item, "pre_cadastro_origem", "") or "").strip().lower()
            if origem_pre_cadastro != "nf":
                return False

            if abs(float(saldo_total or 0.0)) > 1e-6:
                return False

            legacy_entries = int(
                db.session.query(func.count(Entrada.id_entrada))
                .filter(Entrada.codigo_item == item.codigo_item)
                .scalar()
                or 0
            )
            if legacy_entries > 0:
                return False

            processed_document_rows = int(
                db.session.query(func.count(DocumentoEntradaEstoqueItem.id_documento_item))
                .filter(
                    DocumentoEntradaEstoqueItem.codigo_item == item.codigo_item,
                    DocumentoEntradaEstoqueItem.status_processamento == "processado",
                )
                .scalar()
                or 0
            )
            if processed_document_rows > 0:
                return False

            return True

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

            if _is_seeded_nf_pre_registration(item, saldo_total=saldo):
                continue

            minimo = _calculate_min_stock(saldo)
            if item.estoque_minimo != minimo:
                item.estoque_minimo = minimo
                atualizado = True

            if _reconcile_normalized_item_prices(item):
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
                    "unidade_interna_display": item.get_unidade_interna_display(),
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
        if _reconcile_normalized_item_prices(item):
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
        tool_states = self._build_tool_availability_state([item.codigo_item]) if self._is_tool_category(item.categoria) else {}
        return self._apply_withdrawal_availability(item, dados, tool_state=tool_states.get(item.codigo_item))

    def create_item(self, payload: dict[str, Any]) -> str:
        payload = self._normalize_toolkit_registration_payload(payload)
        payload = self._hydrate_missing_packaging_metadata(payload)
        payload["categoria"] = category_catalog_service.resolve_name(payload.get("categoria"))
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
                self._apply_toolkit_unit_semantics(item_existente)
                _sync_packaging_conversion_graph(item_existente)
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

            payload = self._apply_equivalent_item_reuse(payload, codigo=codigo)
        
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
            _sync_packaging_conversion_graph(item)
            if "advanced_unit_settings" in payload:
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

        payload = self._normalize_toolkit_registration_payload(payload, current_item=item)
        payload = self._hydrate_missing_packaging_metadata(payload, current_item=item)
        payload["categoria"] = category_catalog_service.resolve_name(
            payload.get("categoria"),
            fallback=item.categoria or "Material Elétrico",
        )

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

        self._apply_toolkit_unit_semantics(item)

        if "advanced_unit_settings" in payload:
            _apply_advanced_unit_settings(item, payload.get("advanced_unit_settings"))
        _sync_packaging_conversion_graph(item)

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
        codigo_norm = str(getattr(payload, "codigo", "") or "").strip()
        if codigo_norm:
            item_data = self.get_item(codigo_norm)
            if item_data and item_data.get("is_available") is False:
                raise ValueError(
                    str(
                        item_data.get("unavailable_detail")
                        or item_data.get("unavailable_reason")
                        or "Item indisponível para retirada."
                    )
                )
        movimento = self._registrar_movimento(payload, is_entrada=False, skip_notification=skip_notification)
        return getattr(movimento, 'id_saida', 0)

    def _dispatch_movement_notification(
        self,
        movimento: Any,
        *,
        is_entrada: bool,
        skip_notification: bool,
        operation_log_id: int | None,
    ) -> None:
        if skip_notification:
            return

        if is_entrada:
            if operation_log_id:
                operation_log_service.notify_telegram(operation_log_id)
            return

        saida_id = getattr(movimento, "id_saida", None)
        if not saida_id:
            if operation_log_id:
                operation_log_service.notify_telegram(operation_log_id)
            return

        try:
            from .notification_router import NotificationRouterService

            tipo_custodia = self._normalize_tipo_custodia(getattr(movimento, "tipo_custodia", None))
            if tipo_custodia == "permanente":
                NotificationRouterService.route_permanent_custody(saida_id)
            else:
                NotificationRouterService.route_withdrawal(saida_id, force_single=True)
        except Exception:
            logger.exception("Falha ao rotear notificação de retirada para saida_id=%s", saida_id)
            if operation_log_id:
                operation_log_service.notify_telegram(operation_log_id)

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

            _accumulate_dashboard_category_summary(
                categorias,
                categoria_value=item.categoria,
                unidade_value=item.unidade,
                saldo_categoria=saldo_categoria,
                photo_path=(item.foto_path if saldo_categoria > 0 else None),
            )

        if atualizado:
            db.session.commit()

        snapshot = {
            "resumo": resumo,
            "total_quantity": int(round(total_quantity)),
            "category_summary": _finalize_dashboard_category_summary(categorias),
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
            numero = finance_service.normalize_manual_internal_document_number(
                documento.get("numero_documento") or documento.get("nota_fiscal") or ""
            )
            if numero:
                notas_por_numero[numero] = documento

        for numero, nota_legada in agrupadas.items():
            numero_normalizado = finance_service.normalize_manual_internal_document_number(numero)
            if numero_normalizado not in notas_por_numero:
                nota_payload = dict(nota_legada)
                nota_payload["numero_documento"] = numero_normalizado
                nota_payload["nota_fiscal"] = numero_normalizado
                notas_por_numero[numero_normalizado] = nota_payload

        notas = sorted(
            notas_por_numero.values(),
            key=lambda nota: nota.get("data") or datetime.min,
            reverse=True,
        )
        payload = notas[:limit]
        return self._set_cached(cache_key, [dict(item) for item in payload], ttl_seconds=8.0)

    def get_nota_fiscal(self, numero: str) -> dict[str, Any] | None:
        from .finance_service import finance_service

        numero = finance_service.normalize_manual_internal_document_number(numero)
        if not numero:
            return None
        cache_key = f"get_nota_fiscal:{numero}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return dict(cached)

        documento = finance_service.get_stock_document_by_number(numero)
        if documento:
            return self._set_cached(cache_key, dict(documento), ttl_seconds=8.0)

        candidate_numbers = [numero]
        if finance_service.is_manual_internal_document_number(numero):
            candidate_numbers = list(finance_service.manual_internal_document_aliases())

        registros = (
            Entrada.query.filter(Entrada.nota_fiscal.in_(candidate_numbers))
            .order_by(Entrada.data_entrada.desc())
            .all()
        )
        if not registros:
            return None
        notas = _agrupar_notas(registros)
        nota = notas.get(numero)
        if nota is None and finance_service.is_manual_internal_document_number(numero):
            for alias in finance_service.manual_internal_document_aliases():
                nota = notas.get(alias)
                if nota is not None:
                    nota = dict(nota)
                    nota["numero_documento"] = numero
                    nota["nota_fiscal"] = numero
                    break
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

    def list_item_document_history(self, codigo: str, limit: int = 12) -> list[dict[str, Any]]:
        codigo_norm = (codigo or "").strip()
        if not codigo_norm:
            return []

        from .finance_service import FinanceService, _build_document_item_display_metadata

        rows = (
            DocumentoEntradaEstoqueItem.query
            .options(
                joinedload(DocumentoEntradaEstoqueItem.item),
                joinedload(DocumentoEntradaEstoqueItem.documento).joinedload(DocumentoEntradaEstoque.fornecedor),
            )
            .join(DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem.documento_id == DocumentoEntradaEstoque.id_documento)
            .filter(DocumentoEntradaEstoqueItem.codigo_item == codigo_norm)
            .order_by(
                DocumentoEntradaEstoque.data_recebimento.desc(),
                DocumentoEntradaEstoque.data_emissao.desc(),
                DocumentoEntradaEstoque.id_documento.desc(),
                DocumentoEntradaEstoqueItem.id_documento_item.desc(),
            )
            .limit(limit)
            .all()
        )

        history: list[dict[str, Any]] = []
        for row in rows:
            document = row.documento
            if document is None:
                continue

            display = _build_document_item_display_metadata(row)
            supplier_name = document.fornecedor.nome_exibicao() if document.fornecedor else document.nome_emitente()
            document_number = FinanceService.normalize_manual_internal_document_number(document.numero_documento)

            history.append(
                {
                    "id": row.id_documento_item,
                    "documento_id": document.id_documento,
                    "tipo_documento": document.tipo_documento,
                    "numero_documento": document_number,
                    "fornecedor_nome": supplier_name,
                    "cnpj_emitente": document.cnpj_emitente,
                    "data_emissao": document.data_emissao,
                    "data_recebimento": document.data_recebimento,
                    "criado_em": row.criado_em,
                    "movimenta_estoque": bool(document.movimenta_estoque) if document.movimenta_estoque is not None else True,
                    "status_processamento": row.status_processamento,
                    "processado_em": row.processado_em,
                    "chave_acesso": document.chave_acesso,
                    "observacao": row.observacao or document.observacao,
                    "quantidade": float(row.quantidade or 0.0),
                    "quantidade_base": float(row.quantidade_base or 0.0) if row.quantidade_base is not None else None,
                    "valor_unitario": float(row.valor_unitario or 0.0) if row.valor_unitario is not None else None,
                    "valor_total": float(row.valor_total or 0.0) if row.valor_total is not None else None,
                    **display,
                }
            )

        return history

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

        if not movimentos:
            ledger_rows = (
                StockMovement.query
                .filter(StockMovement.product_id == codigo_norm)
                .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
                .limit(limit)
                .all()
            )

            if ledger_rows:
                document_item_ids: set[int] = set()
                stock_movement_ids = [row.id for row in ledger_rows]
                for row in ledger_rows:
                    if (row.reference_type or "").strip().lower() == "entrada_documento_item":
                        try:
                            document_item_ids.add(int(str(row.reference_id or "").strip()))
                        except (TypeError, ValueError):
                            continue

                document_items = (
                    DocumentoEntradaEstoqueItem.query
                    .options(
                        joinedload(DocumentoEntradaEstoqueItem.documento).joinedload(DocumentoEntradaEstoque.fornecedor),
                        joinedload(DocumentoEntradaEstoqueItem.operation_log).joinedload(OperationLog.user),
                    )
                    .filter(
                        or_(
                            DocumentoEntradaEstoqueItem.stock_movement_id.in_(stock_movement_ids),
                            DocumentoEntradaEstoqueItem.id_documento_item.in_(document_item_ids or {-1}),
                        )
                    )
                    .all()
                )

                document_item_by_stock_movement = {
                    int(row.stock_movement_id): row
                    for row in document_items
                    if row.stock_movement_id is not None
                }
                document_item_by_id = {
                    int(row.id_documento_item): row
                    for row in document_items
                }

                creator_ids = {
                    str(row.documento.criado_por).strip()
                    for row in document_items
                    if row.documento is not None and str(row.documento.criado_por or "").strip()
                }
                creator_names = {
                    row.matricula: (row.nome or row.matricula)
                    for row in Usuario.query.filter(Usuario.matricula.in_(creator_ids)).all()
                } if creator_ids else {}

                movement_type_labels = {
                    "entrada": "Entrada",
                    "saida": "Saída",
                    "devolucao": "Devolução",
                    "ajuste": "Ajuste",
                    "inicial": "Saldo inicial",
                }

                def _resolve_ledger_document_item(row: StockMovement) -> DocumentoEntradaEstoqueItem | None:
                    if row.id in document_item_by_stock_movement:
                        return document_item_by_stock_movement[row.id]
                    if (row.reference_type or "").strip().lower() != "entrada_documento_item":
                        return None
                    try:
                        return document_item_by_id.get(int(str(row.reference_id or "").strip()))
                    except (TypeError, ValueError):
                        return None

                def _resolve_ledger_responsavel(row: StockMovement, document_item: DocumentoEntradaEstoqueItem | None) -> str:
                    if document_item is not None and document_item.operation_log is not None:
                        log_user = document_item.operation_log.user
                        if log_user is not None:
                            return log_user.nome or log_user.matricula or "—"
                        if document_item.operation_log.user_id:
                            return creator_names.get(document_item.operation_log.user_id, document_item.operation_log.user_id)
                    if document_item is not None and document_item.documento is not None:
                        created_by = str(document_item.documento.criado_por or "").strip()
                        if created_by:
                            return creator_names.get(created_by, created_by)

                    metadata = dict(row.metadata_json or {})
                    for key in ("usuario_nome", "user_name", "responsavel"):
                        value = str(metadata.get(key) or "").strip()
                        if value:
                            return value
                    for key in ("user_id", "matricula"):
                        value = str(metadata.get(key) or "").strip()
                        if value:
                            return creator_names.get(value, value)
                    if (row.reference_type or "").strip().lower() == "entrada_documento_item":
                        return "Documento fiscal"
                    return "—"

                for row in ledger_rows:
                    movement_type = (row.movement_type or "").strip().lower()
                    label = movement_type_labels.get(movement_type, movement_type.title() or "Movimentação")
                    document_item = _resolve_ledger_document_item(row)
                    movimentos.append(
                        {
                            "id": row.id,
                            "tipo": label,
                            "quantidade": abs(float(row.quantity_base or 0.0)),
                            "data": row.created_at,
                            "responsavel": _resolve_ledger_responsavel(row, document_item),
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

        categorias: dict[str, dict[str, Any]] = {}
        for item in Item.query.order_by(Item.categoria, Item.descricao).all():
            if EmbalagemService.tem_embalagem(item):
                saldo = float(item.estoque_embalagens or 0)
            else:
                saldo = float(item.get_saldo_atual() or 0)

            _accumulate_dashboard_category_summary(
                categorias,
                categoria_value=item.categoria,
                unidade_value=item.unidade,
                saldo_categoria=saldo,
                photo_path=(item.foto_path if saldo > 0 else None),
            )

        return _finalize_dashboard_category_summary(categorias)

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

        if not is_entrada:
            self.validate_exit_payload_policy(item, payload)

        categoria_text = (item.categoria or "").lower()
        if not is_entrada and "ferrament" in categoria_text:
            if self._has_active_tool_withdrawal(payload.codigo, payload.matricula):
                raise ValueError(
                    "Retirada bloqueada: este funcionário já possui esta ferramenta em aberto. "
                    "Faça a devolução antes de nova retirada."
                )

        # Verificar se o item usa sistema de embalagens
        from ..services.embalagem_service import EmbalagemService
        tem_embalagem = EmbalagemService.tem_embalagem(item)

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
                    telegram_balance_before = float(balance_provider.get_balance(item.codigo_item, item=item).quantity_base or 0)
                except Exception:
                    telegram_balance_before = None
            else:
                try:
                    telegram_balance_before = float(item.get_saldo_atual() or 0)
                except Exception:
                    telegram_balance_before = None

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
            self.finalize_ledger_mirror(ledger_result)
            self._dispatch_movement_notification(
                movimento,
                is_entrada=is_entrada,
                skip_notification=skip_notification,
                operation_log_id=ledger_result.operation_log_id,
            )
        
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
