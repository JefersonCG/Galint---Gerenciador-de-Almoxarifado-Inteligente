"""Realinha o adesivo plastico 850g de legado em litro para Unidade.

Atualiza em conjunto:
- cadastro do item;
- unidade base do produto;
- linha documental ja processada;
- lancamento financeiro vinculado;
- movimento de estoque associado.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
sys.path.insert(0, os.getcwd())

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoqueItem, FinanceLedgerEntry, Item, ProductUnit, StockMovement
from galint_flask.services.price_normalization import normalize_document_line


TARGET_CODE = "7891960731416"
TARGET_DOCUMENT_NUMBER = "583016"


def apply_migration() -> dict[str, object]:
    item = db.session.get(Item, TARGET_CODE)
    if item is None:
        raise RuntimeError(f"Item {TARGET_CODE} nao encontrado")

    document_rows = DocumentoEntradaEstoqueItem.query.filter_by(codigo_item=TARGET_CODE).all()
    if len(document_rows) != 1:
        raise RuntimeError(f"Esperava 1 linha documental para {TARGET_CODE}, encontrei {len(document_rows)}")
    document_row = document_rows[0]
    document_number = str(getattr(document_row.documento, "numero_documento", "") or "").strip()
    if document_number != TARGET_DOCUMENT_NUMBER:
        raise RuntimeError(
            f"Documento inesperado para {TARGET_CODE}: {document_number or '-'}"
        )

    finance_rows = FinanceLedgerEntry.query.filter_by(
        codigo_item=TARGET_CODE,
        numero_documento=TARGET_DOCUMENT_NUMBER,
    ).all()
    if len(finance_rows) != 1:
        raise RuntimeError(f"Esperava 1 lancamento financeiro para {TARGET_CODE}, encontrei {len(finance_rows)}")
    finance_row = finance_rows[0]

    stock_movement = db.session.get(StockMovement, document_row.stock_movement_id)
    if stock_movement is None:
        raise RuntimeError(f"Movimento de estoque {document_row.stock_movement_id} nao encontrado")

    item.unidade = "Unidade"
    item.tipo_embalagem_novo = None
    item.tipo_embalagem = None
    item.litros_por_embalagem = None
    item.grandeza_referencia = None
    item.unidades_por_embalagem = None
    item.estoque_embalagens = 0.0
    item.estoque_unidades_soltas = float(document_row.quantidade or 0.0)
    item.preco_compra_unidade_preco = "unidade"
    item.preco_compra_fator_base = 1.0

    for product_unit in item.product_units:
        if bool(getattr(product_unit, "is_base", False)):
            product_unit.unit_code = "un"
            product_unit.unit_label = "Unidade"
            product_unit.dimension = "unit"
            product_unit.active = True

    normalized = normalize_document_line(
        item,
        quantity=float(document_row.quantidade or 0.0),
        quantity_unit="unidade",
        unit_price=float(document_row.valor_unitario or 0.0),
        total_price=float(document_row.valor_total or 0.0),
        price_unit="unidade",
    )

    document_row.unidade_quantidade = normalized.quantity_unit
    document_row.quantidade_base = normalized.quantity_base
    document_row.valor_unitario_base = normalized.unit_price_base
    document_row.unidade_preco = normalized.price_unit
    document_row.fator_preco_base = normalized.factor_to_base
    document_row.valor_total = normalized.total_value

    finance_row.unidade_quantidade = normalized.quantity_unit
    finance_row.quantidade_base = normalized.quantity_base
    finance_row.valor_unitario_base = normalized.unit_price_base
    finance_row.unidade_preco = normalized.price_unit
    finance_row.fator_preco_base = normalized.factor_to_base
    finance_row.valor_total = normalized.total_value or finance_row.valor_total

    stock_movement.quantity_base = normalized.quantity_base
    stock_movement.unit_base = normalized.unit_base
    metadata = dict(stock_movement.metadata_json or {})
    metadata["input_unit"] = normalized.quantity_unit
    metadata["input_quantity"] = normalized.quantity_input
    metadata["factor_applied"] = normalized.factor_to_base
    stock_movement.metadata_json = metadata

    db.session.commit()
    return {
        "codigo_item": TARGET_CODE,
        "documento": TARGET_DOCUMENT_NUMBER,
        "unidade": item.unidade,
        "saldo_unidades_soltas": item.estoque_unidades_soltas,
        "quantidade_documento": document_row.quantidade,
        "unidade_documento": document_row.unidade_quantidade,
        "quantidade_base": document_row.quantidade_base,
        "unidade_movimento": stock_movement.unit_base,
    }


def main() -> int:
    app = create_app()
    with app.app_context():
        result = apply_migration()
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())