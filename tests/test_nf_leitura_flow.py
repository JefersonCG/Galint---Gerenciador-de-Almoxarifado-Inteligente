"""Ler NF → conferir → lançar no pré-cadastro (24/11/2026), pelas rotas reais em banco SQLite.

O DANFE de exemplo tem texto no PDF (lido sem OCR, rápido). O cadastro de teste tem um item com o mesmo
código de uma linha da NF (DISJUNTOR) e outro de nome parecido (FITA ISOLANTE). No lançamento:
- linha ligada a item existente: linha na NF e entrada no estoque;
- linha "Item novo": item criado em PRÉ-CADASTRO (origem nf) e ligado à linha da NF;
- vínculo fornecedor + código do produto guardado para a próxima NF.
"""
import pytest
from flask import Flask
from flask_login import LoginManager
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Item, NFItemVinculo, NFLeitura, Usuario
from galint_flask.views import inventory, nf_leitura
from tests.danfe_sample import ACCESS_KEY, SUPPLIER_CNPJ, build_danfe_pdf


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@compiles(INET, "sqlite")
def _inet_as_text_on_sqlite(element, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = Flask(__name__, instance_path=str(tmp_path))
    app.config.update(
        SECRET_KEY="nf-leitura-flow",
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    from galint_flask.services import notification_router

    monkeypatch.setattr(notification_router.NotificationRouterService, "route_item_created", staticmethod(lambda *args, **kwargs: None))
    with app.app_context():
        db.init_app(app)
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        db.session.add(Usuario(matricula="9001", nome="ADMINISTRADOR", is_admin=True))
        db.session.add(Item(codigo_item="7891234567895", descricao="DISJUNTOR DIN MONOPOLAR 20A", unidade="Unidade", categoria="Material Elétrico", marca="SCHNEIDER", setor="ALMOXARIFADO"))
        db.session.add(Item(codigo_item="FITA001", descricao="FITA ISOLANTE 19MM 20M", unidade="Unidade", categoria="Material Elétrico", marca="3M", setor="ALMOXARIFADO"))
        db.session.commit()
        manager = LoginManager(app)
        manager.request_loader(lambda request: db.session.get(Usuario, "9001"))
        app.register_blueprint(inventory.blueprint)
        app.register_blueprint(nf_leitura.blueprint)
        client = app.test_client()
        yield client
        db.session.remove()


def _send_sample(client):
    from io import BytesIO

    response = client.post("/nf/leitura/enviar", data={"arquivos": (BytesIO(build_danfe_pdf()), "nf 12345.pdf")}, content_type="multipart/form-data")
    assert response.status_code == 302
    return NFLeitura.query.order_by(NFLeitura.id.desc()).first()


def _launch_form(reading, overrides=None):
    from galint_flask.services.nf_leitura_service import load_result

    result = load_result(reading)
    form = {
        "numero": "12345",
        "chave": ACCESS_KEY,
        "cnpj": SUPPLIER_CNPJ,
        "fornecedor": "FERRAGENS SAO JOSE LTDA",
        "data_emissao": "2026-11-18",
        "data_recebimento": "2026-11-19",
    }
    for item in result["itens"]:
        n = item["n"]
        form.update(
            {
                f"incluir_{n}": "1",
                f"acao_{n}": item["acao"],
                f"descricao_{n}": item["descricao"],
                f"unidade_{n}": item["unidade"],
                f"quantidade_{n}": str(item["quantidade"]).replace(".", ","),
                f"valor_unitario_{n}": str(item["valor_unitario"]).replace(".", ","),
            }
        )
    form.update(overrides or {})
    return form


def test_reading_suggests_galint_items(client):
    reading = _send_sample(client)
    from galint_flask.services.nf_leitura_service import load_result

    result = load_result(reading)
    assert reading.status == "lida" and reading.fonte == "texto_pdf"
    assert reading.numero_documento == "12345" and reading.valor_total == 1501.9
    items = {item["n"]: item for item in result["itens"]}
    assert len(items) == 6
    assert items[2]["acao"] == "7891234567895"  # mesmo código do item
    assert items[2]["sugestoes"][0]["motivo"] == "mesmo código"
    assert "FITA001" in [suggestion["codigo"] for suggestion in items[4]["sugestoes"]]  # nome parecido
    assert items[1]["acao"] == "novo"


def test_launch_sends_new_items_to_pre_registration(client):
    reading = _send_sample(client)
    response = client.post(f"/nf/leitura/{reading.id}/lancar", data=_launch_form(reading, {"acao_4": "outro", "outro_4": "FITA001", "incluir_6": ""}))

    assert response.status_code == 302
    assert "open_pre_registered=1" in response.headers["Location"] and "pre_registered_document_number=12345" in response.headers["Location"]
    with client.session_transaction() as session:
        messages = [message for _, message in session.get("_flashes", [])]
    assert "NF 12345 lançada: 3 item(ns) novo(s) no pré-cadastro e 2 com entrada no estoque." in messages, messages
    assert not [message for message in messages if "falhou" in message or "não foi registrado" in message], messages

    document = DocumentoEntradaEstoque.query.one()
    assert document.chave_acesso == ACCESS_KEY
    lines = DocumentoEntradaEstoqueItem.query.order_by(DocumentoEntradaEstoqueItem.id_documento_item).all()
    assert len(lines) == 5  # o item 6 ficou desmarcado
    new_items = Item.query.filter(Item.pre_cadastro_pendente.is_(True)).all()
    assert sorted(item.descricao for item in new_items) == [
        "CABO FLEXIVEL 2,5MM AZUL ROLO 100M",
        "LUVA NITRILICA AZUL TAMANHO G CAIXA COM 100 UNIDADES",
        "TINTA ACRILICA FOSCA BRANCO 18L",
    ]
    assert all(item.pre_cadastro_origem == "nf" and item.pre_cadastro_documento_item_id for item in new_items)
    assert all(item.codigo_item.startswith("2") for item in new_items)  # código interno (o da NF não é EAN)
    assert db.session.get(Item, "FITA001").pre_cadastro_pendente in (False, None)
    links = {row.codigo_fornecedor: row.codigo_item for row in NFItemVinculo.query.all()}
    assert links["000555"] == "FITA001" and links["7891234567895"] == "7891234567895"
    assert db.session.get(NFLeitura, reading.id).status == "lancada"


def test_same_nf_cannot_be_launched_twice(client):
    reading = _send_sample(client)
    client.post(f"/nf/leitura/{reading.id}/lancar", data=_launch_form(reading))

    again = client.post(f"/nf/leitura/{reading.id}/lancar", data=_launch_form(reading))
    assert again.status_code == 302 and again.headers["Location"].endswith(f"/nf/leitura/{reading.id}")
    second = _send_sample(client)
    from galint_flask.services.nf_leitura_service import load_result

    assert load_result(second)["ja_lancada"]["numero"] == "12345"
    blocked = client.post(f"/nf/leitura/{second.id}/lancar", data=_launch_form(second))
    with client.session_transaction() as session:
        messages = [message for _, message in session.get("_flashes", [])]
    assert blocked.headers["Location"].endswith(f"/nf/leitura/{second.id}")
    assert any("já está no GALINT" in message for message in messages), messages
    assert DocumentoEntradaEstoque.query.count() == 1
