from __future__ import annotations

import argparse
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, Saida, StockBalance, StockMovement
from galint_flask.services.inventory import inventory_service
from galint_flask.services.inventory_engine import inventory_engine
from galint_flask.services.ledger_backfill_normalized import ledger_backfill_service

ORPHAN_REFERENCE_TYPES = (
    "legacy_movimento",
    "movements_saida_multipla",
    "api_mobile_retirar",
    "api_mobile_retirar_multipla",
)
TIMESTAMP_SHIFT_BY_REFERENCE_TYPE = {
    "movements_saida_multipla": timedelta(hours=3),
}
FRACTIONAL_PATTERN = re.compile(
    r"retirada\s+fracionada:\s*([0-9]+(?:[.,][0-9]+)?)\s*(kg|quilo(?:s)?|l|litro(?:s)?)\b",
    re.IGNORECASE,
)
FRACTIONAL_LEGACY_RECORDED_PATTERN = re.compile(
    r"retirada:\s*([0-9]+(?:[.,][0-9]+)?)\s*(kg|quilo(?:s)?|l|litro(?:s)?)(?:\b|\.)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class LinkMatch:
    movement_id: int
    saida_id: int
    product_id: str
    reference_type: str
    target_time: datetime
    desired_quantity: float
    matched_quantity: float
    delta_seconds: float
    strategy: str


@dataclass(slots=True)
class FractionalRepair:
    saida_id: int
    product_id: str
    quantity: float
    unit: str
    observacao: str


@dataclass(slots=True)
class BalanceRepair:
    product_id: str
    description: str
    stock_balance: float
    ledger_total: float
    delta: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill conservador dos vinculos Saida x StockMovement e saneamento do legado "
            "fracionado/saldos apontado na auditoria BI."
        )
    )
    parser.add_argument("--apply-links", action="store_true", help="Grava reference_id nos StockMovement órfãos elegíveis")
    parser.add_argument("--apply-fractional", action="store_true", help="Estrutura saídas fracionadas históricas a partir da observação")
    parser.add_argument("--apply-balances", action="store_true", help="Reconstrói StockBalance dos itens com divergência contra o ledger")
    parser.add_argument("--apply-all", action="store_true", help="Aplica links, fracionado e reconstrução de saldos")
    parser.add_argument("--limit", type=int, default=20, help="Quantidade máxima de linhas detalhadas por seção")
    parser.add_argument("--tolerance", type=float, default=1e-6, help="Tolerância para divergência de saldos")
    return parser.parse_args()


def _safe_float(value: object) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").upper().split())


def _target_time_for(movement: StockMovement) -> datetime:
    shift = TIMESTAMP_SHIFT_BY_REFERENCE_TYPE.get(str(movement.reference_type or "").strip(), timedelta(0))
    return movement.created_at - shift


def _expected_saida_quantity(movement: StockMovement, item: Item | None) -> tuple[float, str]:
    metadata = dict(movement.metadata_json or {})
    payload = dict(metadata.get("legacy_payload") or {})
    quantity_base = abs(_safe_float(movement.quantity_base))
    desired_quantity = _safe_float(metadata.get("input_quantity"))
    factor_applied = _safe_float(metadata.get("factor_applied"))

    if payload.get("em_embalagens"):
        package_factor = factor_applied if factor_applied > 1 else _safe_float(
            inventory_service._package_factor_for_operational_policy(item) if item is not None else 0.0
        )
        if package_factor > 1:
            package_quantity = quantity_base / package_factor
            if abs(package_quantity - round(package_quantity)) <= 1e-6:
                return float(round(package_quantity)), "packaging_factor_reverse"

    if desired_quantity > 0:
        return desired_quantity, "metadata_input_quantity"

    return quantity_base, "quantity_base"


