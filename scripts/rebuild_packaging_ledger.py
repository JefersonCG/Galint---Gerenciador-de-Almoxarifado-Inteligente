from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoqueItem, Item, OperationLog, StockBalance, StockMovement
from galint_flask.services.ledger_backfill_normalized import LEGACY_REBUILD_REFERENCE_TYPES, ledger_backfill_service
from galint_flask.services.ledger_cutover import ledger_cutover_service
from galint_flask.services.legacy_stock_normalizer import (
    resolve_packaging_factor,
    resolve_packaging_quantity_and_unit,
    uses_packaging_legacy_normalization,
)
from galint_flask.services.ledger_reconciliation import ledger_reconciliation_service

TOLERANCE = 1e-6


def _legacy_movement_count() -> int:
    return int(
        db.session.query(StockMovement.id)
        .filter(StockMovement.reference_type.in_(LEGACY_REBUILD_REFERENCE_TYPES))
        .count()
    )


def _document_entry_adjustment_preview() -> list[dict[str, object]]:
    preview: list[dict[str, object]] = []
    for movement in (
        StockMovement.query
        .filter(StockMovement.reference_type == "entrada_documento_item")
        .order_by(StockMovement.created_at.asc(), StockMovement.id.asc())
        .all()
    ):
        item = movement.item or db.session.get(Item, movement.product_id)
        if not item or not uses_packaging_legacy_normalization(item):
            continue

        documento_item = _resolve_document_item(movement)
        if documento_item is None:
            continue

        corrected = resolve_packaging_quantity_and_unit(item, float(documento_item.quantidade or 0))
        if corrected is None:
            continue

        corrected_quantity, corrected_unit = corrected
        current_quantity = float(movement.quantity_base or 0)
        current_unit = (movement.unit_base or "").strip().lower()
        if abs(corrected_quantity - current_quantity) <= TOLERANCE and current_unit == corrected_unit:
            continue

        preview.append(
            {
                "movement_id": movement.id,
                "product_id": movement.product_id,
                "descricao": item.descricao,
                "current_quantity": current_quantity,
                "current_unit": current_unit,
                "corrected_quantity": corrected_quantity,
                "corrected_unit": corrected_unit,
                "factor": resolve_packaging_factor(item),
            }
        )
    return preview


def _resolve_document_item(movement: StockMovement) -> DocumentoEntradaEstoqueItem | None:
    try:
        document_item_id = int(str(movement.reference_id or "").strip())
    except (TypeError, ValueError):
        return None
    return db.session.get(DocumentoEntradaEstoqueItem, document_item_id)


def _normalize_document_entry_movements() -> tuple[int, list[dict[str, object]]]:
    updated = 0
    samples: list[dict[str, object]] = []

    for movement in (
        StockMovement.query
        .filter(StockMovement.reference_type == "entrada_documento_item")
        .order_by(StockMovement.created_at.asc(), StockMovement.id.asc())
        .all()
    ):
        item = movement.item or db.session.get(Item, movement.product_id)
        if not item or not uses_packaging_legacy_normalization(item):
            continue

        documento_item = _resolve_document_item(movement)
        if documento_item is None:
            continue

        corrected = resolve_packaging_quantity_and_unit(item, float(documento_item.quantidade or 0))
        if corrected is None:
            continue

        corrected_quantity, corrected_unit = corrected
        current_quantity = float(movement.quantity_base or 0)
        current_unit = (movement.unit_base or "").strip().lower()
        if abs(corrected_quantity - current_quantity) <= TOLERANCE and current_unit == corrected_unit:
            continue

        if len(samples) < 20:
            samples.append(
                {
                    "movement_id": movement.id,
                    "product_id": movement.product_id,
                    "descricao": item.descricao,
                    "before": f"{current_quantity:g} {current_unit or 'un'}",
                    "after": f"{corrected_quantity:g} {corrected_unit}",
                }
            )

        metadata = dict(movement.metadata_json or {})
        metadata["normalized_from_packaging"] = True
        metadata["packaging_factor"] = resolve_packaging_factor(item)
        metadata["original_quantity_base"] = current_quantity
        metadata["original_unit_base"] = current_unit
        metadata["factor_applied"] = resolve_packaging_factor(item)
        movement.metadata_json = metadata
        movement.quantity_base = corrected_quantity
        movement.unit_base = corrected_unit

        if documento_item.operation_log_id:
            operation_log = db.session.get(OperationLog, documento_item.operation_log_id)
            if operation_log is not None:
                operation_log.quantity_base = corrected_quantity
                payload = dict(operation_log.payload_json or {})
                payload["unit_base"] = corrected_unit
                payload["factor_applied"] = resolve_packaging_factor(item)
                payload["quantity_delta"] = corrected_quantity
                operation_log.payload_json = payload

        updated += 1

    return updated, samples


