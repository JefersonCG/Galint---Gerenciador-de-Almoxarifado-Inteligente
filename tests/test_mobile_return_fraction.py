"""Devolução pelo app: ferramenta, fracionado ou unitário (pedido do usuário em 26/11/2026).

"Preciso que o APK, sempre que for devolução, reconheça se é ferramenta, fracionado ou item unitário. Se
devolver uma lata de tinta pela metade, tenho que pôr que foi metade." O app pergunta o tipo em
/api/mobile/devolucao/tipo/<codigo> e manda a quantidade na unidade de devolução (½ lata de 18 L = 9 L).
"""
from datetime import datetime

import pytest
from flask import Flask
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import Entrada, InventarioEvento, Item, Saida, Usuario
from galint_flask.views import api_mobile

AUTH = {"Authorization": "Bearer token-ok"}
TINTA = "7891323079339"


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@compiles(INET, "sqlite")
def _inet_as_text_on_sqlite(element, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="devolucao-fracionada", SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    app.register_blueprint(api_mobile.blueprint)
    with app.app_context():
        db.init_app(app)
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        db.session.add(Usuario(matricula="9001", nome="ADMINISTRADOR", is_admin=True))
        db.session.add_all([
            Item(codigo_item=TINTA, descricao="TINTA PISO AMARELO 18L", unidade="Litro", categoria="Pintura", setor="ALMOXARIFADO",
                 tipo_embalagem_novo="lata", litros_por_embalagem=18),
            Item(codigo_item="ARRUELA", descricao="ARRUELA 5/16", unidade="Unidade", categoria="Fixação", setor="ALMOXARIFADO",
                 tipo_embalagem_novo="pacote", unidades_por_embalagem=300),
            Item(codigo_item="TRENA", descricao="TRENA 5M", unidade="Unidade", categoria="Ferramentas", setor="ALMOXARIFADO"),
        ])
        db.session.commit()
        monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: Usuario.query.get("9001") if token == "token-ok" else None)
        from galint_flask.services import notification_router

        monkeypatch.setattr(notification_router.NotificationRouterService, "route_inventory_event", staticmethod(lambda *args, **kwargs: None))
        yield app.test_client()
        db.session.remove()


def test_paint_can_returns_in_liters_with_the_can_content(client):
    data = client.get(f"/api/mobile/devolucao/tipo/{TINTA}", headers=AUTH).get_json()["data"]
    assert data == {"tipo": "fracionado", "unidade": "litro", "unidade_curta": "L", "decimal": True, "embalagem": "lata", "conteudo": 18.0}


def test_tool_and_unit_items(client):
    assert client.get("/api/mobile/devolucao/tipo/TRENA", headers=AUTH).get_json()["data"]["tipo"] == "ferramenta"
    arruela = client.get("/api/mobile/devolucao/tipo/ARRUELA", headers=AUTH).get_json()["data"]
    assert (arruela["tipo"], arruela["unidade"], arruela["decimal"]) == ("unitario", "unidade", False)
    assert client.get("/api/mobile/devolucao/tipo/NAOEXISTE", headers=AUTH).status_code == 404
    assert client.get(f"/api/mobile/devolucao/tipo/{TINTA}").status_code == 401


def test_half_can_is_returned_as_nine_liters(client):
    # Duas latas no estoque; uma sai inteira (18 L) e volta pela metade.
    db.session.add(Entrada(codigo_item=TINTA, matricula="9001", quantidade=36, data_entrada=datetime(2026, 11, 20, 8, 0)))
    db.session.add(Saida(codigo_item=TINTA, matricula="9001", quantidade=18, data_saida=datetime(2026, 11, 25, 8, 0)))
    db.session.commit()

    response = client.post("/api/mobile/devolver_material", headers=AUTH,
                           json={"codigo": TINTA, "quantidade": 9, "unidade": "litro", "matricula_devolvedor": "9001"})
    assert response.status_code == 201, response.get_json()
    evento = InventarioEvento.query.filter_by(codigo_item=TINTA, tipo="devolucao_material").one()
    assert evento.quantidade == 9.0
    assert "Devolvido: 9 L" in evento.descricao


