from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from app import create_app
from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoqueItem, FinanceLedgerEntry, Item
from galint_flask.services.price_normalization import infer_price_unit_for_item, normalize_document_line, normalize_item_price

TOLERANCE = 1e-8
SAMPLE_LIMIT = 20


@dataclass(slots=True)
class Summary:
    items_scanned: int = 0
    items_updated: int = 0
    document_rows_scanned: int = 0
    document_rows_updated: int = 0
    finance_rows_scanned: int = 0
    finance_rows_updated: int = 0
    missing_item_refs: int = 0
    samples: list[str] = field(default_factory=list)

    def add_sample(self, message: str) -> None:
        if len(self.samples) < SAMPLE_LIMIT:
            self.samples.append(message)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preenche campos normalizados de preco/quantidade base para itens, documentos e ledger financeiro."
    )
    parser.add_argument("--apply", action="store_true", help="Aplica as alteracoes no banco")
    parser.add_argument("--codigo", help="Filtra por um codigo de item especifico")
    return parser.parse_args()


def _as_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed


def _float_changed(current: object, expected: object, *, tolerance: float = TOLERANCE) -> bool:
    current_value = _as_float(current)
    expected_value = _as_float(expected)
    if current_value is None and expected_value is None:
        return False
    if current_value is None or expected_value is None:
        return True
    return abs(current_value - expected_value) > tolerance


def _text_changed(current: object, expected: object) -> bool:
    current_value = (str(current or "").strip().lower()) or None
    expected_value = (str(expected or "").strip().lower()) or None
    return current_value != expected_value


def _set_attr(target: object, attr: str, value: object, *, apply: bool) -> bool:
    changed = False
    current = getattr(target, attr)
    if isinstance(value, str) or isinstance(current, str):
        changed = _text_changed(current, value)
    elif isinstance(value, (float, int)) or isinstance(current, (float, int)) or current is None or value is None:
        changed = _float_changed(current, value)
    else:
        changed = current != value
    if changed and apply:
        setattr(target, attr, value)
    return changed


def _build_item_map(codigo: str | None = None) -> dict[str, Item]:
    query = Item.query.order_by(Item.codigo_item.asc())
    if codigo:
        query = query.filter(Item.codigo_item == codigo)
    return {str(item.codigo_item): item for item in query.all() if item.codigo_item}


def _safe_normalize_item_price(item: Item, *, raw_price: float, price_unit: str) -> dict[str, Any]:
    try:
        normalized = normalize_item_price(item, unit_price=raw_price, price_unit=price_unit)
        return {
            "unit_price_base": float(normalized.unit_price_base),
            "price_unit": normalized.price_unit,
            "factor_to_base": float(normalized.factor_to_base),
        }
    except Exception:
        return {
            "unit_price_base": raw_price,
            "price_unit": price_unit,
            "factor_to_base": 1.0,
        }


def _safe_normalize_line(
    item: Item,
    *,
    quantity: float,
    quantity_unit: str,
    unit_price: float | None,
    total_price: float | None,
    price_unit: str,
) -> dict[str, Any]:
    try:
        normalized = normalize_document_line(
            item,
            quantity=quantity,
            quantity_unit=quantity_unit,
            unit_price=unit_price,
            total_price=total_price,
            price_unit=price_unit,
        )
        return {
            "quantity_unit": normalized.quantity_unit,
            "quantity_base": float(normalized.quantity_base),
            "unit_price_base": normalized.unit_price_base,
            "price_unit": normalized.price_unit,
            "factor_to_base": float(normalized.factor_to_base),
        }
    except Exception:
        resolved_total = total_price
        if resolved_total is None and unit_price is not None:
            resolved_total = round(unit_price * quantity, 2)
        unit_price_base = round(resolved_total / quantity, 8) if resolved_total is not None and quantity > 0 else unit_price
        return {
            "quantity_unit": quantity_unit,
            "quantity_base": quantity,
            "unit_price_base": unit_price_base,
            "price_unit": price_unit,
            "factor_to_base": 1.0 if unit_price is not None else None,
        }


def _backfill_item_prices(item: Item, summary: Summary, *, apply: bool) -> None:
    summary.items_scanned += 1
    changed_any = False

    for kind in ("compra", "reposicao"):
        raw_attr = f"preco_{kind}_unitario"
        base_attr = f"preco_{kind}_unitario_base"
        unit_attr = f"preco_{kind}_unidade_preco"
        factor_attr = f"preco_{kind}_fator_base"

        raw_price = _as_float(getattr(item, raw_attr))
        if raw_price is None or raw_price <= 0:
            continue

        price_unit = (getattr(item, unit_attr) or "").strip().lower() or infer_price_unit_for_item(item)
        normalized = _safe_normalize_item_price(item, raw_price=raw_price, price_unit=price_unit)

        changed = False
        changed |= _set_attr(item, base_attr, float(normalized["unit_price_base"]), apply=apply)
        changed |= _set_attr(item, unit_attr, normalized["price_unit"], apply=apply)
        changed |= _set_attr(item, factor_attr, float(normalized["factor_to_base"]), apply=apply)

        if changed:
            changed_any = True
            summary.add_sample(
                f"ITEM {item.codigo_item} {kind}: bruto={raw_price:g} {normalized['price_unit']} -> base={float(normalized['unit_price_base']):g}"
            )

    if changed_any:
        summary.items_updated += 1