def _candidate_rows_for_movement(movement: StockMovement) -> list[tuple[float, int, LinkMatch]]:
    metadata = dict(movement.metadata_json or {})
    payload = dict(metadata.get("legacy_payload") or {})
    item = db.session.get(Item, movement.product_id)
    target_time = _target_time_for(movement)
    desired_quantity, strategy = _expected_saida_quantity(movement, item)
    matricula = str(payload.get("matricula") or metadata.get("user_id") or metadata.get("matricula") or "").strip()
    local_servico = _normalize_text(payload.get("local_servico") or metadata.get("local_servico"))
    observacao = _normalize_text(payload.get("observacao") or metadata.get("observacao"))

    query = db.session.query(Saida).filter(Saida.codigo_item == movement.product_id)
    if matricula:
        query = query.filter(Saida.matricula == matricula)
    query = query.filter(
        Saida.data_saida >= target_time - timedelta(minutes=2),
        Saida.data_saida <= target_time + timedelta(minutes=2),
    )

    candidates: list[tuple[float, int, LinkMatch]] = []
    for saida in query.all():
        saida_local = _normalize_text(saida.local_servico)
        if local_servico and local_servico not in saida_local and saida_local not in local_servico:
            continue

        matched_quantity = _safe_float(saida.quantidade)
        quantity_matches = abs(matched_quantity - desired_quantity) <= 1e-6
        central_kits_override = (
            not quantity_matches
            and "CENTRAL DE KITS" in local_servico
            and "ASSOCIADO VIA CENTRAL DE KITS" in observacao
            and abs(matched_quantity - 1.0) <= 1e-6
        )
        if not quantity_matches and not central_kits_override:
            continue

        match_strategy = strategy
        if central_kits_override:
            match_strategy = "central_kits_single_saida"
        delta_seconds = abs((saida.data_saida - target_time).total_seconds())
        if not quantity_matches and central_kits_override:
            desired_quantity = matched_quantity
        candidates.append(
            (
                delta_seconds,
                int(saida.id_saida),
                LinkMatch(
                    movement_id=int(movement.id),
                    saida_id=int(saida.id_saida),
                    product_id=str(movement.product_id or ""),
                    reference_type=str(movement.reference_type or ""),
                    target_time=target_time,
                    desired_quantity=desired_quantity,
                    matched_quantity=matched_quantity,
                    delta_seconds=delta_seconds,
                    strategy=match_strategy,
                ),
            )
        )
    return sorted(candidates, key=lambda row: (row[0], row[1]))


def collect_link_matches() -> tuple[list[LinkMatch], list[StockMovement]]:
    movements = (
        db.session.query(StockMovement)
        .filter(StockMovement.movement_type == "saida")
        .filter(StockMovement.reference_id.is_(None))
        .filter(StockMovement.reference_type.in_(ORPHAN_REFERENCE_TYPES))
        .order_by(StockMovement.id.asc())
        .all()
    )

    candidate_map: dict[int, list[tuple[float, int, LinkMatch]]] = {
        int(movement.id): _candidate_rows_for_movement(movement)
        for movement in movements
    }
    sorted_movements = sorted(
        movements,
        key=lambda movement: (
            len(candidate_map[int(movement.id)]) if candidate_map[int(movement.id)] else 10_000,
            candidate_map[int(movement.id)][0][0] if candidate_map[int(movement.id)] else 10_000.0,
            int(movement.id),
        ),
    )

    used_saida_ids: set[int] = set()
    resolved: list[LinkMatch] = []
    unresolved: list[StockMovement] = []
    for movement in sorted_movements:
        candidates = candidate_map[int(movement.id)]
        chosen = next((match for _delta, saida_id, match in candidates if saida_id not in used_saida_ids), None)
        if chosen is None:
            unresolved.append(movement)
            continue
        used_saida_ids.add(chosen.saida_id)
        if len(candidates) > 1 and chosen.strategy != "central_kits_single_saida":
            chosen.strategy = f"{chosen.strategy}+nearest_timestamp"
        resolved.append(chosen)
    resolved.sort(key=lambda match: match.movement_id)
    unresolved.sort(key=lambda movement: int(movement.id))
    return resolved, unresolved


def apply_link_matches(matches: list[LinkMatch]) -> None:
    applied_at = datetime.now(timezone.utc).isoformat()
    for match in matches:
        movement = db.session.get(StockMovement, match.movement_id)
        if movement is None or movement.reference_id not in (None, ""):
            continue
        metadata = dict(movement.metadata_json or {})
        metadata["legacy_link_backfill"] = {
            "saida_id": str(match.saida_id),
            "applied_at": applied_at,
            "strategy": match.strategy,
            "target_time": match.target_time.isoformat(),
            "desired_quantity": match.desired_quantity,
            "matched_quantity": match.matched_quantity,
            "delta_seconds": match.delta_seconds,
        }
        movement.reference_id = str(match.saida_id)
        movement.metadata_json = metadata
    db.session.flush()


