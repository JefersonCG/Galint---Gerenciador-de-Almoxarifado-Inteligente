from flask import Flask
from flask_login import LoginManager
from openpyxl import load_workbook
import pytest

from galint_flask.extensions import db
from galint_flask.models import InventoryCategory, Item
from galint_flask.services.inventory import inventory_service
from galint_flask.services.stock_count_workbook_service import StockCountWorkbookService
from galint_flask.views import inventory as inventory_views
from galint_flask.views.inventory import blueprint

TABLES = [Item.__table__, InventoryCategory.__table__]


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
        db.metadata.create_all(bind=db.engine, tables=TABLES)
        db.session.add(Item(
            codigo_item="COUNT-001",
            descricao="Material de teste",
            setor="Estoque",
            foto_path="uploads/itens/COUNT-001.jpg",
        ))
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = "worker-1"
            session["_fresh"] = True
        yield app, client
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=TABLES)


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
    anchor = sheet._images[0].anchor._from
    assert (anchor.col, anchor.row) == (1, item_row - 1)
    assert anchor.rowOff > 0  # afastada da borda: não cobre a grade nem vaza para a página anterior
    assert "COUNT-001" not in {
        str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value is not None
    }


def test_stock_count_workbook_keeps_going_when_code_cannot_be_a_barcode():
    # Itens reais como "LUVA LÁTEX" usam o nome como código; o Code128 não aceita "Á".
    # E códigos de texto longos ("BOMBA AUTOASPIRANTE") dariam barras finas demais para o leitor.
    workbook = load_workbook(StockCountWorkbookService.build([
        {"codigo": "LUVA LÁTEX", "descricao": "Luva de látex", "saldo_display": "3 pares"},
        {"codigo": "BOMBA AUTOASPIRANTE", "descricao": "Bomba autoaspirante", "saldo_display": "1 unidade"},
        {"codigo": "COUNT-001", "descricao": "Material de teste", "saldo_display": "4 unidades"},
    ]))
    sheet = workbook.active
    header_row = next(
        row[0].row for row in sheet.iter_rows() if row[0].value == "ITEM"
    )
    pump_row = header_row + 1  # ordem pela descrição: Bomba, Luva, Material
    latex_row = header_row + 2

    assert sheet.cell(pump_row, 2).value.startswith("BOMBA AUTOASPIRANTE")
    assert sheet.cell(latex_row, 1).value == "Luva de látex"
    assert sheet.cell(latex_row, 2).value.startswith("LUVA LÁTEX")
    assert "digite na busca" in sheet.cell(latex_row, 2).value
    assert sheet.cell(latex_row, 2).border.left.style == "thin"
    assert sheet.cell(latex_row + 1, 2).value is None
    assert len(sheet._images) == 1


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


def _category_items():
    return [
        {"codigo": "E-1", "descricao": "Disjuntor 20A", "categoria": "Material Elétrico", "saldo_display": "3 unidades"},
        {"codigo": "H-1", "descricao": "Adaptador 25mm", "categoria": "Material Hidráulico", "saldo_display": "8 unidades"},
        {"codigo": "H-2", "descricao": "Joelho 90 25mm", "categoria": "Material  Hidráulico ", "saldo_display": "2 unidades"},
        {"codigo": "P-1", "descricao": "Cloro granulado", "categoria": "Material Piscina", "saldo_display": "1 balde"},
    ]


def test_stock_count_workbook_groups_categories_on_separate_pages():
    workbook = load_workbook(StockCountWorkbookService.build(
        _category_items()[:3],
        scope_label="Categorias: Material Hidráulico, Material Elétrico",
        group_by_category=True,
        category_order=["Material Hidráulico", "Material Elétrico"],
    ))
    sheet = workbook.active
    values = [sheet.cell(row, 1).value for row in range(1, sheet.max_row + 1)]
    header_row = values.index("ITEM") + 1

    assert "Categorias: Material Hidráulico, Material Elétrico" in values[:header_row]
    # Ordem do catálogo, faixa com o total e itens em ordem alfabética dentro da categoria.
    assert values[header_row:] == [
        "MATERIAL HIDRÁULICO  ·  2 itens",
        "Adaptador 25mm",
        "Joelho 90 25mm",
        "MATERIAL ELÉTRICO  ·  1 item",
        "Disjuntor 20A",
    ]
    electric_section_row = header_row + 4
    assert [page_break.id for page_break in sheet.row_breaks.brk] == [electric_section_row - 1]
    assert len(sheet._images) == 3
    assert sheet.print_title_rows == f"$1:${header_row}"


