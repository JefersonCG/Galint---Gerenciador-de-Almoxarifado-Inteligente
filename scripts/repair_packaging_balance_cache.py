from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, StockBalance, StockMovement
from galint_flask.services.balance_provider import balance_provider
from galint_flask.services.embalagem_service import EmbalagemService
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.legacy_stock_normalizer import resolve_packaging_factor


@dataclass(slots=True)
class RepairCandidate:
    codigo_item: str
    descricao: str
    tipo_embalagem: str | None
    fator_embalagem: float
    balance_before: float | None
    ledger_total: float
    snapshot_total: float
    snapshot_source: str
    sync_unit_base: str | None
    item_embalagens_before: float
    item_soltas_before: float
    expected_embalagens: float
    expected_soltas: float
    fix_balance: bool
    fix_read_model: bool


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconstrói stock_balance e o read-model físico de itens com embalagem")
    parser.add_argument("--codes", nargs="*", help="Códigos específicos para filtrar")
    parser.add_argument("--apply", action="store_true", help="Aplica a correção no banco")
    parser.add_argument("--tolerance", type=float, default=0.01, help="Tolerância mínima para considerar divergência")
    return parser.parse_args()


def _ledger_total(codigo_item: str) -> float:
    total = (
        db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
        .filter(StockMovement.product_id == codigo_item)
        .scalar()
    )
    return float(total or 0.0)


def _expected_physical(total: float, factor: float) -> tuple[float, float]:
    quantity = max(float(total or 0.0), 0.0)
    if factor <= 0:
        return 0.0, quantity
    embalagens = float(math.floor((quantity + 1e-9) / factor))
    soltas = float(quantity - (embalagens * factor))
    if abs(soltas) <= 1e-6:
        soltas = 0.0
    return embalagens, soltas


def _collect_candidates(codes: list[str] | None, tolerance: float) -> list[RepairCandidate]:
    normalized_codes = sorted({str(code or "").strip() for code in (codes or []) if str(code or "").strip()})
    query = Item.query.filter(Item.tipo_embalagem_novo.isnot(None)).order_by(Item.codigo_item.asc())
    if normalized_codes:
        query = query.filter(Item.codigo_item.in_(normalized_codes))

    candidates: list[RepairCandidate] = []
    for item in query.all():
        if not EmbalagemService.tem_embalagem(item):
            continue

        fator_embalagem = float(resolve_packaging_factor(item) or 0.0)
        if fator_embalagem <= 0:
            continue

        balance = db.session.get(StockBalance, item.codigo_item)
        ledger_total = _ledger_total(item.codigo_item)
        balance_total = float(balance.quantity_base or 0.0) if balance is not None else None

        snapshot = balance_provider.get_balance(item.codigo_item, item=item)
        sync_unit_base = inventory_engine._resolve_packaging_sync_unit_base(
            product_id=item.codigo_item,
            fallback_unit_base=snapshot.unit_base,
        )
        expected_embalagens, expected_soltas = inventory_engine._decompose_packaging_balance(
            item=item,
            quantity_base=float(snapshot.quantity_base or 0.0),
            unit_base=sync_unit_base,
        )

        fix_balance = balance_total is not None and abs(balance_total - ledger_total) > tolerance
        fix_read_model = (
            abs(float(item.estoque_embalagens or 0.0) - expected_embalagens) > tolerance
            or abs(float(item.estoque_unidades_soltas or 0.0) - expected_soltas) > tolerance
        )
        if not fix_balance and not fix_read_model:
            continue
        candidates.append(
            RepairCandidate(
                codigo_item=item.codigo_item,
                descricao=item.descricao,
                tipo_embalagem=item.tipo_embalagem_novo,
                fator_embalagem=fator_embalagem,
                balance_before=balance_total,
                ledger_total=ledger_total,
                snapshot_total=float(snapshot.quantity_base or 0.0),
                snapshot_source=str(snapshot.source or ""),
                sync_unit_base=sync_unit_base,
                item_embalagens_before=float(item.estoque_embalagens or 0.0),
                item_soltas_before=float(item.estoque_unidades_soltas or 0.0),
                expected_embalagens=expected_embalagens,
                expected_soltas=expected_soltas,
                fix_balance=fix_balance,
                fix_read_model=fix_read_model,
            )
        )
    return candidates


def _print_candidates(candidates: list[RepairCandidate]) -> None:
    print(f"Itens com divergência: {len(candidates)}")
    for candidate in candidates:
        reasons: list[str] = []
        if candidate.fix_balance:
            reasons.append("stock_balance")
        if candidate.fix_read_model:
            reasons.append("read_model")
        expected_emb, expected_soltas = candidate.expected_embalagens, candidate.expected_soltas
        balance_before_txt = "-" if candidate.balance_before is None else f"{candidate.balance_before:g}"
        print(
            f"{candidate.codigo_item} | {candidate.tipo_embalagem or '-'} | motivos={','.join(reasons) or '-'} | "
            f"balance={balance_before_txt} -> ledger={candidate.ledger_total:g} | "
            f"snapshot={candidate.snapshot_total:g} ({candidate.snapshot_source}:{candidate.sync_unit_base or '-'}) | "
            f"fisico_atual={candidate.item_embalagens_before:g} emb + {candidate.item_soltas_before:g} soltas | "
            f"fisico_esperado={expected_emb:g} emb + {expected_soltas:g} soltas | {candidate.descricao}"
        )


def _apply(candidates: list[RepairCandidate]) -> None:
    for candidate in candidates:
        balance = db.session.get(StockBalance, candidate.codigo_item)
        if candidate.fix_balance and balance is not None:
            balance.quantity_base = float(candidate.ledger_total)
        if not candidate.fix_balance and not candidate.fix_read_model:
            continue
        inventory_engine.sync_packaging_read_model(product_id=candidate.codigo_item, commit=False)
    db.session.commit()


def main() -> int:
    args = _parse_args()
    app = create_app()

    with app.app_context():
        candidates = _collect_candidates(args.codes, max(float(args.tolerance or 0.0), 0.0))
        _print_candidates(candidates)
        if not args.apply or not candidates:
            return 0
        _apply(candidates)
        print("\nCorreção aplicada. Estado após ajuste:\n")
        refreshed = _collect_candidates(args.codes, max(float(args.tolerance or 0.0), 0.0))
        _print_candidates(refreshed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())