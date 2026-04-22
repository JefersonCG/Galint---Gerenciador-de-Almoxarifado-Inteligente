"""Audita e corrige drift entre embalagem operacional, conversao dinamica e NF processada.

Uso:
  .\.venv\Scripts\python.exe check_packaging_conversion_drift.py
  .\.venv\Scripts\python.exe check_packaging_conversion_drift.py --codigo 7896155116405
  .\.venv\Scripts\python.exe check_packaging_conversion_drift.py --documento-item-id 307
  .\.venv\Scripts\python.exe check_packaging_conversion_drift.py --apply

Objetivo:
- detectar itens cuja conversao direta embalagem -> unidade base ficou stale
- detectar itens documentais processados depois da ultima edicao do item e que
  ficaram com quantidade_base/movimento divergentes do fator operacional atual
- aplicar reparo seguro opcionalmente

Saida:
- codigo 0: sem divergencias pendentes
- codigo 1: divergencias encontradas em modo auditoria ou pendencias nao reparadas
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import sys
from typing import Any


os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import (
    DocumentoEntradaEstoqueItem,
    Item,
    OperationLog,
    StockBalance,
    StockMovement,
)
from galint_flask.services.finance_service import _normalize_financial_line
from galint_flask.services.inventory import _sync_packaging_conversion_graph
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.legacy_stock_normalizer import (
    ignore_packaging_metadata_for_stock,
    resolve_canonical_unit,
    resolve_packaging_factor,
)
from galint_flask.services.unit_conversion_engine import unit_conversion_engine


TOLERANCE = 1e-6
DISPLAY_TOLERANCE = 1e-3


@dataclass(slots=True)
class ConversionIssue:
    item: Item
    packaging_unit: str
    base_unit: str
    expected_factor: float
    current_factor: float | None
    conversion_id: int | None


@dataclass(slots=True)
class DocumentDriftIssue:
    row: DocumentoEntradaEstoqueItem
    movement: StockMovement | None
    normalized_line: dict[str, Any]
    stored_quantity_base: float | None
    movement_quantity_base: float | None


def _safe_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_unit(value: object) -> str:
    return unit_conversion_engine._normalize_unit_code(str(value or "").strip().lower())


def _format_number(value: float | None) -> str:
    if value is None:
        return "-"
    rounded = round(float(value), 6)
    if abs(rounded - round(rounded)) <= TOLERANCE:
        return str(int(round(rounded)))
    return f"{rounded:.6f}".rstrip("0").rstrip(".")


def _resolve_scope_codes(*, codigo: str | None, documento_item_id: int | None) -> list[str] | None:
    normalized_code = str(codigo or "").strip()
    if normalized_code:
        return [normalized_code]
    if documento_item_id is None:
        return None

    row = db.session.get(DocumentoEntradaEstoqueItem, documento_item_id)
    if row is None:
        raise ValueError(f"Documento item {documento_item_id} nao encontrado.")
    return [str(row.codigo_item or "").strip()]


def _iter_candidate_items(scope_codes: list[str] | None) -> list[Item]:
    query = Item.query.options(
        joinedload(Item.product_unit_conversions),
        joinedload(Item.product_units),
        joinedload(Item.product_dimensions),
    )
    if scope_codes:
        query = query.filter(Item.codigo_item.in_(scope_codes))
    return query.order_by(Item.codigo_item.asc()).all()


def _find_direct_packaging_conversion(item: Item, packaging_unit: str, base_unit: str):
    packaging_key = _normalize_unit(packaging_unit)
    base_key = _normalize_unit(base_unit)
    for row in item.product_unit_conversions or []:
        if not getattr(row, "active", True):
            continue
        if _normalize_unit(getattr(row, "from_unit", None)) == packaging_key and _normalize_unit(getattr(row, "to_unit", None)) == base_key:
            return row
    return None


def _audit_conversion_issue(item: Item) -> ConversionIssue | None:
    packaging_unit = str(getattr(item, "tipo_embalagem_novo", None) or "").strip().lower()
    if not packaging_unit or ignore_packaging_metadata_for_stock(item):
        return None

    expected_factor = _safe_float(resolve_packaging_factor(item)) or 0.0
    if expected_factor <= 0:
        return None

    base_unit = _normalize_unit(resolve_canonical_unit(item))
    if not base_unit or base_unit == _normalize_unit(packaging_unit):
        return None

    conversion = _find_direct_packaging_conversion(item, packaging_unit, base_unit)
    current_factor = _safe_float(getattr(conversion, "factor", None))
    if current_factor is not None and abs(current_factor - expected_factor) <= DISPLAY_TOLERANCE:
        return None

    return ConversionIssue(
        item=item,
        packaging_unit=packaging_unit,
        base_unit=base_unit,
        expected_factor=expected_factor,
        current_factor=current_factor,
        conversion_id=getattr(conversion, "id", None),
    )


def _find_document_movement(row: DocumentoEntradaEstoqueItem) -> StockMovement | None:
    if row.stock_movement is not None:
        return row.stock_movement
    if row.stock_movement_id is not None:
        movement = db.session.get(StockMovement, row.stock_movement_id)
        if movement is not None:
            return movement

    return (
        StockMovement.query
        .filter(StockMovement.reference_type == "entrada_documento_item")
        .filter(StockMovement.reference_id == str(row.id_documento_item))
        .filter(StockMovement.product_id == row.codigo_item)
        .order_by(StockMovement.id.asc())
        .first()
    )


def _audit_document_issue(row: DocumentoEntradaEstoqueItem) -> DocumentDriftIssue | None:
    item = row.item
    if item is None:
        return None
    if (row.status_processamento or "").strip().lower() != "processado":
        return None
    if row.processado_em is None or item.ultima_edicao_em is None:
        return None
    if row.processado_em < item.ultima_edicao_em:
        return None

    normalized_line = _normalize_financial_line(
        item,
        quantity=float(row.quantidade or 0.0),
        valor_unitario=_safe_float(row.valor_unitario),
        valor_total=_safe_float(row.valor_total),
        quantity_unit=row.unidade_quantidade,
        price_unit=row.unidade_preco,
    )
    expected_quantity_base = _safe_float(normalized_line.get("quantity_base")) or 0.0
    if expected_quantity_base <= 0:
        return None

    stored_quantity_base = _safe_float(row.quantidade_base)
    movement = _find_document_movement(row)
    movement_quantity_base = _safe_float(movement.quantity_base) if movement is not None else None

    stored_mismatch = stored_quantity_base is None or abs(stored_quantity_base - expected_quantity_base) > DISPLAY_TOLERANCE
    movement_mismatch = movement_quantity_base is not None and abs(movement_quantity_base - expected_quantity_base) > DISPLAY_TOLERANCE
    if not stored_mismatch and not movement_mismatch:
        return None

    return DocumentDriftIssue(
        row=row,
        movement=movement,
        normalized_line=normalized_line,
        stored_quantity_base=stored_quantity_base,
        movement_quantity_base=movement_quantity_base,
    )


def _iter_document_rows(scope_codes: list[str] | None, documento_item_id: int | None) -> list[DocumentoEntradaEstoqueItem]:
    query = (
        DocumentoEntradaEstoqueItem.query
        .options(
            joinedload(DocumentoEntradaEstoqueItem.item),
            joinedload(DocumentoEntradaEstoqueItem.stock_movement),
            joinedload(DocumentoEntradaEstoqueItem.operation_log),
            joinedload(DocumentoEntradaEstoqueItem.documento),
        )
        .filter(DocumentoEntradaEstoqueItem.status_processamento == "processado")
    )
    if scope_codes:
        query = query.filter(DocumentoEntradaEstoqueItem.codigo_item.in_(scope_codes))
    if documento_item_id is not None:
        query = query.filter(DocumentoEntradaEstoqueItem.id_documento_item == documento_item_id)
    return query.order_by(DocumentoEntradaEstoqueItem.id_documento_item.asc()).all()


def _apply_conversion_issue(issue: ConversionIssue) -> None:
    _sync_packaging_conversion_graph(issue.item)


def _apply_document_issue(issue: DocumentDriftIssue) -> None:
    row = issue.row
    item = row.item
    movement = issue.movement
    normalized_line = issue.normalized_line
    expected_quantity_base = float(normalized_line.get("quantity_base") or 0.0)

    row.unidade_quantidade = normalized_line.get("quantity_unit")
    row.quantidade_base = expected_quantity_base
    row.valor_unitario_base = _safe_float(normalized_line.get("unit_price_base"))
    row.unidade_preco = normalized_line.get("price_unit")
    row.fator_preco_base = _safe_float(normalized_line.get("factor_to_base"))
    row.valor_total = _safe_float(normalized_line.get("total_value"))
    if row.valor_unitario is None and normalized_line.get("unit_price_input") is not None:
        row.valor_unitario = _safe_float(normalized_line.get("unit_price_input"))
    row.status_processamento = "processado"
    row.erro_processamento = None

    if movement is not None:
        row.stock_movement_id = movement.id
        movement.quantity_base = expected_quantity_base
        movement.unit_base = _normalize_unit(resolve_canonical_unit(item)) or movement.unit_base
        metadata = dict(movement.metadata_json or {})
        metadata["repair_reason"] = "packaging_conversion_drift"
        metadata["repair_document_item_id"] = row.id_documento_item
        metadata["repair_applied_at"] = datetime.now(timezone.utc).isoformat()
        metadata["repair_expected_quantity_base"] = expected_quantity_base
        movement.metadata_json = metadata

    operation_log = row.operation_log or (db.session.get(OperationLog, row.operation_log_id) if row.operation_log_id is not None else None)
    if operation_log is not None:
        row.operation_log_id = operation_log.id
        operation_log.quantity_base = expected_quantity_base
        payload = dict(operation_log.payload_json or {})
        payload["quantity_base"] = expected_quantity_base
        payload["repair_reason"] = "packaging_conversion_drift"
        payload["repair_document_item_id"] = row.id_documento_item
        operation_log.payload_json = payload


def _recompute_balance(item_code: str) -> None:
    total_quantity = (
        db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
        .filter(StockMovement.product_id == item_code)
        .scalar()
    )
    balance = db.session.get(StockBalance, item_code)
    if balance is None:
        balance = StockBalance(product_id=item_code)
        db.session.add(balance)
    balance.quantity_base = float(total_quantity or 0.0)
    if hasattr(balance, "read_model_ready"):
        balance.read_model_ready = True

    try:
        inventory_engine.sync_packaging_read_model(product_id=item_code, commit=False)
    except Exception as exc:
        print(f"[warn] {item_code} | falha ao sincronizar read model: {exc}")


def _print_conversion_issues(issues: list[ConversionIssue]) -> None:
    if not issues:
        print("Conversoes stale: nenhuma")
        return
    print(f"Conversoes stale: {len(issues)}")
    for issue in issues:
        print(
            " - "
            f"{issue.item.codigo_item} | {issue.item.descricao or ''} | "
            f"{issue.packaging_unit}->{issue.base_unit} | esperado={_format_number(issue.expected_factor)} | "
            f"atual={_format_number(issue.current_factor)} | conversao_id={issue.conversion_id or '-'}"
        )


def _print_document_issues(issues: list[DocumentDriftIssue]) -> None:
    if not issues:
        print("Documentos com drift seguro: nenhum")
        return
    print(f"Documentos com drift seguro: {len(issues)}")
    for issue in issues:
        row = issue.row
        document_number = row.documento.numero_documento if row.documento is not None else "-"
        print(
            " - "
            f"doc_item={row.id_documento_item} | codigo={row.codigo_item} | documento={document_number} | "
            f"quantidade={_format_number(_safe_float(row.quantidade))} {row.unidade_quantidade or '-'} | "
            f"base_salva={_format_number(issue.stored_quantity_base)} | "
            f"base_movimento={_format_number(issue.movement_quantity_base)} | "
            f"base_esperada={_format_number(_safe_float(issue.normalized_line.get('quantity_base')))} | "
            f"processado={row.processado_em} | item_editado={row.item.ultima_edicao_em if row.item else None}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita drift de conversao de embalagem e repara casos seguros.")
    parser.add_argument("--codigo", help="Codigo do item a limitar a auditoria.")
    parser.add_argument("--documento-item-id", type=int, help="ID do documento item a limitar a auditoria.")
    parser.add_argument("--apply", action="store_true", help="Aplica o reparo seguro nas divergencias encontradas.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        scope_codes = _resolve_scope_codes(codigo=args.codigo, documento_item_id=args.documento_item_id)

        items = _iter_candidate_items(scope_codes)
        conversion_issues = [issue for issue in (_audit_conversion_issue(item) for item in items) if issue is not None]
        _print_conversion_issues(conversion_issues)

        touched_codes: set[str] = set()
        if conversion_issues:
            for issue in conversion_issues:
                _apply_conversion_issue(issue)
                if args.apply:
                    touched_codes.add(issue.item.codigo_item)
            db.session.flush()

        document_rows = _iter_document_rows(scope_codes, args.documento_item_id)
        document_issues = [issue for issue in (_audit_document_issue(row) for row in document_rows) if issue is not None]
        _print_document_issues(document_issues)

        skipped_repairs = 0
        if args.apply and document_issues:
            for issue in document_issues:
                if issue.movement is None:
                    skipped_repairs += 1
                    print(f"[warn] doc_item={issue.row.id_documento_item} sem stock_movement; reparo automatico ignorado")
                    continue
                _apply_document_issue(issue)
                touched_codes.add(issue.row.codigo_item)

        if args.apply and touched_codes:
            for item_code in sorted(touched_codes):
                _recompute_balance(item_code)
            db.session.commit()
            print(f"Reparos aplicados em {len(touched_codes)} item(ns).")
        elif args.apply:
            print("Nenhum reparo precisou ser aplicado.")

        if not args.apply:
            db.session.rollback()

        if not args.apply and (conversion_issues or document_issues):
            return 1
        if args.apply and skipped_repairs > 0:
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())