def _backfill_document_row(row: DocumentoEntradaEstoqueItem, item: Item | None, summary: Summary, *, apply: bool) -> None:
    summary.document_rows_scanned += 1
    if item is None:
        summary.missing_item_refs += 1
        return

    quantity = float(row.quantidade or 0.0)
    quantity_unit = (row.unidade_quantidade or "").strip().lower() or infer_price_unit_for_item(item)
    price_unit = (row.unidade_preco or "").strip().lower() or quantity_unit
    normalized = _safe_normalize_line(
        item,
        quantity=quantity,
        quantity_unit=quantity_unit,
        unit_price=_as_float(row.valor_unitario),
        total_price=_as_float(row.valor_total),
        price_unit=price_unit,
    )

    changed = False
    changed |= _set_attr(row, "unidade_quantidade", normalized["quantity_unit"], apply=apply)
    changed |= _set_attr(row, "quantidade_base", float(normalized["quantity_base"]), apply=apply)
    changed |= _set_attr(row, "valor_unitario_base", normalized["unit_price_base"], apply=apply)
    changed |= _set_attr(row, "unidade_preco", normalized["price_unit"], apply=apply)
    changed |= _set_attr(row, "fator_preco_base", normalized["factor_to_base"], apply=apply)

    if changed:
        summary.document_rows_updated += 1
        summary.add_sample(
            f"DOC_ITEM {row.id_documento_item} {row.codigo_item}: qtd={quantity:g} {normalized['quantity_unit']} -> base={float(normalized['quantity_base']):g}, preco_base={float(normalized['unit_price_base'] or 0.0):g}"
        )


def _backfill_finance_row(entry: FinanceLedgerEntry, item: Item | None, summary: Summary, *, apply: bool) -> None:
    summary.finance_rows_scanned += 1
    if item is None:
        summary.missing_item_refs += 1
        return

    quantity = float(entry.quantidade or 0.0)
    quantity_unit = (entry.unidade_quantidade or "").strip().lower() or infer_price_unit_for_item(item)
    price_unit = (entry.unidade_preco or "").strip().lower() or quantity_unit
    normalized = _safe_normalize_line(
        item,
        quantity=quantity,
        quantity_unit=quantity_unit,
        unit_price=_as_float(entry.valor_unitario),
        total_price=_as_float(entry.valor_total),
        price_unit=price_unit,
    )

    changed = False
    changed |= _set_attr(entry, "unidade_quantidade", normalized["quantity_unit"], apply=apply)
    changed |= _set_attr(entry, "quantidade_base", float(normalized["quantity_base"]), apply=apply)
    changed |= _set_attr(entry, "valor_unitario_base", normalized["unit_price_base"], apply=apply)
    changed |= _set_attr(entry, "unidade_preco", normalized["price_unit"], apply=apply)
    changed |= _set_attr(entry, "fator_preco_base", normalized["factor_to_base"], apply=apply)

    if changed:
        summary.finance_rows_updated += 1
        summary.add_sample(
            f"LEDGER {entry.id} {entry.codigo_item}: qtd={quantity:g} {normalized['quantity_unit']} -> base={float(normalized['quantity_base']):g}, preco_base={float(normalized['unit_price_base'] or 0.0):g}"
        )


def _run_backfill(*, codigo: str | None, apply: bool) -> Summary:
    summary = Summary()
    item_map = _build_item_map(codigo)

    for item in item_map.values():
        _backfill_item_prices(item, summary, apply=apply)

    doc_query = DocumentoEntradaEstoqueItem.query.order_by(DocumentoEntradaEstoqueItem.id_documento_item.asc())
    if codigo:
        doc_query = doc_query.filter(DocumentoEntradaEstoqueItem.codigo_item == codigo)
    for row in doc_query.all():
        _backfill_document_row(row, item_map.get(str(row.codigo_item or "")), summary, apply=apply)

    finance_query = FinanceLedgerEntry.query.order_by(FinanceLedgerEntry.id.asc())
    if codigo:
        finance_query = finance_query.filter(FinanceLedgerEntry.codigo_item == codigo)
    for entry in finance_query.all():
        _backfill_finance_row(entry, item_map.get(str(entry.codigo_item or "")), summary, apply=apply)

    if apply:
        db.session.commit()
    else:
        db.session.rollback()
    return summary


def _print_summary(summary: Summary, *, apply: bool) -> None:
    mode = "APPLY" if apply else "PREVIEW"
    print(f"PRICE NORMALIZATION BACKFILL [{mode}]")
    print(f"Itens verificados: {summary.items_scanned}")
    print(f"Itens atualizados: {summary.items_updated}")
    print(f"Linhas documentais verificadas: {summary.document_rows_scanned}")
    print(f"Linhas documentais atualizadas: {summary.document_rows_updated}")
    print(f"Lancamentos financeiros verificados: {summary.finance_rows_scanned}")
    print(f"Lancamentos financeiros atualizados: {summary.finance_rows_updated}")
    print(f"Referencias sem item vinculado: {summary.missing_item_refs}")
    if summary.samples:
        print("Amostras:")
        for sample in summary.samples:
            print(f"- {sample}")


def main() -> int:
    args = _parse_args()
    app = create_app()
    with app.app_context():
        summary = _run_backfill(codigo=(args.codigo or "").strip() or None, apply=bool(args.apply))
        _print_summary(summary, apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())