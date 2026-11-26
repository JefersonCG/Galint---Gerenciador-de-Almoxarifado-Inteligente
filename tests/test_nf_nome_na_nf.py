"""Nome do produto na NF × nome do item no GALINT (pedido do usuário em 26/11/2026).

"Quero que fique marcado que a Caixa de inspeção (NF) é a Caixa de passagem 20x20 (GALINT). Assim não
criamos confusão." O item fica com o nome do GALINT; a linha do documento guarda o da NF.
"""
from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Item
from galint_flask.services.finance_service import FinanceService
from galint_flask.services.nome_na_nf import ean_na_nf, nome_diferente, nome_na_nf
from tests.test_nf_leitura_flow import _launch_form, _send_sample, client  # noqa: F401 (fixture)


def test_pdf_tail_is_not_part_of_the_name():
    texto = "CX INSP MULTIUSO POLIP C/ TAMPA 20X20CM - EAN 8002255805975 - Cód. Forn 19720N - V. desc. R$ 30.96"
    assert nome_na_nf(texto) == "CX INSP MULTIUSO POLIP C/ TAMPA 20X20CM"
    assert ean_na_nf(texto) == "8002255805975"
    assert nome_na_nf("LIMPADOR DESINCRUSTANTE 6L = BELLINZONI - EAN 7898470069138 - pq 0.00). Cód. Forn 227161") == "LIMPADOR DESINCRUSTANTE 6L = BELLINZONI"
    assert nome_na_nf("DUTO CORRUGADO 1.1/4 DN40 PT 50M") == "DUTO CORRUGADO 1.1/4 DN40 PT 50M"
    assert nome_na_nf(None) == "" and ean_na_nf("SEM CODIGO") is None
    assert nome_diferente("CX INSP 20X20CM", "CAIXA DE PASSAGEM 20X20") and not nome_diferente("fita  isolante", "FITA ISOLANTE")


def test_launch_keeps_the_nf_name_on_the_document_and_the_galint_name_on_the_item(client):
    reading = _send_sample(client)
    form = _launch_form(reading, {"acao_4": "outro", "outro_4": "FITA001", "descricao_1": "CABO FLEXÍVEL AZUL 2,5MM", "incluir_6": ""})
    client.post(f"/nf/leitura/{reading.id}/lancar", data=form)

    fita = DocumentoEntradaEstoqueItem.query.filter_by(codigo_item="FITA001").one()
    assert (fita.descricao_nf, fita.codigo_nf) == ("FITA ISOLANTE 19MMX20M", "000555")
    assert db.session.get(Item, "FITA001").descricao == "FITA ISOLANTE 19MM 20M"  # o item não muda de nome

    cabo = Item.query.filter(Item.descricao == "CABO FLEXÍVEL AZUL 2,5MM").one()  # item novo com o nome do GALINT
    linha_cabo = DocumentoEntradaEstoqueItem.query.filter_by(codigo_item=cabo.codigo_item).one()
    assert linha_cabo.descricao_nf == "CABO FLEXIVEL 2,5MM AZUL ROLO 100M"

    documento = FinanceService._serialize_stock_document(DocumentoEntradaEstoque.query.one())
    linhas = {linha["codigo"]: linha for linha in documento["itens"]}
    assert linhas["FITA001"]["descricao"] == "FITA ISOLANTE 19MM 20M"
    assert linhas["FITA001"]["descricao_nf"] == "FITA ISOLANTE 19MMX20M"
    assert linhas[cabo.codigo_item]["descricao_nf"] == "CABO FLEXIVEL 2,5MM AZUL ROLO 100M"
    assert linhas["7891234567895"]["descricao_nf"] is None  # mesmo nome na NF e no GALINT: nada a marcar


def test_lines_launched_before_use_the_supplier_link(client):
    """Linha sem descricao_nf (lançada antes de 26/11/2026): o nome vem do vínculo do Ler NF."""
    from galint_flask.models import NFItemVinculo

    db.session.add(NFItemVinculo(cnpj_fornecedor="23476033000531", codigo_fornecedor="89152651", codigo_item="FITA001",
                                 descricao_fornecedor="CX INSP MULTIUSO POLIP C/ TAMPA 20X20CM - EAN 8002255805975 - Cód. Forn 19720N"))
    documento = DocumentoEntradaEstoque(tipo_documento="nf", numero_documento="733381", cnpj_emitente="23.476.033/0005-31")
    db.session.add(documento)
    db.session.flush()
    db.session.add(DocumentoEntradaEstoqueItem(documento_id=documento.id_documento, codigo_item="FITA001", quantidade=9))
    db.session.commit()

    linha = FinanceService._serialize_stock_document(documento)["itens"][0]
    assert linha["descricao_nf"] == "CX INSP MULTIUSO POLIP C/ TAMPA 20X20CM"