def _parse_fractional_observation(observacao: str | None) -> tuple[float, str] | None:
    text = str(observacao or "").strip()
    if not text:
        return None
    matched = FRACTIONAL_PATTERN.search(text)
    if not matched:
        matched = FRACTIONAL_LEGACY_RECORDED_PATTERN.search(text)
    if not matched:
        return None
    quantity = _safe_float(matched.group(1).replace(",", "."))
    unit_raw = matched.group(2).strip().lower()
    if unit_raw.startswith("kg") or unit_raw.startswith("quilo"):
        return quantity, "kg"
    return quantity, "l"


def collect_fractional_repairs() -> tuple[list[FractionalRepair], list[Saida]]:
    rows = (
        db.session.query(Saida)
        .filter(func.lower(func.coalesce(Saida.observacao, "")).like("%fracionada%"))
        .filter(
            or_(
                Saida.usou_fracao.is_(False),
                Saida.usou_fracao.is_(None),
                Saida.quantidade_retirada_em_litros.is_(None),
                Saida.quantidade_retirada_em_quilos.is_(None),
            )
        )
        .order_by(Saida.id_saida.asc())
        .all()
    )

    repairs: list[FractionalRepair] = []
    unresolved: list[Saida] = []
    for saida in rows:
        parsed = _parse_fractional_observation(saida.observacao)
        if parsed is None:
            unresolved.append(saida)
            continue
        quantity, unit = parsed
        relevant_value = _safe_float(saida.quantidade_retirada_em_quilos if unit == "kg" else saida.quantidade_retirada_em_litros)
        if bool(getattr(saida, "usou_fracao", False)) and relevant_value > 0:
            continue
        repairs.append(
            FractionalRepair(
                saida_id=int(saida.id_saida),
                product_id=str(saida.codigo_item or ""),
                quantity=quantity,
                unit=unit,
                observacao=str(saida.observacao or ""),
            )
        )
    return repairs, unresolved


def apply_fractional_repairs(repairs: list[FractionalRepair]) -> None:
    for repair in repairs:
        saida = db.session.get(Saida, repair.saida_id)
        if saida is None:
            continue
        saida.usou_fracao = True
        if repair.unit == "kg" and _safe_float(saida.quantidade_retirada_em_quilos) <= 0:
            saida.quantidade_retirada_em_quilos = repair.quantity
        if repair.unit == "l" and _safe_float(saida.quantidade_retirada_em_litros) <= 0:
            saida.quantidade_retirada_em_litros = repair.quantity
    db.session.flush()


def collect_balance_repairs(*, tolerance: float) -> list[BalanceRepair]:
    ledger_totals = dict(
        db.session.query(
            StockMovement.product_id,
            func.coalesce(func.sum(StockMovement.quantity_base), 0.0),
        )
        .group_by(StockMovement.product_id)
        .all()
    )
    balance_totals = {
        str(balance.product_id): _safe_float(balance.quantity_base)
        for balance in StockBalance.query.all()
        if balance.product_id
    }
    descriptions = {
        str(code): description or str(code)
        for code, description in db.session.query(Item.codigo_item, Item.descricao).all()
    }

    repairs: list[BalanceRepair] = []
    for product_id in sorted(set(ledger_totals) | set(balance_totals)):
        if not product_id:
            continue
        ledger_total = _safe_float(ledger_totals.get(product_id))
        stock_balance = _safe_float(balance_totals.get(product_id))
        delta = stock_balance - ledger_total
        if abs(delta) <= tolerance:
            continue
        repairs.append(
            BalanceRepair(
                product_id=str(product_id),
                description=str(descriptions.get(str(product_id), product_id)),
                stock_balance=stock_balance,
                ledger_total=ledger_total,
                delta=delta,
            )
        )
    return repairs


