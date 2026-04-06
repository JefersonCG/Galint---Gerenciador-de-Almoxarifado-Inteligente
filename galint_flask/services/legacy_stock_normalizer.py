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
    r"UNIDADE\s*=\s*([A-ZÇÃÕÁÉÍÓÚ_ ]+)|\b(LITRO|LITROS|KG|KILO|QUILO|METRO|METROS|UNIDADE|UNIDADES)\b",
    re.IGNORECASE,
)
_MOVEMENT_KIND_ORDER = {"entrada": 0, "saida": 1, "evento": 2}
_TOLERANCE = 1e-6
_TOOLKIT_KEYWORDS = ("jogo", "kit", "conjunto")


@dataclass(slots=True, frozen=True)
class NormalizedLegacyMovement:
    movement_type: str
    quantity_base: float
    unit_base: str
    reference_type: str
    reference_id: str
    created_at: datetime | None
    metadata: dict[str, Any]


def is_packaging_unit_code(unit_code: str | None) -> bool:
    return (unit_code or "").strip().lower() in _PACKAGING_UNIT_CODES


def _normalize_search_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.strip().lower().split())


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
    product_units = getattr(item, "product_units", []) or []
    product_unit_conversions = getattr(item, "product_unit_conversions", []) or []
    return any(unit.is_base and unit.active for unit in product_units) or any(
        conversion.active for conversion in product_unit_conversions
    )


def resolve_packaging_factor(item: Item) -> float:
    tipo_emb = (item.tipo_embalagem_novo or "").strip().lower()
    unidades_por = _as_positive_float(item.unidades_por_embalagem)
    litros_por = _as_positive_float(item.litros_por_embalagem)
    grandeza_ref = _as_positive_float(item.grandeza_referencia)

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
    if unidades_por > 0:
        return unidades_por
    return 0.0


def uses_packaging_legacy_normalization(item: Item) -> bool:
    return (
        resolve_packaging_factor(item) > 1.0
        and not has_active_unit_config(item)
        and not ignore_packaging_metadata_for_stock(item)
    )


def resolve_canonical_unit(item: Item) -> str:
    product_units = getattr(item, "product_units", []) or []
    base_unit = next((unit for unit in product_units if unit.is_base and unit.active), None)
    if base_unit and base_unit.unit_code:
        return (base_unit.unit_code or "").strip().lower() or "un"

    tipo_emb = (item.tipo_embalagem_novo or "").strip().lower()
    unidade_raw = (item.unidade or "").strip().lower()
    litros_por = _as_positive_float(item.litros_por_embalagem)
    grandeza_ref = _as_positive_float(item.grandeza_referencia)
    unidades_por = _as_positive_float(item.unidades_por_embalagem)

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
        if any(token in hint for token in ("litro", "litr", "quilo", "kilo", "kg", "metro", "unidade")):
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