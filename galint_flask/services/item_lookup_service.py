"""Busca de itens para os autocompletes do sistema.

As telas de saída, saída fracionada e retirada de ferramenta tinham cada uma o
seu endpoint de busca, e cada endpoint repetia o mesmo trecho: chamar o
inventário, recarregar os modelos um a um para descobrir o valor de referência
e devolver o mesmo par de chaves ("items" e "itens"). Aqui existe uma rotina só,
com o carregamento dos modelos em lote — antes cada endpoint fazia uma consulta
por item, o que crescia junto com o número de resultados.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from ..models import Item
from .inventory import inventory_service
from .operation_visual_payload import operation_visual_payload_service

# Assinatura do enriquecedor opcional: recebe o payload do inventário e o modelo
# correspondente (quando existir) e devolve os campos extras daquela tela.
Enriquecedor = Callable[[dict[str, Any], Item | None], dict[str, Any]]


def _codigos(resultados: Iterable[dict[str, Any]]) -> list[str]:
    codigos = []
    for item in resultados:
        codigo = str(item.get("codigo") or "").strip()
        if codigo:
            codigos.append(codigo)
    return codigos


def packaging_proof_fields(modelo: Item | None) -> dict[str, Any]:
    """Unidade em que a quantidade da NF é lida e quanto vale 1 dela na unidade do item (24/11/2026).

    Para a "prova real" das telas de NF (pedido do usuário depois da NF 617377, em que 2.000 parafusos
    entraram como 2.000 caixas de 1.000): para item com embalagem, o servidor sempre lê a quantidade da
    NF em embalagens (infer_document_quantity_unit_for_item), com o fator de resolve_packaging_factor.
    As telas mostram a mesma conta que o servidor fará, em vez de recalcular por conta própria.
    """
    if modelo is None:
        return {}
    from .legacy_stock_normalizer import resolve_packaging_factor
    from .price_normalization import _infer_packaging_document_unit, infer_document_quantity_unit_for_item

    try:
        fator = float(resolve_packaging_factor(modelo) or 0.0)
        unidade_documental = infer_document_quantity_unit_for_item(modelo)
        converte = bool(_infer_packaging_document_unit(modelo))
    except Exception:
        return {}
    return {
        "fator_embalagem": fator if fator > 0 else None,
        "unidade_documental": unidade_documental or None,
        # True quando o servidor lê a quantidade da NF em embalagens e multiplica pelo fator.
        "converte_embalagem": converte,
    }


def carregar_modelos(codigos: list[str]) -> dict[str, Item]:
    """Carrega os itens em uma consulta só, evitando uma ida ao banco por linha."""
    if not codigos:
        return {}
    return {item.codigo_item: item for item in Item.query.filter(Item.codigo_item.in_(codigos)).all()}


def search_items(
    query: str,
    *,
    limit: int = 20,
    only_available: bool = False,
    enrich: Enriquecedor | None = None,
) -> list[dict[str, Any]]:
    """Resultado de autocomplete já com valor de referência resolvido.

    `only_available=True` remove o que não pode sair agora (estoque zerado,
    ferramenta em uso ou em reparo). A tela de saída prefere trazer tudo e
    mostrar o indisponível em vermelho, então passa False.
    """
    texto = (query or "").strip()
    if not texto:
        return []

    resultados = inventory_service.search_items_for_autocomplete(texto, limit=limit)
    if only_available:
        resultados = [item for item in resultados if item.get("is_available") is not False]

    modelos = carregar_modelos(_codigos(resultados))

    enriquecidos: list[dict[str, Any]] = []
    for payload in resultados:
        codigo = str(payload.get("codigo") or "").strip()
        modelo = modelos.get(codigo)
        item = {
            **payload,
            "valor_referencia": operation_visual_payload_service.resolve_item_financial_reference(modelo),
            **packaging_proof_fields(modelo),
        }
        if enrich is not None:
            item.update(enrich(payload, modelo))
        enriquecidos.append(item)
    return enriquecidos


def autocomplete_response_payload(itens: list[dict[str, Any]]) -> dict[str, Any]:
    """Formato aceito pelos autocompletes: "items" para as telas novas e "itens" para as antigas."""
    return {"items": itens, "itens": itens}
