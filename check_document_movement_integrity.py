"""Audita integridade entre movimentos documentais e seus itens de documento.

Uso:
  .\.venv\Scripts\python.exe check_document_movement_integrity.py
  .\.venv\Scripts\python.exe check_document_movement_integrity.py --codigo 7897432700676
  .\.venv\Scripts\python.exe check_document_movement_integrity.py --movement-id 3677

Objetivo:
- localizar movimentos com reference_type entrada_documento_item que perderam o item documental
- sinalizar movimentos ligados a documentos com movimenta_estoque desativado
- sinalizar movimentos cujo produto diverge do codigo do item documental referenciado
- detectar colisao entre id_documento_item e id_entrada legado no mesmo reference_id
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import os
import sys


os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from galint_flask import create_app
from galint_flask.models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Entrada, StockMovement


@dataclass(slots=True)
class IntegrityIssue:
    movement_id: int
    product_id: str
    movement_type: str
    quantity_base: float
    reference_id: str | None
    source: str | None
    issue_codes: list[str]
    detail: str
    document_number: str | None
    document_item_id: int | None
    document_item_code: str | None
    legacy_entry_id: int | None
    legacy_entry_code: str | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audita movimentos documentais inconsistentes no ledger.")
    parser.add_argument("--codigo", action="append", help="Codigo do item a filtrar. Pode repetir.")
    parser.add_argument("--movement-id", action="append", type=int, help="ID especifico do movimento a filtrar.")
    return parser.parse_args()


def _normalize_codes(values: list[str] | None) -> list[str]:
    return sorted({str(value or "").strip() for value in (values or []) if str(value or "").strip()})


def _safe_ref_id(value: object) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _find_legacy_entry_movement(movement: StockMovement) -> tuple[Entrada | None, StockMovement | None]:
    ref_id = _safe_ref_id(movement.reference_id)
    if ref_id is None:
        return None, None

    entrada = Entrada.query.filter_by(id_entrada=ref_id).first()
    legacy_movement = (
        StockMovement.query
        .filter(StockMovement.reference_type == "entrada")
        .filter(StockMovement.reference_id == str(ref_id))
        .filter(StockMovement.product_id == movement.product_id)
        .order_by(StockMovement.id.asc())
        .first()
    )
    return entrada, legacy_movement


def _classify_movement(movement: StockMovement) -> IntegrityIssue | None:
    ref_id = _safe_ref_id(movement.reference_id)
    source = str((movement.metadata_json or {}).get("source") or "").strip() or None
    if ref_id is None:
        return IntegrityIssue(
            movement_id=int(movement.id),
            product_id=str(movement.product_id or ""),
            movement_type=str(movement.movement_type or ""),
            quantity_base=float(movement.quantity_base or 0.0),
            reference_id=movement.reference_id,
            source=source,
            issue_codes=["reference_id_invalido"],
            detail="reference_id nao e um inteiro valido para resolver o item documental.",
            document_number=None,
            document_item_id=None,
            document_item_code=None,
            legacy_entry_id=None,
            legacy_entry_code=None,
        )

    row = DocumentoEntradaEstoqueItem.query.filter_by(id_documento_item=ref_id).first()
    if row is None:
        entrada, _legacy_movement = _find_legacy_entry_movement(movement)
        detail = "item documental inexistente para o reference_id do movimento."
        if entrada is not None and str(entrada.codigo_item or "").strip() == str(movement.product_id or "").strip():
            detail = (
                "item documental inexistente e reference_id coincide com uma entrada legada do mesmo produto; "
                "possivel colisao entre id_documento_item e id_entrada."
            )
        return IntegrityIssue(
            movement_id=int(movement.id),
            product_id=str(movement.product_id or ""),
            movement_type=str(movement.movement_type or ""),
            quantity_base=float(movement.quantity_base or 0.0),
            reference_id=movement.reference_id,
            source=source,
            issue_codes=["documento_item_inexistente"],
            detail=detail,
            document_number=None,
            document_item_id=None,
            document_item_code=None,
            legacy_entry_id=int(entrada.id_entrada) if entrada is not None else None,
            legacy_entry_code=str(entrada.codigo_item or "").strip() or None if entrada is not None else None,
        )

    document = DocumentoEntradaEstoque.query.filter_by(id_documento=row.documento_id).first()
    issue_codes: list[str] = []
    detail_parts: list[str] = []
    row_code = str(row.codigo_item or "").strip()
    movement_code = str(movement.product_id or "").strip()
    if row_code != movement_code:
        issue_codes.append("codigo_divergente")
        detail_parts.append(f"item documental={row_code} difere do movimento={movement_code}")

    if document is not None and not bool(getattr(document, "movimenta_estoque", True)):
        issue_codes.append("documento_sem_movimento")
        detail_parts.append("documento esta com movimenta_estoque desativado")

    entrada, legacy_movement = _find_legacy_entry_movement(movement)
    if (
        source is not None
        and source.startswith("ajuste_nf_")
        and row_code != movement_code
        and document is not None
        and not bool(getattr(document, "movimenta_estoque", True))
        and entrada is not None
        and str(entrada.codigo_item or "").strip() == movement_code
        and legacy_movement is not None
    ):
        issue_codes.append("colisao_entrada_legada")
        detail_parts.append(
            f"reference_id tambem aponta para entrada legada {entrada.id_entrada} do mesmo produto"
        )

    if not issue_codes:
        return None

    return IntegrityIssue(
        movement_id=int(movement.id),
        product_id=movement_code,
        movement_type=str(movement.movement_type or ""),
        quantity_base=float(movement.quantity_base or 0.0),
        reference_id=movement.reference_id,
        source=source,
        issue_codes=issue_codes,
        detail="; ".join(detail_parts),
        document_number=str(getattr(document, "numero_documento", "") or "").strip() or None,
        document_item_id=int(row.id_documento_item),
        document_item_code=row_code or None,
        legacy_entry_id=int(entrada.id_entrada) if entrada is not None else None,
        legacy_entry_code=str(entrada.codigo_item or "").strip() or None if entrada is not None else None,
    )


def _iter_issues(args: argparse.Namespace) -> list[IntegrityIssue]:
    query = (
        StockMovement.query
        .filter(StockMovement.reference_type == "entrada_documento_item")
        .order_by(StockMovement.id.asc())
    )
    codes = _normalize_codes(args.codigo)
    if codes:
        query = query.filter(StockMovement.product_id.in_(codes))
    if args.movement_id:
        query = query.filter(StockMovement.id.in_(args.movement_id))

    issues: list[IntegrityIssue] = []
    for movement in query.all():
        issue = _classify_movement(movement)
        if issue is not None:
            issues.append(issue)
    return issues


def _format_issue(issue: IntegrityIssue) -> str:
    issue_codes = ",".join(issue.issue_codes)
    document_item = issue.document_item_id if issue.document_item_id is not None else "-"
    legacy_entry = issue.legacy_entry_id if issue.legacy_entry_id is not None else "-"
    document_number = issue.document_number or "-"
    source = issue.source or "-"
    return (
        f"movimento={issue.movement_id} | codigo={issue.product_id} | tipo={issue.movement_type} | "
        f"qtd={issue.quantity_base:g} | ref={issue.reference_id or '-'} | doc={document_number} | "
        f"doc_item={document_item}:{issue.document_item_code or '-'} | entrada_legada={legacy_entry}:{issue.legacy_entry_code or '-'} | "
        f"source={source} | issues={issue_codes} | {issue.detail}"
    )


def main() -> int:
    args = _parse_args()
    app = create_app()
    with app.app_context():
        issues = _iter_issues(args)
        print(f"Movimentos documentais com anomalia: {len(issues)}")
        counts: Counter[str] = Counter()
        for issue in issues:
            counts.update(issue.issue_codes)
        for code, total in sorted(counts.items()):
            print(f"- {code}: {total}")
        if issues:
            print("")
        for issue in issues:
            print(_format_issue(issue))
        return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())