def test_stock_count_row_grows_when_system_text_wraps_by_word():
    # Caso real: "FITA TESTE" saía com a última linha do SISTEMA cortada no papel.
    assert StockCountWorkbookService._wrapped_line_count("8 caixas + 6 unidades | Total: 134un", 19) == 3
    assert StockCountWorkbookService._wrapped_line_count("38.0 litros (38 litros) | Total: 38L", 19) == 3
    assert StockCountWorkbookService._wrapped_line_count("3 unidades", 19) == 1
    workbook = load_workbook(StockCountWorkbookService.build([
        {"codigo": "FT-1", "descricao": "FITA TESTE", "saldo_display": "8 caixas + 6 unidades | Total: 134un"},
        {"codigo": "FT-2", "descricao": "GRAMPO", "saldo_display": "3 unidades"},
    ]))
    sheet = workbook.active
    header_row = next(row[0].row for row in sheet.iter_rows() if row[0].value == "ITEM")

    assert sheet.row_dimensions[header_row + 1].height >= 51
    assert sheet.row_dimensions[header_row + 2].height == 39


def test_stock_count_categories_endpoint_lists_categories_in_catalog_order(stock_count_client):
    app, client = stock_count_client
    with app.app_context():
        db.session.add_all([
            InventoryCategory(nome="Material Piscina", ordem=30, ativa=True, sistema=True),
            InventoryCategory(nome="Material Elétrico", ordem=10, ativa=True, sistema=True),
            Item(codigo_item="P-1", descricao="Cloro granulado", setor="Piscina", categoria="Material Piscina"),
            Item(codigo_item="P-2", descricao="Algicida", setor="Piscina", categoria="Material Piscina"),
            Item(codigo_item="X-1", descricao="Item novo", setor="Geral", categoria="Categoria Nova"),
        ])
        db.session.query(Item).filter_by(codigo_item="COUNT-001").update({"categoria": "Material Elétrico"})
        db.session.commit()
        response = client.get("/itens/api/conferencia-estoque/categorias")

    payload = response.get_json()
    assert response.status_code == 200
    assert [(row["nome"], row["total"]) for row in payload["categories"]] == [
        ("Material Elétrico", 1),
        ("Material Piscina", 2),
        ("Categoria Nova", 1),
    ]
    assert payload["total_items"] == 4
    assert payload["categories"][0]["icon"]


def test_stock_count_download_filters_by_chosen_categories(stock_count_client, monkeypatch):
    app, client = stock_count_client
    monkeypatch.setattr(inventory_service, "list_items", lambda **_kwargs: _category_items())
    calls = []
    real_build = StockCountWorkbookService.build

    def capture_build(items, **kwargs):
        calls.append((items, kwargs))
        return real_build(items, **kwargs)

    monkeypatch.setattr(inventory_views.StockCountWorkbookService, "build", staticmethod(capture_build))

    with app.app_context():
        single = client.get("/itens/conferencia-estoque.xlsx", query_string={"categoria": "Material Hidráulico"})
        several = client.get(
            "/itens/conferencia-estoque.xlsx",
            query_string=[("categoria", "Material Piscina"), ("categoria", "Material Elétrico")],
        )
        everything = client.get("/itens/conferencia-estoque.xlsx")
        unknown = client.get("/itens/conferencia-estoque.xlsx", query_string={"categoria": "Não existe"})

    assert single.status_code == 200
    assert "conferencia_estoque_material-hidraulico_" in single.headers["Content-Disposition"]
    assert [item["codigo"] for item in calls[0][0]] == ["H-1", "H-2"]  # "Material  Hidráulico " também entra
    assert calls[0][1]["scope_label"] == "Categoria: Material Hidráulico"
    assert calls[0][1]["group_by_category"] is False

    assert several.status_code == 200
    assert "_varias-categorias_" in several.headers["Content-Disposition"]
    assert sorted(item["codigo"] for item in calls[1][0]) == ["E-1", "P-1"]
    assert calls[1][1]["group_by_category"] is True

    assert everything.status_code == 200
    assert len(calls[2][0]) == 4
    assert calls[2][1]["scope_label"] == "Todas as categorias"

    assert unknown.status_code == 404
    assert unknown.get_json()["message"] == "Nenhum item nas categorias escolhidas."


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
    monkeypatch.setattr(inventory_service, "get_stock_count_snapshot", lambda _code: snapshot)
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
    assert lookup.get_json()["item"]["foto_url"] == "/static/uploads/itens/COUNT-001.jpg"
    assert adjustment.status_code == 200
    assert adjustment.get_json()["success"] is True
    assert calls[0]["adjustment_payload"]["admin_balance_direct_value"] == "0"
    assert calls[0]["matricula"] == "worker-1"
    assert calls[0]["audit_context"]["source"] == "barcode_stock_count_modal"
