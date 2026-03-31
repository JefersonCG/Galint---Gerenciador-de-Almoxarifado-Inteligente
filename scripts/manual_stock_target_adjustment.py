from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from app import create_app
from galint_flask.extensions import db
from galint_flask.models import InventarioEvento, Item, StockBalance, StockMovement, stock_balance_supports_read_model_ready
from galint_flask.services.embalagem_service import EmbalagemService
from galint_flask.services.ledger_reconciliation import ReconciliationResult, ledger_reconciliation_service
from galint_flask.services.legacy_stock_normalizer import resolve_canonical_unit

TOLERANCE = 1e-6


@dataclass(slots=True)
class TargetBalance:
    total: float
    embalagens: float | None
    soltas: float | None
    fator_embalagem: float | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aplica correcao manual absoluta de estoque alinhando legado, ledger e saldo fisico."
    )
    parser.add_argument("--codigo", required=True, help="Codigo do item")
    parser.add_argument("--saldo-total", type=float, help="Saldo alvo total na unidade base do item")
    parser.add_argument("--embalagens", type=float, help="Quantidade alvo de embalagens fechadas")
    parser.add_argument("--soltas", type=float, default=0.0, help="Quantidade alvo de unidades/litros/kg/metros soltos")
    parser.add_argument("--matricula", help="Matricula do responsavel pelo ajuste")
    parser.add_argument(
        "--observacao",
        default="Ajuste manual assistido de saldo alvo",
        help="Texto livre para auditoria",
    )
    parser.add_argument("--apply", action="store_true", help="Executa a correcao no banco")
    return parser.parse_args()


