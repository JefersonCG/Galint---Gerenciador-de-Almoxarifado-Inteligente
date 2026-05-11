from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_TELEGRAM_STARTUP_GREETING", "false")

from app import create_app
from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, FinanceLedgerEntry, StockMovement, Usuario
from galint_flask.services.finance_service import FinanceService
from galint_flask.services.inventory_engine import inventory_engine


def _float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)  # type: ignore[arg-type]


def _clean(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[no-any-return]
    return value


def _line_signature(row: DocumentoEntradaEstoqueItem) -> tuple[object, ...]:
    return (
        row.codigo_item,
        round(_float(row.quantidade) or 0.0, 6),
        (row.unidade_quantidade or "").strip().lower(),
        round(_float(row.quantidade_base) or 0.0, 6),
        round(_float(row.valor_unitario) or 0.0, 6),
        round(_float(row.valor_unitario_base) or 0.0, 6),
        (row.unidade_preco or "").strip().lower(),
        round(_float(row.fator_preco_base) or 0.0, 6),
        round(_float(row.valor_total) or 0.0, 6),
    )


def _ledger_signature(entry: FinanceLedgerEntry) -> tuple[object, ...]:
    return (
        FinanceService.normalize_nf_identity_number(entry.numero_documento),
        entry.codigo_item,
        round(_float(entry.quantidade) or 0.0, 6),
        (entry.unidade_quantidade or "").strip().lower(),
        round(_float(entry.quantidade_base) or 0.0, 6),
        round(_float(entry.valor_unitario) or 0.0, 6),
        round(_float(entry.valor_unitario_base) or 0.0, 6),
        (entry.unidade_preco or "").strip().lower(),
        round(_float(entry.fator_preco_base) or 0.0, 6),
        round(_float(entry.valor_total) or 0.0, 6),
    )


def _document_snapshot(document: DocumentoEntradaEstoque) -> dict[str, Any]:
    return {
        "id_documento": document.id_documento,
        "numero_documento": document.numero_documento,
        "fornecedor_id": document.fornecedor_id,
        "fornecedor_nome": document.fornecedor_nome,
        "cnpj_emitente": document.cnpj_emitente,
        "criado_em": _clean(document.criado_em),
        "itens": [
            {
                "id_documento_item": row.id_documento_item,
                "codigo_item": row.codigo_item,
                "quantidade": _float(row.quantidade),
                "unidade_quantidade": row.unidade_quantidade,
                "quantidade_base": _float(row.quantidade_base),
                "valor_unitario": _float(row.valor_unitario),
                "valor_total": _float(row.valor_total),
                "status_processamento": row.status_processamento,
                "stock_movement_id": row.stock_movement_id,
            }
            for row in document.itens
        ],
    }


def _preferred_document(documents: list[DocumentoEntradaEstoque], canonical_number: str | None) -> DocumentoEntradaEstoque:
    if canonical_number:
        exact = [doc for doc in documents if (doc.numero_documento or "").strip() == canonical_number]
        if exact:
            return sorted(exact, key=lambda doc: (doc.criado_em or datetime.min, int(doc.id_documento or 0)), reverse=True)[0]
    selected = FinanceService._select_preferred_nf_document(documents, numero_documento=canonical_number or documents[0].numero_documento or "")
    if selected is None:
        return sorted(documents, key=lambda doc: int(doc.id_documento or 0), reverse=True)[0]
    return selected


def _safe_duplicate_document(canonical: DocumentoEntradaEstoque, duplicate: DocumentoEntradaEstoque) -> tuple[bool, list[str]]:
    canonical_signatures = defaultdict(int)
    for row in canonical.itens:
        canonical_signatures[_line_signature(row)] += 1
    missing: list[str] = []
    for row in duplicate.itens:
        signature = _line_signature(row)
        if canonical_signatures.get(signature, 0) <= 0:
            missing.append(f"linha {row.id_documento_item} sem par equivalente no documento canônico")
            continue
        canonical_signatures[signature] -= 1
    return not missing, missing


def _delete_financial_entries_for_row(document: DocumentoEntradaEstoque, row: DocumentoEntradaEstoqueItem) -> int:
    query = FinanceLedgerEntry.query.filter(
        FinanceLedgerEntry.codigo_item == row.codigo_item,
        FinanceLedgerEntry.numero_documento == document.numero_documento,
    )
    if document.tipo_documento:
        query = query.filter(FinanceLedgerEntry.tipo_documento == document.tipo_documento)
    return query.delete(synchronize_session=False)


def _update_document_number(document: DocumentoEntradaEstoque, canonical_number: str) -> dict[str, Any] | None:
    previous_number = (document.numero_documento or "").strip()
    if not canonical_number or previous_number == canonical_number:
        return None
    document.numero_documento = canonical_number
    updated_ledger = FinanceLedgerEntry.query.filter(
        FinanceLedgerEntry.tipo_documento == "nf",
        FinanceLedgerEntry.numero_documento == previous_number,
    ).update({FinanceLedgerEntry.numero_documento: canonical_number}, synchronize_session=False)
    updated_movements = 0
    for row in document.itens:
        if row.stock_movement_id is None:
            continue
        movement = db.session.get(StockMovement, row.stock_movement_id)
        if movement is None or not isinstance(movement.metadata_json, dict):
            continue
        metadata = dict(movement.metadata_json)
        metadata["numero_documento"] = canonical_number
        movement.metadata_json = metadata
        updated_movements += 1
    return {
        "action": "rename_document_number",
        "document_id": document.id_documento,
        "from": previous_number,
        "to": canonical_number,
        "ledger_rows_updated": int(updated_ledger or 0),
        "movement_metadata_updated": updated_movements,
    }


def _dedupe_ledger_entries(identity: str, canonical_number: str | None) -> list[dict[str, Any]]:
    entries = [
        entry
        for entry in FinanceLedgerEntry.query.filter(FinanceLedgerEntry.tipo_documento == "nf").all()
        if FinanceService.normalize_nf_identity_number(entry.numero_documento) == identity
    ]
    groups: dict[tuple[object, ...], list[FinanceLedgerEntry]] = defaultdict(list)
    for entry in entries:
        groups[_ledger_signature(entry)].append(entry)

    actions: list[dict[str, Any]] = []
    for signature, grouped_entries in groups.items():
        if len(grouped_entries) <= 1:
            continue
        grouped_entries.sort(
            key=lambda entry: (
                (entry.numero_documento or "").strip() == (canonical_number or "").strip(),
                entry.criado_em or datetime.min,
                int(entry.id or 0),
            ),
            reverse=True,
        )
        keeper = grouped_entries[0]
        removed_ids = [entry.id for entry in grouped_entries[1:]]
        for duplicate_entry in grouped_entries[1:]:
            db.session.delete(duplicate_entry)
        actions.append({
            "action": "delete_duplicate_finance_ledger_entries",
            "identity": identity,
            "signature": list(signature),
            "kept_entry_id": keeper.id,
            "removed_entry_ids": removed_ids,
        })
    return actions


def _apply_duplicate_cleanup(
    canonical: DocumentoEntradaEstoque,
    duplicates: list[DocumentoEntradaEstoque],
    *,
    user: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    affected_items: set[str] = set()
    for duplicate in duplicates:
        safe, reasons = _safe_duplicate_document(canonical, duplicate)
        if not safe:
            actions.append({
                "action": "skip_duplicate_document",
                "document_id": duplicate.id_documento,
                "numero_documento": duplicate.numero_documento,
                "reasons": reasons,
            })
            continue

        removed_rows: list[int] = []
        reversed_rows: list[dict[str, Any]] = []
        deleted_ledger = 0
        for row in list(duplicate.itens):
            affected_items.add(row.codigo_item)
            if (row.status_processamento or "").strip().lower() == "processado" and row.stock_movement_id is not None:
                reversed_rows.append(FinanceService.delete_document_item_for_typo(row, usuario_matricula=user))
            deleted_ledger += _delete_financial_entries_for_row(duplicate, row)
            removed_rows.append(row.id_documento_item)
            db.session.delete(row)
        db.session.flush()
        remaining_item = DocumentoEntradaEstoqueItem.query.filter_by(documento_id=duplicate.id_documento).first()
        if remaining_item is None:
            db.session.delete(duplicate)
        actions.append({
            "action": "delete_duplicate_document",
            "document_id": duplicate.id_documento,
            "numero_documento": duplicate.numero_documento,
            "removed_document_item_ids": removed_rows,
            "reversal_results": reversed_rows,
            "finance_ledger_deleted": deleted_ledger,
        })

    for codigo_item in affected_items:
        inventory_engine.sync_packaging_read_model(product_id=codigo_item, commit=False)
    return actions


def _build_groups(only_numbers: list[str]) -> tuple[dict[str, str], dict[str, list[DocumentoEntradaEstoque]]]:
    canonical_by_identity = {
        FinanceService.normalize_nf_identity_number(number): number.strip()
        for number in only_numbers
        if FinanceService.normalize_nf_identity_number(number)
    }
    groups: dict[str, list[DocumentoEntradaEstoque]] = defaultdict(list)
    for document in DocumentoEntradaEstoque.query.filter(DocumentoEntradaEstoque.tipo_documento == "nf").all():
        identity = FinanceService.normalize_nf_identity_number(document.numero_documento)
        if not identity:
            continue
        if canonical_by_identity and identity not in canonical_by_identity:
            continue
        groups[identity].append(document)
    return canonical_by_identity, groups


def run_metric(*, apply: bool, only_numbers: list[str], user: str) -> dict[str, Any]:
    canonical_by_identity, groups = _build_groups(only_numbers)
    report: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat(),
        "applied": apply,
        "only_numbers": only_numbers,
        "document_groups": [],
        "actions": [],
    }

    for identity, documents in sorted(groups.items()):
        canonical_number = canonical_by_identity.get(identity)
        document_numbers = sorted({(document.numero_documento or "").strip() for document in documents})
        should_review = len(documents) > 1 or (canonical_number and canonical_number not in document_numbers)
        if not should_review:
            continue

        canonical = _preferred_document(documents, canonical_number)
        duplicates = [document for document in documents if document.id_documento != canonical.id_documento]
        group_report = {
            "identity": identity,
            "canonical_number": canonical_number,
            "canonical_document_id": canonical.id_documento,
            "documents": [_document_snapshot(document) for document in documents],
            "safe_duplicates": [],
            "unsafe_duplicates": [],
        }
        for duplicate in duplicates:
            safe, reasons = _safe_duplicate_document(canonical, duplicate)
            target = "safe_duplicates" if safe else "unsafe_duplicates"
            group_report[target].append({
                "document_id": duplicate.id_documento,
                "numero_documento": duplicate.numero_documento,
                "reasons": reasons,
            })
        report["document_groups"].append(group_report)

        if apply:
            rename_action = _update_document_number(canonical, canonical_number or canonical.numero_documento or "")
            if rename_action:
                report["actions"].append(rename_action)
            report["actions"].extend(_apply_duplicate_cleanup(canonical, duplicates, user=user))
            report["actions"].extend(_dedupe_ledger_entries(identity, canonical_number))

    if apply:
        db.session.commit()
    else:
        db.session.rollback()
    return report


def _parse_only(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _resolve_existing_user(preferred: str | None) -> str | None:
    preferred = (preferred or "").strip()
    if preferred and db.session.get(Usuario, preferred) is not None:
        return preferred
    user = Usuario.query.order_by(Usuario.is_admin.desc(), Usuario.matricula.asc()).first()
    return user.matricula if user is not None else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita e corrige NFs duplicadas por identidade numérica normalizada.")
    parser.add_argument("--apply", action="store_true", help="Aplica as correções seguras encontradas.")
    parser.add_argument("--only", default="", help="Lista de NFs separadas por vírgula para restringir e definir o número canônico.")
    parser.add_argument("--user", default="", help="Usuário/matrícula usado nos estornos automáticos. Se omitido, usa um usuário existente.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        user = _resolve_existing_user(args.user)
        report = run_metric(
            apply=bool(args.apply),
            only_numbers=_parse_only(args.only),
            user=user or "",
        )
        audit_dir = ROOT / "audit"
        audit_dir.mkdir(exist_ok=True)
        suffix = "apply" if args.apply else "dry_run"
        output_path = audit_dir / f"duplicate_nf_identity_metric_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{suffix}.json"
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "applied": report["applied"],
            "document_groups": len(report["document_groups"]),
            "actions": len(report["actions"]),
            "report": str(output_path),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())