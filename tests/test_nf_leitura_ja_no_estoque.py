"""Ler NF com produtos que já estavam no estoque (pedido do usuário em 26/11/2026).

"Muitas dessas NF que coloquei são de produtos que já tínhamos colocado sem ter a existência do Ler NF.
Somente agora consegui as NF digitalizadas para lançar e documentar." A conferência mostra o saldo e as
entradas sem NF do item; a escolhida fica ligada à linha da NF e não soma de novo. Também: o PDF da NF
226340 não deixou ler número nem chave, e o número no nome do arquivo acha a NF que já estava no GALINT.
"""
import json
from datetime import date, datetime

from galint_flask.extensions import db
from galint_flask.models import (
    DocumentoEntradaEstoque,
    DocumentoEntradaEstoqueItem,
    Entrada,
    FinanceSupplier,
    NFLeitura,
    StockMovement,
)
from galint_flask.services import nf_leitura_service as service
from tests.test_nf_leitura_flow import _launch_form, _send_sample, client  # noqa: F401 (fixture)

DISJUNTOR = "7891234567895"
FITA = "FITA001"


def _move(product, kind, quantity, reference_type, reference_id, day):
    movement = StockMovement(product_id=product, movement_type=kind, quantity_base=quantity, reference_type=reference_type,
                             reference_id=str(reference_id), created_at=datetime(2026, 2, day, 10, 0))
    db.session.add(movement)
    db.session.flush()
    return movement


def _legacy_entry(product, quantity, day, nota=None):
    entrada = Entrada(codigo_item=product, quantidade=quantity, nota_fiscal=nota, data_entrada=datetime(2026, 2, day, 10, 0))
    db.session.add(entrada)
    db.session.flush()
    return _move(product, "entrada", quantity, "entrada", entrada.id_entrada, day)


def _document_entry(product, quantity, day, tipo, numero):
    documento = DocumentoEntradaEstoque(tipo_documento=tipo, numero_documento=numero, data_emissao=date(2026, 2, day))
    db.session.add(documento)
    db.session.flush()
    line = DocumentoEntradaEstoqueItem(documento_id=documento.id_documento, codigo_item=product, quantidade=quantity,
                                       quantidade_base=quantity, status_processamento="processado")
    db.session.add(line)
    db.session.flush()
    movement = _move(product, "entrada", quantity, "entrada_documento_item", line.id_documento_item, day)
    line.stock_movement_id = movement.id
    return movement


def test_file_name_gives_the_nf_number():
    assert service.numero_do_arquivo("OBRAMAX NF 226340 R$ 531,37 (LIMPA PEDRA).pdf") == "226340"
    assert service.numero_do_arquivo("OBRAMAX NF.202472 PARC.3X VENC 1° - 09.04.pdf") == "202472"
    assert service.numero_do_arquivo("OBRAMAX NF226480  R$ 137,80.pdf") == "226480"
    assert service.numero_do_arquivo("INNOVA RIO venc 07.12  NF4002 R$ 3.996,34.pdf") == "4002"
    assert service.numero_do_arquivo("CONFERENCIA 2026.pdf") is None
    assert service.numero_do_arquivo(None) is None


def test_stock_shows_only_entries_without_nf(client):
    legacy = _legacy_entry(DISJUNTOR, 10, 10, nota="101456")
    _document_entry(DISJUNTOR, 5, 11, "nf", "777")  # já documentada por NF: fica fora
    ajuste = _move(DISJUNTOR, "ajuste", 3, "inventario_evento", 1, 12)
    nota_interna = _document_entry(DISJUNTOR, 4, 13, "manual", "NOTA INTERNA")
    _move(DISJUNTOR, "saida", -2, "saida", 1, 14)
    db.session.commit()

    data = service.entradas_anteriores(DISJUNTOR)
    assert data["saldo"] == 20 and data["unidade"] == "un"
    assert [(row["id"], row["quantidade"], row["origem"]) for row in data["entradas"]] == [
        (nota_interna.id, 4, "NOTA INTERNA"),
        (ajuste.id, 3, "AJUSTE"),
        (legacy.id, 10, "ENTRADA ANTIGA · NF 101456"),
    ]
    assert client.get(f"/nf/leitura/estoque/{DISJUNTOR}").get_json()["saldo"] == 20


