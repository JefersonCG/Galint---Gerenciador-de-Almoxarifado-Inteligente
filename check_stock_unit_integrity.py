"""Audita integridade entre saldo canônico, ledger, cache e read model de embalagens.

Uso:
  .\.venv\Scripts\python.exe check_stock_unit_integrity.py
  .\.venv\Scripts\python.exe check_stock_unit_integrity.py --codigo 7891323088072
  .\.venv\Scripts\python.exe check_stock_unit_integrity.py --strict-movements

Objetivo:
- detectar divergências entre `stock_movements`, `stock_balances` e
  `estoque_embalagens`/`estoque_unidades_soltas`
- validar se itens embalados usam unidade canônica coerente (`kg`, `l`, `m`, `un`)
- sinalizar movimentos com `unit_base` de embalagem que merecem revisão

Saída:
- código 0: nenhum erro crítico encontrado
- código 1: ao menos um erro crítico encontrado
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from sqlalchemy import func

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, StockBalance, StockMovement
from galint_flask.services.balance_provider import balance_provider
from galint_flask.services.embalagem_service import EmbalagemService
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.legacy_stock_normalizer import (
    is_packaging_unit_code,
    resolve_canonical_unit,
    resolve_packaging_factor,
)


TOLERANCE = 1e-6
DISPLAY_TOLERANCE = 1e-3
DEFAULT_BASELINE_PATH = Path("audit") / "stock_unit_integrity_baseline.json"


@dataclass(slots=True)
class Issue:
    severity: str
    code: str
    description: str
    check: str
    detail: str


def _normalize_unit(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "unidade": "un",
        "unidades": "un",
        "quilo": "kg",
        "quilos": "kg",
        "litro": "l",
        "litros": "l",
        "metro": "m",
        "metros": "m",
    }
    return aliases.get(raw, raw)


def _safe_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _physical_read_model_target(quantity_base: float | None) -> float:
    return max(float(quantity_base or 0.0), 0.0)


def _format_issue(issue: Issue) -> str:
    return f"[{issue.severity}] {issue.code} | {issue.description} | {issue.check} | {issue.detail}"


def _issue_signature(issue: Issue) -> str:
    return "|".join(
        (
            issue.code,
            issue.check,
            issue.detail,
        )
    )


def _load_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    issues = payload.get("known_issues") or []
    return {str(value) for value in issues if value}


def _write_baseline(path: Path, issues: list[Issue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    unique_issues = sorted({_issue_signature(issue) for issue in issues})
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "known_issue_count": len(unique_issues),
        "known_issues": unique_issues,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _classify_packaging_movement(
    *,
    item: Item,
    movement: StockMovement,
    canonical_unit: str,
    packaging_factor: float,
) -> Issue | None:
    unit_base = _normalize_unit(movement.unit_base)
    if not unit_base or not is_packaging_unit_code(unit_base):
        return None
    if not canonical_unit or canonical_unit == unit_base:
        return None

    metadata = movement.metadata_json or {}
    source = str(metadata.get("source") or "").strip().lower()
    input_unit = _normalize_unit(metadata.get("input_unit"))
    input_quantity = _safe_float(metadata.get("input_quantity"))
    factor_applied = _safe_float(metadata.get("factor_applied"))
    quantity_base = abs(float(movement.quantity_base or 0.0))
    expected_canonical = None
    if input_quantity is not None and packaging_factor > 0:
        expected_canonical = abs(input_quantity) * packaging_factor

    if (
        packaging_factor > 1.0
        and source == "inventory_engine"
        and bool(metadata.get("dual_write_active"))
        and input_unit
        and is_packaging_unit_code(input_unit)
        and input_quantity is not None
        and abs(quantity_base - abs(input_quantity)) <= DISPLAY_TOLERANCE
        and (factor_applied is None or abs(factor_applied - 1.0) <= DISPLAY_TOLERANCE)
    ):
        return Issue(
            severity="warning",
            code=item.codigo_item,
            description=item.descricao or "",
            check="movement_packaging_leak",
            detail=(
                f"movimento {movement.id} usa unit_base={movement.unit_base} e quantity_base={movement.quantity_base:g}; "
                f"entrada em embalagem sem conversão canônica aparente"
            ),
        )

    if expected_canonical is not None and abs(quantity_base - expected_canonical) <= DISPLAY_TOLERANCE:
        return Issue(
            severity="warning",
            code=item.codigo_item,
            description=item.descricao or "",
            check="movement_packaging_label",
            detail=(
                f"movimento {movement.id} parece convertido corretamente em quantidade, mas unit_base={movement.unit_base} "
                f"não corresponde à unidade canônica {canonical_unit}"
            ),
        )

    return Issue(
        severity="warning",
        code=item.codigo_item,
        description=item.descricao or "",
        check="movement_packaging_review",
        detail=(
            f"movimento {movement.id} usa unit_base={movement.unit_base} fora da unidade canônica {canonical_unit}; "
            f"revisar histórico"
        ),
    )


def _audit_item(item: Item, *, strict_movements: bool) -> list[Issue]:
    issues: list[Issue] = []
    canonical_unit = _normalize_unit(resolve_canonical_unit(item))
    packaging_factor = float(resolve_packaging_factor(item) or 0.0)
    configured_base_units = [
        _normalize_unit(unit.unit_code)
        for unit in (item.product_units or [])
        if getattr(unit, "is_base", False) and getattr(unit, "active", False)
    ]

    if not canonical_unit:
        issues.append(
            Issue(
                severity="error",
                code=item.codigo_item,
                description=item.descricao or "",
                check="canonical_unit",
                detail="item embalado sem unidade canônica resolvida",
            )
        )
        return issues

    if is_packaging_unit_code(canonical_unit):
        issues.append(
            Issue(
                severity="error",
                code=item.codigo_item,
                description=item.descricao or "",
                check="canonical_unit",
                detail=f"unidade canônica inválida para item embalado: {canonical_unit}",
            )
        )

    packaging_base_units = [unit_code for unit_code in configured_base_units if is_packaging_unit_code(unit_code)]
    if packaging_base_units:
        issues.append(
            Issue(
                severity="error",
                code=item.codigo_item,
                description=item.descricao or "",
                check="product_unit_base_packaging",
                detail=(
                    f"product_units base configurada como embalagem: {', '.join(packaging_base_units)}; "
                    f"esperado base canônica {canonical_unit or 'indefinida'}"
                ),
            )
        )

    if packaging_factor <= 0.0:
        issues.append(
            Issue(
                severity="error",
                code=item.codigo_item,
                description=item.descricao or "",
                check="packaging_factor",
                detail="item embalado sem fator de embalagem positivo",
            )
        )
        return issues

    movement_sum = float(
        db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
        .filter(StockMovement.product_id == item.codigo_item)
        .scalar()
        or 0.0
    )
    balance_row = db.session.get(StockBalance, item.codigo_item)
    stock_balance = float(balance_row.quantity_base or 0.0) if balance_row else 0.0
    balance_snapshot = balance_provider.get_balance(item.codigo_item, item=item)

    if abs(stock_balance - movement_sum) > DISPLAY_TOLERANCE:
        issues.append(
            Issue(
                severity="error",
                code=item.codigo_item,
                description=item.descricao or "",
                check="ledger_vs_cache",
                detail=f"stock_balance={stock_balance:g} diverge de stock_movements={movement_sum:g}",
            )
        )

    if abs(float(balance_snapshot.quantity_base or 0.0) - movement_sum) > DISPLAY_TOLERANCE:
        issues.append(
            Issue(
                severity="error",
                code=item.codigo_item,
                description=item.descricao or "",
                check="provider_vs_ledger",
                detail=(
                    f"balance_provider={float(balance_snapshot.quantity_base or 0.0):g} diverge de "
                    f"stock_movements={movement_sum:g}"
                ),
            )
        )

    expected_embalagens, expected_unidades_soltas = inventory_engine._decompose_packaging_balance(
        item=item,
        quantity_base=movement_sum,
        unit_base=canonical_unit,
    )
    actual_embalagens = float(item.estoque_embalagens or 0.0)
    actual_unidades_soltas = float(item.estoque_unidades_soltas or 0.0)

    if abs(actual_embalagens - expected_embalagens) > DISPLAY_TOLERANCE or abs(actual_unidades_soltas - expected_unidades_soltas) > DISPLAY_TOLERANCE:
        issues.append(
            Issue(
                severity="error",
                code=item.codigo_item,
                description=item.descricao or "",
                check="read_model_vs_ledger",
                detail=(
                    f"esperado {expected_embalagens:g} embalagens + {expected_unidades_soltas:g} soltas, "
                    f"encontrado {actual_embalagens:g} + {actual_unidades_soltas:g}"
                ),
            )
        )

    recomposed_total = (actual_embalagens * packaging_factor) + actual_unidades_soltas
    physical_target = _physical_read_model_target(movement_sum)
    if abs(recomposed_total - physical_target) > DISPLAY_TOLERANCE:
        issues.append(
            Issue(
                severity="error",
                code=item.codigo_item,
                description=item.descricao or "",
                check="physical_total_vs_ledger",
                detail=(
                    f"total físico recombinado={recomposed_total:g} diverge de alvo físico={physical_target:g} "
                    f"(stock_movements={movement_sum:g})"
                ),
            )
        )

    for movement in (
        StockMovement.query
        .filter(StockMovement.product_id == item.codigo_item)
        .order_by(StockMovement.created_at.asc(), StockMovement.id.asc())
        .all()
    ):
        issue = _classify_packaging_movement(
            item=item,
            movement=movement,
            canonical_unit=canonical_unit,
            packaging_factor=packaging_factor,
        )
        if issue is None:
            continue
        if strict_movements:
            issue = Issue(
                severity="error",
                code=issue.code,
                description=issue.description,
                check=issue.check,
                detail=issue.detail,
            )
        issues.append(issue)

    return issues


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audita integridade de saldo/unidade dos itens embalados.")
    parser.add_argument("--codigo", help="Audita apenas um código de item específico.")
    parser.add_argument(
        "--strict-movements",
        action="store_true",
        help="Trata movimentos suspeitos com unit_base de embalagem como erro crítico.",
    )
    parser.add_argument(
        "--baseline-file",
        default=str(DEFAULT_BASELINE_PATH),
        help="Arquivo JSON com baseline de inconsistências já conhecidas.",
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Ignora o baseline e avalia todas as inconsistências atuais como novas.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Grava o estado atual das inconsistências no arquivo de baseline informado.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    app = create_app()
    baseline_path = Path(args.baseline_file)

    with app.app_context():
        query = Item.query.order_by(Item.codigo_item.asc())
        if args.codigo:
            query = query.filter(Item.codigo_item == args.codigo.strip())

        items = [item for item in query.all() if EmbalagemService.tem_embalagem(item)]
        if args.codigo and not items:
            print(f"Nenhum item embalado encontrado para o código {args.codigo}.")
            return 1

        issues: list[Issue] = []
        scanned = 0
        for item in items:
            scanned += 1
            issues.extend(_audit_item(item, strict_movements=args.strict_movements))

        errors = [issue for issue in issues if issue.severity == "error"]
        warnings = [issue for issue in issues if issue.severity == "warning"]

        if args.write_baseline:
            _write_baseline(baseline_path, issues)
            print(f"Baseline gravado em {baseline_path} com {len({_issue_signature(issue) for issue in issues})} assinaturas.")
            return 0

        known_signatures = set()
        if not args.no_baseline:
            known_signatures = _load_baseline(baseline_path)

        new_errors = [issue for issue in errors if _issue_signature(issue) not in known_signatures]
        new_warnings = [issue for issue in warnings if _issue_signature(issue) not in known_signatures]
        blocking_new_warnings = [
            issue for issue in new_warnings
            if issue.check == "movement_packaging_leak"
        ]

        print(f"Itens embalados auditados: {scanned}")
        print(f"Erros críticos: {len(errors)}")
        print(f"Avisos: {len(warnings)}")
        if known_signatures:
            print(f"Baseline carregado: {baseline_path} ({len(known_signatures)} assinaturas conhecidas)")
            print(f"Novos erros críticos: {len(new_errors)}")
            print(f"Novos avisos: {len(new_warnings)}")

        issues_to_print = issues
        if known_signatures:
            issues_to_print = [*new_errors, *new_warnings]

        for issue in [issue for issue in issues_to_print if issue.severity == "error"]:
            print(_format_issue(issue))
        for issue in [issue for issue in issues_to_print if issue.severity == "warning"]:
            print(_format_issue(issue))

        if known_signatures:
            if new_errors or blocking_new_warnings:
                return 1
            print("Nenhuma regressão nova encontrada em relação ao baseline.")
            return 0

        if errors:
            return 1

        print("Nenhum erro crítico encontrado.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())