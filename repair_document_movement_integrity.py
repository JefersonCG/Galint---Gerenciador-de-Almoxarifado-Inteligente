"""Corrige de forma assistida movimentos documentais anômalos.

Uso:
  .\.venv\Scripts\python.exe repair_document_movement_integrity.py
  .\.venv\Scripts\python.exe repair_document_movement_integrity.py --movement-id 3677
  .\.venv\Scripts\python.exe repair_document_movement_integrity.py --movement-id 3677 --apply

Objetivo:
- consumir a auditoria de check_document_movement_integrity.py
- aplicar apenas o reparo seguro para colisões entre reference_id documental e id_entrada legado
- normalizar antes os movimentos legados mistos do produto afetado
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

from check_document_movement_integrity import IntegrityIssue, _iter_issues
from normalize_packaging_stock_movements import _normalize_movement, _rebuild_product_state

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, StockBalance, StockMovement, stock_balance_supports_read_model_ready
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.legacy_stock_normalizer import resolve_canonical_unit


SAFE_COLLISION_CODES = {"codigo_divergente", "documento_sem_movimento", "colisao_entrada_legada"}
REPAIR_SOURCE = "repair_doc_mvt"


@dataclass(slots=True)
class RepairCandidate:
    issue: IntegrityIssue
    safe_to_apply: bool
    reason: str
    normalized_quantity_base: float
    canonical_unit: str | None
    normalized_movement_count: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Corrige assistidamente movimentos documentais anômalos.")
    parser.add_argument("--codigo", action="append", help="Codigo do item a filtrar. Pode repetir.")
    parser.add_argument("--movement-id", action="append", type=int, help="ID específico do movimento a filtrar.")
    parser.add_argument("--matricula", default="0000000000000", help="Matricula usada na trilha de auditoria.")
    parser.add_argument("--apply", action="store_true", help="Aplica os reparos seguros encontrados.")
    return parser.parse_args()


def _ledger_total(product_id: str) -> float:
    return float(
        db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
        .filter(StockMovement.product_id == product_id)
        .scalar()
        or 0.0
    )


def _mark_balance_ready(product_id: str) -> None:
    balance = db.session.get(StockBalance, product_id)
    if balance is None:
        balance = StockBalance(product_id=product_id, quantity_base=_ledger_total(product_id))
        db.session.add(balance)
    else:
        balance.quantity_base = _ledger_total(product_id)
    if stock_balance_supports_read_model_ready() and hasattr(balance, "read_model_ready"):
        balance.read_model_ready = True


def _normalize_product_mixed_legacy_movements(product_id: str) -> int:
    item = db.session.get(Item, product_id)
    if item is None:
        return 0

    changed = 0
    movements = (
        StockMovement.query
        .filter(StockMovement.product_id == product_id)
        .order_by(StockMovement.id.asc())
        .all()
    )
    for movement in movements:
        normalized = _normalize_movement(item, movement)
        if normalized is None:
            continue
        if hasattr(normalized, "reason") and getattr(normalized, "quantity_after", None) is not None:
            changed += 1
    if changed:
        _rebuild_product_state(product_id)
    return changed


def _build_candidate(issue: IntegrityIssue) -> RepairCandidate:
    movement = db.session.get(StockMovement, issue.movement_id)
    if movement is None:
        return RepairCandidate(issue, False, "movimento_inexistente", 0.0, None, 0)

    item = db.session.get(Item, issue.product_id)
    if item is None:
        return RepairCandidate(issue, False, "item_inexistente", 0.0, None, 0)

    canonical_unit = (resolve_canonical_unit(item) or "").strip().lower() or None
    normalized_movement_count = 0
    normalized_quantity_base = abs(float(movement.quantity_base or 0.0))
    safe_to_apply = False
    reason = "issue_not_supported"

    issue_codes = set(issue.issue_codes)
    source = str(issue.source or "").strip().lower()
    if issue_codes == SAFE_COLLISION_CODES and source.startswith("ajuste_nf_") and issue.movement_type == "saida":
        normalized_movement_count = _normalize_product_mixed_legacy_movements(issue.product_id)
        db.session.flush()
        refreshed = db.session.get(StockMovement, issue.movement_id)
        normalized_quantity_base = abs(float(refreshed.quantity_base or 0.0)) if refreshed is not None else 0.0
        if canonical_unit and normalized_quantity_base > 0:
            safe_to_apply = True
            reason = "safe_collision_compensation"
        else:
            reason = "normalized_quantity_unresolved"

    return RepairCandidate(
        issue=issue,
        safe_to_apply=safe_to_apply,
        reason=reason,
        normalized_quantity_base=normalized_quantity_base,
        canonical_unit=canonical_unit,
        normalized_movement_count=normalized_movement_count,
    )


def _print_candidates(candidates: list[RepairCandidate]) -> None:
    print(f"Candidatos avaliados: {len(candidates)}")
    for candidate in candidates:
        issue = candidate.issue
        status = "SAFE" if candidate.safe_to_apply else "REVIEW"
        print(
            f"[{status}] movimento={issue.movement_id} | codigo={issue.product_id} | issues={','.join(issue.issue_codes)} | "
            f"motivo={candidate.reason} | qtd_normalizada={candidate.normalized_quantity_base:g} {candidate.canonical_unit or '-'} | "
            f"normalizados_no_produto={candidate.normalized_movement_count}"
        )


def _apply_candidate(candidate: RepairCandidate, matricula: str) -> int:
    movement = db.session.get(StockMovement, candidate.issue.movement_id)
    if movement is None:
        raise ValueError("Movimento não encontrado para aplicar reparo.")

    product_id = candidate.issue.product_id
    canonical_unit = candidate.canonical_unit or ""
    quantity = abs(float(candidate.normalized_quantity_base or 0.0))
    if quantity <= 0 or not canonical_unit:
        raise ValueError("Quantidade canônica não resolvida para o reparo.")

    metadata = dict(movement.metadata_json or {})
    metadata["repair_document_collision"] = {
        "source": "repair_document_movement_integrity",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "reason": candidate.reason,
        "original_reference_type": movement.reference_type,
    }
    movement.reference_type = "entrada_documento_item_collision"
    movement.metadata_json = metadata

    _mark_balance_ready(product_id)
    result = inventory_engine.register_adjustment(
        product_id=product_id,
        quantity=quantity,
        from_unit=canonical_unit,
        metadata={
            "source": REPAIR_SOURCE,
            "channel": "maintenance_script",
            "reference_type": "document_movement_repair",
            "reference_id": str(movement.id),
            "user_id": matricula,
            "matricula": matricula,
            "origin_movement_id": movement.id,
            "origin_issue_codes": list(candidate.issue.issue_codes),
            "observacao": "Compensa colisao entre item documental e entrada legada",
        },
        commit=False,
        write_audit=True,
    )

    metadata = dict(movement.metadata_json or {})
    metadata["repair_document_collision"]["compensation_movement_id"] = int(result.movement_id)
    metadata["repair_document_collision"]["operation_log_id"] = int(result.operation_log_id) if result.operation_log_id is not None else None
    metadata["repair_document_collision"]["matricula"] = matricula
    movement.metadata_json = metadata

    _mark_balance_ready(product_id)
    try:
        inventory_engine.sync_packaging_read_model(product_id=product_id, commit=False)
    except Exception:
        pass
    return int(result.movement_id)


def main() -> int:
    args = _parse_args()
    app = create_app()
    with app.app_context():
        issues = _iter_issues(args)
        candidates = [_build_candidate(issue) for issue in issues]
        _print_candidates(candidates)
        if not args.apply:
            db.session.rollback()
            return 0

        safe_candidates = [candidate for candidate in candidates if candidate.safe_to_apply]
        if not safe_candidates:
            print("Nenhum candidato seguro para aplicar.")
            db.session.rollback()
            return 0

        applied_movements: list[int] = []
        for candidate in safe_candidates:
            applied_movements.append(_apply_candidate(candidate, str(args.matricula or "").strip() or "0000000000000"))

        db.session.commit()
        print(
            f"Reparos aplicados: {len(applied_movements)} | movimentos de compensacao={','.join(str(value) for value in applied_movements)}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())