from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Flask
from openpyxl import load_workbook
from PIL import Image

from galint_flask.models import EquipamentoReparo, Item
from galint_flask.services.purchase_projection_runtime_service import PurchaseProjectionService


def test_purchase_workbook_embeds_item_photos_and_keeps_items_without_photos(tmp_path):
    static_dir = tmp_path / "static"
    photo_dir = static_dir / "uploads" / "itens"
    photo_dir.mkdir(parents=True)
    Image.new("RGB", (120, 80), "red").save(photo_dir / "item.png")
    app = Flask(__name__, root_path=str(tmp_path))

    def item(description, photo_path, value):
        return {
            "foto_path": photo_path,
            "supplier": {"name": "Fornecedor teste", "cnpj": ""},
            "price_reference_type": "NF",
            "price_reference_document": "1",
            "requested_quantity_display": "1",
            "requested_quantity_base_display": "1",
            "request_quantity_short_label": "UN",
            "descricao": description,
            "marca": "Marca teste",
            "requested_quantity_input": 1,
            "price_unit_request": value,
            "price_unit_base": value,
            "requested_total_value": value,
        }

    report = {
        "generated_at": "2026-04-08",
        "cart": {
            "requested_value_total": 30,
            "category_groups": [
                {
                    "category_name": "Teste",
                    "requested_value_total": 30,
                    "items": [
                        item("Item com foto", "uploads/itens/item.png", 10),
                        item("Item sem foto", None, 20),
                    ],
                }
            ],
        },
    }

    with app.app_context():
        output = PurchaseProjectionService.build_workbook(report)

    sheet = load_workbook(output)["Pedido"]
    header_row = next(row[0].row for row in sheet.iter_rows() if row[0].value == "Foto")
    photo_row = next(row[0].row for row in sheet.iter_rows() if any(cell.value == "Item com foto" for cell in row))
    no_photo_row = next(row[0].row for row in sheet.iter_rows() if any(cell.value == "Item sem foto" for cell in row))

    assert sheet.max_column == 12
    assert sheet.cell(header_row, 5).value == "Descricao"
    assert len(sheet._images) == 1
    assert sheet._images[0].anchor._from.col == 0
    assert sheet._images[0].anchor._from.row == photo_row - 1
    assert sheet.row_dimensions[photo_row].height == 52
    assert sheet.cell(no_photo_row, 5).value == "Item sem foto"


def test_zero_stock_workbook_embeds_item_photo(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    photo_dir = static_dir / "uploads" / "itens"
    photo_dir.mkdir(parents=True)
    Image.new("RGB", (120, 80), "blue").save(photo_dir / "item.png")
    app = Flask(__name__, root_path=str(tmp_path))
    item = SimpleNamespace(
        codigo_item="A-1",
        descricao="Item zerado",
        marca="Marca teste",
        unidade="UN",
        localizacao="Prateleira",
        foto_path="uploads/itens/item.png",
        categoria="Teste",
        get_unidade_interna_display=lambda: "UN",
    )
    item_query = MagicMock()
    item_query.order_by.return_value.all.return_value = [item]
    repair_query = MagicMock()
    repair_query.filter.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(
        PurchaseProjectionService,
        "_load_ledger_balances",
        classmethod(lambda cls, product_ids: {"A-1": 0.0}),
    )

    with app.app_context():
        item_had_query = "query" in Item.__dict__
        repair_had_query = "query" in EquipamentoReparo.__dict__
        original_item_query = Item.__dict__.get("query")
        original_repair_query = EquipamentoReparo.__dict__.get("query")
        Item.query = item_query
        EquipamentoReparo.query = repair_query
        try:
            output = PurchaseProjectionService.build_zero_stock_workbook()
        finally:
            if item_had_query:
                Item.query = original_item_query
            else:
                del Item.query
            if repair_had_query:
                EquipamentoReparo.query = original_repair_query
            else:
                del EquipamentoReparo.query

    sheet = load_workbook(output)["Teste"]
    assert sheet["A4"].value == "Foto"
    assert sheet["C5"].value == "Item zerado"
    assert sheet.auto_filter.ref == "A4:L5"
    assert len(sheet._images) == 1
    assert sheet._images[0].anchor._from.col == 0
    assert sheet._images[0].anchor._from.row == 4
