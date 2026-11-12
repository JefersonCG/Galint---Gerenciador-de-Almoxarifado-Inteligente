from types import SimpleNamespace
import base64
import gzip

from defusedxml import ElementTree

from galint_flask.services.nfe_distribution_service import (
    _decode_doc_zip,
    _parse_document,
    _process_response,
    _soap_body,
)


def test_parse_complete_nfe_xml():
    xml_data = b"""<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
      <NFe><infNFe Id="NFe35261112345678000199550010000001231234567890">
        <ide><nNF>123</nNF><serie>1</serie><dhEmi>2026-11-10T12:30:00-03:00</dhEmi></ide>
        <emit><CNPJ>12345678000199</CNPJ><xNome>Fornecedor Exemplo</xNome></emit>
        <det nItem="1"><prod><cProd>MAT-1</cProd><xProd>Parafuso zincado</xProd><NCM>73181500</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>2.0000</qCom><vUnCom>5.00</vUnCom><vProd>10.00</vProd></prod></det>
        <total><ICMSTot><vNF>250.75</vNF></ICMSTot></total>
      </infNFe></NFe>
    </nfeProc>"""

    parsed = _parse_document(xml_data)

    assert parsed is not None
    assert parsed["chave_acesso"] == "35261112345678000199550010000001231234567890"
    assert parsed["numero_documento"] == "123"
    assert parsed["emitente"] == "Fornecedor Exemplo"
    assert parsed["cnpj_emitente"] == "12345678000199"
    assert parsed["data_emissao"].isoformat() == "2026-11-10"
    assert parsed["valor_total"] == 250.75
    assert parsed["resumo"] is False
    assert parsed["itens"] == [{
        "numero_item": "1",
        "codigo": "MAT-1",
        "descricao": "Parafuso zincado",
        "ncm": "73181500",
        "cfop": "5102",
        "unidade": "UN",
        "quantidade": 2.0,
        "valor_unitario": 5.0,
        "valor_total": 10.0,
    }]


def test_parse_nfe_summary_without_items():
    parsed = _parse_document(
        b"""<resNFe xmlns="http://www.portalfiscal.inf.br/nfe">
          <chNFe>35261112345678000199550010000001231234567890</chNFe>
          <CNPJ>12345678000199</CNPJ><xNome>Fornecedor</xNome>
          <dhEmi>2026-11-10T12:30:00-03:00</dhEmi><vNF>100.00</vNF>
          <nNF>123</nNF><serie>1</serie>
        </resNFe>"""
    )

    assert parsed is not None
    assert parsed["resumo"] is True
    assert parsed["chave_acesso"].endswith("1234567890")
    assert parsed["valor_total"] == 100.0


def test_decode_distribution_gzip_payload():
    xml_data = b"<resNFe><nNF>7</nNF></resNFe>"
    encoded = base64.b64encode(gzip.compress(xml_data)).decode("ascii")
    element = ElementTree.fromstring(f'<docZip NSU="42" schema="resNFe_v1.01">{encoded}</docZip>')

    assert _decode_doc_zip(element) == xml_data


def test_distribution_response_accepts_soap_escaped_payload():
    config = SimpleNamespace(ultimo_nsu="000000000000001", maximo_nsu="000000000000001")
    config.ultimo_status = None
    config.ultima_mensagem = None
    response = b"""<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
      <soap:Body><nfeDistDFeInteresseResponse>
        <nfeDistDFeInteresseResult>&lt;retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe"&gt;
          &lt;tpAmb&gt;1&lt;/tpAmb&gt;&lt;cStat&gt;137&lt;/cStat&gt;&lt;xMotivo&gt;Nenhum documento localizado&lt;/xMotivo&gt;
          &lt;ultNSU&gt;000000000000002&lt;/ultNSU&gt;&lt;maxNSU&gt;000000000000004&lt;/maxNSU&gt;
        &lt;/retDistDFeInt&gt;</nfeDistDFeInteresseResult>
      </nfeDistDFeInteresseResponse></soap:Body>
    </soap:Envelope>"""

    result = _process_response(config, response)

    assert result["status"] == "137"
    assert result["ultimo_nsu"] == "000000000000002"
    assert result["maximo_nsu"] == "000000000000004"
    assert result["imported"] == 0


def test_soap_request_uses_configured_recipient_and_nsu():
    request_xml = _soap_body("12345678000199", "35", "producao", "23").decode("utf-8")

    assert "<tpAmb>1</tpAmb>" in request_xml
    assert "<cUFAutor>35</cUFAutor>" in request_xml
    assert "<CNPJ>12345678000199</CNPJ>" in request_xml
    assert "<ultNSU>000000000000023</ultNSU>" in request_xml
