from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..models import Item, ProductUnitConversion


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

    def convert_to_base(self, product_id: str, quantity: float, from_unit: str) -> ConversionResult:
        product_id = (product_id or "").strip()
        from_unit = (from_unit or "").strip().lower()
        if not product_id:
            raise UnitConversionError("product_id é obrigatório")
        if not from_unit:
            raise UnitConversionError("from_unit é obrigatório")

        try:
            quantity_value = float(quantity)
        except (TypeError, ValueError) as exc:
            raise UnitConversionError("quantity inválida") from exc

        if not isfinite(quantity_value):
            raise UnitConversionError("quantity inválida")

        item = Item.query.get(product_id)
        if not item:
            raise UnitConversionError("Produto não encontrado")

        base_unit = self._get_base_unit(item)
        if from_unit == base_unit.unit_code:
            return ConversionResult(
                quantity_base=quantity_value,
                unit_base=base_unit.unit_code,
                conversion_path=[],
                factor_applied=1.0,
                metadata={"mode": "identity"},
            )

        graph = self._build_graph(item.product_unit_conversions)
        factor, path = self._find_factor(graph, from_unit, base_unit.unit_code)
        quantity_base = quantity_value * factor
        return ConversionResult(
            quantity_base=quantity_base,
            unit_base=base_unit.unit_code,
            conversion_path=path,
            factor_applied=factor,
            metadata={
                "product_id": product_id,
                "steps": len(path),
            },
        )

    def _get_base_unit(self, item: Item) -> ResolvedBaseUnit:
        base_units = [unit for unit in item.product_units if unit.is_base and unit.active]
        if not base_units:
            unidade_item = (item.unidade or "").strip().lower()
            if unidade_item:
                return ResolvedBaseUnit(unit_code=unidade_item, source="legacy_item_unidade")
            tipo_emb = (item.tipo_embalagem_novo or "").strip().lower()
            if tipo_emb:
                return ResolvedBaseUnit(unit_code=tipo_emb, source="legacy_tipo_embalagem")
            raise UnitConversionError("Produto sem unidade base configurada")
        if len(base_units) > 1:
            raise UnitConversionError("Produto com múltiplas unidades base ativas")
        return ResolvedBaseUnit(unit_code=base_units[0].unit_code, source="product_unit")

    def _build_graph(self, conversions: list[ProductUnitConversion]) -> dict[str, list[tuple[str, float]]]:
        graph: dict[str, list[tuple[str, float]]] = {}
        for conversion in conversions:
            if not conversion.active:
                continue
            from_unit = (conversion.from_unit or "").strip().lower()
            to_unit = (conversion.to_unit or "").strip().lower()
            factor = float(conversion.factor or 0)
            if not from_unit or not to_unit or factor <= 0:
                continue
            graph.setdefault(from_unit, []).append((to_unit, factor))
        return graph

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