def test_line_already_in_stock_is_documented_without_a_new_entry(client):
    legacy = _legacy_entry(DISJUNTOR, 10, 10)
    db.session.commit()
    reading = _send_sample(client)
    movements_before = StockMovement.query.filter_by(product_id=DISJUNTOR).count()

    form = _launch_form(reading, {"acao_4": "outro", "outro_4": FITA, "estoque_2": str(legacy.id), "incluir_6": ""})
    response = client.post(f"/nf/leitura/{reading.id}/lancar", data=form)
    assert response.status_code == 302
    with client.session_transaction() as session:
        messages = [message for _, message in session.get("_flashes", [])]
    assert "NF 12345 lançada: 3 item(ns) novo(s) no pré-cadastro, 1 com entrada no estoque e 1 já no estoque (só documentado)." in messages, messages

    line = DocumentoEntradaEstoqueItem.query.filter_by(codigo_item=DISJUNTOR).one()
    assert (line.status_processamento, line.stock_movement_id) == ("processado", legacy.id)
    assert line.observacao == "Já estava no estoque: entrada de 10/02/2026."
    assert StockMovement.query.filter_by(product_id=DISJUNTOR).count() == movements_before  # não somou de novo
    assert StockMovement.query.filter_by(product_id=FITA).count() == 1  # a outra linha entrou normalmente
    assert service.entradas_anteriores(DISJUNTOR)["entradas"] == []  # a entrada antiga ficou coberta pela NF

    # Excluir a linha da NF não tira do estoque o que entrou antes dela.
    from galint_flask.services.finance_service import finance_service

    result = finance_service.reverse_and_delete_document_item(line, usuario_matricula="9001")
    assert result["reversed"] is False
    assert StockMovement.query.filter_by(product_id=DISJUNTOR).count() == movements_before


def test_entry_already_covered_cannot_be_chosen_again(client):
    legacy = _legacy_entry(DISJUNTOR, 10, 10)
    _document_entry(DISJUNTOR, 1, 9, "nf", "999")
    db.session.commit()
    covering = DocumentoEntradaEstoqueItem.query.one()
    covering.stock_movement_id = legacy.id  # outra NF já cobre 1 + a própria entrada de 1
    covering.quantidade_base = 10
    db.session.commit()
    reading = _send_sample(client)

    response = client.post(f"/nf/leitura/{reading.id}/lancar", data=_launch_form(reading, {"estoque_2": str(legacy.id)}))
    with client.session_transaction() as session:
        messages = [message for _, message in session.get("_flashes", [])]
    assert response.headers["Location"].endswith(f"/nf/leitura/{reading.id}")
    assert any("não está mais livre" in message for message in messages), messages
    assert db.session.get(NFLeitura, reading.id).status == "lida"


def test_nf_number_from_the_file_name_finds_the_nf_already_in_galint(client):
    supplier = FinanceSupplier(razao_social="BMB MATERIAL DE CONSTRUCAO S.A.", cnpj="23.476.033/0008-84")
    db.session.add(supplier)
    db.session.flush()
    documento = DocumentoEntradaEstoque(tipo_documento="nf", numero_documento="226340", fornecedor_id=supplier.id, data_emissao=date(2026, 5, 4))
    db.session.add(documento)
    reading = NFLeitura(
        arquivo_nome="OBRAMAX NF 226340 R$ 531,37 (LIMPA PEDRA).pdf",
        arquivo_path="nf_leituras/x.pdf",
        status="lida",
        resultado_json=json.dumps({"cabecalho": {"numero": None, "chave": None, "cnpj_emitente": "23476033000884"}, "itens": []}),
    )
    db.session.add(reading)
    db.session.commit()

    response = client.get(f"/nf/leitura/{reading.id}")
    assert response.status_code == 302 and response.headers["Location"].endswith("/nf/leitura/")
    reading = db.session.get(NFLeitura, reading.id)
    assert (reading.status, reading.documento_id, reading.numero_documento) == ("arquivada", documento.id_documento, "226340")
