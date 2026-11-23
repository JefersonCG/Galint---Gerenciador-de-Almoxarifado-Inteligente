"""Retirada de vários itens pelo app: POST /api/mobile/retirar_multipla.

Defeito de 23/11/2026 (print do usuário: "Erro interno ao processar retiradas"): desde eb50423a
(09/04/2026) a rota usava "quantidade_int", nome que não existe nela. O NameError derrubava toda
retirada múltipla, e na ferramenta a custódia do dia também não era criada. O saldo, o razão e o aviso
são simulados; a rota, a saída e a custódia são as reais (SQLite em memória).
"""
import pytest
from flask import Flask

from galint_flask.extensions import db
from galint_flask.models import Item, ProductUnit, RetiradaFerramenta, Saida, Usuario
from galint_flask.services.inventory import inventory_service
from galint_flask.views import api_mobile

TABLES = [Item.__table__, ProductUnit.__table__, Usuario.__table__, Saida.__table__, RetiradaFerramenta.__table__]
AUTH = {"Authorization": "Bearer token-ok"}


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="multiple-withdrawal-test",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    app.register_blueprint(api_mobile.blueprint)
    monkeypatch.setattr(Item, "get_saldo_atual", lambda self: 10.0)
    monkeypatch.setattr(inventory_service, "validate_exit_payload_policy", lambda item, payload: None)
    monkeypatch.setattr(inventory_service, "_ensure_tool_withdrawal_limit", lambda *args, **kwargs: 1)
    monkeypatch.setattr(inventory_service, "mirror_legacy_movement", lambda **kwargs: None)
    monkeypatch.setattr(inventory_service, "invalidate_realtime_views", lambda: None)
    from galint_flask.services import notification_router

    monkeypatch.setattr(notification_router.NotificationRouterService, "route_multiple_withdrawal", staticmethod(lambda ids: {}))
    with app.app_context():
        db.init_app(app)
        db.metadata.create_all(bind=db.engine, tables=TABLES)
        operator = Usuario(matricula="1001", nome="MELQUESEDEQUE")
        db.session.add_all([
            operator,
            Item(codigo_item="7898907779036", descricao='PANO XADREZ 42X68CM "M"', categoria="Limpeza", unidade="Unidade", setor="Estoque"),
            Item(codigo_item="7891000000001", descricao="SACO DE LIXO 100L", categoria="Limpeza", unidade="Unidade", setor="Estoque"),
            Item(codigo_item="FER-1", descricao="FURADEIRA", categoria="Ferramentas Elétricas", unidade="Unidade", setor="Estoque"),
        ])
        db.session.commit()
        monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: Usuario.query.get("1001") if token == "token-ok" else None)
        yield app.test_client()
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=TABLES)


def _post(client, itens):
    return client.post(
        "/api/mobile/retirar_multipla",
        json={"itens": itens, "matricula_retirante": "1001", "local_servico": "para uso nos blocos"},
        headers=AUTH,
    )


def test_multiple_withdrawal_records_every_item(client):
    response = _post(client, [
        {"codigo": "7898907779036", "quantidade": 4},
        {"codigo": "7891000000001", "quantidade": 2},
    ])

    payload = response.get_json()
    assert response.status_code == 201, payload
    assert payload["success"] is True
    assert [row["quantidade"] for row in payload["resultados"]] == [4, 2]
    saidas = Saida.query.order_by(Saida.id_saida).all()
    assert [(s.codigo_item, s.quantidade, s.local_servico) for s in saidas] == [
        ("7898907779036", 4, "PARA USO NOS BLOCOS"),
        ("7891000000001", 2, "PARA USO NOS BLOCOS"),
    ]


def test_tool_in_multiple_withdrawal_opens_the_daily_custody(client):
    response = _post(client, [
        {"codigo": "FER-1", "quantidade": 1},
        {"codigo": "7891000000001", "quantidade": 1},
    ])

    assert response.status_code == 201, response.get_json()
    custody = RetiradaFerramenta.query.all()
    assert [(r.codigo_item, r.quantidade, r.status) for r in custody] == [("FER-1", 1, "em_uso")]


def test_unavailable_tool_is_skipped_without_recording_its_exit(client):
    db.session.add(RetiradaFerramenta(codigo_item="FER-1", matricula="1001", quantidade=10, status="em_uso"))
    db.session.commit()

    response = _post(client, [
        {"codigo": "FER-1", "quantidade": 1},
        {"codigo": "7891000000001", "quantidade": 1},
    ])

    payload = response.get_json()
    assert response.status_code == 201, payload
    assert payload["resultados"][0]["success"] is False
    assert "indisponível" in payload["resultados"][0]["message"]
    assert [s.codigo_item for s in Saida.query.all()] == ["7891000000001"]
