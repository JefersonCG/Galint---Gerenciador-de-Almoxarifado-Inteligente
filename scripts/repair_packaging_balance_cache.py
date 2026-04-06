from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, StockBalance, StockMovement
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.legacy_stock_normalizer import resolve_packaging_factor


@dataclass(slots=True)
class RepairCandidate:
    codigo_item: str
    descricao: str
    tipo_embalagem: str | None
    fator_embalagem: float
    balance_before: float
    ledger_total: float
    item_embalagens_before: float
    item_soltas_before: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconstrói stock_balance e o read-model físico de itens com embalagem a partir do ledger")
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
    query = Item.query.filter(
        Item.tipo_embalagem_novo.isnot(None),
        Item.unidades_por_embalagem.isnot(None),
    ).order_by(Item.codigo_item.asc())
    if normalized_codes:
        query = query.filter(Item.codigo_item.in_(normalized_codes))

    candidates: list[RepairCandidate] = []
    for item in query.all():
        balance = db.session.get(StockBalance, item.codigo_item)
        if balance is None:
            continue
        ledger_total = _ledger_total(item.codigo_item)
        balance_total = float(balance.quantity_base or 0.0)
        if abs(balance_total - ledger_total) <= tolerance:
            continue
        candidates.append(
            RepairCandidate(
                codigo_item=item.codigo_item,
                descricao=item.descricao,
                tipo_embalagem=item.tipo_embalagem_novo,
                fator_embalagem=float(resolve_packaging_factor(item) or 0.0),
                balance_before=balance_total,
                ledger_total=ledger_total,
                item_embalagens_before=float(item.estoque_embalagens or 0.0),
                item_soltas_before=float(item.estoque_unidades_soltas or 0.0),
            )
        )
    return candidates


def _print_candidates(candidates: list[RepairCandidate]) -> None:
    print(f"Itens com divergência: {len(candidates)}")
    for candidate in candidates:
        expected_emb, expected_soltas = _expected_physical(candidate.ledger_total, candidate.fator_embalagem)
        print(
            f"{candidate.codigo_item} | {candidate.tipo_embalagem or '-'} | "
            f"balance={candidate.balance_before:g} -> ledger={candidate.ledger_total:g} | "
            f"fisico_atual={candidate.item_embalagens_before:g} emb + {candidate.item_soltas_before:g} soltas | "
            f"fisico_esperado={expected_emb:g} emb + {expected_soltas:g} soltas | {candidate.descricao}"
        )


def _apply(candidates: list[RepairCandidate]) -> None:
    for candidate in candidates:
        balance = db.session.get(StockBalance, candidate.codigo_item)
        item = db.session.get(Item, candidate.codigo_item)
        if balance is None or item is None:
            continue
        balance.quantity_base = float(candidate.ledger_total)
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