def _resolve_target(item: Item, args: argparse.Namespace) -> TargetBalance:
    using_total = args.saldo_total is not None
    using_packaging = args.embalagens is not None

    if using_total == using_packaging:
        raise ValueError("Informe exatamente um modo: --saldo-total ou --embalagens")

    if using_total:
        total = float(args.saldo_total)
        if total < 0:
            raise ValueError("Saldo alvo nao pode ser negativo")
        if not EmbalagemService.tem_embalagem(item):
            return TargetBalance(total=total, embalagens=None, soltas=None, fator_embalagem=None)

        fator = float(item.unidades_por_embalagem or 0)
        if fator <= 0:
            raise ValueError("Item com embalagem sem unidades_por_embalagem valido")
        embalagens = float(int(total // fator))
        soltas = round(total - (embalagens * fator), 6)
        return TargetBalance(total=total, embalagens=embalagens, soltas=soltas, fator_embalagem=fator)

    if not EmbalagemService.tem_embalagem(item):
        raise ValueError("--embalagens so pode ser usado para itens com sistema de embalagem")

    fator = float(item.unidades_por_embalagem or 0)
    if fator <= 0:
        raise ValueError("Item com embalagem sem unidades_por_embalagem valido")

    embalagens = float(args.embalagens)
    soltas = float(args.soltas or 0.0)
    if embalagens < 0 or soltas < 0:
        raise ValueError("Saldo alvo nao pode ser negativo")
    if soltas >= fator and abs(soltas - fator) > TOLERANCE:
        raise ValueError("Para itens com embalagem, --soltas deve ser menor que unidades_por_embalagem")

    total = round((embalagens * fator) + soltas, 6)
    return TargetBalance(total=total, embalagens=embalagens, soltas=soltas, fator_embalagem=fator)


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    if abs(value - round(value)) <= TOLERANCE:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _describe_packaging(item: Item, target: TargetBalance) -> str:
    if target.embalagens is None:
        return "nao se aplica"
    tipo = (item.tipo_embalagem_novo or "embalagem").strip().lower() or "embalagem"
    unidade_solta = (resolve_canonical_unit(item) or item.unidade or "un").strip().lower()
    return f"{_fmt(target.embalagens)} {tipo}(s) + {_fmt(target.soltas or 0.0)} {unidade_solta}"


def _create_legacy_event(
    item: Item,
    *,
    matricula: str,
    current_legacy: float,
    target_total: float,
    legacy_delta: float,
    audit_tag: str,
    observacao: str,
) -> InventarioEvento | None:
    if abs(legacy_delta) <= TOLERANCE:
        return None

    descricao = (
        f"{observacao} | alvo={_fmt(target_total)} | legado: de {_fmt(current_legacy)} para {_fmt(target_total)} | audit={audit_tag}"
    )
    evento = InventarioEvento(
        codigo_item=item.codigo_item,
        matricula=matricula,
        tipo="ajuste_manual_assistido",
        quantidade=float(legacy_delta),
        descricao=descricao,
        data_evento=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.session.add(evento)
    db.session.flush()
    return evento


def _create_ledger_adjustment(
    item: Item,
    *,
    current_ledger: float,
    target_total: float,
    ledger_delta: float,
    audit_tag: str,
    observacao: str,
    event_id: int | None,
) -> StockMovement | None:
    if abs(ledger_delta) <= TOLERANCE:
        return None

    movement = StockMovement(
        product_id=item.codigo_item,
        movement_type="ajuste",
        quantity_base=float(ledger_delta),
        unit_base=(resolve_canonical_unit(item) or (item.unidade or "").strip().lower() or "un"),
        reference_type="ajuste_manual_assistido",
        reference_id=audit_tag,
        metadata_json={
            "source": "manual_stock_target_adjustment",
            "audit_tag": audit_tag,
            "legacy_event_id": event_id,
            "ledger_before": float(current_ledger),
            "ledger_target": float(target_total),
            "observacao": observacao,
        },
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.session.add(movement)
    db.session.flush()
    return movement


def _ensure_balance(item: Item, *, target_total: float) -> StockBalance:
    balance = db.session.get(StockBalance, item.codigo_item)
    if balance is None:
        balance = StockBalance()
        balance.product_id = item.codigo_item
        db.session.add(balance)
    balance.quantity_base = float(target_total)
    if stock_balance_supports_read_model_ready() and hasattr(balance, "read_model_ready"):
        balance.read_model_ready = False
    db.session.flush()
    return balance


def _sync_packaging_fields(item: Item, target: TargetBalance) -> None:
    if target.embalagens is None:
        return
    item.estoque_embalagens = float(target.embalagens)
    item.estoque_unidades_soltas = float(target.soltas or 0.0)
    db.session.flush()


def _print_snapshot(label: str, item: Item, reconciliation: ReconciliationResult, target: TargetBalance | None = None) -> None:
    print(label)
    print(f"- codigo: {item.codigo_item}")
    print(f"- descricao: {item.descricao}")
    print(f"- legado: {_fmt(reconciliation.legacy_balance)}")
    print(f"- ledger: {_fmt(reconciliation.ledger_balance)}")
    print(f"- cache: {_fmt(reconciliation.stock_balance)}")
    print(f"- classificacao: {reconciliation.classification}")
    if EmbalagemService.tem_embalagem(item):
        print(
            f"- fisico: {_fmt(float(item.estoque_embalagens or 0.0))} emb + {_fmt(float(item.estoque_unidades_soltas or 0.0))} soltas"
        )
        try:
            print(f"- fisico total: {_fmt(float(EmbalagemService.calcular_estoque_total(item) or 0.0))}")
        except Exception:
            pass
    if target is not None:
        print(f"- alvo total: {_fmt(target.total)}")
        print(f"- alvo fisico: {_describe_packaging(item, target)}")


def main() -> int:
    args = _parse_args()
    app = create_app()

    with app.app_context():
        item = db.session.get(Item, (args.codigo or "").strip())
        if item is None:
            raise SystemExit("Item nao encontrado")

        target = _resolve_target(item, args)
        before = ledger_reconciliation_service.reconcile_product(item.codigo_item)
        legacy_delta = round(target.total - float(before.legacy_balance or 0.0), 6)
        ledger_delta = round(target.total - float(before.ledger_balance or 0.0), 6)

        _print_snapshot("ESTADO ATUAL", item, before, target)
        print(f"- delta legado necessario: {_fmt(legacy_delta)}")
        print(f"- delta ledger necessario: {_fmt(ledger_delta)}")

        if not args.apply:
            print("\nPreview apenas. Use --apply para gravar.")
            return 0

        matricula = (args.matricula or "").strip()
        if not matricula:
            raise SystemExit("Informe --matricula para aplicar a correcao")

        audit_tag = f"manual-target-{item.codigo_item}-{uuid4().hex[:10]}"
        event = _create_legacy_event(
            item,
            matricula=matricula,
            current_legacy=float(before.legacy_balance or 0.0),
            target_total=target.total,
            legacy_delta=legacy_delta,
            audit_tag=audit_tag,
            observacao=str(args.observacao or "").strip() or "Ajuste manual assistido de saldo alvo",
        )
        movement = _create_ledger_adjustment(
            item,
            current_ledger=float(before.ledger_balance or 0.0),
            target_total=target.total,
            ledger_delta=ledger_delta,
            audit_tag=audit_tag,
            observacao=str(args.observacao or "").strip() or "Ajuste manual assistido de saldo alvo",
            event_id=event.id_evento if event is not None else None,
        )
        balance = _ensure_balance(item, target_total=target.total)
        _sync_packaging_fields(item, target)

        after = ledger_reconciliation_service.reconcile_product(item.codigo_item)
        if stock_balance_supports_read_model_ready() and hasattr(balance, "read_model_ready"):
            balance.read_model_ready = after.classification in {"divergencia_zero", "divergencia_explicavel"}

        db.session.commit()

        refreshed_item = db.session.get(Item, item.codigo_item)
        refreshed = ledger_reconciliation_service.reconcile_product(item.codigo_item)
        print()
        _print_snapshot("ESTADO APOS AJUSTE", refreshed_item, refreshed)
        print(f"- evento legado criado: {event.id_evento if event is not None else 'nao'}")
        print(f"- movimento ledger criado: {movement.id if movement is not None else 'nao'}")
        print(f"- read_model_ready: {getattr(balance, 'read_model_ready', None)}")
        print(f"- audit_tag: {audit_tag}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())