def test_unit_item_does_not_accept_a_fraction(client):
    response = client.post("/api/mobile/devolver_material", headers=AUTH,
                           json={"codigo": "ARRUELA", "quantidade": 2.5, "matricula_devolvedor": "9001"})
    assert response.status_code == 400
    assert response.get_json()["message"] == "Este item volta em quantidade inteira."


# 27/11/2026: a LUVA CORRER SOLDA 25MM voltou e o app só dizia "não há retirada pendente para este material". A única
# retirada (ISAQUE GABRIEL, 07/08/2026) já tinha voltado em 04/09/2026; pedido do usuário: "seria mais fácil a
# mensagem explicar isso, que já havia sido devolvida".
def _luva_com_retirada_devolvida():
    db.session.add_all([
        Usuario(matricula="9370968490078", nome="ISAQUE GABRIEL"),
        Usuario(matricula="1740", nome="GLÁUCIA (SERVIÇOS GERAIS)"),
        Item(codigo_item="LUVA25", descricao="LUVA CORRER SOLDA 25MM", unidade="Unidade", categoria="Material Hidráulico", setor="ALMOXARIFADO"),
    ])
    db.session.add(Entrada(codigo_item="LUVA25", matricula="9001", quantidade=12, data_entrada=datetime(2026, 8, 1, 8, 0)))
    db.session.add(Saida(codigo_item="LUVA25", matricula="9370968490078", quantidade=1, data_saida=datetime(2026, 8, 7, 16, 55)))
    db.session.add(InventarioEvento(codigo_item="LUVA25", matricula="9370968490078", tipo="devolucao_material", quantidade=1,
                                    descricao="Devolução de Material: LUVA", data_evento=datetime(2026, 9, 4, 20, 4)))
    db.session.commit()


def test_refused_return_says_it_was_already_returned(client):
    _luva_com_retirada_devolvida()
    response = client.post("/api/mobile/devolver_material", headers=AUTH,
                           json={"codigo": "LUVA25", "quantidade": 1, "matricula_devolvedor": "1740"})
    assert response.status_code == 400
    mensagem = response.get_json()["message"]
    assert mensagem.startswith("Já devolvida: a última retirada (1 unidade, ISAQUE GABRIEL, ")
    assert "voltou em " in mensagem
    assert InventarioEvento.query.filter_by(codigo_item="LUVA25", tipo="devolucao_material").count() == 1


def test_material_never_withdrawn_says_so(client):
    _luva_com_retirada_devolvida()
    db.session.add(Item(codigo_item="NUNCA", descricao="CAP 25MM", unidade="Unidade", categoria="Material Hidráulico", setor="ALMOXARIFADO"))
    db.session.commit()
    response = client.post("/api/mobile/devolver_material", headers=AUTH,
                           json={"codigo": "NUNCA", "quantidade": 1, "matricula_devolvedor": "1740"})
    assert response.status_code == 400
    assert response.get_json()["message"] == "Devolução não permitida: este material não tem retirada registrada no GALINT."


def test_return_by_someone_else_settles_the_withdrawer_pending(client):
    # Quem devolve (GLÁUCIA) não é quem retirou (ISAQUE): abate a retirada dele, como o site já permite.
    _luva_com_retirada_devolvida()
    db.session.add(Saida(codigo_item="LUVA25", matricula="9370968490078", quantidade=3, data_saida=datetime(2026, 11, 20, 9, 0)))
    db.session.commit()
    response = client.post("/api/mobile/devolver_material", headers=AUTH,
                           json={"codigo": "LUVA25", "quantidade": 2, "matricula_devolvedor": "1740"})
    assert response.status_code == 201, response.get_json()
    evento = InventarioEvento.query.filter_by(codigo_item="LUVA25", tipo="devolucao_material").order_by(InventarioEvento.id_evento.desc()).first()
    assert evento.matricula == "9370968490078"
    assert "Retirado por: ISAQUE GABRIEL" in evento.descricao and "Devolvido por: GLÁUCIA" in evento.descricao
