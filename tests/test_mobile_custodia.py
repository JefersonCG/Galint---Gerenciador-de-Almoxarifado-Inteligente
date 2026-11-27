"""Com quem está a ferramenta (app 2.6.2, comando de voz "custódia"): GET /api/mobile/custodia.

Pedido do usuário em 27/11/2026: "coloca um comando de custódia, para sabermos com quem está a ferramenta".
A rota usa a mesma conta da página Custódia de ferramentas do site: saída de ferramenta sem devolução depois dela.
"""
from datetime import datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import InventarioEvento, Item, Saida, Usuario
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
    app.config.update(SECRET_KEY="custodia", SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    app.register_blueprint(api_mobile.blueprint)
    with app.app_context():
        db.init_app(app)
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        db.session.add_all([
            Usuario(matricula="9001", nome="ADMINISTRADOR", is_admin=True),
            Usuario(matricula="1740", nome="GLÁUCIA (SERVIÇOS GERAIS)"),
            Usuario(matricula="2001", nome="ANTONIO"),
            Item(codigo_item="0265", descricao="PARAFUSADEIRA WESCO 18V", unidade="Unidade", categoria="Ferramentas", setor="ALMOXARIFADO"),
            Item(codigo_item="0300", descricao="TRENA 5M", unidade="Unidade", categoria="Ferramentas", setor="ALMOXARIFADO"),
            Item(codigo_item="7891", descricao="PAPEL TOALHA INTERFOLHAS", unidade="Unidade", categoria="Limpeza", setor="ALMOXARIFADO"),
        ])
        agora = datetime(2026, 11, 27, 9, 0)
        db.session.add_all([
            Saida(codigo_item="0265", matricula="2001", quantidade=1, data_saida=agora - timedelta(days=2), local_servico="BLOCO A", tipo_custodia="temporaria"),
            Saida(codigo_item="0300", matricula="1740", quantidade=1, data_saida=agora - timedelta(days=40), tipo_custodia="permanente"),
            # trena da Gláucia que já voltou: não aparece
            Saida(codigo_item="0300", matricula="2001", quantidade=1, data_saida=agora - timedelta(days=5)),
            # material não é custódia
            Saida(codigo_item="7891", matricula="1740", quantidade=5, data_saida=agora),
        ])
        db.session.add(InventarioEvento(tipo="devolucao_ferramenta", codigo_item="0300", matricula="2001", quantidade=1, data_evento=agora - timedelta(days=4)))
        db.session.commit()
        monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: Usuario.query.get("9001") if token == "token-ok" else None)
        yield app.test_client()
        db.session.remove()


def test_lists_who_has_each_tool(client):
    response = client.get("/api/mobile/custodia", headers=AUTH)
    assert response.status_code == 200
    linhas = response.get_json()["data"]
    assert [(linha["descricao"], linha["nome"], linha["tipo_custodia"]) for linha in linhas] == [
        ("PARAFUSADEIRA WESCO 18V", "ANTONIO", "temporaria"),
        ("TRENA 5M", "GLÁUCIA (SERVIÇOS GERAIS)", "permanente"),
    ]
    assert linhas[0]["local"] == "BLOCO A" and linhas[1]["local"] == ""


def test_filters_one_tool_by_code(client):
    linhas = client.get("/api/mobile/custodia?codigo=0265", headers=AUTH).get_json()["data"]
    assert [(linha["codigo"], linha["nome"]) for linha in linhas] == [("0265", "ANTONIO")]


def test_unknown_code_and_login(client):
    assert client.get("/api/mobile/custodia?codigo=999999", headers=AUTH).status_code == 404
    assert client.get("/api/mobile/custodia").status_code == 401
