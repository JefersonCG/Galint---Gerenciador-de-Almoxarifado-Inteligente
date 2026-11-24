"""Páginas "Ler NF" e "Conferir NF" (24/11/2026) montadas com dados reais do leitor.

O base.html do site depende do app inteiro (menu, tema, PostgreSQL); aqui ele é trocado por um esqueleto
com os mesmos blocos, e as páginas novas são as reais. Confere que montam e mostram o que importa.
"""
import json
from datetime import date
from types import SimpleNamespace

import jinja2
import pytest

from galint_flask.services import nf_ocr
from tests.danfe_sample import build_danfe_pdf

TEMPLATES = "galint_flask/templates"
BASE = "<html>{% block title %}{% endblock %}{% block content %}{% endblock %}{% block scripts %}{% endblock %}</html>"


@pytest.fixture(scope="module")
def env():
    environment = jinja2.Environment(
        loader=jinja2.ChoiceLoader([jinja2.DictLoader({"base.html": BASE}), jinja2.FileSystemLoader(TEMPLATES)]),
        autoescape=True,
    )
    environment.filters["currency_br"] = lambda value, default="R$ 0,00": f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if value else default
    environment.globals["url_for"] = lambda endpoint, **kwargs: f"/{endpoint}/" + "/".join(str(value) for value in kwargs.values())
    environment.globals["endpoint_exists"] = lambda endpoint: True
    return environment


@pytest.fixture(scope="module")
def result():
    parsed = nf_ocr.read_and_parse(build_danfe_pdf(), "nf.pdf")
    for item in parsed["itens"]:
        item["sugestoes"] = [{"codigo": "FITA001", "descricao": "FITA ISOLANTE 19MM 20M", "marca": "3M", "unidade": "Metro", "score": 0.81, "motivo": "nome parecido",
                              "fator_embalagem": 20.0, "unidade_documental": "rolo", "converte_embalagem": True}] if item["n"] == 4 else []
        item["acao"] = "FITA001" if item["n"] == 4 else "novo"
    return parsed


def test_review_page_renders_compact_form(env, result):
    reading = SimpleNamespace(id=7, arquivo_nome="nf.pdf")
    html = env.get_template("nf/leitura_conferir.html").render(
        reading=reading, result=result, header=result["cabecalho"], items=result["itens"], launched=set(), today=date(2026, 11, 24).isoformat()
    )
    assert 'name="numero" value="12345"' in html
    assert 'name="data_emissao" type="date" value="2026-11-18"' in html
    assert 'value="CABO FLEXIVEL 2,5MM AZUL ROLO 100M"' in html
    assert 'name="quantidade_1" inputmode="decimal" value="2"' in html
    assert 'name="valor_unitario_1" inputmode="decimal" value="289,90"' in html
    assert 'name="valor_unitario_6" inputmode="decimal" value="0,35"' in html
    assert '<option value="FITA001" data-fator="20.0" data-unidade-doc="rolo" data-unidade-base="Metro" data-converte="true" selected>FITA ISOLANTE 19MM 20M · 3M · Metro (81%)</option>' in html
    assert 'js/nf-prova-real.js' in html and 'data-role="prova"' in html  # prova real (24/11/2026)
    assert html.count("Item novo (pré-cadastro)") == 6


def test_list_page_renders_statuses(env, result):
    readings = [
        SimpleNamespace(id=1, status="lida", numero_documento="12345", fornecedor_nome="FERRAGENS SAO JOSE LTDA", valor_total=1501.9, arquivo_nome="a.pdf", mensagem=None),
        SimpleNamespace(id=2, status="lendo", numero_documento=None, fornecedor_nome=None, valor_total=None, arquivo_nome="b.jpg", mensagem=None),
        SimpleNamespace(id=3, status="erro", numero_documento=None, fornecedor_nome=None, valor_total=None, arquivo_nome="c.png", mensagem="Tesseract não encontrado neste servidor."),
    ]
    html = env.get_template("nf/leitura.html").render(
        readings=readings,
        results={1: json.loads(json.dumps(result)), 2: {}, 3: {}},
        status_labels={"lendo": "Lendo…", "lida": "Pronta para conferir", "erro": "Erro", "lancada": "Lançada"},
        ocr={"ok": True, "pdf": True, "message": ""},
        accept=".jpg,.pdf",
    )
    assert "Pronta para conferir" in html and "R$ 1.501,90" in html
    assert 'data-status="lendo"' in html and "Tesseract não encontrado" in html
    assert "/nf_leitura.conferir/1" in html
