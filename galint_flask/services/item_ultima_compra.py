"""Última compra do item (NF, chave, datas e preço), gravada a cada NF lançada.

Achado do usuário em 25/11/2026 (cloro granulado 10 kg): a NF 3891 foi lançada pelo "Ler NF", mas o
cartão Financeiro do item continuou em "Compra: compra_nf (3740)". O lançamento por Documentos
Fiscais (views/nf.py, _sync_document_financial_entries) grava a compra no item; o Ler NF
(nf_leitura_service) e a entrada pelo app (/api/mobile/documentos-fiscais) não gravavam. Pedido do
usuário: "o sistema deveria ter atualizado o número da nf e a data! e preciso que o sistema armazene
as datas e nf anteriores sempre que entrarem novas". As anteriores continuam nas linhas de NF
(entrada_documento_itens), que o histórico do item lista; aqui fica só a mais recente.

Diferença para o fluxo de Documentos Fiscais: NF mais antiga lançada depois (ex.: uma de setembro
lançada em novembro) não toma o lugar da mais recente.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Item
from ..utils.time_service import TimeService


def _origin_for_document_type(document_type: object) -> str:
    normalized = str(document_type or "").strip().lower()
    if normalized == "nf":
        return "compra_nf"
    if normalized in {"cupom", "recibo"}:
        return "compra_cupom"
    return "compra_documento"


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def purchase_date(documento: DocumentoEntradaEstoque | None) -> date | None:
    if documento is None:
        return None
    return _as_date(documento.data_recebimento) or _as_date(documento.data_emissao)


def record_item_last_purchase(
    item: Item | None,
    documento: DocumentoEntradaEstoque | None,
    linha: DocumentoEntradaEstoqueItem | None,
    *,
    actor: str | None = None,
) -> bool:
    """Leva para o item a compra desta linha de NF. Não faz commit (fica com a transação de quem chamou).

    Devolve False quando a NF é mais antiga que a compra que o item já mostra, ou falta algum dado.
    """
    if item is None or documento is None or linha is None:
        return False
    if str(documento.tipo_documento or "").strip().lower() == "manual":
        return False
    nova = purchase_date(documento)
    atual = _as_date(item.preco_compra_data_recebimento) or _as_date(item.preco_compra_data_emissao)
    if nova is not None and atual is not None and nova < atual:
        return False

    item.nota_fiscal = documento.numero_documento
    item.preco_compra_documento = documento.numero_documento
    item.preco_compra_chave_acesso = documento.chave_acesso
    item.preco_compra_data_emissao = documento.data_emissao
    item.preco_compra_data_recebimento = documento.data_recebimento
    item.preco_compra_fonte = _origin_for_document_type(documento.tipo_documento)
    item.preco_compra_atualizado_em = TimeService.now_db()
    item.preco_compra_atualizado_por = str(actor) if actor else item.preco_compra_atualizado_por
    if linha.valor_unitario not in (None, "") and float(linha.valor_unitario) > 0:
        item.preco_compra_unitario = float(linha.valor_unitario)
        item.preco_compra_unitario_base = linha.valor_unitario_base
        item.preco_compra_unidade_preco = linha.unidade_preco
        item.preco_compra_fator_base = linha.fator_preco_base
    return True
