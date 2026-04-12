"""Audita e realinha metadados de unidades operacionais com base em documentos.

Uso:
  .\.venv\Scripts\python.exe auditar_realinhamento_unidades_operacionais.py
  .\.venv\Scripts\python.exe auditar_realinhamento_unidades_operacionais.py --codigo 7898472262513
  .\.venv\Scripts\python.exe auditar_realinhamento_unidades_operacionais.py --apply-safe

Objetivo:
- manter intactos os itens ja compativeis com a regra operacional nova;
- listar itens que ainda precisam de realinhamento;
- aplicar automaticamente apenas os casos seguros, usando o historico documental
  e a inferencia de embalagem que o proprio sistema ja possui.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from math import isclose
from pathlib import Path
from types import SimpleNamespace
from typing import Any


os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoqueItem, Item
from galint_flask.services.inventory import InventoryService
from galint_flask.services.legacy_stock_normalizer import (
    ignore_packaging_metadata_for_stock,
    is_legacy_liter_packaging_compatible,
    resolve_canonical_unit,
    resolve_packaging_factor,
)


TARGET_OPERATIONAL_UNITS = (
    "unidade",
    "lata",
    "rolo",
    "pacote",
    "caixa",
    "fardo",
    "balde",
    "bombona",
    "saco",
)
TARGET_PACKAGING_UNITS = tuple(unit for unit in TARGET_OPERATIONAL_UNITS if unit != "unidade")
TARGET_INTERNAL_UNITS = {"un", "par", "kg", "l", "m"}
PACKAGING_FIELDS = (
    "tipo_embalagem_novo",
    "litros_por_embalagem",
    "grandeza_referencia",
    "unidades_por_embalagem",
    "unidade",
)
ALIASES = {
    "un": "unidade",
    "und": "unidade",
    "unid": "unidade",
    "peca": "unidade",
    "peça": "unidade",
    "pc": "unidade",
    "par": "par",
    "pares": "par",
    "l": "litro",
    "lt": "litro",
}
DISPLAY_INTERNAL_UNITS = {
    "un": "Unidade",
    "par": "Par",
    "kg": "Quilo",
    "l": "Litro",
    "m": "Metro",
}
INTERNAL_ALIASES = {
    "un": "un",
    "und": "un",
    "unidade": "un",
    "unidades": "un",
    "peca": "un",
    "peça": "un",
    "pc": "un",
    "par": "par",
    "pares": "par",
    "kg": "kg",
    "quilo": "kg",
    "quilos": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "l": "l",
    "lt": "l",
    "litro": "l",
    "litros": "l",
    "m": "m",
    "mt": "m",
    "mts": "m",
    "metro": "m",
    "metros": "m",
}
NUMERIC_TOLERANCE = 1e-6


@dataclass(slots=True)
class DocumentEvidence:
    rows_count: int
    unique_units: list[str]
    unique_factors: list[float]
    strong_unit: str | None
    strong_factor: float | None
    sample_document_numbers: list[str]


@dataclass(slots=True)
class AuditResult:
    codigo_item: str
    descricao: str
    status: str
    reason: str
    current_unit: str | None
    current_packaging: str | None
    current_factor: float
    current_canonical_unit: str | None
    proposed_unit: str | None
    proposed_packaging: str | None
    proposed_factor: float
    proposed_canonical_unit: str | None
    changes: dict[str, Any]
    document_evidence: DocumentEvidence


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audita o realinhamento das unidades operacionais.")
    parser.add_argument("--codigo", action="append", help="Codigo do item a auditar. Pode repetir.")
    parser.add_argument(
        "--apply-safe",
        action="store_true",
        help="Aplica somente os realinhamentos classificados como seguros.",
    )
    parser.add_argument(
        "--report-dir",
        default="audit",
        help="Diretorio onde os relatorios JSON e Markdown serao gravados.",
    )
    return parser.parse_args()


def _normalize_text(value: object) -> str:
    raw = str(value or "").strip().lower()
    return ALIASES.get(raw, raw)


def _normalize_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _normalize_internal_unit(value: object) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    return INTERNAL_ALIASES.get(raw, raw)


def _is_same_value(current: object, proposed: object) -> bool:
    current_number = _normalize_float(current)
    proposed_number = _normalize_float(proposed)
    if current_number is not None or proposed_number is not None:
        if current_number is None or proposed_number is None:
            return False
        return isclose(current_number, proposed_number, rel_tol=NUMERIC_TOLERANCE, abs_tol=NUMERIC_TOLERANCE)
    return str(current or "") == str(proposed or "")


def _collect_target_codes(explicit_codes: list[str] | None) -> list[str]:
    normalized = sorted({str(code or "").strip() for code in (explicit_codes or []) if str(code or "").strip()})
    if normalized:
        return normalized
    return [str(code).strip() for code, in db.session.query(Item.codigo_item).order_by(Item.codigo_item.asc()).all()]


def _build_document_index() -> dict[str, list[DocumentoEntradaEstoqueItem]]:
    index: dict[str, list[DocumentoEntradaEstoqueItem]] = defaultdict(list)
    rows = DocumentoEntradaEstoqueItem.query.filter(DocumentoEntradaEstoqueItem.quantidade > 0).all()
    for row in rows:
        index[str(row.codigo_item or "").strip()].append(row)
    return index


def _build_document_evidence(rows: list[DocumentoEntradaEstoqueItem]) -> DocumentEvidence:
    units: set[str] = set()
    factors: set[float] = set()
    document_numbers: list[str] = []
    for row in rows:
        quantity_value = float(row.quantidade or 0.0)
        quantity_base = _normalize_float(row.quantidade_base) or 0.0
        unit = _normalize_text(row.unidade_quantidade)
        if quantity_value > 0 and quantity_base > 0 and unit:
            units.add(unit)
            factors.add(round(quantity_base / quantity_value, 6))
        document = getattr(row, "documento", None)
        document_number = str(getattr(document, "numero_documento", "") or "").strip()
        if document_number and document_number not in document_numbers:
            document_numbers.append(document_number)

    strong_unit = next(iter(units)) if len(units) == 1 else None
    strong_factor = next(iter(factors)) if len(factors) == 1 else None
    return DocumentEvidence(
        rows_count=len(rows),
        unique_units=sorted(units),
        unique_factors=sorted(factors),
        strong_unit=strong_unit,
        strong_factor=strong_factor,
        sample_document_numbers=document_numbers[:5],
    )


def _probe_with_changes(item: Item, changes: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        codigo_item=item.codigo_item,
        descricao=item.descricao,
        categoria=item.categoria,
        marca=item.marca,
        unidade=changes.get("unidade", item.unidade),
        tipo_embalagem_novo=changes.get("tipo_embalagem_novo", item.tipo_embalagem_novo),
        litros_por_embalagem=changes.get("litros_por_embalagem", item.litros_por_embalagem),
        grandeza_referencia=changes.get("grandeza_referencia", item.grandeza_referencia),
        unidades_por_embalagem=changes.get("unidades_por_embalagem", item.unidades_por_embalagem),
        product_units=getattr(item, "product_units", []) or [],
    )


def _build_proposed_changes(item: Item) -> tuple[dict[str, Any], str | None, float, str | None, str | None]:
    hydrated = InventoryService._hydrate_missing_packaging_metadata({}, current_item=item)
    changes: dict[str, Any] = {}
    for field in PACKAGING_FIELDS:
        proposed = hydrated.get(field)
        if proposed in (None, ""):
            continue
        current = getattr(item, field, None)
        if _is_same_value(current, proposed):
            continue
        changes[field] = proposed

    probe = _probe_with_changes(item, changes)
    proposed_packaging = _normalize_text(getattr(probe, "tipo_embalagem_novo", None)) or None
    proposed_factor = float(resolve_packaging_factor(probe) or 0.0)
    proposed_canonical = _normalize_internal_unit(resolve_canonical_unit(probe))
    proposed_unit = changes.get("unidade") if "unidade" in changes else getattr(item, "unidade", None)
    return changes, proposed_packaging, proposed_factor, proposed_canonical or None, proposed_unit


def _reason_for_manual_review(
    *,
    item: Item,
    current_packaging: str | None,
    proposed_packaging: str | None,
    proposed_factor: float,
    proposed_canonical_unit: str | None,
    document_evidence: DocumentEvidence,
) -> str:
    current_unit = _normalize_text(item.unidade)
    if current_packaging == "litro":
        return "tipo_embalagem_novo=litro fica fora da nova regra operacional e exige revisao manual"
    if current_unit and current_unit.replace(".", "", 1).isdigit():
        return "unidade atual esta gravada como valor numerico legado"
    if document_evidence.strong_unit == "litro":
        return "documento antigo indica litro como unidade operacional"
    if document_evidence.strong_unit and proposed_packaging and document_evidence.strong_unit != proposed_packaging:
        return f"documento aponta {document_evidence.strong_unit} mas a inferencia atual aponta {proposed_packaging}"
    if (
        document_evidence.strong_unit
        and proposed_packaging == document_evidence.strong_unit
        and document_evidence.strong_factor is not None
        and proposed_factor > 0
        and not isclose(float(document_evidence.strong_factor), float(proposed_factor), rel_tol=NUMERIC_TOLERANCE, abs_tol=NUMERIC_TOLERANCE)
    ):
        return f"fator documental {document_evidence.strong_factor:g} diverge do fator inferido {proposed_factor:g}"
    if proposed_packaging and proposed_packaging not in TARGET_PACKAGING_UNITS:
        return f"embalagem inferida {proposed_packaging} nao pertence ao alvo operacional atual"
    if proposed_canonical_unit and proposed_canonical_unit not in TARGET_INTERNAL_UNITS:
        return f"unidade canonica inferida {proposed_canonical_unit} nao esta no conjunto suportado"
    if proposed_factor <= 0:
        return "fator operacional nao foi resolvido com seguranca"
    if not proposed_packaging:
        return "nao foi possivel inferir embalagem operacional com seguranca"
    return "revisao manual necessaria"


def _classify_item(item: Item, document_index: dict[str, list[DocumentoEntradaEstoqueItem]]) -> AuditResult:
    current_packaging = _normalize_text(item.tipo_embalagem_novo) or None
    current_unit = str(item.unidade or "").strip() or None
    current_internal_unit = _normalize_internal_unit(current_unit)
    current_factor = float(resolve_packaging_factor(item) or 0.0)
    current_canonical = _normalize_internal_unit(resolve_canonical_unit(item))
    document_rows = document_index.get(item.codigo_item, [])
    document_evidence = _build_document_evidence(document_rows)
    current_unit_numeric_legacy = bool(current_unit and current_unit.replace(".", "", 1).isdigit())

    if current_packaging == "litro" and is_legacy_liter_packaging_compatible(item):
        return AuditResult(
            codigo_item=item.codigo_item,
            descricao=item.descricao or "",
            status="kept",
            reason="item legado em litro mantido por compatibilidade operacional",
            current_unit=current_unit,
            current_packaging=current_packaging,
            current_factor=current_factor,
            current_canonical_unit=current_canonical,
            proposed_unit=current_unit,
            proposed_packaging=current_packaging,
            proposed_factor=current_factor,
            proposed_canonical_unit=current_canonical,
            changes={},
            document_evidence=document_evidence,
        )

    if current_packaging and ignore_packaging_metadata_for_stock(item):
        return AuditResult(
            codigo_item=item.codigo_item,
            descricao=item.descricao or "",
            status="kept",
            reason="item kit/ferramenta mantido sem normalizacao operacional de embalagem",
            current_unit=current_unit,
            current_packaging=current_packaging,
            current_factor=current_factor,
            current_canonical_unit=current_canonical,
            proposed_unit=current_unit,
            proposed_packaging=current_packaging,
            proposed_factor=current_factor,
            proposed_canonical_unit=current_canonical,
            changes={},
            document_evidence=document_evidence,
        )

    if current_packaging in TARGET_PACKAGING_UNITS and current_factor > 0:
        return AuditResult(
            codigo_item=item.codigo_item,
            descricao=item.descricao or "",
            status="kept",
            reason="item ja compativel com a regra operacional nova",
            current_unit=current_unit,
            current_packaging=current_packaging,
            current_factor=current_factor,
            current_canonical_unit=current_canonical,
            proposed_unit=current_unit,
            proposed_packaging=current_packaging,
            proposed_factor=current_factor,
            proposed_canonical_unit=current_canonical,
            changes={},
            document_evidence=document_evidence,
        )

    if not current_packaging and current_internal_unit in {"un", "par"}:
        return AuditResult(
            codigo_item=item.codigo_item,
            descricao=item.descricao or "",
            status="kept",
            reason="item sem embalagem ja pode ser mantido na unidade base atual",
            current_unit=current_unit,
            current_packaging=current_packaging,
            current_factor=current_factor,
            current_canonical_unit=current_canonical,
            proposed_unit=current_unit,
            proposed_packaging=current_packaging,
            proposed_factor=current_factor,
            proposed_canonical_unit=current_canonical,
            changes={},
            document_evidence=document_evidence,
        )

    changes, proposed_packaging, proposed_factor, proposed_canonical, proposed_unit = _build_proposed_changes(item)
    doc_unit = document_evidence.strong_unit
    doc_factor = document_evidence.strong_factor
    safe_packaging_apply = (
        proposed_packaging in TARGET_PACKAGING_UNITS
        and proposed_factor > 0
        and (proposed_canonical or "") in TARGET_INTERNAL_UNITS
        and (
            not doc_unit
            or (
                doc_unit == proposed_packaging
                and doc_factor is not None
                and isclose(float(doc_factor), float(proposed_factor), rel_tol=NUMERIC_TOLERANCE, abs_tol=NUMERIC_TOLERANCE)
            )
        )
    )
    safe_unit_only_apply = (
        current_unit_numeric_legacy
        and not proposed_packaging
        and str(proposed_unit or "").strip() in {"Unidade", "Par"}
        and (proposed_canonical or "") in {"un", "par"}
        and not doc_unit
        and doc_factor is None
    )
    safe_to_apply = safe_packaging_apply or safe_unit_only_apply

    if safe_to_apply and changes:
        return AuditResult(
            codigo_item=item.codigo_item,
            descricao=item.descricao or "",
            status="safe_apply",
            reason="inferencia atual do sistema e historico documental permitem realinhamento automatico",
            current_unit=current_unit,
            current_packaging=current_packaging,
            current_factor=current_factor,
            current_canonical_unit=current_canonical,
            proposed_unit=str(proposed_unit or "").strip() or None,
            proposed_packaging=proposed_packaging,
            proposed_factor=proposed_factor,
            proposed_canonical_unit=proposed_canonical,
            changes=changes,
            document_evidence=document_evidence,
        )

    return AuditResult(
        codigo_item=item.codigo_item,
        descricao=item.descricao or "",
        status="manual_review",
        reason=_reason_for_manual_review(
            item=item,
            current_packaging=current_packaging,
            proposed_packaging=proposed_packaging,
            proposed_factor=proposed_factor,
            proposed_canonical_unit=proposed_canonical,
            document_evidence=document_evidence,
        ),
        current_unit=current_unit,
        current_packaging=current_packaging,
        current_factor=current_factor,
        current_canonical_unit=current_canonical,
        proposed_unit=str(proposed_unit or "").strip() or None,
        proposed_packaging=proposed_packaging,
        proposed_factor=proposed_factor,
        proposed_canonical_unit=proposed_canonical,
        changes=changes,
        document_evidence=document_evidence,
    )


def _markdown_table_row(columns: list[str]) -> str:
    escaped = [column.replace("|", "\\|") for column in columns]
    return "| " + " | ".join(escaped) + " |"


def _render_markdown(results: list[AuditResult], applied_codes: set[str]) -> str:
    counter = Counter(result.status for result in results)
    manual_reason_counter = Counter(result.reason for result in results if result.status == "manual_review")
    safe_results = [result for result in results if result.status == "safe_apply"]
    manual_results = [result for result in results if result.status == "manual_review"]
    numeric_legacy_results = [
        result
        for result in manual_results
        if result.reason == "unidade atual esta gravada como valor numerico legado"
    ]
    numeric_legacy_buckets = Counter(
        result.proposed_packaging
        or (f"base {DISPLAY_INTERNAL_UNITS[result.proposed_canonical_unit]}" if result.proposed_canonical_unit in DISPLAY_INTERNAL_UNITS else "sem proposta")
        for result in numeric_legacy_results
    )

    lines = [
        "# Relatorio de Realinhamento de Unidades Operacionais",
        "",
        f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Resumo",
        "",
        f"- Itens avaliados: {len(results)}",
        f"- Mantidos sem alteracao: {counter.get('kept', 0)}",
        f"- Candidatos seguros para realinhamento: {counter.get('safe_apply', 0)}",
        f"- Revisao manual necessaria: {counter.get('manual_review', 0)}",
        f"- Ajustes seguros aplicados nesta execucao: {len(applied_codes)}",
        "",
        "## Motivos de revisao manual",
        "",
    ]
    for reason, amount in manual_reason_counter.most_common():
        lines.append(f"- {reason}: {amount}")

    lines.extend([
        "",
        "## Lotes de unidade numerica legada",
        "",
    ])
    if numeric_legacy_buckets:
        for bucket, amount in numeric_legacy_buckets.most_common():
            lines.append(f"- {bucket}: {amount}")
    else:
        lines.append("- Nenhum caso numerico legado pendente.")

    lines.extend([
        "",
        "## Candidatos seguros",
        "",
        _markdown_table_row(["Codigo", "Descricao", "Atual", "Proposto", "Mudancas", "Documentos"]),
        _markdown_table_row(["---", "---", "---", "---", "---", "---"]),
    ])
    for result in safe_results:
        current = f"{result.current_packaging or '-'} / fator {result.current_factor:g}"
        proposed = f"{result.proposed_packaging or '-'} / fator {result.proposed_factor:g}"
        changes = ", ".join(f"{key}={value}" for key, value in sorted(result.changes.items())) or "-"
        documents = ", ".join(result.document_evidence.sample_document_numbers) or "-"
        if result.codigo_item in applied_codes:
            proposed = proposed + " (aplicado)"
        lines.append(_markdown_table_row([result.codigo_item, result.descricao, current, proposed, changes, documents]))

    lines.extend([
        "",
        "## Revisao manual",
        "",
        _markdown_table_row(["Codigo", "Descricao", "Atual", "Proposta", "Motivo", "Documentos"]),
        _markdown_table_row(["---", "---", "---", "---", "---", "---"]),
    ])
    for result in manual_results:
        current = f"{result.current_packaging or '-'} / fator {result.current_factor:g}"
        proposed = f"{result.proposed_packaging or '-'} / fator {result.proposed_factor:g}" if result.proposed_packaging else "-"
        documents = ", ".join(result.document_evidence.sample_document_numbers) or "-"
        lines.append(_markdown_table_row([result.codigo_item, result.descricao, current, proposed, result.reason, documents]))

    lines.append("")
    return "\n".join(lines)


def _serialize_results(results: list[AuditResult], applied_codes: set[str]) -> dict[str, Any]:
    counter = Counter(result.status for result in results)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "items_evaluated": len(results),
            "kept": counter.get("kept", 0),
            "safe_apply": counter.get("safe_apply", 0),
            "manual_review": counter.get("manual_review", 0),
            "applied_safe_codes": sorted(applied_codes),
        },
        "results": [],
    }
    for result in results:
        result_payload = asdict(result)
        result_payload["applied"] = result.codigo_item in applied_codes
        payload["results"].append(result_payload)
    return payload


def _write_reports(results: list[AuditResult], applied_codes: set[str], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / "realinhamento_unidades_operacionais.md"
    json_path = report_dir / "realinhamento_unidades_operacionais.json"
    markdown_path.write_text(_render_markdown(results, applied_codes), encoding="utf-8")
    json_path.write_text(json.dumps(_serialize_results(results, applied_codes), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Relatorio Markdown: {markdown_path}")
    print(f"Relatorio JSON: {json_path}")


def main() -> int:
    args = _parse_args()
    app = create_app()
    applied_codes: set[str] = set()

    with app.app_context():
        target_codes = _collect_target_codes(args.codigo)
        items = [db.session.get(Item, code) for code in target_codes]
        items = [item for item in items if item is not None]
        document_index = _build_document_index()
        results = [_classify_item(item, document_index) for item in items]

        if args.apply_safe:
            for result in results:
                if result.status != "safe_apply" or not result.changes:
                    continue
                item = db.session.get(Item, result.codigo_item)
                if item is None:
                    continue
                for field, value in result.changes.items():
                    setattr(item, field, value)
                applied_codes.add(result.codigo_item)
            db.session.commit()
        else:
            db.session.rollback()

        _write_reports(results, applied_codes, Path(args.report_dir))

        counter = Counter(result.status for result in results)
        print(
            "Resumo: "
            f"avaliados={len(results)} | "
            f"mantidos={counter.get('kept', 0)} | "
            f"seguros={counter.get('safe_apply', 0)} | "
            f"manuais={counter.get('manual_review', 0)} | "
            f"aplicados={len(applied_codes)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())