def _sync_packaging_fields_from_balances() -> int:
    updated = 0
    for item in Item.query.order_by(Item.codigo_item.asc()).all():
        if not uses_packaging_legacy_normalization(item):
            continue

        factor = resolve_packaging_factor(item)
        if factor <= 0:
            continue

        balance = db.session.get(StockBalance, item.codigo_item)
        total = max(float(balance.quantity_base or 0), 0.0) if balance is not None else 0.0
        embalagens = int(total // factor)
        unidades_soltas = total - (embalagens * factor)
        if abs(unidades_soltas) <= TOLERANCE:
            unidades_soltas = 0.0
        if abs(unidades_soltas - factor) <= TOLERANCE:
            embalagens += 1
            unidades_soltas = 0.0

        if (
            abs(float(item.estoque_embalagens or 0) - float(embalagens)) <= TOLERANCE
            and abs(float(item.estoque_unidades_soltas or 0) - float(unidades_soltas)) <= TOLERANCE
        ):
            continue

        item.estoque_embalagens = float(embalagens)
        item.estoque_unidades_soltas = float(unidades_soltas)
        updated += 1

    return updated


def _activate_packaging_read_models() -> tuple[int, int, list[dict[str, object]]]:
    activated = 0
    pending = 0
    samples: list[dict[str, object]] = []

    for item in Item.query.order_by(Item.codigo_item.asc()).all():
        if not uses_packaging_legacy_normalization(item):
            continue
        if db.session.get(StockBalance, item.codigo_item) is None:
            continue

        decision = ledger_cutover_service.activate_product(
            item.codigo_item,
            allow_explainable=True,
        )
        if decision.activated:
            activated += 1
            if len(samples) < 20:
                samples.append(
                    {
                        "product_id": item.codigo_item,
                        "descricao": item.descricao,
                        "classification": decision.classification,
                    }
                )
            continue

        pending += 1

    return activated, pending, samples


def _print_preview() -> None:
    legacy_count = _legacy_movement_count()
    document_preview = _document_entry_adjustment_preview()
    print("REBUILD LEDGER COM EMBALAGENS")
    print(f"Movimentos legados a recriar: {legacy_count}")
    print(f"Entradas documentais embaladas a corrigir: {len(document_preview)}")
    for row in document_preview[:20]:
        print(
            f"- movimento={row['movement_id']} produto={row['product_id']} | "
            f"{row['current_quantity']:g} {row['current_unit']} -> {row['corrected_quantity']:g} {row['corrected_unit']}"
        )
    print("\nUse --apply para executar as alterações.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstrói o ledger legado com normalização de embalagens.")
    parser.add_argument("--apply", action="store_true", help="Executa as alterações no banco")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if not args.apply:
            _print_preview()
            return

        deleted = _legacy_movement_count()
        if deleted:
            (
                StockMovement.query
                .filter(StockMovement.reference_type.in_(LEGACY_REFERENCE_TYPES))
                .delete(synchronize_session=False)
            )
            db.session.flush()

        backfill_summary = ledger_backfill_service.backfill(clear_balances=True)
        normalized_docs, samples = _normalize_document_entry_movements()
        balances_rebuilt = ledger_backfill_service.rebuild_balances()
        synced_packaging_fields = _sync_packaging_fields_from_balances()
        db.session.commit()
        activated_read_models, pending_read_models, read_model_samples = _activate_packaging_read_models()

        branco_fosco = ledger_reconciliation_service.reconcile_product("7891323003242")
        print("REBUILD LEDGER COM EMBALAGENS")
        print(f"Movimentos legados removidos: {deleted}")
        print(f"Legacy backfill: entradas={backfill_summary.processed_entries} saidas={backfill_summary.processed_exits} eventos={backfill_summary.processed_events}")
        print(f"Entradas documentais normalizadas: {normalized_docs}")
        print(f"Saldos reconstruidos: {balances_rebuilt}")
        print(f"Campos fisicos sincronizados: {synced_packaging_fields}")
        print(f"Read models ativados para embalagens: {activated_read_models}")
        print(f"Itens embalados ainda pendentes: {pending_read_models}")
        if samples:
            print("Amostra de entradas documentais corrigidas:")
            for row in samples:
                print(f"- movimento={row['movement_id']} produto={row['product_id']} | {row['before']} -> {row['after']}")
        if read_model_samples:
            print("Amostra de read models ativados:")
            for row in read_model_samples:
                print(
                    f"- produto={row['product_id']} | {row['descricao']} | classificacao={row['classification']}"
                )
        print("BRANCO FOSCO 18L:")
        print(
            f"- legado={branco_fosco.legacy_balance:g} | ledger={branco_fosco.ledger_balance:g} | "
            f"cache={branco_fosco.stock_balance:g} | classificacao={branco_fosco.classification}"
        )


if __name__ == "__main__":
    main()