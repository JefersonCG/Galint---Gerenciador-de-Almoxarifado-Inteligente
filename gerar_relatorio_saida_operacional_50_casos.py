"""Gera um relatorio enxuto com os 50 casos auditados na saida operacional.

O conjunto e montado assim:
- 7 itens com unidade numerica legada, agora acompanhados do status do cadastro;
- 16 itens cujo cadastro base e Par, acompanhados do status do fluxo da saida;
- 27 divergencias ainda abertas no recorte critico da saida em unidade.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from galint_flask import create_app
from galint_flask.models import Item
from galint_flask.views.movements import _build_saida_balance_display, _build_saida_unit_context


TARGET_CODES: tuple[str, ...] = (
    "0216A008",
    "7896038108244",
    "7896231701129",
    "7897613520529",
    "7897826107937",
    "7898056460076",
    "7899036387024",
)
AUDITED_OPERATIONAL_UNIT_CODES: tuple[str, ...] = (
    "07892904021716",
    "07898936842022",
    "100L",
    "200L",
    "300L",
    "60L",
    "7891035919787",
    "7891738018954",
    "7892261000447",
    "7897432700676",
    "7897637118962",
    "7897637126240",
    "7897841947686",
    "7898180829107",
    "7898214962961",
    "7898729414320",
    "7898924601617",
    "7898936842060",
    "7899682763500",
    "789987456654002",
    "789987456654003",
    "789987456654004",
    "789987456654005",
    "78998745665421",
    "CABO-RG6-001",
    "FOOD12215",
    "UYLN30460",
)
AUDITED_OPERATIONAL_DIVERGENCE_CODES: frozenset[str] = frozenset(
    {
        "07892904021716",
        "7898214962961",
        "CABO-RG6-001",
        "UYLN30460",
    }
)
UNIT_LIKE = {"un", "und", "unidade", "unidades", "peca", "peça", "pecas", "peças"}
MEASURE_PATTERN = re.compile(r"\b(kg|quilo|quilos|litro|litros|metro|metros)\b", re.IGNORECASE)
OUTPUT_JSON = Path("audit/saida_operacional_50_casos_2026_05_04.json")
OUTPUT_MD = Path("audit/saida_operacional_50_casos_2026_05_04.md")


def _build_row(item: Item, *, grupo: str, status: str, observacao: str) -> dict[str, object]:
    payload = item.to_dict(include_balance=True)
    unit_context = _build_saida_unit_context(payload, item)
    return {
        "codigo": item.codigo_item,
        "descricao": item.descricao,
        "grupo": grupo,
        "status": status,
        "observacao": observacao,
        "unidade_cadastro": item.unidade,
        "tipo_embalagem_novo": item.tipo_embalagem_novo,
        "saldo_legado": str(payload.get("saldo_display") or "").strip(),
        "unidade_saida": unit_context.get("devolucao_unidade_label"),
        "saldo_saida": _build_saida_balance_display(
            payload,
            unit_context,
            balance_key="saldo",
            fallback_key="saldo_display",
        ),
    }


def collect_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen_codes: set[str] = set()

    for codigo in TARGET_CODES:
        item = Item.query.get(codigo)
        if item is None:
            raise RuntimeError(f"Item numerico auditado nao encontrado: {codigo}")
        normalized = str(item.unidade or "").strip().lower()
        status = "corrigido_cadastro" if normalized == "unidade" else "pendente_cadastro"
        rows.append(
            _build_row(
                item,
                grupo="cadastro_numerico_legado",
                status=status,
                observacao="unidade numerica legada removida do cadastro",
            )
        )
        seen_codes.add(codigo)

    par_items = Item.query.filter(Item.unidade.ilike("Par")).order_by(Item.codigo_item).all()
    for item in par_items:
        context = _build_saida_unit_context(item.to_dict(include_balance=True), item)
        status = "corrigido_fluxo_par" if str(context.get("devolucao_unidade_codigo") or "").strip().lower() == "par" else "pendente_fluxo_par"
        rows.append(
            _build_row(
                item,
                grupo="cadastro_par",
                status=status,
                observacao="saida deve operar e exibir saldo em pares",
            )
        )
        seen_codes.add(item.codigo_item)

    for codigo in AUDITED_OPERATIONAL_UNIT_CODES:
        item = Item.query.get(codigo)
        if item is None:
            raise RuntimeError(f"Item auditado nao encontrado: {codigo}")

        payload = item.to_dict(include_balance=True)
        unit_context = _build_saida_unit_context(payload, item)
        raw_unit = str(item.unidade or "").strip()
        raw_unit_norm = raw_unit.lower()
        raw_display = str(payload.get("saldo_display") or "").strip()

        group_is_divergence = codigo in AUDITED_OPERATIONAL_DIVERGENCE_CODES
        grupo = "divergencia_operacional_unidade" if group_is_divergence else "cadastro_embalagem_ou_medida"
        corrected = (
            str(unit_context.get("devolucao_unidade_codigo") or "").strip().lower() == "unidade"
            and raw_unit_norm in UNIT_LIKE
            and not MEASURE_PATTERN.search(raw_display)
        )
        status = "corrigido_unidade_operacional" if corrected else "pendente"
        observacao = "cadastro realinhado para unidade operacional" if corrected else (
            "saldo legado ainda diverge do saldo operacional em unidade"
            if group_is_divergence
            else "cadastro com embalagem/medida ainda gera display legado na saida"
        )
        rows.append(
            _build_row(
                item,
                grupo=grupo,
                status=status,
                observacao=observacao,
            )
        )
        seen_codes.add(codigo)
    if len(rows) != 50:
        raise RuntimeError(f"Esperava 50 casos no relatorio consolidado, encontrei {len(rows)}")
    return rows


def write_outputs(rows: list[dict[str, object]]) -> dict[str, object]:
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    summary_by_status = Counter(str(row["status"]) for row in rows)
    summary_by_group = Counter(str(row["grupo"]) for row in rows)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total": len(rows),
            "by_status": dict(summary_by_status),
            "by_group": dict(summary_by_group),
        },
        "items": rows,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Relatorio Enxuto da Saida Operacional",
        "",
        f"Gerado em: {payload['generated_at']}",
        "",
        "## Resumo",
        "",
        f"- Total de casos consolidados: {len(rows)}",
    ]
    for status, count in sorted(summary_by_status.items()):
        lines.append(f"- {status}: {count}")
    lines.extend([
        "",
        "## Casos",
        "",
        "| Codigo | Descricao | Grupo | Status | Unidade cadastro | Unidade saida | Saldo legado | Saldo saida | Observacao |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in rows:
        lines.append(
            "| {codigo} | {descricao} | {grupo} | {status} | {unidade_cadastro} | {unidade_saida} | {saldo_legado} | {saldo_saida} | {observacao} |".format(
                codigo=str(row.get("codigo") or "").replace("|", "/"),
                descricao=str(row.get("descricao") or "").replace("|", "/"),
                grupo=str(row.get("grupo") or "").replace("|", "/"),
                status=str(row.get("status") or "").replace("|", "/"),
                unidade_cadastro=str(row.get("unidade_cadastro") or "").replace("|", "/"),
                unidade_saida=str(row.get("unidade_saida") or "").replace("|", "/"),
                saldo_legado=str(row.get("saldo_legado") or "").replace("|", "/"),
                saldo_saida=str(row.get("saldo_saida") or "").replace("|", "/"),
                observacao=str(row.get("observacao") or "").replace("|", "/"),
            )
        )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload["summary"]


def main() -> int:
    app = create_app()
    with app.app_context():
        rows = collect_rows()
        summary = write_outputs(rows)
    print({"json": str(OUTPUT_JSON), "md": str(OUTPUT_MD), "summary": summary})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())