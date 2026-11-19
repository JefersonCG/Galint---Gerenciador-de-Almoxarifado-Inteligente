"""Conferência física pelo app: rotas /api/mobile/conferencia-estoque/*.

A autenticação do app (JWT/sessão de dispositivo) é simulada; a busca pelo código lido,
o serviço comum de contagem e a resposta são os reais.
"""
from flask import Flask
import pytest

from galint_flask.extensions import db
from galint_flask.models import Item, StockBalance
from galint_flask.services import stock_count_service
from galint_flask.services.inventory import inventory_service
from galint_flask.views import api_mobile


class _MobileUser:
    matricula = "op-7"
    nome = "Operador do App"


SNAPSHOT = {
    "codigo": "7891133006266",
    "descricao": "ESPUMA EXPANSIVA 500ML",
    "unidade": "Unidade",
    "saldo_exibido": 4.0,
    "saldo_display": "4 unidades",
    "admin_balance_input": {"supports_packaging": False, "internal_unit_display": "un", "internal_allow_decimal": False},
    "pre_cadastro_pendente": False,
}


@pytest.fixture
def mobile_client(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="mobile-stock-count-test",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    app.register_blueprint(api_mobile.blueprint)
    monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: _MobileUser() if token == "token-ok" else None)
    monkeypatch.setattr(api_mobile, "_mobile_user_block_info", lambda user: (False, None))
    monkeypatch.setattr(api_mobile, "_validate_mobile_session_token", lambda token, user: (True, None))
    monkeypatch.setattr(inventory_service, "get_admin_balance_snapshot", lambda code: dict(SNAPSHOT, codigo=code))
    with app.app_context():
        db.init_app(app)
        db.metadata.create_all(bind=db.engine, tables=TABLES)
        db.session.add(Item(
            codigo_item="7891133006266",
            descricao="ESPUMA EXPANSIVA 500ML",
            setor="Estoque",
            categoria="Mat. Pintura e Drywall",
            foto_path="uploads/itens/7891133006266_20261118_112227.webp",
        ))
        db.session.commit()
        yield app.test_client()
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=TABLES)


TABLES = [Item.__table__, StockBalance.__table__]
AUTH = {"Authorization": "Bearer token-ok"}


def test_lookup_finds_item_from_scanned_code_with_photo(mobile_client):
    # Leitor que devolve o EAN com o identificador de simbologia (]E0) também acha o item.
    response = mobile_client.get("/api/mobile/conferencia-estoque/item", query_string={"codigo": "]E07891133006266"}, headers=AUTH)

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["item"]["codigo"] == "7891133006266"
    assert payload["item"]["saldo_display"] == "4 unidades"
    assert payload["item"]["foto_url"] == "/static/uploads/itens/7891133006266_20261118_112227.webp"
    assert payload["item"]["categoria"] == "Mat. Pintura e Drywall"


def test_lookup_requires_login_and_reports_unknown_code(mobile_client):
    assert mobile_client.get("/api/mobile/conferencia-estoque/item", query_string={"codigo": "x"}).status_code == 401
    unknown = mobile_client.get("/api/mobile/conferencia-estoque/item", query_string={"codigo": "0000000"}, headers=AUTH)
    assert unknown.status_code == 404
    assert unknown.get_json()["message"] == "Item não encontrado."


def test_adjust_records_zero_count_with_app_as_audit_source(mobile_client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        inventory_service,
        "apply_admin_item_adjustments",
        lambda **kwargs: calls.append(kwargs) or {"changed": True, "codigo_atual": "7891133006266", "message": "Saldo atualizado."},
    )
    # O saldo exibido lê entradas/saídas, que este banco mínimo não tem.
    monkeypatch.setattr(Item, "get_saldo_fisico_display", lambda self: "0 unidades")

    response = mobile_client.post(
        "/api/mobile/conferencia-estoque/ajuste",
        json={"codigo": "7891133006266", "mode": "direct", "quantity": "0"},
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert response.get_json()["saldo_display"] == "0 unidades"
    assert calls[0]["adjustment_payload"] == {"admin_balance_mode": "direct", "admin_balance_direct_value": "0"}
    assert calls[0]["matricula"] == "op-7"
    assert calls[0]["motivo"] == "Contagem física pelo app (código de barras)"
    assert calls[0]["audit_context"]["source"] == stock_count_service.SOURCE_MOBILE_APP
    assert calls[0]["audit_context"]["user_name"] == "Operador do App"


def test_adjust_returns_engine_validation_message(mobile_client, monkeypatch):
    def refuse(**_kwargs):
        raise ValueError("Item com pré-cadastro pendente não pode ter o saldo ajustado.")

    monkeypatch.setattr(inventory_service, "apply_admin_item_adjustments", refuse)
    pending = mobile_client.post(
        "/api/mobile/conferencia-estoque/ajuste",
        json={"codigo": "7891133006266", "mode": "direct", "quantity": "3"},
        headers=AUTH,
    )
    bad_mode = mobile_client.post(
        "/api/mobile/conferencia-estoque/ajuste",
        json={"codigo": "7891133006266", "mode": "outro"},
        headers=AUTH,
    )
    no_code = mobile_client.post("/api/mobile/conferencia-estoque/ajuste", json={"mode": "direct"}, headers=AUTH)

    assert pending.status_code == 400
    assert "pré-cadastro" in pending.get_json()["message"]
    assert bad_mode.status_code == 400
    assert bad_mode.get_json()["message"] == "Modo de contagem inválido."
    assert no_code.status_code == 400
