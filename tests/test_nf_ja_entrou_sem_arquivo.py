"""NF cujo material já entrou no estoque sem o arquivo da NF (27/11/2026).

Caso real: a NF 101456 da Obramax entrou em fevereiro pela tela antiga de entradas, com "NF 101456" escrito, e virou o
documento manual 15 (sem fornecedor nem chave). O Ler NF não reconhecia e ia lançar tudo de novo como item novo. Agora
cada linha da NF é casada com o item dessas entradas e a conferência marca o "Já no estoque" sozinha.
"""
from datetime import datetime

from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoque, Entrada
from galint_flask.services.nf_leitura_service import load_result
from tests.test_nf_leitura_flow import _send_sample, client  # noqa: F401 (fixture)


def test_lines_are_linked_to_what_entered_with_the_same_nf_number(client):
    db.session.add(Entrada(codigo_item="FITA001", matricula="9001", quantidade=12, nota_fiscal="12345", data_entrada=datetime(2026, 2, 10, 9)))
    db.session.commit()

    reading = _send_sample(client)
    result = load_result(reading)
    fita = next(item for item in result["itens"] if "FITA ISOLANTE" in item["descricao"])
    assert fita["acao"] == "FITA001"
    assert fita["sugestoes"][0]["motivo"] == "entrou com a NF 12345 10/02/2026"
    assert result["ja_entrou_sem_arquivo"] == {"numero": "12345", "itens": 1, "ligadas": 1}
    assert result["avisos"][0].startswith("A NF 12345 já tinha entrado no estoque sem o arquivo (1 itens em 10/02/2026).")
    # O que não entrou com a NF segue a sugestão de sempre.
    disjuntor = next(item for item in result["itens"] if "DISJUNTOR" in item["descricao"])
    assert not disjuntor["sugestoes"][0]["motivo"].startswith("entrou com a NF")


def test_nf_with_a_real_document_is_not_matched_again(client):
    """Com o documento da NF de verdade (mesma chave), a leitura vira NF física; não há o que casar."""
    from tests.danfe_sample import ACCESS_KEY

    db.session.add(DocumentoEntradaEstoque(tipo_documento="nf", numero_documento="12345", chave_acesso=ACCESS_KEY))
    db.session.add(Entrada(codigo_item="FITA001", matricula="9001", quantidade=12, nota_fiscal="12345", data_entrada=datetime(2026, 2, 10, 9)))
    db.session.commit()
    reading = _send_sample(client)
    assert reading.status == "arquivada"
    assert "ja_entrou_sem_arquivo" not in load_result(reading)
