"""Última compra do item (25/11/2026): a NF mais recente vai para o item; NF antiga lançada depois não.

Achado do usuário: o cloro granulado ficou em "compra_nf (3740)" depois de a NF 3891 ser lançada pelo
Ler NF. Objetos em memória, sem banco.
"""
from datetime import date

from galint_flask.models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Item
from galint_flask.services.item_ultima_compra import record_item_last_purchase


def _nf(numero, recebimento, emissao=None, tipo="nf"):
    return DocumentoEntradaEstoque(numero_documento=numero, tipo_documento=tipo, data_emissao=emissao or recebimento,
                                   data_recebimento=recebimento, chave_acesso=f"CHAVE-{numero}")


def _linha(valor, base=None):
    return DocumentoEntradaEstoqueItem(valor_unitario=valor, valor_unitario_base=base, unidade_preco="balde", fator_preco_base=10.0)


def _cloro():
    return Item(codigo_item="7897432700140", descricao="CLORO GRANULADO 10KG", preco_compra_documento="3740",
                preco_compra_data_emissao=date(2026, 10, 16), preco_compra_data_recebimento=date(2026, 10, 29),
                preco_compra_unitario=477.0, preco_compra_fonte="compra_nf")


def test_newer_nf_becomes_the_last_purchase():
    item = _cloro()
    assert record_item_last_purchase(item, _nf("3891", date(2026, 11, 25), date(2026, 11, 23)), _linha(480.0, 48.0), actor="9001")
    assert (item.preco_compra_documento, item.nota_fiscal, item.preco_compra_chave_acesso) == ("3891", "3891", "CHAVE-3891")
    assert (item.preco_compra_data_emissao, item.preco_compra_data_recebimento) == (date(2026, 11, 23), date(2026, 11, 25))
    assert (item.preco_compra_unitario, item.preco_compra_unitario_base, item.preco_compra_unidade_preco) == (480.0, 48.0, "balde")
    assert item.preco_compra_atualizado_por == "9001"


def test_older_nf_launched_later_does_not_replace_the_newest():
    item = _cloro()
    assert not record_item_last_purchase(item, _nf("2520", date(2026, 8, 31)), _linha(349.9))
    assert (item.preco_compra_documento, item.preco_compra_unitario) == ("3740", 477.0)


def test_manual_document_and_line_without_price():
    item = _cloro()
    assert not record_item_last_purchase(item, _nf("183363", date(2026, 11, 25), tipo="manual"), _linha(None))
    assert item.preco_compra_documento == "3740"
    assert record_item_last_purchase(item, _nf("3900", date(2026, 11, 26)), _linha(None))
    assert item.preco_compra_documento == "3900" and item.preco_compra_unitario == 477.0  # sem preço na linha, fica o anterior
