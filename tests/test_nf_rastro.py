"""Para onde foram os itens de uma NF (25/11/2026): primeiro que entra, primeiro que sai, sobre o razão.

Pedido do usuário: a NF 77777 estava no GALINT só por xerox; chegou o PDF e os itens já saíram. A NF tem
de mostrar a lista completa das retiradas que gastaram o que ela trouxe. Banco SQLite em memória.
"""
from datetime import date, datetime

import pytest
from flask import Flask
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import (
    DocumentoEntradaEstoque,
    DocumentoEntradaEstoqueItem,
    InventarioEvento,
    Item,
    Saida,
    StockMovement,
    Usuario,
)
from galint_flask.services.nf_rastro import rastro_do_documento


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@compiles(INET, "sqlite")
def _inet_as_text_on_sqlite(element, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def app_db():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False, GALINT_DISABLE_BACKGROUND_SERVICES=True)
    with app.app_context():
        db.init_app(app)
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        db.session.add_all([
            Usuario(matricula="9001", nome="JOÃO SILVA"),
            Usuario(matricula="9002", nome="PEDRO LIMA"),
            Item(codigo_item="CLORO10", descricao="CLORO GRANULADO 10KG", unidade="Quilo", setor="ALMOXARIFADO"),
            Item(codigo_item="ALGI1", descricao="ALGICIDA 1L", unidade="Litro", setor="ALMOXARIFADO"),
        ])
        db.session.commit()
        yield
        db.session.remove()


def _move(day, kind, quantity, reference_type=None, reference_id=None, product="CLORO10"):
    movement = StockMovement(product_id=product, movement_type=kind, quantity_base=quantity, reference_type=reference_type,
                             reference_id=None if reference_id is None else str(reference_id), created_at=datetime(2026, 11, day, 10, 0))
    db.session.add(movement)
    db.session.flush()
    return movement


def _withdraw(day, quantity, matricula, local, reference_type="movements_saida_multipla"):
    saida = Saida(codigo_item="CLORO10", matricula=matricula, quantidade=quantity, local_servico=local, data_saida=datetime(2026, 11, day, 10, 0))
    db.session.add(saida)
    db.session.flush()
    return _move(day, "saida", -quantity, reference_type, saida.id_saida)


def _nf(numero="77777"):
    documento = DocumentoEntradaEstoque(numero_documento=numero, tipo_documento="nf", data_emissao=date(2026, 11, 1), data_recebimento=date(2026, 11, 2))
    db.session.add(documento)
    db.session.flush()
    return documento


def test_nf_shows_every_withdrawal_that_used_it_until_it_ran_out(app_db):
    _move(1, "entrada", 20, "entrada")  # saldo antigo: sai primeiro
    documento = _nf()
    line = DocumentoEntradaEstoqueItem(documento_id=documento.id_documento, codigo_item="CLORO10", quantidade=25, unidade_quantidade="balde", quantidade_base=250)
    db.session.add(line)
    db.session.flush()
    entry = _move(2, "entrada", 250, "entrada_documento_item", line.id_documento_item)
    line.stock_movement_id = entry.id
    _withdraw(3, 30, "9001", "PISCINA")  # 20 do saldo antigo + 10 da NF
    evento = InventarioEvento(codigo_item="CLORO10", matricula="9002", tipo="ajuste", quantidade=-15)
    db.session.add(evento)
    db.session.flush()
    _move(5, "ajuste", -15, "inventario_evento", evento.id_evento)
    _move(6, "entrada", 100, "entrada_documento_item", 999)  # estoque mais novo: não mexe na NF
    _withdraw(7, 100, "9002", "BLOCO A")
    _move(8, "devolucao", 10, "inventario_evento")  # volta para a NF
    _withdraw(10, 135, "9001", "PISCINA", reference_type="api_mobile_retirar")
    db.session.commit()

    [rastro] = rastro_do_documento(documento.id_documento, hoje=datetime(2026, 11, 25, 9, 0))

    assert (rastro["entrou"], rastro["restante"], rastro["saiu_tudo"], rastro["ultima_dias"]) == (250.0, 0.0, True, 15)
    assert (rastro["unidade"], rastro["fator"], rastro["unidade_doc"]) == ("kg", 10.0, "balde")
    assert [(row["tipo"], row["quem"], row["local"], row["quantidade"], row["dias"]) for row in rastro["linhas"]] == [
        ("Retirada", "JOÃO SILVA", "PISCINA", 10.0, 22),
        ("Conferência", "PEDRO LIMA", None, 15.0, 20),
        ("Retirada", "PEDRO LIMA", "BLOCO A", 100.0, 18),
        ("Devolução", None, None, -10.0, 17),
        ("Retirada", "JOÃO SILVA", "PISCINA", 135.0, 15),
    ]


def test_nf_still_has_stock_and_line_without_stock_entry(app_db):
    documento = _nf("88888")
    with_entry = DocumentoEntradaEstoqueItem(documento_id=documento.id_documento, codigo_item="CLORO10", quantidade=5, quantidade_base=50, unidade_quantidade="balde")
    no_entry = DocumentoEntradaEstoqueItem(documento_id=documento.id_documento, codigo_item="ALGI1", quantidade=12)
    db.session.add_all([with_entry, no_entry])
    db.session.flush()
    _move(2, "entrada", 50, "entrada_documento_item", with_entry.id_documento_item)  # achada pela referência
    _withdraw(4, 20, "9001", "PISCINA")
    db.session.commit()

    cloro, algicida = rastro_do_documento(documento.id_documento, hoje=datetime(2026, 11, 25))

    assert (cloro["restante"], cloro["saiu_tudo"], cloro["ultima_dias"]) == (30.0, False, 21)
    assert [row["quantidade"] for row in cloro["linhas"]] == [20.0]
    assert algicida["sem_entrada"] is True and algicida["linhas"] == []
