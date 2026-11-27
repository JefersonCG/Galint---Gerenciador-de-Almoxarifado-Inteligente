"""NFC-e da consulta da SEFAZ (layout das NFs da Obramax/BMB) no Ler NF (27/11/2026).

Pedido do usuário: "quero que o Ler NF leia o material dessas NF + os valores e a quantidade, cruze com o sistema e me
entregue algo que eu possa corrigir na conferência". As NFs 75788 e 101456 saíam com 0 itens: cada item ocupa duas
linhas (descrição + "(Código: …)"; "Qtde.: … UN: … Vl. Unit.: … total") e o rodapé traz o desconto.
"""
from galint_flask.services import nf_ocr
from tests.danfe_sample import build_nfce_pdf


def test_nfce_reads_items_values_and_quantities():
    parsed = nf_ocr.read_and_parse(build_nfce_pdf(), "OBRAMAX-CC.pdf")
    itens = parsed["itens"]
    assert [(i["codigo"], i["descricao"], i["unidade"], i["quantidade"], i["valor_unitario"], i["valor_total"], i["confere"]) for i in itens] == [
        ("89916505", "PTA LAMI FECH AL BR DIR STD 210X70CM", "UN", 1.0, 849.9, 849.9, True),
        ("89580491", "TINTA PRM EPOXI MULTISSUPERF BR 36L SV", "UN", 5.0, 259.9, 1299.5, True),
        ("89699463", "ESTILETE MODELO 510 STAMACO", "UN", 1.0, 26.99, 26.99, True),
    ]
    cabecalho = parsed["cabecalho"]
    assert (cabecalho["numero"], cabecalho["modelo"]) == ("75788", "NFC-e")
    assert cabecalho["emitente"] == "BMB Material de Construcao S.A"
    # Soma dos produtos (antes do desconto) e o valor pago.
    assert (cabecalho["valor_produtos"], cabecalho["valor_total"]) == (2176.39, 2166.39)
    assert parsed["avisos"] == ["Desconto de R$ 10,00 no total da nota; os valores dos itens estão sem o desconto."]


def test_nfce_warns_when_items_are_missing():
    parsed = nf_ocr.read_and_parse(build_nfce_pdf(itens_no_rodape=4), "OBRAMAX-CC.pdf")
    assert "Lidos 3 de 4 itens da NFC-e: confira os que faltam." in parsed["avisos"]
