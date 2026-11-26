"""DANFE de exemplo para os testes da leitura de NF (24/11/2026).

Monta com o reportlab um DANFE no leiaute comum (canhoto, quadro do emitente, chave de acesso,
destinatário, cálculo do imposto e tabela de produtos com colunas de ICMS), em letra miúda como os
reais, com uma descrição quebrada em duas linhas. Sem NF real disponível, é a referência para medir
o leitor pelo texto do PDF e pelo OCR (página desenhada em imagem).
"""
from __future__ import annotations

import io

from galint_flask.services.nf_ocr import access_key_check_digit

SUPPLIER = "FERRAGENS SAO JOSE LTDA"
SUPPLIER_CNPJ = "12345678000195"
NUMBER = "12345"
SERIES = "1"
EMISSION = "18/11/2026"
EXIT_DATE = "19/11/2026"

def chave_da_nf(numero: int) -> str:
    """Chave de acesso válida do fornecedor de teste para o número dado (dígito verificador certo)."""
    key43 = "53" + "2611" + SUPPLIER_CNPJ + "55" + "001" + f"{numero:09d}" + "1" + "12345678"
    return key43 + str(access_key_check_digit(key43))


ACCESS_KEY = chave_da_nf(int(NUMBER))

# (código, descrição em linhas, NCM, CST, CFOP, UN, quantidade, unitário, total)
ITEMS = [
    ("000123", ["CABO FLEXIVEL 2,5MM AZUL ROLO 100M"], "85444900", "000", "5102", "RL", "2,0000", "289,9000", "579,80"),
    ("7891234567895", ["DISJUNTOR DIN MONOPOLAR 20A"], "85362000", "000", "5102", "UN", "10,0000", "18,5000", "185,00"),
    ("A-778", ["LUVA NITRILICA AZUL TAMANHO G", "CAIXA COM 100 UNIDADES"], "40151900", "060", "5405", "CX", "3,0000", "45,9000", "137,70"),
    ("000555", ["FITA ISOLANTE 19MMX20M"], "39191010", "000", "5102", "UN", "12,0000", "7,2500", "87,00"),
    ("889", ["TINTA ACRILICA FOSCA BRANCO 18L"], "32091010", "000", "5102", "LT", "1,0000", "459,9000", "459,90"),
    ("12", ["PARAFUSO SEXTAVADO 1/4 X 2"], "73181500", "000", "5102", "PC", "150,0000", "0,3500", "52,50"),
]
TOTAL_PRODUCTS = "1.501,90"


def _group_key(key: str) -> str:
    return " ".join(key[index:index + 4] for index in range(0, 44, 4))


