"""Nome do produto na NF × nome do item no GALINT (pedido do usuário em 26/11/2026).

"Preciso que o item tenha um outro nome no sistema e o da NF fica na NF, mas quero que fique marcado que a
Caixa de inspeção (NF) é a Caixa de passagem 20x20 (GALINT). Assim não criamos confusão." O item continua
com o nome do GALINT; a linha do documento guarda o nome e o código do produto como vieram na NF
(DocumentoEntradaEstoqueItem.descricao_nf / codigo_nf), e as telas mostram os dois.

Linhas lançadas antes disso (ou digitadas) não têm descricao_nf: o nome vem do vínculo que o Ler NF guarda
por fornecedor (NFItemVinculo: CNPJ + item → descrição do fornecedor), quando existe.
"""
from __future__ import annotations

import re
from typing import Any

from flask import g, has_app_context

# O texto do PDF de algumas lojas (BMB/Obramax) junta à descrição: " - EAN 8002255805975 - Cód. Forn 19720N
# - V. desc. R$ 30.96". O nome do produto é o que vem antes.
_TAIL = re.compile(r"\s+-\s+(?:EAN\b|C[óo]d\.?\s*Forn\b|V\.\s*desc\b|pq\s)", re.IGNORECASE)
_EAN = re.compile(r"\bEAN\s*:?\s*(\d{8,14})\b", re.IGNORECASE)


def nome_na_nf(descricao: Any) -> str:
    texto = " ".join(str(descricao or "").split())
    return _TAIL.split(texto, maxsplit=1)[0].strip(" -") if texto else ""


def ean_na_nf(descricao: Any) -> str | None:
    match = _EAN.search(str(descricao or ""))
    return match.group(1) if match else None


def _so_digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _nomes_do_fornecedor(cnpj: str) -> dict[str, str]:
    """codigo_item → descrição do fornecedor, dos vínculos do Ler NF (uma consulta por CNPJ e pedido)."""
    from ..models import NFItemVinculo

    cache = None
    if has_app_context():
        cache = g.setdefault("_nomes_na_nf", {})
        if cnpj in cache:
            return cache[cnpj]
    nomes: dict[str, str] = {}
    for row in NFItemVinculo.query.filter_by(cnpj_fornecedor=cnpj).order_by(NFItemVinculo.id).all():
        nome = nome_na_nf(row.descricao_fornecedor)
        if row.codigo_item and nome:
            nomes[row.codigo_item] = nome
    if cache is not None:
        cache[cnpj] = nomes
    return nomes


def nome_na_nf_da_linha(row: Any, documento: Any = None) -> str | None:
    """Nome do produto como está na NF desta linha de documento, ou None quando não se sabe."""
    proprio = nome_na_nf(getattr(row, "descricao_nf", None))
    if proprio:
        return proprio
    documento = documento if documento is not None else getattr(row, "documento", None)
    cnpj = _so_digitos(getattr(documento, "cnpj_emitente", None))
    if len(cnpj) != 14 or not getattr(row, "codigo_item", None):
        return None
    try:
        return _nomes_do_fornecedor(cnpj).get(row.codigo_item) or None
    except Exception:
        return None


def nome_diferente(nome_nf: str | None, nome_galint: str | None) -> bool:
    """Só vale marcar quando a NF chama o item de outro jeito."""
    a = " ".join(str(nome_nf or "").upper().split())
    b = " ".join(str(nome_galint or "").upper().split())
    return bool(a) and a != b
