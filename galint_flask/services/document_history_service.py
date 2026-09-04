"""Persistência imutável das entradas fiscais para auditoria futura."""
from __future__ import annotations

from typing import Any

from ..extensions import db
from ..models import DocumentoEntradaEstoqueItem, EntradaFiscalHistorico


def record_document_item(item_row: DocumentoEntradaEstoqueItem, *, evento: str, usuario: str | None = None, motivo: str | None = None) -> EntradaFiscalHistorico:
    documento = item_row.documento
    item = item_row.item
    record = EntradaFiscalHistorico(
        evento=evento,
        documento_id=documento.id_documento if documento else None,
        documento_item_id=item_row.id_documento_item,
        codigo_item=item_row.codigo_item,
        descricao_item=getattr(item, "descricao", None),
        marca_item=getattr(item, "marca", None),
        categoria_item=getattr(item, "categoria", None),
        tipo_documento=documento.tipo_documento if documento else "nf",
        numero_documento=documento.numero_documento if documento else "N/D",
        chave_acesso=getattr(documento, "chave_acesso", None),
        data_emissao=getattr(documento, "data_emissao", None),
        data_recebimento=getattr(documento, "data_recebimento", None),
        quantidade=item_row.quantidade,
        unidade_quantidade=item_row.unidade_quantidade,
        quantidade_base=item_row.quantidade_base,
        valor_unitario=item_row.valor_unitario,
        valor_unitario_base=item_row.valor_unitario_base,
        unidade_preco=item_row.unidade_preco,
        valor_total=item_row.valor_total,
        lote=item_row.lote,
        data_validade=item_row.data_validade,
        status_processamento=item_row.status_processamento,
        usuario_matricula=usuario,
        motivo=motivo,
    )
    db.session.add(record)
    return record