def build_danfe_pdf(numero: int = int(NUMBER)) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left, right = 22, width - 22

    def label(x, y, text, size=5.5):
        page.setFont("Helvetica", size)
        page.drawString(x, y, text)

    def value(x, y, text, size=7.5, bold=False):
        page.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        page.drawString(x, y, text)

    def box(x, y, w, h):
        page.rect(x, y, w, h, stroke=1, fill=0)

    top = height - 22
    # Canhoto
    box(left, top - 34, right - left, 34)
    label(left + 4, top - 10, f"RECEBEMOS DE {SUPPLIER} OS PRODUTOS E/OU SERVIÇOS CONSTANTES DA NOTA FISCAL ELETRÔNICA INDICADA AO LADO", 6)
    label(left + 4, top - 26, "DATA DE RECEBIMENTO", 5.5)
    label(left + 160, top - 26, "IDENTIFICAÇÃO E ASSINATURA DO RECEBEDOR", 5.5)
    value(right - 80, top - 14, "NF-e", 9, True)
    numero_br = f"{numero:09d}"
    numero_br = f"{numero_br[:3]}.{numero_br[3:6]}.{numero_br[6:]}"
    value(right - 80, top - 26, f"Nº {numero_br}  SÉRIE 001", 6.5)

    # Emitente + DANFE + chave
    y = top - 44
    box(left, y - 92, 230, 92)
    value(left + 6, y - 18, SUPPLIER, 9, True)
    label(left + 6, y - 32, "RUA DAS FERRAMENTAS, 100 - TAGUATINGA - BRASILIA/DF", 6)
    label(left + 6, y - 42, "CEP 72000-000  FONE (61) 3333-4444", 6)
    box(left + 232, y - 92, 100, 92)
    value(left + 258, y - 18, "DANFE", 11, True)
    label(left + 236, y - 30, "DOCUMENTO AUXILIAR DA", 5.5)
    label(left + 236, y - 37, "NOTA FISCAL ELETRÔNICA", 5.5)
    label(left + 236, y - 50, "0 - ENTRADA   1 - SAÍDA", 5.5)
    value(left + 236, y - 66, f"Nº {numero_br}", 7.5, True)
    value(left + 236, y - 78, "SÉRIE 001  FOLHA 1/1", 7)
    box(left + 334, y - 92, right - left - 334, 92)
    label(left + 338, y - 52, "CHAVE DE ACESSO", 5.5)
    value(left + 338, y - 62, _group_key(chave_da_nf(numero)), 6.6, True)
    label(left + 338, y - 78, "Consulta de autenticidade no portal nacional da NF-e", 5.5)

    y -= 100
    box(left, y - 20, right - left, 20)
    label(left + 4, y - 7, "NATUREZA DA OPERAÇÃO", 5.5)
    value(left + 4, y - 16, "VENDA DE MERCADORIA", 7)
    label(left + 300, y - 7, "INSCRIÇÃO ESTADUAL", 5.5)
    value(left + 300, y - 16, "0712345600123", 7)
    label(left + 420, y - 7, "CNPJ", 5.5)
    value(left + 420, y - 16, "12.345.678/0001-95", 7)

    # Destinatário
    y -= 30
    label(left, y, "DESTINATÁRIO / REMETENTE", 6)
    y -= 4
    box(left, y - 20, right - left, 20)
    label(left + 4, y - 7, "NOME / RAZÃO SOCIAL", 5.5)
    value(left + 4, y - 16, "CONDOMINIO RESIDENCIAL EXEMPLO", 7)
    label(left + 300, y - 7, "CNPJ / CPF", 5.5)
    value(left + 300, y - 16, "98.765.432/0001-10", 7)
    label(left + 450, y - 7, "DATA DA EMISSÃO", 5.5)
    value(left + 450, y - 16, EMISSION, 7)
    box(left, y - 40, right - left, 20)
    label(left + 4, y - 27, "ENDEREÇO", 5.5)
    value(left + 4, y - 36, "QUADRA 10 CONJUNTO A", 7)
    label(left + 450, y - 27, "DATA DA SAÍDA/ENTRADA", 5.5)
    value(left + 450, y - 36, EXIT_DATE, 7)

    # Cálculo do imposto
    y -= 50
    label(left, y, "CÁLCULO DO IMPOSTO", 6)
    y -= 4
    box(left, y - 20, right - left, 20)
    for x, text in ((4, "BASE DE CÁLC. DO ICMS"), (120, "VALOR DO ICMS"), (230, "BASE CÁLC. ICMS ST"), (340, "VALOR DO ICMS ST"), (440, "VALOR TOTAL DOS PRODUTOS")):
        label(left + x, y - 7, text, 5.5)
    for x, text in ((4, "1.501,90"), (120, "270,34"), (230, "0,00"), (340, "0,00"), (440, TOTAL_PRODUCTS)):
        value(left + x, y - 16, text, 7)
    box(left, y - 40, right - left, 20)
    for x, text in ((4, "VALOR DO FRETE"), (120, "VALOR DO SEGURO"), (230, "DESCONTO"), (340, "VALOR DO IPI"), (440, "VALOR TOTAL DA NOTA")):
        label(left + x, y - 27, text, 5.5)
    for x, text in ((4, "0,00"), (120, "0,00"), (230, "0,00"), (340, "0,00"), (440, TOTAL_PRODUCTS)):
        value(left + x, y - 36, text, 7)

    # Produtos
    y -= 50
    label(left, y, "DADOS DOS PRODUTOS / SERVIÇOS", 6)
    y -= 4
    columns = [(2, "CÓDIGO"), (50, "DESCRIÇÃO DO PRODUTO / SERVIÇO"), (215, "NCM/SH"), (252, "CST"), (272, "CFOP"), (296, "UN"), (316, "QUANT"), (360, "VALOR UNIT"), (410, "VALOR TOTAL"), (458, "BC ICMS"), (500, "V. ICMS"), (535, "ALÍQ")]
    box(left, y - 12, right - left, 12)
    for x, text in columns:
        label(left + x, y - 8, text, 5.5)
    row_y = y - 22
    for code, desc_lines, ncm, cst, cfop, unit, qty, price, total in ITEMS:
        total_value = float(total.replace(".", "").replace(",", "."))
        icms = f"{total_value * 0.18:.2f}".replace(".", ",")
        cells = [(2, code), (50, desc_lines[0]), (215, ncm), (252, cst), (272, cfop), (296, unit), (316, qty), (360, price), (410, total), (458, total), (500, icms), (535, "18,00")]
        for x, text in cells:
            value(left + x, row_y, text, 6.5)
        for extra in desc_lines[1:]:
            row_y -= 9
            value(left + 50, row_y, extra, 6.5)
        row_y -= 12
    box(left, row_y + 4, right - left, (y - 12) - (row_y + 4))

    row_y -= 14
    label(left, row_y, "DADOS ADICIONAIS", 6)
    box(left, row_y - 40, right - left, 36)
    label(left + 4, row_y - 12, "INFORMAÇÕES COMPLEMENTARES", 5.5)
    value(left + 4, row_y - 22, "PEDIDO 4567 - ENTREGA NO ALMOXARIFADO", 6.5)
    page.showPage()
    page.save()
    return buffer.getvalue()


def render_png(pdf_bytes: bytes, *, dpi: int = 300, rotate: int = 0) -> bytes:
    """A mesma página como foto/scan (PNG sem texto), para exercitar o OCR."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf_bytes)
    try:
        image = document[0].render(scale=dpi / 72, grayscale=True).to_pil()
    finally:
        document.close()
    if rotate:
        image = image.rotate(rotate, expand=True)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
