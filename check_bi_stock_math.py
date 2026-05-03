"""Auditoria read-only da matematica de estoque e cobertura BI.

Uso:
    .venv\Scripts\python.exe check_bi_stock_math.py
"""
from __future__ import annotations

import math
import os
from collections import defaultdict

from sqlalchemy import case, func, or_

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, Saida, StockBalance, StockMovement
from galint_flask.services.inventory import inventory_service


WITHDRAWAL_REFERENCE_TYPES = (
    "saida",
    "legacy_movimento",
    "movements_saida_multipla",
    "api_mobile_retirar",
    "api_mobile_retirar_multipla",
)
TOP_ROWS = 20


def _safe_float(value: object) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def _print_header(title: str) -> None:
    print("\n" + "=" * 92)
    print(title)
    print("=" * 92)


def audit_fractional_rows() -> None:
    _print_header("1. Saidas fracionadas sem campos estruturados")
    rows = (
        db.session.query(
            Saida.id_saida,
            Saida.codigo_item,
            Saida.quantidade,
            Saida.observacao,
            Saida.quantidade_retirada_em_litros,
            Saida.quantidade_retirada_em_quilos,
        )
        .filter(func.lower(func.coalesce(Saida.observacao, "")).like("%fracionada%"))
        .filter(or_(Saida.usou_fracao.is_(False), Saida.usou_fracao.is_(None)))
        .order_by(Saida.id_saida.desc())
        .all()
    )
    print(f"Total encontrado: {len(rows)}")
    for row in rows[:TOP_ROWS]:
        print(
            f"- saida={row.id_saida} item={row.codigo_item} qtd={_safe_float(row.quantidade):g} "
            f"litros={_safe_float(row.quantidade_retirada_em_litros):g} "
            f"quilos={_safe_float(row.quantidade_retirada_em_quilos):g} obs={row.observacao!r}"
        )


def audit_movement_reference_types() -> None:
    _print_header("2. StockMovement de saida por reference_type")
    rows = (
        db.session.query(
            StockMovement.reference_type,
            func.count(StockMovement.id),
            func.sum(case((StockMovement.reference_id.is_(None), 1), else_=0)),
        )
        .filter(StockMovement.movement_type == "saida")
        .group_by(StockMovement.reference_type)
        .order_by(func.count(StockMovement.id).desc())
        .all()
    )
    for reference_type, total, missing_ref in rows:
        print(
            f"- reference_type={reference_type or 'NULL'} total={int(total or 0)} "
            f"sem_reference_id={int(missing_ref or 0)}"
        )


def audit_bi_link_coverage() -> None:
    _print_header("3. Cobertura de vinculo Saida x StockMovement")
    saida_ids = [
        str(row[0])
        for row in db.session.query(Saida.id_saida)
        .filter(Saida.id_saida.isnot(None))
        .all()
    ]
    linked_ids = set()
    if saida_ids:
        linked_ids = {
            str(reference_id)
            for reference_id, in db.session.query(StockMovement.reference_id)
            .filter(StockMovement.movement_type == "saida")
            .filter(StockMovement.reference_type.in_(WITHDRAWAL_REFERENCE_TYPES))
            .filter(StockMovement.reference_id.in_(saida_ids))
            .distinct()
            .all()
            if reference_id not in (None, "")
        }
    total_saidas = len(saida_ids)
    matched = len(linked_ids)
    unmatched = max(total_saidas - matched, 0)
    coverage = (matched / total_saidas * 100.0) if total_saidas else 0.0
    print(f"- saídas totais: {total_saidas}")
    print(f"- saídas com StockMovement vinculado: {matched}")
    print(f"- saídas sem vinculo direto: {unmatched}")
    print(f"- cobertura atual: {coverage:.2f}%")


def audit_balance_vs_movements() -> None:
    _print_header("4. Divergencia entre StockBalance e soma do ledger")
    movement_sum_by_item = {
        str(product_id): _safe_float(quantity_sum)
        for product_id, quantity_sum in db.session.query(
            StockMovement.product_id,
            func.coalesce(func.sum(StockMovement.quantity_base), 0.0),
        )
        .group_by(StockMovement.product_id)
        .all()
        if product_id
    }
    balance_by_item = {
        str(balance.product_id): _safe_float(balance.quantity_base)
        for balance in StockBalance.query.all()
        if balance.product_id
    }
    item_map = {
        item.codigo_item: item.descricao
        for item in Item.query.with_entities(Item.codigo_item, Item.descricao).all()
    }
    divergences: list[tuple[float, str, float, float, str]] = []
    for codigo in sorted(set(movement_sum_by_item) | set(balance_by_item)):
        ledger_sum = movement_sum_by_item.get(codigo, 0.0)
        balance_qty = balance_by_item.get(codigo, 0.0)
        delta = round(balance_qty - ledger_sum, 6)
        if abs(delta) <= 1e-6:
            continue
        divergences.append((abs(delta), codigo, balance_qty, ledger_sum, item_map.get(codigo) or codigo))
    print(f"Total com divergencia: {len(divergences)}")
    for _weight, codigo, balance_qty, ledger_sum, descricao in divergences[:TOP_ROWS]:
        print(
            f"- {codigo} | {descricao} | stock_balance={balance_qty:g} | ledger_sum={ledger_sum:g} | delta={balance_qty - ledger_sum:g}"
        )


def audit_suspicious_common_mass_volume_exits() -> None:
    _print_header("5. Saidas kg/L suspeitas no fluxo comum")
    suspicious: list[tuple[int, str, str, float, float, str]] = []
    rows = (
        db.session.query(Saida, Item)
        .join(Item, Item.codigo_item == Saida.codigo_item)
        .order_by(Saida.id_saida.desc())
        .all()
    )
    for saida, item in rows:
        if inventory_service._is_tool_item(item):
            continue
        if not inventory_service._is_mass_or_volume_item(item):
            continue
        obs_lower = str(getattr(saida, "observacao", "") or "").strip().lower()
        if getattr(saida, "usou_fracao", False):
            continue
        if _safe_float(getattr(saida, "quantidade_retirada_em_litros", None)) > 0:
            continue
        if _safe_float(getattr(saida, "quantidade_retirada_em_quilos", None)) > 0:
            continue
        if "fracionada" in obs_lower:
            continue
        package_factor = inventory_service._package_factor_for_operational_policy(item)
        if package_factor <= 1:
            continue
        quantidade = _safe_float(saida.quantidade)
        em_embalagens = getattr(saida, "em_embalagens", None)
        if em_embalagens is False or not math.isclose(quantidade, round(quantidade), rel_tol=0.0, abs_tol=1e-6):
            suspicious.append(
                (
                    int(saida.id_saida or 0),
                    item.codigo_item,
                    item.descricao or item.codigo_item,
                    quantidade,
                    package_factor,
                    str(saida.observacao or ""),
                )
            )
    print(f"Total suspeito: {len(suspicious)}")
    for saida_id, codigo, descricao, quantidade, package_factor, observacao in suspicious[:TOP_ROWS]:
        print(
            f"- saida={saida_id} item={codigo} | {descricao} | qtd={quantidade:g} | fator_emb={package_factor:g} | obs={observacao!r}"
        )


def main() -> None:
    app = create_app()
    with app.app_context():
        _print_header("AUDITORIA BI / REGUA OPERACIONAL")
        print("Execucao read-only. Nenhum dado e alterado.")
        audit_fractional_rows()
        audit_movement_reference_types()
        audit_bi_link_coverage()
        audit_balance_vs_movements()
        audit_suspicious_common_mass_volume_exits()


if __name__ == "__main__":
    main()