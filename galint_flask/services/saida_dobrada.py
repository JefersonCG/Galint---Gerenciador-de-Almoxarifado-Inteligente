"""Saída contada duas vezes no razão do estoque (achado de 26/11/2026).

Como apareceu: a NF 28498 (1 FARDO de BAMBU RACHADO = 24 un) ficou em "Erro: Saldo insuficiente". O bambu estava com
saldo -432: as saídas de 24/04 (288 un) e 11/05 (144 un) estavam no razão duas vezes. Uma pela saída múltipla
(inventory_engine), outra pela reconstrução do razão a partir da tabela antiga de saídas (metadata source =
"ledger_backfill"), que não reconheceu a primeira. A reconstrução gravou o horário local e o motor o UTC, por isso a
gêmea fica 3 horas antes ou depois, com a mesma quantidade e, quando há, o mesmo número de saída (reference_id).

Na medição de 26/11/2026: 1.821 saídas assim em 431 itens. Em parte deles a conferência física já acertou o saldo com
um ajuste DEPOIS da duplicada; ali a duplicada está compensada e não se mexe. As que nenhum ajuste compensou podem ser
corrigidas à mão, item por item, pela pessoa que conhece o estoque (pedido do usuário: "mais acessibilidade de correção
manual"). Uma contagem que confirmou o saldo sem mudar nada não deixa movimento, então o sistema não decide sozinho.

A correção não apaga nada: grava um ajuste de +quantidade com reference_type "correcao_saida_dobrada" e reference_id
igual ao movimento duplicado. Fica no histórico do item, e o mesmo par nunca é corrigido duas vezes.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from ..extensions import db
from ..models import Item, StockMovement

REFERENCIA = "correcao_saida_dobrada"  # stock_movements.reference_type (até 50)
# operation_logs.source tem 20 caracteres. Em 27/11/2026 o primeiro CORRIGIR (bambu) falhou com
# StringDataRightTruncation porque a origem era "correcao_saida_dobrada" (22); o teste em SQLite não pegou.
FONTE = "saida_dobrada"
_FUSO_S = 3 * 3600
_JANELA_S = 5.0


def _fonte(movimento: StockMovement) -> str:
    metadata = movimento.metadata_json if isinstance(movimento.metadata_json, dict) else {}
    return str(metadata.get("source") or "").strip().lower()


def _perto(a: datetime | None, b: datetime | None) -> bool:
    if a is None or b is None:
        return False
    diferenca = (a - b).total_seconds()
    return abs(diferenca) <= _JANELA_S or abs(abs(diferenca) - _FUSO_S) <= _JANELA_S


def _local(movimento: StockMovement) -> str:
    metadata = movimento.metadata_json if isinstance(movimento.metadata_json, dict) else {}
    return str(metadata.get("local_servico") or "").strip()


def _pares(movimentos: list[StockMovement]) -> list[dict[str, Any]]:
    """Pares (duplicada da reconstrução, saída original) de um item, com o que cada par pede."""
    saidas = [m for m in movimentos if m.movement_type == "saida" and float(m.quantity_base or 0) < 0]
    reconstruidas = [m for m in saidas if _fonte(m) == "ledger_backfill"]
    if not reconstruidas:
        return []
    originais = [m for m in saidas if _fonte(m) != "ledger_backfill"]
    corrigidas = {str(m.reference_id) for m in movimentos if m.reference_type == REFERENCIA and m.reference_id}
    ajustes = [m.created_at for m in movimentos if m.movement_type == "ajuste" and m.reference_type != REFERENCIA and m.created_at]
    ultimo_ajuste = max(ajustes) if ajustes else None

    usados: set[int] = set()
    pares: list[dict[str, Any]] = []
    for duplicada in sorted(reconstruidas, key=lambda m: m.id):
        quantidade = float(duplicada.quantity_base)
        gemea = None
        for original in originais:
            if original.id in usados or abs(float(original.quantity_base) - quantidade) > 1e-4:
                continue
            mesmo_numero = bool(original.reference_id) and str(original.reference_id) == str(duplicada.reference_id or "")
            if mesmo_numero or _perto(original.created_at, duplicada.created_at):
                gemea = original
                break
        if gemea is None:
            continue
        usados.add(gemea.id)
        momento = max(filter(None, [duplicada.created_at, gemea.created_at]))
        pares.append({
            "duplicada_id": duplicada.id,
            "original_id": gemea.id,
            "quantidade": round(-quantidade, 6),
            "unidade": duplicada.unit_base or gemea.unit_base or "un",
            "data": (gemea.created_at or duplicada.created_at).isoformat() if (gemea.created_at or duplicada.created_at) else None,
            "local": _local(duplicada) or _local(gemea),
            "corrigida": str(duplicada.id) in corrigidas,
            "compensada": bool(ultimo_ajuste and ultimo_ajuste > momento),
        })
    return pares


def _resumo(pares: list[dict[str, Any]]) -> dict[str, Any] | None:
    abertas = [p for p in pares if not p["corrigida"] and not p["compensada"]]
    if not abertas:
        return None
    return {
        "pares": len(abertas),
        "quantidade": round(sum(p["quantidade"] for p in abertas), 6),
        "unidade": abertas[0]["unidade"],
        "saidas": [{"data": p["data"], "quantidade": p["quantidade"], "local": p["local"]} for p in abertas],
    }


def resumo_por_item(codigos: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    """{codigo: {pares, quantidade, unidade, saidas}} só dos itens com saída em dobro ainda aberta."""
    filtro = None if codigos is None else sorted({str(c) for c in codigos if c})
    if filtro is not None and not filtro:
        return {}
    candidatos = db.session.query(StockMovement.product_id).filter(
        StockMovement.movement_type == "saida",
        StockMovement.reference_type == "saida",
    )
    if filtro is not None:
        candidatos = candidatos.filter(StockMovement.product_id.in_(filtro))
    produtos = {row[0] for row in candidatos.distinct().all()}
    if not produtos:
        return {}
    movimentos = (
        StockMovement.query
        .filter(StockMovement.product_id.in_(sorted(produtos)))
        .filter(StockMovement.movement_type.in_(("saida", "ajuste")))
        .order_by(StockMovement.id)
        .all()
    )
    por_item: dict[str, list[StockMovement]] = defaultdict(list)
    for movimento in movimentos:
        por_item[movimento.product_id].append(movimento)
    resultado: dict[str, dict[str, Any]] = {}
    for codigo, lista in por_item.items():
        resumo = _resumo(_pares(lista))
        if resumo:
            resultado[codigo] = resumo
    return resultado


def corrigir_item(codigo: str, *, matricula: str | None) -> dict[str, Any]:
    """Devolve ao saldo cada saída em dobro ainda aberta do item. Erro se não houver nenhuma."""
    from .balance_provider import balance_provider
    from .inventory import inventory_service
    from .inventory_engine import inventory_engine

    item = db.session.get(Item, codigo)
    if item is None:
        raise ValueError("Item não encontrado.")
    movimentos = StockMovement.query.filter(StockMovement.product_id == codigo).order_by(StockMovement.id).all()
    abertas = [p for p in _pares(movimentos) if not p["corrigida"] and not p["compensada"]]
    if not abertas:
        raise ValueError("Este item não tem saída contada duas vezes para corrigir.")

    saldo_antes = float(balance_provider.get_balance(codigo).quantity_base)
    for par in abertas:
        data = (par["data"] or "")[:10]
        data_br = f"{data[8:10]}/{data[5:7]}/{data[:4]}" if len(data) == 10 else ""
        inventory_engine.register_adjustment(
            product_id=codigo,
            quantity=par["quantidade"],
            from_unit=par["unidade"],
            metadata={
                "source": FONTE,
                "channel": "estoque",
                "reference_type": REFERENCIA,
                "reference_id": str(par["duplicada_id"]),
                "saida_original_id": par["original_id"],
                "user_id": matricula,
                "matricula": matricula,
                "observacao": f"Saída de {data_br} contada duas vezes".strip(),
            },
            commit=False,
            write_audit=True,
        )
    db.session.commit()
    try:
        inventory_engine.sync_packaging_read_model(product_id=codigo, commit=True)
    except Exception:
        db.session.rollback()
    inventory_service.invalidate_realtime_views()
    saldo_depois = float(balance_provider.get_balance(codigo).quantity_base)
    return {
        "codigo": codigo,
        "corrigidas": len(abertas),
        "quantidade": round(sum(p["quantidade"] for p in abertas), 6),
        "saldo_antes": saldo_antes,
        "saldo_depois": saldo_depois,
    }
