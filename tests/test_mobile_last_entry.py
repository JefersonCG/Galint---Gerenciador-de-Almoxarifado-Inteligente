"""Última NF do item para o cartão do "Lançar entrada" no app (24/11/2026): GET /api/mobile/itens/<codigo>/ultima_entrada.

Pedido do usuário: mostrar no cartão do item o número da NF e a data da entrada anterior. A NF mais recente é
a de recebimento mais novo; documento sem data fica por último.
"""
from datetime import date

import pytest
from flask import Flask
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Item, Usuario
from galint_flask.views import api_mobile

AUTH = {"Authorization": "Bearer token-ok"}


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@compiles(INET, "sqlite")
def _inet_as_text_on_sqlite(element, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="ultima-entrada", SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    app.register_blueprint(api_mobile.blueprint)
    with app.app_context():
        db.init_app(app)
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        db.session.add(Usuario(matricula="9001", nome="ADMINISTRADOR", is_admin=True))
        db.session.add(Item(codigo_item="7898472259629", descricao="SILICONE ACÉTICO TRANSPARENTE 256g", unidade="Unidade", categoria="Material/Uso geral", setor="ALMOXARIFADO"))
        for numero, recebimento, quantidade in (("2418474", date(2026, 6, 29), 10), ("617377", date(2026, 11, 23), 12), ("SEM-DATA", None, 1)):
            documento = DocumentoEntradaEstoque(numero_documento=numero, tipo_documento="nf", data_recebimento=recebimento, data_emissao=recebimento)
            db.session.add(documento)
            db.session.flush()
            db.session.add(DocumentoEntradaEstoqueItem(documento_id=documento.id_documento, codigo_item="7898472259629", quantidade=quantidade, unidade_quantidade="unidade"))
        db.session.commit()
        monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: Usuario.query.get("9001") if token == "token-ok" else None)
        yield app.test_client()
        db.session.remove()


def test_last_entry_is_the_most_recent_received_nf(client):
    response = client.get("/api/mobile/itens/7898472259629/ultima_entrada", headers=AUTH)
    data = response.get_json()["data"]
    assert response.status_code == 200
    assert (data["numero"], data["data"], data["quantidade"], data["tipo_documento"]) == ("617377", "2026-11-23", 12.0, "nf")


def test_item_without_entries_returns_nothing(client):
    response = client.get("/api/mobile/itens/0000000000000/ultima_entrada", headers=AUTH)
    assert response.status_code == 200 and response.get_json()["data"] is None


def test_requires_login(client):
    assert client.get("/api/mobile/itens/7898472259629/ultima_entrada").status_code == 401
