"""Itens zerados (pedido do usuário em 26/11/2026).

"Preciso que todos os itens zerados no sistema fiquem ocultos nas listas que aparecem nas buscas e se concentrem no
botão 'Itens zerados'. Ao clicar, um modal com eles, as suas respectivas NFs, as datas de entrada no sistema e um botão
'Adicionar à Projeção'."

Zerado = saldo físico <= 0 (o mesmo saldo da lista de itens). As entradas vêm das linhas de documento fiscal (NF, cupom,
nota interna) e das entradas antigas que não têm linha de documento. No mesmo modal ficam os itens com saída contada duas
vezes (services/saida_dobrada.py), cada um com o saldo que ficaria depois da correção.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable

from ..extensions import db
from ..models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Entrada
from .saida_dobrada import resumo_por_item

ENTRADAS_POR_ITEM = 4
_ZERO = 1e-9


def eh_zerado(item: dict[str, Any]) -> bool:
    try:
        saldo = float(item.get("saldo") or 0.0)
    except (TypeError, ValueError):
        saldo = 0.0
    return saldo <= _ZERO and not item.get("pre_cadastro_pendente")


def _quando(valor: date | datetime | None) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    return valor.isoformat()


def _rotulo_documento(tipo: str | None, numero: str | None) -> str:
    tipo_norm = str(tipo or "").strip().lower()
    numero_txt = str(numero or "").strip()
    if not numero_txt or numero_txt.upper().startswith(("SEM", "NOTA INTERNA", "MANUAL")):
        return "SEM NF"
    if tipo_norm in {"cupom", "cupom_fiscal", "nfce"}:
        return f"CUPOM {numero_txt}"
    if tipo_norm in {"recibo", "nota_interna", "interno", "manual"}:
        return "SEM NF"
    return f"NF {numero_txt}"


def _rotulo_antigo(nota: str | None) -> str:
    texto = str(nota or "").strip()
    digitos = re.sub(r"\D", "", texto)
    if digitos and len(digitos) >= 3 and len(digitos) >= len(texto.replace(" ", "")) - 3:
        return f"NF {digitos}"
    return "SEM NF"


def entradas_dos_itens(codigos: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """{codigo: [{nf, data, quantidade}]} da mais recente para a mais antiga, até ENTRADAS_POR_ITEM por item."""
    lista = sorted({str(c) for c in codigos if c})
    if not lista:
        return {}
    por_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    entradas_com_documento: set[int] = set()

    linhas = (
        db.session.query(DocumentoEntradaEstoqueItem, DocumentoEntradaEstoque)
        .join(DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem.documento_id == DocumentoEntradaEstoque.id_documento)
        .filter(DocumentoEntradaEstoqueItem.codigo_item.in_(lista))
        .all()
    )
    for linha, documento in linhas:
        if linha.entrada_id:
            entradas_com_documento.add(int(linha.entrada_id))
        por_item[linha.codigo_item].append({
            "nf": _rotulo_documento(documento.tipo_documento, documento.numero_documento),
            "data": _quando(documento.data_recebimento or documento.data_emissao or documento.criado_em),
            "quantidade": float(linha.quantidade or 0.0),
            "unidade": str(linha.unidade_quantidade or "").strip().upper() or None,
        })

    for entrada in Entrada.query.filter(Entrada.codigo_item.in_(lista)).all():
        if entrada.id_entrada in entradas_com_documento:
            continue
        por_item[entrada.codigo_item].append({
            "nf": _rotulo_antigo(entrada.nota_fiscal),
            "data": _quando(entrada.data_entrada),
            "quantidade": float(entrada.quantidade or 0.0),
            "unidade": None,
        })

    return {
        codigo: sorted(entradas, key=lambda e: e["data"] or "", reverse=True)[:ENTRADAS_POR_ITEM]
        for codigo, entradas in por_item.items()
    }


def _base(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "codigo": item.get("codigo"),
        "descricao": item.get("descricao"),
        "categoria": item.get("categoria") or "Sem categoria",
        "unidade": item.get("unidade"),
        "saldo": float(item.get("saldo") or 0.0),
        "saldo_display": item.get("saldo_display"),
        "foto_path": item.get("foto_path"),
        "ultima_edicao_em": item.get("ultima_edicao_em"),
    }


def _saldos_do_razao(codigos: Iterable[str]) -> dict[str, float]:
    """Saldo do razão (stock_balances). O saldo da lista de itens de item com embalagem não fica negativo (o BAMBU
    com -408 aparecia como 0, e a correção mostrava "0 → 432" em vez de "-408 → 24"; 27/11/2026)."""
    from .balance_provider import balance_provider

    lista = sorted({str(c) for c in codigos if c})
    if not lista:
        return {}
    try:
        return {codigo: float(snapshot.quantity_base) for codigo, snapshot in balance_provider.get_balances(lista).items()}
    except Exception:
        return {}


def montar(itens: list[dict[str, Any]], *, no_carrinho: set[str]) -> dict[str, Any]:
    """Zerados (com entradas) e itens com saída em dobro aberta, para o modal da página de itens."""
    zerados = [item for item in itens if eh_zerado(item)]
    dobradas = resumo_por_item(None)
    entradas = entradas_dos_itens(item.get("codigo") for item in zerados)
    razao = _saldos_do_razao([str(item.get("codigo") or "") for item in zerados] + list(dobradas))

    def _base_com_razao(item: dict[str, Any]) -> dict[str, Any]:
        linha = _base(item)
        codigo = str(item.get("codigo") or "")
        if codigo in razao:
            linha["saldo"] = razao[codigo]
        return linha

    lista_zerados = []
    for item in sorted(zerados, key=lambda i: str(i.get("descricao") or "")):
        codigo = str(item.get("codigo") or "")
        linha = _base_com_razao(item)
        linha["entradas"] = entradas.get(codigo, [])
        linha["na_projecao"] = codigo in no_carrinho
        dobro = dobradas.get(codigo)
        linha["dobro"] = {**dobro, "saldo_corrigido": round(linha["saldo"] + dobro["quantidade"], 6)} if dobro else None
        lista_zerados.append(linha)

    por_codigo = {str(item.get("codigo") or ""): item for item in itens}
    lista_dobradas = []
    for codigo, dobro in dobradas.items():
        item = por_codigo.get(codigo)
        if item is None:
            continue
        linha = _base_com_razao(item)
        linha["dobro"] = {**dobro, "saldo_corrigido": round(linha["saldo"] + dobro["quantidade"], 6)}
        linha["na_projecao"] = codigo in no_carrinho
        lista_dobradas.append(linha)
    lista_dobradas.sort(key=lambda i: (i["saldo"], str(i.get("descricao") or "")))
    return {"zerados": lista_zerados, "dobradas": lista_dobradas}
