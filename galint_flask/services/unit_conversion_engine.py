from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..models import Item, ProductUnitConversion
from .legacy_stock_normalizer import ignore_packaging_metadata_for_stock, is_packaging_unit_code, resolve_canonical_unit, resolve_packaging_factor, uses_packaging_legacy_normalization


class UnitConversionError(ValueError):
    pass


@dataclass(slots=True)
class ConversionResult:
    quantity_base: float
    unit_base: str
    conversion_path: list[dict[str, object]]
    factor_applied: float
    metadata: dict[str, object]


@dataclass(slots=True)
class ResolvedBaseUnit:
    unit_code: str
    source: str


class UnitConversionEngine:
    """Serviço puro de conversão entre unidades do produto."""

    MAX_DEPTH = 10

    _UNIT_ALIASES = {
        "unidade": "un",
        "unidades": "un",
        "unit": "un",
        "units": "un",
        "metro": "m",
        "metros": "m",
        "metre": "m",
        "metres": "m",
        "litro": "l",
        "litros": "l",
        "quilo": "kg",
        "quilos": "kg",
        "kilo": "kg",
        "kilos": "kg",
        "caixas": "caixa",
        "pacotes": "pacote",
        "fardos": "fardo",
        "rolos": "rolo",
        "latas": "lata",
        "baldes": "balde",
        "bombonas": "bombona",
        "sacos": "saco",
    }

    def convert_to_base(self, product_id: str, quantity: float, from_unit: str) -> ConversionResult:
        product_id = (product_id or "").strip()
        if not product_id:
            raise UnitConversionError("product_id é obrigatório")

        try:
            quantity_value = float(quantity)
        except (TypeError, ValueError) as exc:
            raise UnitConversionError("quantity inválida") from exc

        if not isfinite(quantity_value):
            raise UnitConversionError("quantity inválida")

        item = Item.query.get(product_id)
        if not item:
            raise UnitConversionError("Produto não encontrado")

        return self.convert_item_to_base(item, quantity_value, from_unit)

    def convert_item_to_base(self, item: Item, quantity: float, from_unit: str) -> ConversionResult:
        from_unit_norm = self._normalize_unit_code(from_unit)
        if not from_unit_norm:
            raise UnitConversionError("from_unit é obrigatório")

        try:
            quantity_value = float(quantity)
        except (TypeError, ValueError) as exc:
            raise UnitConversionError("quantity inválida") from exc

        if not isfinite(quantity_value):
            raise UnitConversionError("quantity inválida")

        base_unit = self._get_base_unit(item)
        if from_unit_norm == base_unit.unit_code:
            return ConversionResult(
                quantity_base=quantity_value,
                unit_base=base_unit.unit_code,
                conversion_path=[],
                factor_applied=1.0,
                metadata={"mode": "identity"},
            )

        graph = self._build_graph(item.product_unit_conversions)
        if graph:
            try:
                factor, path = self._find_factor(graph, from_unit_norm, base_unit.unit_code)
                quantity_base = quantity_value * factor
                return ConversionResult(
                    quantity_base=quantity_base,
                    unit_base=base_unit.unit_code,
                    conversion_path=path,
                    factor_applied=factor,
                    metadata={
                        "product_id": item.codigo_item,
                        "steps": len(path),
                    },
                )
            except UnitConversionError:
                pass

        legacy_packaging = self._convert_legacy_packaging(item, quantity_value, from_unit_norm, base_unit.unit_code)
        if legacy_packaging is not None:
            quantity_base, factor = legacy_packaging
            return ConversionResult(
                quantity_base=quantity_base,
                unit_base=base_unit.unit_code,
                conversion_path=[
                    {
                        "from_unit": from_unit_norm,
                        "to_unit": base_unit.unit_code,
                        "factor": factor,
                        "source": "legacy_packaging",
                    }
                ],
                factor_applied=factor,
                metadata={"mode": "legacy_packaging"},
            )

        raise UnitConversionError(
            f"Não existe caminho de conversão válido de '{from_unit_norm}' para '{base_unit.unit_code}'"
        )

    def _get_base_unit(self, item: Item) -> ResolvedBaseUnit:
        base_units = [unit for unit in item.product_units if unit.is_base and unit.active]
        if not base_units:
            if uses_packaging_legacy_normalization(item):
                return ResolvedBaseUnit(unit_code=self._normalize_unit_code(resolve_canonical_unit(item)), source="legacy_packaging")
            unidade_item = (item.unidade or "").strip().lower()
            if unidade_item:
                return ResolvedBaseUnit(unit_code=self._normalize_unit_code(unidade_item), source="legacy_item_unidade")
            tipo_emb = (item.tipo_embalagem_novo or "").strip().lower()
            if tipo_emb:
                return ResolvedBaseUnit(unit_code=self._normalize_unit_code(tipo_emb), source="legacy_tipo_embalagem")
            raise UnitConversionError("Produto sem unidade base configurada")
        if len(base_units) > 1:
            raise UnitConversionError("Produto com múltiplas unidades base ativas")

        configured_base_unit = self._normalize_unit_code(base_units[0].unit_code)
        if configured_base_unit and not is_packaging_unit_code(configured_base_unit):
            return ResolvedBaseUnit(unit_code=configured_base_unit, source="product_unit")

        canonical_unit = self._normalize_unit_code(resolve_canonical_unit(item))
        if canonical_unit:
            return ResolvedBaseUnit(unit_code=canonical_unit, source="canonical_unit")

        return ResolvedBaseUnit(unit_code=configured_base_unit, source="product_unit_packaging")

    def _build_graph(self, conversions: list[ProductUnitConversion]) -> dict[str, list[tuple[str, float]]]:
        graph: dict[str, list[tuple[str, float]]] = {}
        for conversion in conversions:
            if not conversion.active:
                continue
            from_unit = self._normalize_unit_code(conversion.from_unit)
            to_unit = self._normalize_unit_code(conversion.to_unit)
            factor = float(conversion.factor or 0)
            if not from_unit or not to_unit or factor <= 0:
                continue
            graph.setdefault(from_unit, []).append((to_unit, factor))
        return graph

    def _convert_legacy_packaging(
        self,
        item: Item,
        quantity_value: float,
        from_unit: str,
        base_unit: str,
    ) -> tuple[float, float] | None:
        factor = float(resolve_packaging_factor(item) or 0.0)
        if factor <= 0 or ignore_packaging_metadata_for_stock(item):
            return None
        if from_unit == base_unit:
            return quantity_value, 1.0

        packaging_units = {
            self._normalize_unit_code(item.tipo_embalagem_novo),
            self._normalize_unit_code(item.unidade),
        }
        packaging_units.update(
            self._normalize_unit_code(unit.unit_code)
            for unit in (getattr(item, "product_units", None) or [])
            if getattr(unit, "active", False) and getattr(unit, "unit_code", None)
        )
        packaging_units.discard("")

        content_unit = self._legacy_packaging_content_unit(item)
        if content_unit and (base_unit in packaging_units or is_packaging_unit_code(base_unit)):
            if from_unit == content_unit:
                inverse_factor = 1.0 / factor
                return quantity_value * inverse_factor, inverse_factor

        if from_unit in packaging_units or is_packaging_unit_code(from_unit):
            return quantity_value * factor, factor
        return None

    def _legacy_packaging_content_unit(self, item: Item) -> str:
        tipo_emb = self._normalize_unit_code(getattr(item, "tipo_embalagem_novo", None))
        try:
            unidades_por = float(getattr(item, "unidades_por_embalagem", 0) or 0)
        except (TypeError, ValueError):
            unidades_por = 0.0
        try:
            litros_por = float(getattr(item, "litros_por_embalagem", 0) or 0)
        except (TypeError, ValueError):
            litros_por = 0.0
        try:
            grandeza_ref = float(getattr(item, "grandeza_referencia", 0) or 0)
        except (TypeError, ValueError):
            grandeza_ref = 0.0

        if litros_por > 0:
            return "l"
        if tipo_emb == "rolo" and unidades_por > 0:
            return "m"
        if grandeza_ref > 0:
            return "kg"
        if unidades_por > 0:
            return "un"

        canonical_unit = self._normalize_unit_code(resolve_canonical_unit(item))
        if canonical_unit and not is_packaging_unit_code(canonical_unit):
            return canonical_unit
        return ""

    def _normalize_unit_code(self, value: str | None) -> str:
        raw = (value or "").strip().lower()
        if not raw:
            return ""
        return self._UNIT_ALIASES.get(raw, raw)

    def _find_factor(
        self,
        graph: dict[str, list[tuple[str, float]]],
        from_unit: str,
        base_unit: str,
    ) -> tuple[float, list[dict[str, object]]]:
        visited_depth: dict[str, int] = {from_unit: 0}
        queue: list[tuple[str, float, list[dict[str, object]]]] = [(from_unit, 1.0, [])]

        while queue:
            current, factor_so_far, path = queue.pop(0)
            depth = len(path)
            if depth > self.MAX_DEPTH:
                continue
            if current == base_unit:
                return factor_so_far, path
            for next_unit, edge_factor in graph.get(current, []):
                next_depth = depth + 1
                if next_depth > self.MAX_DEPTH:
                    continue
                previous_depth = visited_depth.get(next_unit)
                if previous_depth is not None and previous_depth <= next_depth:
                    continue
                visited_depth[next_unit] = next_depth
                queue.append(
                    (
                        next_unit,
                        factor_so_far * edge_factor,
                        [
                            *path,
                            {
                                "from_unit": current,
                                "to_unit": next_unit,
                                "factor": edge_factor,
                            },
                        ],
                    )
                )

        raise UnitConversionError(
            f"Não existe caminho de conversão válido de '{from_unit}' para '{base_unit}'"
        )


unit_conversion_engine = UnitConversionEngine()