def apply_balance_repairs(repairs: list[BalanceRepair]) -> None:
    product_ids = [repair.product_id for repair in repairs]
    if not product_ids:
        return
    ledger_backfill_service.rebuild_balances_for_products(product_ids)
    for product_id in product_ids:
        item = db.session.get(Item, product_id)
        if item is None:
            continue
        if _safe_float(inventory_service._package_factor_for_operational_policy(item)) > 0:
            inventory_engine.sync_packaging_read_model(product_id=product_id, commit=False)
    db.session.flush()


def _print_section(title: str) -> None:
    print("\n" + "=" * 92)
    print(title)
    print("=" * 92)


def _print_link_summary(matches: list[LinkMatch], unresolved: list[StockMovement], limit: int) -> None:
    _print_section("1. Backfill Saida x StockMovement")
    print(f"Matches conservadores: {len(matches)}")
    print(f"Sem match seguro: {len(unresolved)}")
    for match in matches[:limit]:
        print(
            f"- movement={match.movement_id} -> saida={match.saida_id} | item={match.product_id} | "
            f"ref={match.reference_type} | qtd={match.desired_quantity:g}/{match.matched_quantity:g} | "
            f"delta={match.delta_seconds:.6f}s | estrategia={match.strategy}"
        )
    for movement in unresolved[:limit]:
        print(
            f"- sem_match movement={movement.id} | item={movement.product_id} | ref={movement.reference_type} | "
            f"created_at={movement.created_at}"
        )


def _print_fractional_summary(repairs: list[FractionalRepair], unresolved: list[Saida], limit: int) -> None:
    _print_section("2. Saídas fracionadas legadas")
    print(f"Linhas reparáveis: {len(repairs)}")
    print(f"Linhas sem parser: {len(unresolved)}")
    for repair in repairs[:limit]:
        print(
            f"- saida={repair.saida_id} | item={repair.product_id} | qtd={repair.quantity:g} {repair.unit} | obs={repair.observacao!r}"
        )
    for saida in unresolved[:limit]:
        print(f"- sem_parser saida={saida.id_saida} | item={saida.codigo_item} | obs={saida.observacao!r}")


def _print_balance_summary(repairs: list[BalanceRepair], limit: int) -> None:
    _print_section("3. Divergências de saldo")
    print(f"Itens com divergência: {len(repairs)}")
    for repair in repairs[:limit]:
        print(
            f"- {repair.product_id} | {repair.description} | stock_balance={repair.stock_balance:g} | "
            f"ledger={repair.ledger_total:g} | delta={repair.delta:g}"
        )


def main() -> int:
    args = _parse_args()
    apply_links = bool(args.apply_all or args.apply_links)
    apply_fractional = bool(args.apply_all or args.apply_fractional)
    apply_balances = bool(args.apply_all or args.apply_balances)

    app = create_app()
    with app.app_context():
        matches, unresolved_links = collect_link_matches()
        fractional_repairs, unresolved_fractional = collect_fractional_repairs()
        balance_repairs = collect_balance_repairs(tolerance=max(_safe_float(args.tolerance), 0.0))

        _print_link_summary(matches, unresolved_links, max(int(args.limit or 0), 0))
        _print_fractional_summary(fractional_repairs, unresolved_fractional, max(int(args.limit or 0), 0))
        _print_balance_summary(balance_repairs, max(int(args.limit or 0), 0))

        if not any((apply_links, apply_fractional, apply_balances)):
            print("\nExecução em dry-run. Use --apply-links, --apply-fractional, --apply-balances ou --apply-all para gravar.")
            return 0

        if apply_links:
            apply_link_matches(matches)
        if apply_fractional:
            apply_fractional_repairs(fractional_repairs)
        if apply_balances:
            apply_balance_repairs(balance_repairs)
        db.session.commit()

        print("\nAlterações aplicadas. Reauditando estado final...\n")
        refreshed_matches, refreshed_unresolved_links = collect_link_matches()
        refreshed_fractional, refreshed_unresolved_fractional = collect_fractional_repairs()
        refreshed_balances = collect_balance_repairs(tolerance=max(_safe_float(args.tolerance), 0.0))
        _print_link_summary(refreshed_matches, refreshed_unresolved_links, max(int(args.limit or 0), 0))
        _print_fractional_summary(refreshed_fractional, refreshed_unresolved_fractional, max(int(args.limit or 0), 0))
        _print_balance_summary(refreshed_balances, max(int(args.limit or 0), 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())