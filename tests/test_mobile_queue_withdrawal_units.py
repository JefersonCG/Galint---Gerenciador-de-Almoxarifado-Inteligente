"""Fila de saída do app 2.4.0 (25/11/2026): a quantidade vai na unidade base.

Pedido do usuário: fila de retirada no app "igual temos" no site. No site, "3 pacotes" sai com
em_embalagens=True e o servidor converte; a rota do app (/api/mobile/retirar_multipla) não recebe essa
marca, então o app manda 3 pacotes × 1.000 = 3.000 unidades. Estes testes provam que, nessa rota
(reference_type "api_mobile_retirar_multipla", em_embalagens=None), o razão grava 3.000 na unidade base
e não 3.000 pacotes — inclusive no item com unidade base "litro" (bombona de 5 L), que o
legacy_stock_normalizer trata como unidade de embalagem. SQLite em memória, sem rota.
"""
import pytest
from flask import Flask
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import Item, ProductUnit, ProductUnitConversion
from galint_flask.services.inventory import MovimentoPayload, inventory_service

TABLES = [Item.__table__, ProductUnit.__table__, ProductUnitConversion.__table__]
MOBILE_QUEUE = {"reference_type": "api_mobile_retirar_multipla"}


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    with app.app_context():
        db.init_app(app)
        db.metadata.create_all(bind=db.engine, tables=TABLES)
        db.session.add_all([
            Item(codigo_item="7899682763500", descricao="PAPEL TOALHA INTERFOLHAS", categoria="Materiais de Limpeza",
                 unidade="Unidade", setor="Estoque", tipo_embalagem_novo="pacote", unidades_por_embalagem=1000),
            Item(codigo_item="262711316362", descricao="CDC-10", categoria="Materiais de Limpeza",
                 unidade="Litro", setor="Estoque", tipo_embalagem_novo="bombona", unidades_por_embalagem=5, litros_por_embalagem=5),
            ProductUnit(product_id="262711316362", unit_code="litro", unit_label="Litro", dimension="volume", is_base=True, active=True),
        ])
        db.session.commit()
        yield app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=TABLES)


def _ledger_input(codigo, quantidade):
    item = db.session.get(Item, codigo)
    payload = MovimentoPayload(codigo=codigo, quantidade=float(quantidade), em_embalagens=None, canal_saida="materiais")
    return inventory_service._resolve_ledger_input_for_mirror(item, payload, metadata=MOBILE_QUEUE)


def test_three_packs_sent_as_3000_units_stay_3000_units(app):
    assert _ledger_input("7899682763500", 3000) == (3000.0, "unidade")


def test_one_drum_sent_as_5_liters_stays_5_liters(app):
    assert _ledger_input("262711316362", 5) == (5.0, "litro")


def test_full_drum_passes_the_kg_l_policy(app):
    item = db.session.get(Item, "262711316362")
    payload = MovimentoPayload(codigo=item.codigo_item, quantidade=5.0, em_embalagens=None, canal_saida="materiais")
    inventory_service.validate_exit_payload_policy(item, payload)  # não levanta: é a bombona inteira
