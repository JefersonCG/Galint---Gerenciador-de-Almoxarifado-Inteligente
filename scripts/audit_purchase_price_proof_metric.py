"""Audita e corrige itens sem preco de compra comprovado por documento.

Uso:
    python scripts/audit_purchase_price_proof_metric.py
    python scripts/audit_purchase_price_proof_metric.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ["GALINT_DISABLE_BACKGROUND_SERVICES"] = "true"
os.environ["GALINT_TELEGRAM_POLLING"] = "false"
os.environ["GALINT_TELEGRAM_STARTUP_GREETING"] = "false"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from galint_flask.extensions import db
from galint_flask.models import Item
from galint_flask.services import inventory as inventory_service


PLACEHOLDER_TEXT = {"", "none", "null", "nan"}


def _float_or_none(value: object) -> float | None:
    return inventory_service._coerce_price_value(value)


def _text_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _is_placeholder(value: object) -> bool:
    return str(value or "").strip().lower() in PLACEHOLDER_TEXT


def _serialize_date(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _serialize_candidate(candidate: dict[str, object] | None) -> dict[str, object] | None:
    if not candidate:
        return None
    return {
        "valor_bruto": candidate.get("raw_value"),
        "valor_unitario_base": candidate.get("unit_price_base"),
        "unidade_preco": candidate.get("price_unit"),
        "fator_base": candidate.get("factor_to_base"),
        "documento": candidate.get("document_number"),
        "tipo_documento": candidate.get("document_type"),
        "chave_acesso": candidate.get("access_key"),
        "data_emissao": _serialize_date(candidate.get("emission_date")),
        "data_recebimento": _serialize_date(candidate.get("receipt_date")),
    }


def _item_metric(item: Item) -> dict[str, Any] | None:
    purchase_raw = _float_or_none(item.preco_compra_unitario)
    purchase_base = _float_or_none(item.preco_compra_unitario_base)
    replacement_raw = _float_or_none(item.preco_reposicao_unitario)
    purchase_document = _text_or_none(item.preco_compra_documento)

    missing_purchase = purchase_raw is None or purchase_raw <= 0 or purchase_base is None or purchase_base <= 0
    missing_document = _is_placeholder(purchase_document)
    has_replacement = replacement_raw is not None and replacement_raw > 0
    if not has_replacement or not (missing_purchase or missing_document):
        return None

    candidate = inventory_service._latest_document_purchase_candidate(item)
    status = "auto_corrigivel_por_documento" if candidate else "sem_prova_fiscal_direta"
    return {
        "status": status,
        "codigo": item.codigo_item,
        "descricao": item.descricao,
        "categoria": item.categoria,
        "marca": item.marca,
        "preco_compra_unitario": purchase_raw,
        "preco_compra_unitario_base": purchase_base,
        "preco_compra_documento": purchase_document,
        "preco_reposicao_unitario": replacement_raw,
        "preco_reposicao_unitario_base": _float_or_none(item.preco_reposicao_unitario_base),
        "preco_reposicao_fonte": _text_or_none(item.preco_reposicao_fonte),
        "documento_candidato": _serialize_candidate(candidate),
    }


def run_metric(*, apply: bool) -> dict[str, Any]:
    app = create_app()
    with app.app_context():
        rows: list[dict[str, Any]] = []
        corrected_codes: list[str] = []
        placeholder_cleaned_codes: list[str] = []

        for item in Item.query.order_by(Item.codigo_item).all():
            metric = _item_metric(item)
            if metric is None:
                continue
            rows.append(metric)

            if apply and metric["status"] == "auto_corrigivel_por_documento":
                if inventory_service._sync_missing_item_purchase_price_from_history(item):
                    corrected_codes.append(item.codigo_item)

            if apply and _is_placeholder(item.preco_compra_documento):
                item.preco_compra_documento = None
                if _is_placeholder(item.nota_fiscal):
                    item.nota_fiscal = None
                placeholder_cleaned_codes.append(item.codigo_item)

        if apply and (corrected_codes or placeholder_cleaned_codes):
            db.session.commit()
        elif apply:
            db.session.rollback()

        summary = {
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "apply": apply,
            "total_suspeitos": len(rows),
            "auto_corrigiveis_por_documento": sum(1 for row in rows if row["status"] == "auto_corrigivel_por_documento"),
            "sem_prova_fiscal_direta": sum(1 for row in rows if row["status"] == "sem_prova_fiscal_direta"),
            "corrigidos_por_documento": corrected_codes,
            "placeholders_documento_limpos": placeholder_cleaned_codes,
        }
        return {"summary": summary, "items": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplica correcoes seguras no banco.")
    args = parser.parse_args()

    report = run_metric(apply=args.apply)
    audit_dir = Path("audit")
    audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = "apply" if args.apply else "dry_run"
    path = audit_dir / f"purchase_price_proof_metric_{stamp}_{suffix}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Relatorio: {path}")


if __name__ == "__main__":
    main()