"""Para onde foram os itens de uma NF (pedido do usuário em 25/11/2026).

Caso do usuário: a NF 77777 estava no GALINT só por uma cópia de xerox; agora chegou o PDF (vira a NF
física pelo Ler NF) e os itens dela já saíram há tempo. Ele quer ver, na NF, a lista completa: cada
retirada que gastou o que a NF trouxe, com data, quem levou, local e há quantos dias.

A saída não guarda de qual NF veio, então a conta é a do primeiro que entra, primeiro que sai, sobre o
razão de estoque (stock_movements, com sinal):
- o saldo que já existia antes da entrada da NF sai primeiro;
- depois, cada saída (retirada, conferência ou ajuste para menos) gasta a NF até acabar;
- entrada ou ajuste para mais depois da NF é estoque mais novo e não mexe na NF;
- devolução volta para a NF o que saiu dela por último (ferramenta que retorna, material devolvido).
O que sobra da NF nunca passa do saldo atual do item.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..extensions import db
from ..models import DocumentoEntradaEstoqueItem, InventarioEvento, Item, Saida, StockMovement, Usuario
from ..utils.time_service import TimeService

EPS = 1e-6
SAIDA_REFS = {"saida", "movements_saida_multipla", "api_mobile_retirar", "api_mobile_retirar_multipla"}
UNIT_SHORT = {"quilo": "kg", "litro": "L", "metro": "m", "unidade": "un", "par": "par", "grama": "g", "mililitro": "mL"}


def _label(movement: StockMovement) -> str:
    reference = movement.reference_type or ""
    if movement.movement_type == "devolucao":
        return "Devolução"
    if reference in SAIDA_REFS or reference == "legacy_movimento":
        return "Retirada"
    if reference == "inventario_evento":
        return "Conferência"
    if reference == "entrada_documento_item_exclusao":
        return "NF excluída"
    return "Ajuste"


def _entry_movement(line: DocumentoEntradaEstoqueItem) -> StockMovement | None:
    movement = db.session.get(StockMovement, line.stock_movement_id) if line.stock_movement_id else None
    if movement is not None and float(movement.quantity_base or 0) > 0:
        return movement
    return (
        StockMovement.query.filter_by(reference_type="entrada_documento_item", reference_id=str(line.id_documento_item))
        .filter(StockMovement.quantity_base > 0)
        .order_by(StockMovement.id)
        .first()
    )


def _who_and_where(movements: list[StockMovement]) -> dict[int, tuple[str | None, str | None]]:
    """Quem levou e o local de cada movimento (retirada pela saída; conferência pelo evento)."""
    saida_ids = {int(m.reference_id) for m in movements if (m.reference_type or "") in SAIDA_REFS and str(m.reference_id or "").isdigit()}
    event_ids = {int(m.reference_id) for m in movements if m.reference_type == "inventario_evento" and str(m.reference_id or "").isdigit()}
    saidas = {row.id_saida: row for row in Saida.query.filter(Saida.id_saida.in_(saida_ids)).all()} if saida_ids else {}
    events = {row.id_evento: row for row in InventarioEvento.query.filter(InventarioEvento.id_evento.in_(event_ids)).all()} if event_ids else {}
    raw: dict[int, tuple[str | None, str | None]] = {}
    for movement in movements:
        reference_id = int(movement.reference_id) if str(movement.reference_id or "").isdigit() else None
        metadata = movement.metadata_json if isinstance(movement.metadata_json, dict) else {}
        legacy = metadata.get("legacy_payload") if isinstance(metadata.get("legacy_payload"), dict) else {}
        matricula, local = None, None
        if (movement.reference_type or "") in SAIDA_REFS and reference_id in saidas:
            matricula, local = saidas[reference_id].matricula, saidas[reference_id].local_servico
        elif movement.reference_type == "inventario_evento" and reference_id in events:
            matricula = events[reference_id].matricula
        matricula = matricula or legacy.get("matricula") or metadata.get("matricula") or metadata.get("user_id")
        local = local or legacy.get("local_servico")
        raw[movement.id] = (str(matricula) if matricula else None, local)
    matriculas = {matricula for matricula, _ in raw.values() if matricula}
    names = {row.matricula: row.nome for row in Usuario.query.filter(Usuario.matricula.in_(matriculas)).all()} if matriculas else {}
    return {movement_id: (names.get(matricula, matricula) if matricula else None, local) for movement_id, (matricula, local) in raw.items()}


def rastro_da_linha(line: DocumentoEntradaEstoqueItem, *, hoje: datetime | None = None) -> dict[str, Any]:
    item = line.item or db.session.get(Item, line.codigo_item)
    unidade = UNIT_SHORT.get(str(getattr(item, "unidade", "") or "").strip().lower(), str(getattr(item, "unidade", "") or "").lower())
    fator = None
    if line.quantidade and line.quantidade_base and line.unidade_quantidade and float(line.quantidade_base) / float(line.quantidade) > 1 + EPS:
        fator = float(line.quantidade_base) / float(line.quantidade)
    result: dict[str, Any] = {
        "codigo": line.codigo_item,
        "descricao": getattr(item, "descricao", None) or line.codigo_item,
        "unidade": unidade,
        "fator": fator,
        "unidade_doc": line.unidade_quantidade if fator else None,
        "linhas": [],
    }
    entry = _entry_movement(line)
    if entry is None:
        result.update(sem_entrada=True, entrou=float(line.quantidade_base or line.quantidade or 0), restante=None, saiu_tudo=False, ultima_dias=None, entrou_em=None)
        return result

    movements = StockMovement.query.filter_by(product_id=line.codigo_item).order_by(StockMovement.created_at, StockMovement.id).all()
    entry_key = (entry.created_at, entry.id)
    older = max(0.0, sum(float(m.quantity_base or 0) for m in movements if (m.created_at, m.id) < entry_key))
    balance = sum(float(m.quantity_base or 0) for m in movements)
    total = float(entry.quantity_base)
    remaining = total
    taken: list[tuple[StockMovement, float]] = []
    for movement in movements:
        if (movement.created_at, movement.id) <= entry_key:
            continue
        quantity = float(movement.quantity_base or 0)
        if quantity < 0:
            out = -quantity
            from_older = min(older, out)
            older -= from_older
            out -= from_older
            take = min(remaining, out)
            if take > EPS:
                remaining -= take
                taken.append((movement, take))
        elif movement.movement_type == "devolucao":
            back = min(quantity, total - remaining)
            if back > EPS:
                remaining += back
                taken.append((movement, -back))
    remaining = max(0.0, min(remaining, balance))

    today = (hoje or TimeService.now_db()).date()
    places = _who_and_where([movement for movement, _ in taken])
    for movement, quantity in taken:
        who, local = places.get(movement.id, (None, None))
        result["linhas"].append({
            "data": movement.created_at,
            "dias": (today - movement.created_at.date()).days,
            "tipo": _label(movement),
            "quem": who,
            "local": local,
            "quantidade": quantity,
        })
    saidas = [row for row in result["linhas"] if row["quantidade"] > 0]
    result.update(
        sem_entrada=False,
        entrou=total,
        entrou_em=entry.created_at,
        restante=remaining,
        saiu_tudo=remaining <= EPS,
        ultima_dias=saidas[-1]["dias"] if saidas else None,
    )
    return result


def rastro_do_documento(documento_id: int, *, hoje: datetime | None = None) -> list[dict[str, Any]]:
    lines = (
        DocumentoEntradaEstoqueItem.query.filter_by(documento_id=documento_id)
        .order_by(DocumentoEntradaEstoqueItem.id_documento_item)
        .all()
    )
    return [rastro_da_linha(line, hoje=hoje) for line in lines]
