"""Saldos em lote para listas do estoque inteiro (app, resumo, soma do estoque).

Origem: em 21/11/2026 o app pedia a lista completa a cada 5 s e o servidor levava ~28 s
(20.698 consultas) para montá-la; os pedidos abandonados entupiam o servidor e a leitura de
código da conferência e da saída dava "Sem conexão" / "Item não encontrado".
"""
from flask import Flask
from sqlalchemy import event
import pytest

from galint_flask import models
from galint_flask.extensions import db
from galint_flask.models import Entrada, InventarioEvento, Item, ProductUnit, Saida, StockBalance
from galint_flask.services.balance_provider import balance_provider
from galint_flask.services.inventory import inventory_service
from galint_flask.views import api_mobile


TABLES = [
    Item.__table__,
    StockBalance.__table__,
    ProductUnit.__table__,
    Entrada.__table__,
    Saida.__table__,
    InventarioEvento.__table__,
]
AUTH = {"Authorization": "Bearer token-ok"}


class _MobileUser:
    matricula = "op-7"
    nome = "Operador do App"


@pytest.fixture
def app_with_stock(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="balance-prefetch-test",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    app.register_blueprint(api_mobile.blueprint)
    monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: _MobileUser() if token == "token-ok" else None)
    monkeypatch.setattr(api_mobile, "_mobile_user_block_info", lambda user: (False, None))
    monkeypatch.setattr(api_mobile, "_validate_mobile_session_token", lambda token, user: (True, None))
    with app.app_context():
        db.init_app(app)
        db.metadata.create_all(bind=db.engine, tables=TABLES)
        db.session.add_all([
            Item(codigo_item="A-MIGRADO", descricao="ALFA", setor="Estoque", categoria="Geral", unidade="Unidade"),
            Item(codigo_item="B-PENDENTE", descricao="BETA", setor="Estoque", categoria="Geral", unidade="Unidade"),
            Item(codigo_item="C-SEM-SALDO", descricao="GAMA", setor="Estoque", categoria="Geral", unidade="Unidade"),
        ])
        db.session.flush()
        db.session.add_all([
            StockBalance(product_id="A-MIGRADO", quantity_base=7.0, read_model_ready=True),
            StockBalance(product_id="B-PENDENTE", quantity_base=3.0, read_model_ready=False),
        ])
        db.session.commit()
        yield app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=TABLES)


def _count_queries():
    counter = {"n": 0}

    def _on_execute(*_args, **_kwargs):
        counter["n"] += 1

    event.listen(db.engine, "before_cursor_execute", _on_execute)
    return counter, lambda: event.remove(db.engine, "before_cursor_execute", _on_execute)


def test_prefetched_balances_match_one_by_one_and_end_with_the_block(app_with_stock):
    with app_with_stock.app_context():
        items = Item.query.order_by(Item.codigo_item).all()
        one_by_one = {item.codigo_item: balance_provider.get_balance(item.codigo_item, item=item) for item in items}
        db.session.expire_all()

        with balance_provider.prefetched_balances(items) as snapshots:
            counter, stop = _count_queries()
            inside = {item.codigo_item: balance_provider.get_balance(item.codigo_item, item=item) for item in items}
            stop()

        assert {code: snap.quantity_base for code, snap in inside.items()} == {"A-MIGRADO": 7.0, "B-PENDENTE": 3.0, "C-SEM-SALDO": 0.0}
        assert {code: snap.quantity_base for code, snap in one_by_one.items()} == {code: snap.quantity_base for code, snap in inside.items()}
        assert set(snapshots) == {"A-MIGRADO", "B-PENDENTE", "C-SEM-SALDO"}
        assert counter["n"] == 0  # dentro do bloco o saldo não volta ao banco

        # Fora do bloco o saldo volta a ser lido: uma gravação depois aparece na hora.
        db.session.get(StockBalance, "A-MIGRADO").quantity_base = 9.0
        db.session.flush()
        assert balance_provider.get_balance("A-MIGRADO").quantity_base == 9.0


def test_stock_balance_column_check_reads_table_structure_only_once(app_with_stock, monkeypatch):
    with app_with_stock.app_context():
        models._STOCK_BALANCE_READ_MODEL_READY_ENGINES.clear()
        calls = []
        real_inspect = models.sa_inspect
        monkeypatch.setattr(models, "sa_inspect", lambda bind: calls.append(bind) or real_inspect(bind))

        assert models.stock_balance_supports_read_model_ready() is True
        assert models.stock_balance_supports_read_model_ready() is True
        assert len(calls) == 1


def test_mobile_stock_list_and_total_use_batch_balances(app_with_stock):
    client = app_with_stock.test_client()
    with app_with_stock.app_context():
        response = client.get("/api/mobile/estoque", headers=AUTH)
        total = inventory_service.total_quantity()

    assert response.status_code == 200
    by_code = {row["id"]: row["quantidade"] for row in response.get_json()}
    assert by_code == {"A-MIGRADO": 7.0, "B-PENDENTE": 3.0, "C-SEM-SALDO": 0.0}
    assert total == 10
