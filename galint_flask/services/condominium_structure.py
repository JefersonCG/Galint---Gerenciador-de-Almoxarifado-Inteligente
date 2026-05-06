from __future__ import annotations

import re
from typing import Any

from ..models import CondominiumBuilding, CondominiumUnit


VALID_UNIT_STATUSES = {"ocupado", "vago", "reforma"}
DASHBOARD_UNIT_STATUSES = (*sorted(VALID_UNIT_STATUSES), "sem_cadastro")
UNIT_STATUS_LABELS = {
    "ocupado": "Ocupado",
    "vago": "Vago",
    "reforma": "Reforma",
    "sem_cadastro": "Sem cadastro",
}


def normalize_unit_status(value: object, *, default: str = "vago") -> str:
    status = str(value or "").strip().lower()
    return status if status in VALID_UNIT_STATUSES else default


def unit_dashboard_status(unit: CondominiumUnit) -> str:
    has_active_owner = any(str(owner.status or "").strip().lower() == "ativo" for owner in unit.owners)
    if not has_active_owner:
        return "sem_cadastro"
    return normalize_unit_status(unit.status, default="ocupado")


def _natural_key(value: object) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", str(value or ""))
    return tuple(int(part) if part.isdigit() else part.casefold() for part in parts)


def _split_units(raw_units: str) -> list[str]:
    if "," in raw_units or ";" in raw_units:
        tokens = re.split(r"[,;]+", raw_units)
    else:
        tokens = re.split(r"\s+", raw_units)
    return [token.strip() for token in tokens if token.strip()]


def _infer_floor_from_unit(unit_number: str, *, suffix_width: int) -> int:
    digits = re.sub(r"\D", "", unit_number)
    if len(digits) > suffix_width:
        return int(digits[:-suffix_width])
    return 0


def _parse_custom_units(custom_units_text: str, *, suffix_width: int) -> dict[int, list[str]]:
    custom_by_floor: dict[int, list[str]] = {}
    for line_number, raw_line in enumerate((custom_units_text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        floor_number: int | None = None
        units_raw = line
        for separator in (":", "="):
            if separator in line:
                floor_raw, units_raw = line.split(separator, 1)
                try:
                    floor_number = int(floor_raw.strip())
                except ValueError as exc:
                    raise ValueError(f"Linha {line_number}: andar invalido.") from exc
                break

        for unit_number in _split_units(units_raw):
            target_floor = floor_number
            if target_floor is None:
                target_floor = _infer_floor_from_unit(unit_number, suffix_width=suffix_width)
            custom_by_floor.setdefault(target_floor, []).append(unit_number)
    return custom_by_floor


def generate_unit_layout(
    *,
    floor_start: int,
    floor_count: int,
    units_per_floor: int,
    unit_suffix_start: int,
    suffix_width: int,
    custom_units_text: str = "",
) -> list[dict[str, object]]:
    if floor_count < 1:
        raise ValueError("Informe pelo menos 1 andar.")
    if units_per_floor < 0:
        raise ValueError("Unidades por andar nao pode ser negativo.")
    if suffix_width < 1 or suffix_width > 4:
        raise ValueError("Casas do final da unidade deve ficar entre 1 e 4.")

    by_floor: dict[int, list[str]] = {}
    for offset in range(floor_count):
        floor_number = floor_start + offset
        units = []
        for position in range(units_per_floor):
            suffix = unit_suffix_start + position
            units.append(f"{floor_number}{suffix:0{suffix_width}d}")
        by_floor[floor_number] = units

    custom_by_floor = _parse_custom_units(custom_units_text, suffix_width=suffix_width)
    for floor_number, units in custom_by_floor.items():
        by_floor[floor_number] = units

    seen: set[str] = set()
    layout: list[dict[str, object]] = []
    for floor_number in sorted(by_floor):
        for position, unit_number in enumerate(by_floor[floor_number], start=1):
            normalized_number = str(unit_number).strip()
            if not normalized_number:
                continue
            unique_key = normalized_number.casefold()
            if unique_key in seen:
                raise ValueError(f"Unidade duplicada no bloco: {normalized_number}.")
            seen.add(unique_key)
            layout.append({"floor_number": floor_number, "number": normalized_number, "position": position})
    return layout


def sync_building_units(building: CondominiumBuilding, layout: list[dict[str, object]], *, default_status: str = "vago") -> None:
    initial_status = normalize_unit_status(default_status)
    existing_by_number = {str(unit.number).casefold(): unit for unit in building.units}
    synced_numbers: set[str] = set()

    for spec in layout:
        number = str(spec["number"]).strip()
        number_key = number.casefold()
        synced_numbers.add(number_key)
        unit = existing_by_number.get(number_key)
        if unit is None:
            unit = CondominiumUnit(number=number, status=initial_status)
            building.units.append(unit)
        unit.floor_number = int(spec["floor_number"])
        unit.position = int(spec["position"])
        unit.active = True

    for number_key, unit in existing_by_number.items():
        if number_key not in synced_numbers:
            unit.active = False


def build_condominium_block_dashboard() -> dict[str, object] | None:
    buildings = (
        CondominiumBuilding.query
        .filter_by(active=True)
        .order_by(CondominiumBuilding.display_order.asc(), CondominiumBuilding.id.asc())
        .all()
    )
    if not buildings:
        return None

    cards: list[dict[str, object]] = []
    totals = {status: 0 for status in DASHBOARD_UNIT_STATUSES}
    totals["unidades"] = 0

    for building in buildings:
        active_units = [unit for unit in building.units if unit.active]
        floors_by_number: dict[int, list[CondominiumUnit]] = {}
        block_totals = {status: 0 for status in DASHBOARD_UNIT_STATUSES}
        block_totals["unidades"] = 0

        for unit in active_units:
            floors_by_number.setdefault(int(unit.floor_number or 0), []).append(unit)
            status = unit_dashboard_status(unit)
            block_totals[status] += 1
            block_totals["unidades"] += 1
            totals[status] += 1
            totals["unidades"] += 1

        max_columns = max((len(units) for units in floors_by_number.values()), default=1)
        floors: list[dict[str, object]] = []
        for floor_number in sorted(floors_by_number, reverse=True):
            ordered_units = sorted(
                floors_by_number[floor_number],
                key=lambda unit: (int(unit.position or 0), _natural_key(unit.number)),
            )
            row_units: list[dict[str, object]] = []
            for position in range(max_columns):
                if position >= len(ordered_units):
                    row_units.append({"empty": True})
                    continue
                unit = ordered_units[position]
                status = unit_dashboard_status(unit)
                row_units.append({"empty": False, "number": unit.number, "status": status, "status_label": UNIT_STATUS_LABELS[status]})
            floors.append({"floor": floor_number, "units": row_units})

        cards.append(
            {
                "building_id": building.id,
                "number": building.code,
                "name": building.name,
                "max_columns": max_columns,
                "floors": floors,
                "totals": block_totals,
            }
        )

    return {"cards": cards, "totals": totals, "block_count": len(cards)}