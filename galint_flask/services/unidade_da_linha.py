"""Unidade da linha do documento fiscal escolhida à mão (26/11/2026).

Pedido do usuário, com a NF 28498 em "Erro" (1 FARDO de BAMBU com 24 unidades): "nem me deu opção de colocar a unidade
dinâmica (...) deixar o sistema mais preciso e com mais acessibilidade de correção manual". O "Corrigir" do documento
deixava mudar quantidade e valores, mas não a unidade: a linha ficava presa à unidade que a leitura escolheu.

Aqui ficam as unidades do item, cada uma com quanto vale na unidade base ("FARDO = 24 UN"), e a troca da unidade da
linha. A troca recalcula a quantidade na unidade base e o preço pela mesma conta de quando a linha foi lançada
(_normalize_financial_line). A entrada no estoque continua usando a quantidade e a unidade da linha.
"""
from __future__ import annotations

from typing import Any

from ..models import DocumentoEntradaEstoqueItem, Item
from .unit_conversion_engine import unit_conversion_engine

_CURTA = {"unidade": "UN", "un": "UN", "quilo": "KG", "kg": "KG", "litro": "L", "l": "L", "metro": "M", "m": "M"}


def _fator(item: Item, unidade: str) -> float | None:
    try:
        return float(unit_conversion_engine.convert_item_to_base(item, 1, unidade).quantity_base)
    except Exception:
        return None


def _base_curta(item: Item) -> str:
    for unit in item.product_units or []:
        if unit.is_base and unit.active and unit.unit_code:
            codigo = str(unit.unit_code).strip().lower()
            return _CURTA.get(codigo, str(unit.unit_label or unit.unit_code).upper())
    codigo = str(item.unidade or "").strip().lower()
    return _CURTA.get(codigo, codigo.upper() or "UN")


def opcoes_de_unidade(item: Item | None) -> list[dict[str, Any]]:
    """Unidades ativas do item: [{codigo, rotulo, fator, base}], a base primeiro. Vazia se o item só tem uma."""
    if item is None:
        return []
    opcoes: list[dict[str, Any]] = []
    vistos: set[str] = set()
    base = _base_curta(item)
    unidades = sorted(item.product_units or [], key=lambda unit: (not bool(unit.is_base), str(unit.unit_code or "")))
    for unit in unidades:
        codigo = str(unit.unit_code or "").strip().lower()
        if not unit.active or not codigo or codigo in vistos:
            continue
        fator = _fator(item, codigo)
        if not fator or fator <= 0:
            continue
        vistos.add(codigo)
        opcoes.append({"codigo": codigo, "rotulo": str(unit.unit_label or codigo).upper(), "fator": round(fator, 6), "base": base})
    return opcoes if len(opcoes) > 1 else []


def trocar_unidade(item_row: DocumentoEntradaEstoqueItem, unidade: str | None) -> bool:
    """Troca a unidade da linha ainda não processada e refaz a conta. Devolve True se mudou."""
    from .finance_service import _normalize_financial_line

    nova = str(unidade or "").strip().lower()
    atual = str(item_row.unidade_quantidade or "").strip().lower()
    if not nova or nova == atual:
        return False
    item = item_row.item
    if item is None or nova not in {opcao["codigo"] for opcao in opcoes_de_unidade(item)}:
        raise ValueError(f"Unidade {nova.upper()} não existe no item {item_row.codigo_item}.")
    if (item_row.status_processamento or "").strip().lower() == "processado":
        raise ValueError(f"O item {item_row.codigo_item} já entrou no estoque e não pode trocar de unidade neste documento.")

    # O valor total é o que a NF diz; o unitário sai dele na unidade nova (1 FARDO de R$ 119,39 virou 24 UN:
    # R$ 4,97 cada). Sem total, vale o unitário informado.
    total = float(item_row.valor_total) if item_row.valor_total not in (None, "") else None
    unitario = float(item_row.valor_unitario) if item_row.valor_unitario not in (None, "") and total is None else None
    linha = _normalize_financial_line(
        item,
        quantity=float(item_row.quantidade or 0.0),
        valor_unitario=unitario,
        valor_total=total,
        quantity_unit=nova,
        price_unit=nova,
    )
    quantidade = float(item_row.quantidade or 0.0)
    if total is not None and quantidade > 0:
        item_row.valor_unitario = round(total / quantidade, 6)
    item_row.unidade_quantidade = linha["quantity_unit"]
    item_row.quantidade_base = linha["quantity_base"]
    item_row.valor_unitario_base = linha["unit_price_base"]
    item_row.unidade_preco = linha["price_unit"]
    item_row.fator_preco_base = linha["factor_to_base"]
    item_row.valor_total = linha["total_value"]
    return True
