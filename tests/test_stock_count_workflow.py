from flask import Flask
from flask_login import LoginManager
from openpyxl import load_workbook
import pytest

from galint_flask.extensions import db
from galint_flask.models import Item
from galint_flask.services.inventory import inventory_service
from galint_flask.services.stock_count_workbook_service import StockCountWorkbookService
from galint_flask.views.inventory import blueprint


class _AuthenticatedWorker:
    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_admin = False
    id = "worker-1"
    matricula = "worker-1"
    nome = "Operador"

    def get_id(self):
        return self.id


@pytest.fixture
def stock_count_client():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="stock-count-test",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    manager = LoginManager()
    manager.init_app(app)

    @manager.user_loader
    def load_user(user_id):
        return _AuthenticatedWorker() if user_id == "worker-1" else None

    app.register_blueprint(blueprint)
    with app.app_context():
        db.init_app(app)
        db.metadata.create_all(bind=db.engine, tables=[Item.__table__])
        db.session.add(Item(codigo_item="COUNT-001", descricao="Material de teste", setor="Estoque"))
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = "worker-1"
            session["_fresh"] = True
        yield app, client
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=[Item.__table__])


def test_stock_count_workbook_is_a4_and_has_blank_physical_column():
    workbook_stream = StockCountWorkbookService.build(
        [{
            "codigo": "COUNT-001",
            "descricao": "Material de teste",
            "saldo": 4,
            "saldo_display": "4 unidades",
        }]
    )
    workbook = load_workbook(workbook_stream)
    sheet = workbook.active
    header_row = next(
        row[0].row
        for row in sheet.iter_rows()
        if [cell.value for cell in row[:4]] == ["ITEM", "CÓDIGO DE BARRAS", "SISTEMA", "FÍSICO"]
    )
    item_row = header_row + 1

    assert str(sheet.page_setup.paperSize) == str(sheet.PAPERSIZE_A4)
    assert sheet.page_setup.orientation == "portrait"
    assert sheet.page_setup.fitToWidth == 1
    assert [sheet.cell(item_row, column).value for column in (1, 3, 4)] == [
        "Material de teste",
        "4 unidades",
        None,
    ]
    assert len(sheet._images) == 1
    assert "COUNT-001" not in {
        str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value is not None
    }


def test_stock_count_download_endpoint_returns_generated_workbook(stock_count_client, monkeypatch):
    app, client = stock_count_client
    monkeypatch.setattr(
        inventory_service,
        "list_items",
        lambda **_kwargs: [{
            "codigo": "COUNT-001",
            "descricao": "Material de teste",
            "saldo": 4,
            "saldo_display": "4 unidades",
        }],
    )

    with app.app_context():
        response = client.get("/itens/conferencia-estoque.xlsx")

    assert response.status_code == 200
    assert response.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert response.data[:2] == b"PK"


def test_any_authenticated_user_can_lookup_item_and_apply_zero_count(stock_count_client, monkeypatch):
    app, client = stock_count_client
    snapshot = {
        "codigo": "COUNT-001",
        "descricao": "Material de teste",
        "unidade": "Unidade",
        "saldo_exibido": 4.0,
        "saldo_display": "4 unidades",
        "admin_balance_input": {
            "supports_packaging": False,
            "internal_unit_display": "un",
            "internal_allow_decimal": False,
        },
        "pre_cadastro_pendente": False,
    }
    calls = []
    monkeypatch.setattr(inventory_service, "get_admin_balance_snapshot", lambda _code: snapshot)
    monkeypatch.setattr(
        inventory_service,
        "apply_admin_item_adjustments",
        lambda **kwargs: calls.append(kwargs) or {"changed": True, "message": "Saldo atualizado."},
    )

    with app.app_context():
        lookup = client.get("/itens/api/conferencia-estoque/item?codigo=COUNT-001")
        adjustment = client.post(
            "/itens/api/conferencia-estoque/item/COUNT-001/ajuste",
            json={"mode": "direct", "quantity": "0"},
        )

    assert lookup.status_code == 200
    assert lookup.get_json()["item"]["saldo"] == 4.0
    assert adjustment.status_code == 200
    assert adjustment.get_json()["success"] is True
    assert calls[0]["adjustment_payload"]["admin_balance_direct_value"] == "0"
    assert calls[0]["matricula"] == "worker-1"
    assert calls[0]["audit_context"]["source"] == "barcode_stock_count_modal"
