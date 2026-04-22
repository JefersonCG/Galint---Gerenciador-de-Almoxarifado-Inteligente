"""Audita e compensa saidas historicas ajuste_nf_* vinculadas a itens documentais validos.

Uso:
  .\.venv\Scripts\python.exe repair_nf_adjustment_exits.py
  .\.venv\Scripts\python.exe repair_nf_adjustment_exits.py --movement-id 3678
  .\.venv\Scripts\python.exe repair_nf_adjustment_exits.py --movement-id 3678 --apply

Objetivo:
- localizar movimentos de saida com source ajuste_nf_<numero> ligados a entrada_documento_item
- aplicar compensacao apenas quando o item documental original ainda esta processado
  e ligado ao movimento de entrada canonico correspondente
- manter trilha de auditoria sem apagar o movimento historico problemático
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import sys


os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from sqlalchemy import func

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import (
    DocumentoEntradaEstoqueItem,
    Item,
    StockBalance,
    StockMovement,
    stock_balance_supports_read_model_ready,
)
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.legacy_stock_normalizer import resolve_canonical_unit


DISPLAY_TOLERANCE = 1e-3
REPAIR_SOURCE = "repair_nf_adjust"


@dataclass(slots=True)
class CandidateIssue:
    movement: StockMovement
    source: str
    document_item: DocumentoEntradaEstoqueItem | None
    original_movement: StockMovement | None
    safe_to_apply: bool
    reason: str
    current_balance: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita e compensa saidas historicas ajuste_nf_* ainda divergentes."
    )
    parser.add_argument("--codigo", action="append", help="Codigo do item a filtrar. Pode repetir.")
    parser.add_argument("--movement-id", action="append", type=int, help="ID especifico do movimento a filtrar.")
    parser.add_argument(
        "--documento-item-id",
        action="append",
        type=int,
        help="ID do item documental a filtrar. Pode repetir.",
    )
    parser.add_argument(
        "--matricula",
        default="0000000000000",
        help="Matricula usada na trilha de auditoria ao aplicar a compensacao.",
    )
    parser.add_argument("--apply", action="store_true", help="Aplica as compensacoes seguras encontradas.")
    return parser.parse_args()


def _safe_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_usable_unit(value: object) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    return any(not char.isdigit() and char not in {".", ",", "-", "/"} for char in raw)


def _normalize_codes(values: list[str] | None) -> list[str]:
    return sorted({str(value or "").strip() for value in (values or []) if str(value or "").strip()})


def _resolve_document_item(movement: StockMovement) -> DocumentoEntradaEstoqueItem | None:
    try:
        document_item_id = int(str(movement.reference_id or "").strip())
    except (TypeError, ValueError):
        return None
    return db.session.get(DocumentoEntradaEstoqueItem, document_item_id)


def _resolve_original_movement(
    movement: StockMovement,
    document_item: DocumentoEntradaEstoqueItem | None,
) -> StockMovement | None:
    if document_item is None:
        return None

    if document_item.stock_movement_id is not None:
        linked = db.session.get(StockMovement, int(document_item.stock_movement_id))
        if linked is not None:
            return linked

    return (
        StockMovement.query
        .filter(StockMovement.reference_type == "entrada_documento_item")
        .filter(StockMovement.reference_id == str(document_item.id_documento_item))
        .filter(StockMovement.product_id == movement.product_id)
        .filter(StockMovement.id != movement.id)
        .filter(StockMovement.movement_type == "entrada")
        .order_by(StockMovement.id.asc())
        .first()
    )


def _ledger_balance(product_id: str) -> float:
    return float(
        db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
        .filter(StockMovement.product_id == product_id)
        .scalar()
        or 0.0
    )


def _build_issue(movement: StockMovement) -> CandidateIssue | None:
    metadata = movement.metadata_json or {}
    source = str(metadata.get("source") or "").strip().lower()
    if not source.startswith("ajuste_nf_"):
        return None
    if metadata.get("repair_compensation"):
        return None

    document_item = _resolve_document_item(movement)
    original_movement = _resolve_original_movement(movement, document_item)
    current_balance = _ledger_balance(movement.product_id)
    reason = "compensacao_segura"
    safe_to_apply = True

    if document_item is None:
        safe_to_apply = False
        reason = "documento_item_inexistente"
    elif (document_item.status_processamento or "").strip().lower() != "processado":
        safe_to_apply = False
        reason = f"documento_item_{(document_item.status_processamento or 'sem_status').strip().lower() or 'sem_status'}"
    elif document_item.stock_movement_id is None:
        safe_to_apply = False
        reason = "documento_item_sem_link_canonico"
    elif original_movement is None:
        safe_to_apply = False
        reason = "movimento_documental_original_inexistente"
    elif original_movement.id != int(document_item.stock_movement_id):
        safe_to_apply = False
        reason = "movimento_original_diverge_do_link"
    elif (original_movement.movement_type or "").strip().lower() != "entrada":
        safe_to_apply = False
        reason = "movimento_original_nao_e_entrada"
    else:
        adjustment_qty = abs(float(movement.quantity_base or 0.0))
        original_qty = abs(float(original_movement.quantity_base or 0.0))
        document_qty = abs(_safe_float(document_item.quantidade_base) or 0.0)
        if abs(adjustment_qty - original_qty) > DISPLAY_TOLERANCE:
            safe_to_apply = False
            reason = "quantidade_diverge_do_movimento_original"
        elif document_qty > 0 and abs(adjustment_qty - document_qty) > DISPLAY_TOLERANCE:
            safe_to_apply = False
            reason = "quantidade_diverge_do_documento"

    return CandidateIssue(
        movement=movement,
        source=source,
        document_item=document_item,
        original_movement=original_movement,
        safe_to_apply=safe_to_apply,
        reason=reason,
        current_balance=current_balance,
    )


def _iter_candidate_issues(args: argparse.Namespace) -> list[CandidateIssue]:
    query = (
        StockMovement.query
        .filter(StockMovement.reference_type == "entrada_documento_item")
        .filter(StockMovement.movement_type == "saida")
        .order_by(StockMovement.created_at.asc(), StockMovement.id.asc())
    )

    codes = _normalize_codes(args.codigo)
    if codes:
        query = query.filter(StockMovement.product_id.in_(codes))
    if args.movement_id:
        query = query.filter(StockMovement.id.in_(args.movement_id))
    if args.documento_item_id:
        query = query.filter(StockMovement.reference_id.in_([str(value) for value in args.documento_item_id]))

    issues: list[CandidateIssue] = []
    for movement in query.all():
        issue = _build_issue(movement)
        if issue is not None:
            issues.append(issue)
    return issues


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    rounded = round(float(value), 6)
    if abs(rounded - round(rounded)) <= 1e-6:
        return str(int(round(rounded)))
    return f"{rounded:.6f}".rstrip("0").rstrip(".")


def _print_issues(issues: list[CandidateIssue]) -> None:
    if not issues:
        print("Nenhum movimento ajuste_nf_* pendente foi encontrado.")
        return

    print(f"Movimentos ajuste_nf_* encontrados: {len(issues)}")
    for issue in issues:
        movement = issue.movement
        row = issue.document_item
        original = issue.original_movement
        status = "SAFE" if issue.safe_to_apply else "REVIEW"
        print(
            f"[{status}] movimento={movement.id} | codigo={movement.product_id} | qtd={_fmt(movement.quantity_base)} | "
            f"saldo_atual={_fmt(issue.current_balance)} | source={issue.source} | motivo={issue.reason}"
        )
        print(
            f"          documento_item={getattr(row, 'id_documento_item', None)} | "
            f"status={getattr(row, 'status_processamento', None)} | stock_movement_id={getattr(row, 'stock_movement_id', None)} | "
            f"mov_original={getattr(original, 'id', None)}"
        )


def _mark_balance_ready(product_id: str) -> None:
    balance = db.session.get(StockBalance, product_id)
    if balance is None:
        balance = StockBalance(product_id=product_id, quantity_base=_ledger_balance(product_id))
        db.session.add(balance)
    else:
        balance.quantity_base = _ledger_balance(product_id)
    if stock_balance_supports_read_model_ready() and hasattr(balance, "read_model_ready"):
        balance.read_model_ready = True


def _resolve_repair_input_unit(
    *,
    item: Item,
    row: DocumentoEntradaEstoqueItem,
    original: StockMovement,
) -> str:
    metadata = original.metadata_json or {}
    candidates = (
        row.unidade_quantidade,
        metadata.get("input_unit"),
        item.unidade,
        resolve_canonical_unit(item),
        original.unit_base,
        "Unidade",
    )
    for candidate in candidates:
        if _is_usable_unit(candidate):
            return str(candidate).strip()
    return "Unidade"


def _apply_issue(issue: CandidateIssue, matricula: str) -> int:
    row = issue.document_item
    original = issue.original_movement
    movement = issue.movement
    if row is None or original is None:
        raise ValueError("Tentativa de aplicar compensacao em caso nao seguro.")

    item = db.session.get(Item, movement.product_id)
    if item is None:
        raise ValueError(f"Item {movement.product_id} nao encontrado.")

    document = row.documento
    quantity = abs(float(movement.quantity_base or 0.0))
    from_unit = _resolve_repair_input_unit(item=item, row=row, original=original)
    result = inventory_engine.register_adjustment(
        product_id=movement.product_id,
        quantity=quantity,
        from_unit=from_unit,
        metadata={
            "source": REPAIR_SOURCE,
            "channel": "maintenance_script",
            "reference_type": "entrada_documento_item_repair",
            "reference_id": str(row.id_documento_item),
            "documento_id": row.documento_id,
            "documento_item_id": row.id_documento_item,
            "numero_documento": document.numero_documento if document is not None else None,
            "tipo_documento": document.tipo_documento if document is not None else None,
            "user_id": matricula,
            "matricula": matricula,
            "origin_adjustment_movement_id": movement.id,
            "origin_adjustment_source": issue.source,
            "origin_document_movement_id": original.id,
            "observacao": (
                f"Compensa {issue.source} no movimento {movement.id} com item documental ainda processado"
            ),
        },
        commit=False,
        write_audit=True,
    )

    metadata = dict(movement.metadata_json or {})
    metadata["repair_compensation"] = {
        "source": "repair_nf_adjustment_exits",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "movement_id": int(result.movement_id),
        "operation_log_id": int(result.operation_log_id) if result.operation_log_id is not None else None,
        "matricula": matricula,
    }
    movement.metadata_json = metadata

    _mark_balance_ready(movement.product_id)
    try:
        inventory_engine.sync_packaging_read_model(product_id=movement.product_id, commit=False)
    except Exception:
        pass
    return int(result.movement_id)


def main() -> int:
    args = _parse_args()
    app = create_app()

    with app.app_context():
        issues = _iter_candidate_issues(args)
        _print_issues(issues)
        if not args.apply:
            return 0

        safe_issues = [issue for issue in issues if issue.safe_to_apply]
        if not safe_issues:
            print("Nenhum caso seguro para aplicar.")
            db.session.rollback()
            return 0

        applied_movements: list[int] = []
        touched_products: set[str] = set()
        for issue in safe_issues:
            repair_movement_id = _apply_issue(issue, str(args.matricula or "").strip() or "0000000000000")
            applied_movements.append(repair_movement_id)
            touched_products.add(issue.movement.product_id)

        db.session.commit()
        print(
            f"Compensacoes aplicadas: {len(applied_movements)} | "
            f"movimentos criados={','.join(str(value) for value in applied_movements)} | "
            f"produtos afetados={len(touched_products)}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())