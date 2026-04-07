from __future__ import annotations

from collections import defaultdict

from ..utils.formatters import format_number_br


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(int(value))
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _normalize_category_unit_label(value: str | None) -> str:
    raw = _safe_text(value).strip()
    lowered = raw.lower()
    if lowered in {"", "unidade", "unidades", "und"}:
        return "un"
    if lowered == "un":
        return "un"
    if lowered in {"l", "litro", "litros"}:
        return "L"
    if lowered in {"kg", "quilo", "quilos"}:
        return "Kg"
    if lowered in {"m", "metro", "metros"}:
        return "m"
    if lowered in {"peca", "peça", "pecas", "peças"}:
        return "Peça"
    if lowered in {"par", "pares"}:
        return "Par"
    if raw:
        try:
            float(raw.replace(",", "."))
            return "Cadastro inconsistente"
        except ValueError:
            return raw
    return "Sem unidade"


def _category_unit_sort_key(unit_label: str) -> tuple[int, str]:
    order = {
        "un": 0,
        "L": 1,
        "Kg": 2,
        "m": 3,
        "Peça": 4,
        "Par": 5,
        "Cadastro inconsistente": 90,
        "Sem unidade": 91,
    }
    return (order.get(unit_label, 50), unit_label.lower())


def _format_category_quantity(value: float) -> str:
    magnitude = abs(float(value or 0.0))
    decimals = 0 if abs(magnitude - round(magnitude)) <= 1e-6 else 2
    return format_number_br(value, decimals=decimals, strip_trailing_zeros=True)


def build_category_balance_summary(items: list[dict]) -> list[dict[str, object]]:
    totals: dict[str, float] = defaultdict(float)
    for item in items:
        quantity = _safe_float(item.get("saldo"))
        if abs(quantity) <= 1e-6:
            continue
        unit_label = _normalize_category_unit_label(item.get("unidade_interna_display") or item.get("unidade"))
        totals[unit_label] += quantity

    lines: list[dict[str, object]] = []
    for unit_label, total in sorted(totals.items(), key=lambda row: _category_unit_sort_key(row[0])):
        lines.append(
            {
                "unit": unit_label,
                "quantity": total,
                "display": f"{_format_category_quantity(total)} {unit_label}",
            }
        )
    return lines


def build_category_value_summary(items: list[dict]) -> dict[str, object]:
    total_compra = 0.0
    total_reposicao = 0.0
    with_compra = 0
    with_reposicao = 0
    missing_compra = 0
    missing_reposicao = 0

    for item in items:
        compra = item.get("valor_estoque_compra_total")
        reposicao = item.get("valor_estoque_reposicao_total")
        if compra is None:
            missing_compra += 1
        else:
            total_compra += _safe_float(compra)
            with_compra += 1
        if reposicao is None:
            missing_reposicao += 1
        else:
            total_reposicao += _safe_float(reposicao)
            with_reposicao += 1

    return {
        "total_compra": total_compra if with_compra > 0 else None,
        "total_reposicao": total_reposicao if with_reposicao > 0 else None,
        "with_compra": with_compra,
        "with_reposicao": with_reposicao,
        "missing_compra": missing_compra,
        "missing_reposicao": missing_reposicao,
    }