"""Grupos de itens (produto genérico), 24/11/2026: sugestões por nome igual, seleção e ordem de retirada.

Decisões do usuário: sai primeiro o mais antigo; sugestão por nome igual com seleção (joelho tem de todo
tipo); ferramentas ficam fora. Banco SQLite em memória, rotas reais.
"""
from datetime import date

import pytest
from flask import Flask
from flask_login import LoginManager
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Item, ItemGrupo, StockBalance, Usuario
from galint_flask.services import item_grupo_service as service
from galint_flask.views import inventory, item_grupos


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@compiles(INET, "sqlite")
def _inet_as_text_on_sqlite(element, compiler, **kwargs):
    return "TEXT"


ITENS = [
    # código, descrição, marca, unidade, categoria, saldo, última entrada
    ("7899874560001", "JOELHO 25MM", "AMANCO", "Unidade", "Material Hidráulico", 29, date(2026, 3, 1)),
    ("261596002186", "JOELHO 25MM", "KRONA", "Unidade", "Material Hidráulico", 38, date(2026, 6, 1)),
    ("7899874560099", "Joelho  25mm", "TIGRE", "Unidade", "Material Hidráulico", 0, date(2025, 1, 1)),
    ("7899874560012", "JOELHO 45GRAUS 25MM", "TIGRE", "Unidade", "Material Hidráulico", 1, None),
    ("17897801302248", "JOELHO 45GRAUS 25MM", "KRONA", "Unidade", "Material Hidráulico", 50, None),
    ("BAT1", "BATERIA WESCO 18V", "WESCO", "Unidade", "Ferramentas", 1, None),
    ("BAT2", "BATERIA WESCO 18V", "WESCO", "Unidade", "Ferramentas", 1, None),
    ("CONDUITE1", "JOELHO 25MM", "FORTLEV", "Metro", "Material Elétrico", 10, None),
]


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="grupos", TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    with app.app_context():
        db.init_app(app)
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        db.session.add(Usuario(matricula="9001", nome="ADMINISTRADOR", is_admin=True))
        for codigo, descricao, marca, unidade, categoria, saldo, entrada in ITENS:
            db.session.add(Item(codigo_item=codigo, descricao=descricao, marca=marca, unidade=unidade, categoria=categoria, setor="ALMOXARIFADO"))
            db.session.add(StockBalance(product_id=codigo, quantity_base=saldo, read_model_ready=True))
            if entrada:
                documento = DocumentoEntradaEstoque(numero_documento=f"NF-{codigo}", tipo_documento="nf", data_recebimento=entrada)
                db.session.add(documento)
                db.session.flush()
                db.session.add(DocumentoEntradaEstoqueItem(documento_id=documento.id_documento, codigo_item=codigo, quantidade=saldo or 1))
        db.session.commit()
        manager = LoginManager(app)
        manager.request_loader(lambda request: db.session.get(Usuario, "9001"))
        app.register_blueprint(inventory.blueprint)
        app.register_blueprint(item_grupos.blueprint)
        yield app
        db.session.remove()


def test_suggestions_join_same_name_and_unit_but_not_tools(app):
    sugestoes = {s["nome"].upper().replace("  ", " "): sorted(i["marca"] for i in s["itens"]) for s in service.suggestions()}
    assert sugestoes["JOELHO 25MM"] == ["AMANCO", "KRONA", "TIGRE"]  # "Joelho  25mm" entra; o de metro não
    assert sugestoes["JOELHO 45GRAUS 25MM"] == ["KRONA", "TIGRE"]
    assert not any("BATERIA" in nome for nome in sugestoes)


def test_selection_search_includes_all_words_and_excludes_minus_words(app):
    marcas = sorted(item["marca"] for item in service.search_items("joelho 25 -45"))
    assert marcas == ["AMANCO", "FORTLEV", "KRONA", "TIGRE"]
    assert all("45" not in item["descricao"] for item in service.search_items("joelho 25 -45"))
    assert service.search_items("bateria") == []  # ferramenta fica fora


def test_group_rules(app):
    with pytest.raises(ValueError, match="mesma unidade"):
        service.create_group("JOELHO 25MM", ["7899874560001", "CONDUITE1"])
    with pytest.raises(ValueError, match="Ferramenta"):
        service.create_group("BATERIAS", ["BAT1", "BAT2"])
    grupo = service.create_group("joelho 25mm", ["7899874560001", "261596002186", "7899874560099"])
    assert grupo.nome == "JOELHO 25MM" and grupo.unidade == "Unidade"
    with pytest.raises(ValueError, match="outro grupo"):
        service.create_group("OUTRO", ["261596002186", "7899874560012"])
    assert "JOELHO 25MM" not in {s["nome"].upper() for s in service.suggestions()}  # já agrupado sai das sugestões


def test_oldest_goes_first_and_empty_member_is_skipped(app):
    grupo = service.create_group("JOELHO 25MM", ["7899874560001", "261596002186", "7899874560099"])
    ordem = [card["marca"] for card in service.withdrawal_order(grupo)]
    assert ordem == ["AMANCO", "KRONA"]  # Amanco (última entrada em março) antes da Krona (junho); Tigre sem saldo
    listed = {g["nome"]: g for g in service.list_groups()}["JOELHO 25MM"]
    assert listed["saldo_total"] == 67


def test_routes_create_add_remove(app):
    client = app.test_client()
    response = client.post("/itens/grupos/criar", data={"nome": "JOELHO 45GRAUS 25MM", "codigos": ["7899874560012", "17897801302248"]})
    assert response.status_code == 302
    grupo = ItemGrupo.query.one()
    assert sorted(m.codigo_item for m in grupo.membros) == ["17897801302248", "7899874560012"]
    client.post(f"/itens/grupos/{grupo.id}/remover", data={"codigo": "7899874560012"})
    assert [m.codigo_item for m in db.session.get(ItemGrupo, grupo.id).membros] == ["17897801302248"]
    found = client.get("/itens/grupos/buscar?q=joelho 45").get_json()
    assert {item["codigo"]: item["grupo_nome"] for item in found}["17897801302248"] == "JOELHO 45GRAUS 25MM"
    adapter = app.url_map.bind("localhost")
    assert adapter.match("/itens/grupos/buscar")[0] == "item_grupos.buscar"
    assert adapter.match("/itens/grupos/criar", method="POST")[0] == "item_grupos.criar"
