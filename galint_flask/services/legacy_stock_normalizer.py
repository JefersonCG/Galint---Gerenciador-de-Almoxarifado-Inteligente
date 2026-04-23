from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any
import unicodedata

from ..models import Entrada, InventarioEvento, Item, Saida

_PAIR_RE = re.compile(r"de\s+([0-9]+(?:\.[0-9]+)?)\s+para\s+([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_PACKAGING_UNIT_CODES = {"lata", "balde", "bombona", "caixa", "pacote", "fardo", "rolo", "saco", "litro"}
_TOOLKIT_PIECES_RE = re.compile(r"\b[0-9]+(?:\.[0-9]+)?\s*pecas?\b", re.IGNORECASE)
_UNIT_HINT_RE = re.compile(
    r"UNIDADE\s*=\s*([A-ZÇÃÕÁÉÍÓÚ_ ]+)|\b(LITRO|LITROS|KG|KILO|QUILO|METRO|METROS|UNIDADE|UNIDADES|PAR|PARES)\b",
    re.IGNORECASE,
)
_TEXT_MEASURE_RE = re.compile(
    r"\b([0-9]+(?:[.,][0-9]+)?)\s*(ml|mililitro|mililitros|l|lt|lts|litro|litros|g|gr|grama|gramas|kg|quilo|quilos|kilo|kilos|m|mt|mts|metro|metros)\b",
    re.IGNORECASE,
)
_ROLL_DIMENSION_HEAD_RE = re.compile(
    r"\b([0-9]+(?:[.,][0-9]+)?)\s*[x×]\s*[0-9]+(?:[.,][0-9]+)?\s*mm\b",
    re.IGNORECASE,
)
_ROLL_DIMENSION_TAIL_RE = re.compile(
    r"[x×]\s*([0-9]+(?:[.,][0-9]+)?)\s*(m|mt|mts|metro|metros)\b",
    re.IGNORECASE,
)
_MOVEMENT_KIND_ORDER = {"entrada": 0, "saida": 1, "evento": 2}
_TOLERANCE = 1e-6
_TOOLKIT_KEYWORDS = ("jogo", "kit", "conjunto")
_SINGLE_PIECE_PACKAGED_KEYWORDS = ("lampada", "luminaria", "painel", "refletor", "iluminacao")
_LIQUID_KEYWORDS = (
    "tinta",
    "resina",
    "verniz",
    "solvente",
    "thinner",
    "selador",
    "impermeabilizante",
    "esmalte",
    "alcool",
    "algicida",
    "clarificante",
    "desinfetante",
    "creolina",
    "limpa",
    "facilitador",
    "ferrugem",
    "endurecedor",
    "aditivo",
    "acetinado",
    "cola",
    "fosco",
    "seda",
    "toque",
    "vedalit",
    "oleosidade",
)
_WEIGHT_KEYWORDS = ("massa", "argamassa", "rejunte", "rejuntamento", "cimento", "gesso", "cloro", "manta", "quartzo", "ecopoxi")


@dataclass(slots=True, frozen=True)
class NormalizedLegacyMovement:
    movement_type: str
    quantity_base: float
    unit_base: str
    reference_type: str
    reference_id: str
    created_at: datetime | None
    metadata: dict[str, Any]


def _read_field(source: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(field_name, default)
    return getattr(source, field_name, default)


def is_packaging_unit_code(unit_code: str | None) -> bool:
    return (unit_code or "").strip().lower() in _PACKAGING_UNIT_CODES


def _normalize_search_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.strip().lower().split())


def _build_packaging_lookup_text(item: Item) -> str:
    return " ".join(
        part for part in (
            _normalize_search_text(getattr(item, "descricao", None)),
            _normalize_search_text(getattr(item, "categoria", None)),
            _normalize_search_text(getattr(item, "marca", None)),
            _normalize_search_text(getattr(item, "unidade", None)),
            _normalize_search_text(getattr(item, "tipo_embalagem_novo", None)),
        )
        if part
    ).strip()


def _extract_measure_from_text(text: str) -> tuple[float, str] | None:
    if not text:
        return None
    roll_dimension_head_match = _ROLL_DIMENSION_HEAD_RE.search(text)
    if roll_dimension_head_match:
        raw_value = (roll_dimension_head_match.group(1) or "").replace(",", ".")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value, "m"

    roll_dimension_match = _ROLL_DIMENSION_TAIL_RE.search(text)
    if roll_dimension_match:
        raw_value = (roll_dimension_match.group(1) or "").replace(",", ".")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value, "m"

    match = _TEXT_MEASURE_RE.search(text)
    if not match:
        return None
    raw_value = (match.group(1) or "").replace(",", ".")
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    raw_unit = str(match.group(2) or "").strip().lower()
    if raw_unit in {"ml", "mililitro", "mililitros"}:
        return value / 1000.0, "l"
    if raw_unit in {"g", "gr", "grama", "gramas"}:
        return value / 1000.0, "kg"
    unit = _normalize_simple_unit(raw_unit)
    if not unit:
        return None
    return value, unit


def _text_prefers_liquid_measure(text: str) -> bool:
    return bool(text and any(keyword in text for keyword in _LIQUID_KEYWORDS))


def _text_prefers_weight_measure(text: str) -> bool:
    return bool(text and any(keyword in text for keyword in _WEIGHT_KEYWORDS))


def _accept_text_measure(*, unit: str, package_type: str, lookup_text: str) -> bool:
    if unit == "l":
        return package_type in {"lata", "balde", "bombona", "litro"} or _text_prefers_liquid_measure(lookup_text)
    if unit == "kg":
        if package_type in {"caixa", "fardo"}:
            return False
        return package_type in {"lata", "balde", "bombona", "saco"} or _text_prefers_weight_measure(lookup_text)
    if unit == "m":
        return package_type == "rolo"
    return False


def _accept_untyped_text_measure(*, unit: str, lookup_text: str) -> bool:
    if unit == "l":
        return _text_prefers_liquid_measure(lookup_text)
    if unit == "kg":
        return _text_prefers_weight_measure(lookup_text)
    return False


def _looks_like_single_piece_packaged_item(text: str) -> bool:
    return bool(text and any(keyword in text for keyword in _SINGLE_PIECE_PACKAGED_KEYWORDS))


def _resolve_grandeza_reference_unit(*, item: Item, package_type: str, lookup_text: str) -> str:
    parsed_measure = _extract_measure_from_text(lookup_text)
    if package_type == "rolo":
        return "m"
    if package_type in {"caixa", "fardo"}:
        return "un"
    if package_type == "pacote":
        if parsed_measure is not None and _accept_text_measure(unit=parsed_measure[1], package_type=package_type, lookup_text=lookup_text):
            return parsed_measure[1]
        if _text_prefers_weight_measure(lookup_text):
            return "kg"
        return "un"
    if package_type == "saco":
        if parsed_measure is not None and _accept_text_measure(unit=parsed_measure[1], package_type=package_type, lookup_text=lookup_text):
            return parsed_measure[1]
        return "kg"
    if package_type in {"lata", "balde", "bombona", "litro"}:
        if parsed_measure is not None and _accept_text_measure(unit=parsed_measure[1], package_type=package_type, lookup_text=lookup_text):
            return parsed_measure[1]
        if _text_prefers_liquid_measure(lookup_text):
            return "l"
        return "kg"
    return "kg"


def infer_packaging_measure(item: Item) -> tuple[float, str] | None:
    tipo_emb = (getattr(item, "tipo_embalagem_novo", None) or "").strip().lower()
    unidade_raw = (getattr(item, "unidade", None) or "").strip().lower()
    lookup_text = _build_packaging_lookup_text(item)

    litros_por = _as_positive_float(getattr(item, "litros_por_embalagem", None))
    if litros_por > 0:
        return litros_por, "l"

    grandeza_ref = _as_positive_float(getattr(item, "grandeza_referencia", None))
    if grandeza_ref > 0:
        return grandeza_ref, _resolve_grandeza_reference_unit(item=item, package_type=tipo_emb, lookup_text=lookup_text)

    product_units = _read_field(item, "product_units", []) or []
    base_unit = next(
        (
            unit
            for unit in product_units
            if _read_field(unit, "is_base", False) and _read_field(unit, "active", False)
        ),
        None,
    )
    if base_unit and _read_field(base_unit, "unit_code", None):
        normalized = _normalize_simple_unit(_read_field(base_unit, "unit_code", None))
        if normalized:
            factor = _as_positive_float(getattr(item, "unidades_por_embalagem", None))
            if factor > 0:
                return factor, normalized

    parsed_measure = _extract_measure_from_text(lookup_text)
    if parsed_measure is not None:
        if _accept_text_measure(unit=parsed_measure[1], package_type=tipo_emb, lookup_text=lookup_text):
            return parsed_measure
        if not tipo_emb and _accept_untyped_text_measure(unit=parsed_measure[1], lookup_text=lookup_text):
            return parsed_measure

    unidades_por = _as_positive_float(getattr(item, "unidades_por_embalagem", None))
    mapped_unit = _normalize_simple_unit(unidade_raw)

    if tipo_emb == "litro":
        return ((unidades_por or 1.0), "l")

    if tipo_emb == "rolo" and unidades_por > 0:
        return unidades_por, "m"

    if tipo_emb in {"caixa", "pacote"} and _looks_like_single_piece_packaged_item(lookup_text):
        return 1.0, "un"

    if unidades_por > 0:
        if mapped_unit and mapped_unit != "un":
            return unidades_por, mapped_unit
        if tipo_emb in {"lata", "balde", "bombona", "saco", "pacote"}:
            if _text_prefers_liquid_measure(lookup_text):
                return unidades_por, "l"
            if _text_prefers_weight_measure(lookup_text):
                return unidades_por, "kg"
        if tipo_emb in {"pacote", "caixa", "fardo", "saco"}:
            return unidades_por, "un"

    if mapped_unit and mapped_unit != "un":
        return 1.0, mapped_unit

    return None


def is_legacy_liter_packaging_compatible(item: Item) -> bool:
    tipo_emb = (getattr(item, "tipo_embalagem_novo", None) or "").strip().lower()
    if tipo_emb != "litro":
        return False

    factor = float(resolve_packaging_factor(item) or 0.0)
    if factor <= 0 or factor > (1.0 + _TOLERANCE):
        return False

    canonical_unit = _normalize_simple_unit(resolve_canonical_unit(item))
    if canonical_unit != "l":
        return False

    lookup_text = _build_packaging_lookup_text(item)
    parsed_measure = _extract_measure_from_text(lookup_text)
    if parsed_measure is not None:
        return parsed_measure[1] == "l"

    return _text_prefers_liquid_measure(lookup_text)


def ignore_packaging_metadata_for_stock(item: Item) -> bool:
    packaging_markers = {
        _normalize_search_text(getattr(item, "tipo_embalagem_novo", None)),
        _normalize_search_text(getattr(item, "tipo_embalagem", None)),
        _normalize_search_text(getattr(item, "unidade", None)),
    }
    packaging_markers.discard("")
    if not packaging_markers.intersection({"pacote", "caixa", "fardo"}):
        return False

    categoria = _normalize_search_text(getattr(item, "categoria", None))
    if "ferrament" not in categoria:
        return False

    descricao = _normalize_search_text(getattr(item, "descricao", None))
    if not descricao:
        return False

    if any(keyword in descricao for keyword in _TOOLKIT_KEYWORDS):
        return True
    return bool(_TOOLKIT_PIECES_RE.search(descricao))


def has_active_unit_config(item: Item) -> bool:
    product_units = _read_field(item, "product_units", []) or []
    product_unit_conversions = _read_field(item, "product_unit_conversions", []) or []
    return any(
        _read_field(unit, "is_base", False) and _read_field(unit, "active", False)
        for unit in product_units
    ) or any(
        _read_field(conversion, "active", False) for conversion in product_unit_conversions
    )


def resolve_packaging_factor(item: Item) -> float:
    tipo_emb = (_read_field(item, "tipo_embalagem_novo", None) or "").strip().lower()
    unidades_por = _as_positive_float(_read_field(item, "unidades_por_embalagem", None))
    litros_por = _as_positive_float(_read_field(item, "litros_por_embalagem", None))
    grandeza_ref = _as_positive_float(_read_field(item, "grandeza_referencia", None))

    if tipo_emb in {"pacote", "caixa", "fardo"} and unidades_por > 0:
        return unidades_por

    if tipo_emb == "rolo" and unidades_por > 0:
        return unidades_por

    if tipo_emb in {"lata", "balde", "bombona", "litro"}:
        if litros_por > 0:
            return litros_por
        if grandeza_ref > 0:
            return grandeza_ref
        if unidades_por > 0:
            return unidades_por

    if tipo_emb == "saco":
        if grandeza_ref > 0:
            return grandeza_ref
        if unidades_por > 0:
            return unidades_por

    if litros_por > 0:
        return litros_por
    if grandeza_ref > 0:
        return grandeza_ref
    inferred_measure = infer_packaging_measure(item)
    if inferred_measure is not None and inferred_measure[0] > 0:
        return inferred_measure[0]
    if unidades_por > 0:
        return unidades_por
    return 0.0


def uses_packaging_legacy_normalization(item: Item) -> bool:
    factor = float(resolve_packaging_factor(item) or 0.0)
    if factor <= 0.0 or abs(factor - 1.0) <= _TOLERANCE:
        return False
    if has_active_unit_config(item) or ignore_packaging_metadata_for_stock(item):
        return False

    canonical_unit = _normalize_simple_unit(resolve_canonical_unit(item))
    if not canonical_unit or is_packaging_unit_code(canonical_unit):
        return False

    unidade_raw = (_read_field(item, "unidade", None) or "").strip().lower()
    unidade_normalized = _normalize_simple_unit(unidade_raw) or unidade_raw
    if unidade_normalized and unidade_normalized != canonical_unit:
        return True

    tipo_emb = (_read_field(item, "tipo_embalagem_novo", None) or "").strip().lower()
    if tipo_emb and tipo_emb != canonical_unit:
        return True

    return factor > 1.0


def resolve_canonical_unit(item: Item) -> str:
    product_units = _read_field(item, "product_units", []) or []
    base_unit = next(
        (
            unit
            for unit in product_units
            if _read_field(unit, "is_base", False) and _read_field(unit, "active", False)
        ),
        None,
    )
    if base_unit and _read_field(base_unit, "unit_code", None):
        normalized = _normalize_simple_unit(_read_field(base_unit, "unit_code", None))
        if normalized:
            return normalized
        unit_code_raw = (_read_field(base_unit, "unit_code", None) or "").strip().lower()
        if unit_code_raw and not is_packaging_unit_code(unit_code_raw):
            return unit_code_raw

    inferred_measure = infer_packaging_measure(item)
    if inferred_measure is not None:
        return inferred_measure[1]

    tipo_emb = (_read_field(item, "tipo_embalagem_novo", None) or "").strip().lower()
    unidade_raw = (_read_field(item, "unidade", None) or "").strip().lower()
    litros_por = _as_positive_float(_read_field(item, "litros_por_embalagem", None))
    grandeza_ref = _as_positive_float(_read_field(item, "grandeza_referencia", None))
    unidades_por = _as_positive_float(_read_field(item, "unidades_por_embalagem", None))

    if litros_por > 0:
        return "l"

    if tipo_emb == "rolo" and unidades_por > 0:
        return "m"

    if grandeza_ref > 0:
        return "kg"

    if tipo_emb in {"pacote", "caixa", "fardo", "saco"} and unidades_por > 0:
        return "un"

    mapped_unit = _normalize_simple_unit(unidade_raw)
    if mapped_unit:
        return mapped_unit

    if unidade_raw and not is_packaging_unit_code(unidade_raw):
        return unidade_raw

    if tipo_emb == "rolo":
        return "m"
    if tipo_emb in {"pacote", "caixa", "fardo", "saco"}:
        return "un"
    return "un"


def resolve_packaging_quantity_and_unit(item: Item, quantity: float) -> tuple[float, str] | None:
    if not uses_packaging_legacy_normalization(item):
        return None

    factor = resolve_packaging_factor(item)
    if factor <= 0:
        return None

    return float(quantity) * factor, resolve_canonical_unit(item)


def build_normalized_legacy_movements(
    item: Item,
    *,
    entries: list[Entrada] | None = None,
    exits: list[Saida] | None = None,
    events: list[InventarioEvento] | None = None,
) -> list[NormalizedLegacyMovement]:
    if not item or not item.codigo_item:
        return []

    rows: list[tuple[str, datetime | None, int, Entrada | Saida | InventarioEvento]] = []
    for entry in entries if entries is not None else list(item.entradas):
        rows.append(("entrada", entry.data_entrada, int(entry.id_entrada), entry))
    for exit_row in exits if exits is not None else list(item.saidas):
        rows.append(("saida", exit_row.data_saida, int(exit_row.id_saida), exit_row))
    if events is None:
        events = list(
            InventarioEvento.query
            .filter_by(codigo_item=item.codigo_item)
            .order_by(InventarioEvento.data_evento.asc(), InventarioEvento.id_evento.asc())
            .all()
        )
    for event in events:
        rows.append(("evento", event.data_evento, int(event.id_evento), event))

    rows.sort(key=lambda row: (row[1] or datetime.min, _MOVEMENT_KIND_ORDER[row[0]], row[2]))
    unit_base = resolve_canonical_unit(item)
    normalized: list[NormalizedLegacyMovement] = []
    running_before = 0.0

    for kind, created_at, sequence_id, row in rows:
        if kind == "entrada":
            quantity_base = _normalize_entry_quantity(item, row)
            movement_type = "entrada"
            reference_type = "entrada"
            metadata = {
                "legacy_table": "entradas",
                "legacy_row_id": sequence_id,
                "legacy_quantity": float(getattr(row, "quantidade", 0) or 0),
                "matricula": row.matricula,
                "nota_fiscal": row.nota_fiscal,
            }
        elif kind == "saida":
            quantity_base = -_normalize_exit_quantity(item, row)
            movement_type = "saida"
            reference_type = "saida"
            metadata = {
                "legacy_table": "saidas",
                "legacy_row_id": sequence_id,
                "legacy_quantity": float(getattr(row, "quantidade", 0) or 0),
                "matricula": row.matricula,
                "observacao": row.observacao,
                "local_servico": row.local_servico,
                "tipo_custodia": getattr(row, "tipo_custodia", None),
            }
        else:
            quantity_base = _normalize_event_delta(item, row, running_before)
            movement_type = _classify_event_type(getattr(row, "tipo", None))
            reference_type = "inventario_evento"
            metadata = {
                "legacy_table": "inventario_eventos",
                "legacy_row_id": sequence_id,
                "legacy_quantity": float(getattr(row, "quantidade", 0) or 0),
                "legacy_event_type": row.tipo,
                "matricula": row.matricula,
                "descricao": row.descricao,
            }

        if abs(quantity_base) <= _TOLERANCE:
            continue

        if uses_packaging_legacy_normalization(item):
            metadata["normalized_from_packaging"] = True
            metadata["packaging_factor"] = resolve_packaging_factor(item)
            metadata["canonical_unit"] = unit_base

        normalized.append(
            NormalizedLegacyMovement(
                movement_type=movement_type,
                quantity_base=float(quantity_base),
                unit_base=unit_base,
                reference_type=reference_type,
                reference_id=str(sequence_id),
                created_at=created_at,
                metadata=metadata,
            )
        )
        running_before += float(quantity_base)

    return normalized


def _normalize_entry_quantity(item: Item, entry: Entrada) -> float:
    raw_quantity = float(entry.quantidade or 0)
    resolved = resolve_packaging_quantity_and_unit(item, raw_quantity)
    if resolved is None:
        return raw_quantity
    return resolved[0]


def _normalize_exit_quantity(item: Item, exit_row: Saida) -> float:
    raw_quantity = float(exit_row.quantidade or 0)
    if not uses_packaging_legacy_normalization(item):
        return raw_quantity

    litros = _as_positive_float(getattr(exit_row, "quantidade_retirada_em_litros", None))
    if litros > 0:
        return litros

    quilos = _as_positive_float(getattr(exit_row, "quantidade_retirada_em_quilos", None))
    if quilos > 0:
        return quilos

    observacao = (getattr(exit_row, "observacao", None) or "").strip()
    hint_match = _UNIT_HINT_RE.search(observacao)
    if hint_match:
        hint = (hint_match.group(1) or hint_match.group(2) or "").strip().lower()
        if any(token in hint for token in ("litro", "litr", "quilo", "kilo", "kg", "metro", "unidade", "par")):
            return raw_quantity

    factor = resolve_packaging_factor(item)
    if bool(getattr(exit_row, "usou_fracao", False)) and factor > 0:
        numerador = getattr(exit_row, "fracao_numerador", None)
        denominador = getattr(exit_row, "fracao_denominador", None)
        if numerador and denominador:
            return float(numerador) / float(denominador) * factor
        if abs(raw_quantity) < 1:
            return raw_quantity * factor

    return raw_quantity * factor


def _normalize_event_delta(item: Item, event: InventarioEvento, running_before: float) -> float:
    raw_quantity = float(event.quantidade or 0)
    descricao = (event.descricao or "").strip()
    if not descricao:
        return raw_quantity

    descricao_lower = descricao.lower()
    pairs = _PAIR_RE.findall(descricao)

    if uses_packaging_legacy_normalization(item) and "saldo em embalagens" in descricao_lower and pairs:
        target_balance = float(pairs[-1][1])
        return target_balance - float(running_before)

    if uses_packaging_legacy_normalization(item) and not pairs:
        return raw_quantity

    if uses_packaging_legacy_normalization(item) and abs(running_before) <= _TOLERANCE and pairs:
        if descricao_lower.startswith("saldo inicial configurado"):
            target_balance = float(pairs[-1][1]) * resolve_packaging_factor(item)
            return target_balance - float(running_before)

    return raw_quantity


def _normalize_simple_unit(unit_raw: str | None) -> str | None:
    value = (unit_raw or "").strip().lower()
    if not value:
        return None
    if value in {"par", "pares"}:
        return "par"
    if value in {"l", "lt", "lts", "litro", "litros"}:
        return "l"
    if value in {"kg", "quilo", "quilos", "kilo", "kilos"}:
        return "kg"
    if value in {"m", "mt", "mts", "metro", "metros"}:
        return "m"
    if value in {"un", "und", "unidade", "unidades"}:
        return "un"
    return None


def _as_positive_float(value: Any) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return 0.0
    return normalized if normalized > 0 else 0.0


def _classify_event_type(event_type: str | None) -> str:
    raw = (event_type or "").strip().lower()
    if raw.startswith("devolucao"):
        return "devolucao"
    if "ajuste" in raw:
        return "ajuste"
    if raw in {"quebra_ferramenta", "reparo_ferramenta", "perda"}:
        return "ajuste"
    return "ajuste"