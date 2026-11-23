"""Financeiro numa página só (23/11/2026): rotas do consumo que a aba Consumo usa.

O painel de Consumo e as subpáginas viraram a aba Consumo do Financeiro, com o detalhe num modal
(/itens/consumo/detalhe) e o arquivo em PDF ou Excel. O serviço financeiro é simulado com um painel
de exemplo; as rotas e o gerador de relatório são os reais.
"""
from datetime import date
from io import BytesIO

import openpyxl
import pytest
from flask import Flask
from flask_login import LoginManager

from galint_flask.services.finance_service import finance_service
from galint_flask.views import inventory

PANEL = {
    "exercise": {"label": "2026", "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31)},
    "exercise_options": [{"label": "2026"}],
    "overview": {"total_valor": 459.9, "saidas": 1, "itens": 1, "locais": 1, "colaboradores": 1},
    "locations": [{"local": "PORTARIA", "total_valor": 459.9, "saidas": 1, "itens": 1, "colaboradores": 1}],
    "categories": [{"categoria": "Mat. Pintura e Drywall", "total_valor": 459.9, "saidas": 1, "locais": 1, "colaboradores": 1}],
    "employees": [{"nome": "JOÃO PEDRO", "matricula": "1002", "total_valor": 459.9, "saidas": 1, "locais": 1}],
    "entries": [{
        "data_saida_label": "23/11/2026 14:05", "colaborador_nome": "JOÃO PEDRO", "descricao_item": "TINTA ACRÍLICA 18L",
        "categoria": "Mat. Pintura e Drywall", "local": "PORTARIA", "contexto_uso": "Pintura do hall",
        "quantidade_display": "1 lata", "valor_total": 459.9,
    }],
    "scope_type": "local",
    "filters": {"local": "PORTARIA"},
}


class _Admin:
    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_admin = True

    def get_id(self):
        return "adm"


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="finance-single-page", TESTING=True)
    manager = LoginManager(app)
    manager.request_loader(lambda request: _Admin())
    app.register_blueprint(inventory.blueprint)
    calls = []

    def fake_panel(exercise=None, *, local_name=None, category_name=None, employee_id=None):
        calls.append((exercise, local_name, category_name, employee_id))
        return PANEL

    monkeypatch.setattr(finance_service, "get_consumption_panel_report", fake_panel)
    client = app.test_client()
    client.calls = calls
    return client


def test_detail_returns_rows_and_export_links(client):
    response = client.get("/itens/consumo/detalhe", query_string={"exercicio": "2026", "local": "PORTARIA"})

    data = response.get_json()
    assert response.status_code == 200
    assert client.calls == [("2026", "PORTARIA", None, None)]
    assert data["titulo"] == "PORTARIA"
    assert data["linhas"] == [{
        "data": "23/11/2026 14:05", "colaborador": "JOÃO PEDRO", "material": "TINTA ACRÍLICA 18L",
        "local": "PORTARIA · Pintura do hall", "quantidade": "1 lata", "valor": 459.9,
    }]
    assert data["pdf_url"] == "/itens/consumo/relatorio/pdf?exercicio=2026&local=PORTARIA"
    assert data["xlsx_url"] == "/itens/consumo/relatorio/xlsx?exercicio=2026&local=PORTARIA"


def test_xlsx_export(client):
    response = client.get("/itens/consumo/relatorio/xlsx", query_string={"exercicio": "2026", "local": "PORTARIA"})

    assert response.status_code == 200
    book = openpyxl.load_workbook(BytesIO(response.data))
    assert "Lançamentos" in book.sheetnames


def test_old_consumption_pages_open_the_consumption_tab(client):
    assert client.get("/itens/consumo").headers["Location"] == "/itens/valor-estoque?aba=consumo"
    local = client.get("/itens/consumo/local", query_string={"local": "PORTARIA", "exercicio": "2026"})
    assert local.headers["Location"] == "/itens/valor-estoque?aba=consumo&exercicio=2026&local=PORTARIA"
    employee = client.get("/itens/consumo/funcionario/1002")
    assert employee.headers["Location"] == "/itens/valor-estoque?aba=consumo&matricula=1002"
