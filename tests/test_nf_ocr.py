"""Leitor de NF (DANFE) pelo texto do PDF e por OCR com o Tesseract (24/11/2026).

O DANFE de exemplo (tests/danfe_sample.py) tem 6 itens, um com a descrição em duas linhas, e colunas de
ICMS depois do total. O teste de OCR só roda onde o Tesseract está instalado.
"""
import pytest

from galint_flask.services import nf_ocr
from tests.danfe_sample import ACCESS_KEY, EMISSION, ITEMS, SUPPLIER, SUPPLIER_CNPJ, build_danfe_pdf, render_png


def _expected_totals():
    return {round(float(item[8].replace(".", "").replace(",", ".")), 2) for item in ITEMS}


def test_access_key_check_digit_and_parts():
    assert nf_ocr.is_valid_access_key(ACCESS_KEY)
    broken = ACCESS_KEY[:-1] + str((int(ACCESS_KEY[-1]) + 1) % 10)
    assert not nf_ocr.is_valid_access_key(broken)
    parts = nf_ocr.describe_access_key(ACCESS_KEY)
    assert (parts["cnpj_emitente"], parts["numero"], parts["serie"], parts["modelo_label"]) == (SUPPLIER_CNPJ, "12345", "1", "NF-e")


def test_brazilian_numbers_and_ocr_noise():
    assert nf_ocr.parse_number("1.234,56") == 1234.56
    assert nf_ocr.parse_number("12,0000") == 12.0
    assert nf_ocr.parse_number("‘2,0000") == 2.0  # borda da célula lida junto
    assert nf_ocr.parse_number("1O,5O") == 10.5  # letra O no lugar de zero
    assert nf_ocr.number_candidates("1.000") == [1.0, 1000.0]  # ambíguo: a conta decide


def test_gtin_validation():
    assert nf_ocr.is_valid_gtin("7891234567895")
    assert not nf_ocr.is_valid_gtin("7891234567890")
    assert not nf_ocr.is_valid_gtin("A-778")


def test_item_line_with_dotted_cfop_and_trailing_tax_columns():
    # Linha real da NF da ACQUA ILHA PISCINA (23/11/2026): CFOP "5.102" e colunas de ICMS/IPI depois do total.
    tokens = "14041221 Cloro Granulado Hth Tradicional 10kg 38089419 0102 5.102 Un 25,00 477,00 11.925,00 0,00 0,00 0,00".split()
    item = nf_ocr._item_from_tokens(tokens)
    assert item["codigo"] == "14041221"
    assert item["descricao"] == "Cloro Granulado Hth Tradicional 10kg"
    assert (item["ncm"], item["cfop"], item["unidade"]) == ("38089419", "5102", "UN")
    assert (item["quantidade"], item["valor_unitario"], item["valor_total"], item["confere"]) == (25.0, 477.0, 11925.0, True)


def test_split_numbers_are_repaired_only_when_the_math_closes():
    tokens = "889 TINTA ACRILICA 18L 32091010 000 5102 LT 1,0000 459 9000 459,90".split()
    item = nf_ocr._item_from_tokens(tokens)
    assert (item["quantidade"], item["valor_unitario"], item["valor_total"], item["confere"]) == (1.0, 459.9, 459.9, True)


def test_receipt_line_without_ncm_needs_the_math_to_close():
    good = nf_ocr._receipt_item_from_tokens("001 7891234567895 FITA ISOLANTE 20M 3 UN X 7,25 21,75".split())
    assert good["descricao"] == "FITA ISOLANTE 20M" and good["valor_total"] == 21.75
    assert nf_ocr._receipt_item_from_tokens("TOTAL 3 ITENS 21,75 10,00 5,00".split()) is None


def test_pdf_with_text_layer_is_read_without_ocr():
    result = nf_ocr.read_and_parse(build_danfe_pdf(), "nf.pdf")
    header = result["cabecalho"]
    assert result["fonte"] == "texto_pdf"
    assert header["chave"] == ACCESS_KEY
    assert (header["numero"], header["serie"], header["cnpj_emitente"], header["emitente"]) == ("12345", "1", SUPPLIER_CNPJ, SUPPLIER)
    assert header["data_emissao"] == "2026-11-18" == "-".join(reversed(EMISSION.split("/")))
    assert header["valor_produtos"] == header["valor_total"] == 1501.9
    assert len(result["itens"]) == 6 and all(item["confere"] for item in result["itens"])
    assert {round(item["valor_total"], 2) for item in result["itens"]} == _expected_totals()
    assert result["itens"][2]["descricao"] == "LUVA NITRILICA AZUL TAMANHO G CAIXA COM 100 UNIDADES"
    assert result["avisos"] == []


@pytest.mark.skipif(nf_ocr.find_tesseract() is None, reason="Tesseract não instalado nesta máquina")
def test_scanned_page_is_read_by_ocr():
    result = nf_ocr.read_and_parse(render_png(build_danfe_pdf(), dpi=300), "nf.png")
    assert result["fonte"] == "ocr"
    assert result["cabecalho"]["chave"] == ACCESS_KEY
    assert result["cabecalho"]["valor_total"] == 1501.9
    assert {round(item["valor_total"], 2) for item in result["itens"] if item["confere"]} == _expected_totals()
