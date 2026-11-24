"""Cadastro de item pelo código lido no app (2.2.6): POST /api/mobile/documentos-fiscais.

Pedido do usuário em 23/11/2026: quando o código lido não existe, o app pergunta se quer cadastrar e
abre o mesmo "Lançar entrada com NF", chamando a mesma rota. Este teste manda exatamente o que a tela
manda (com nova_descricao, nova_categoria e nova_unidade) e confere que o item nasce com o código lido,
em pré-cadastro como no site, com o documento e o financeiro gravados. Banco SQLite em memória; só o
aviso do Telegram/app é simulado.
"""
import pytest
from flask import Flask
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Item, Usuario
from galint_flask.views import api_mobile

AUTH = {"Authorization": "Bearer token-ok"}
CHAVE = "53251112345678000195550010000012341000012345"


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@compiles(INET, "sqlite")
def _inet_as_text_on_sqlite(element, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="mobile-new-item-test",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    app.register_blueprint(api_mobile.blueprint)
    from galint_flask.services import notification_router

    created = []
    monkeypatch.setattr(
        notification_router.NotificationRouterService,
        "route_item_created",
        staticmethod(lambda codigo, **kwargs: created.append((codigo, kwargs))),
    )
    with app.app_context():
        db.init_app(app)
        # Tabelas com tipos só do PostgreSQL (INET etc.) não entram; a rota não usa nenhuma delas.
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        db.session.add(Usuario(matricula="9001", nome="ADMINISTRADOR", is_admin=True))
        db.session.commit()
        monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: Usuario.query.get("9001") if token == "token-ok" else None)
        client = app.test_client()
        client.created = created
        yield client
        db.session.remove()
        db.drop_all()


def _payload(**extra):
    payload = {
        "doc_mode": "nf",
        "finance_tipo_documento": "nf",
        "finance_origem_valor": "compra_nf",
        "finance_comprovacao_status": "comprovado",
        "codigo": "7891234567895",
        "novo_codigo": "7891234567895",
        "nova_descricao": "LUVA NITRÍLICA AZUL G",
        "nova_categoria": "EPI",
        "nova_unidade": "Par",
        "quantidade": 12,
        "nota_fiscal": "1234",
        "chave_acesso": CHAVE,
        "supplier_cnpj": "12345678000195",
        "data_emissao": "2026-11-20",
        "data_recebimento": "2026-11-23",
        "preco_unitario": 4.5,
    }
    payload.update(extra)
    return payload


def test_scanned_code_becomes_a_new_item_through_the_entry_route(client):
    response = client.post("/api/mobile/documentos-fiscais", json=_payload(), headers=AUTH)

    data = response.get_json()
    assert response.status_code == 200, data
    assert data["success"] is True
    assert data["data"]["item_criado"] is True
    assert data["data"]["pre_cadastro_pendente"] is True

    item = db.session.get(Item, "7891234567895")
    assert item.descricao == "LUVA NITRÍLICA AZUL G"
    assert item.unidade == "Par"
    assert item.pre_cadastro_pendente is True
    assert item.pre_cadastro_origem == "nf"

    documento = DocumentoEntradaEstoque.query.one()
    assert (documento.numero_documento, documento.chave_acesso) == ("1234", CHAVE)
    linha = DocumentoEntradaEstoqueItem.query.one()
    assert (linha.codigo_item, float(linha.quantidade)) == ("7891234567895", 12.0)
    assert item.pre_cadastro_documento_item_id == linha.id_documento_item
    assert [codigo for codigo, _ in client.created] == ["7891234567895"]


def test_new_item_with_packaging_counts_the_can_not_the_liters(client):
    """App 2.3.1 (24/11/2026): 1 lata de 18 L por R$ 429,90 na NF 617377. Com só a unidade base (Litro),
    o app pedia "Quantidade (litros)" e a conta dava 18 × 429,90 = R$ 7.738,20. Agora a tela manda a
    embalagem e o conteúdo (como o site): a NF conta latas e o estoque recebe os litros."""
    response = client.post(
        "/api/mobile/documentos-fiscais",
        json=_payload(
            nova_descricao="TINTA ACRÍLICA BRANCA 18L",
            nova_categoria="Pintura",
            nova_unidade="Litro",
            nova_unidade_documental="lata",
            novo_conteudo_embalagem=18,
            quantidade=1,
            preco_unitario=429.9,
        ),
        headers=AUTH,
    )

    assert response.status_code == 200, response.get_json()
    item = db.session.get(Item, "7891234567895")
    assert (item.unidade, item.tipo_embalagem_novo, float(item.unidades_por_embalagem)) == ("Litro", "lata", 18.0)
    assert float(item.litros_por_embalagem) == 18.0
    linha = DocumentoEntradaEstoqueItem.query.one()
    assert float(linha.quantidade) == 1.0
    assert float(linha.quantidade_base) == 18.0
    assert float(linha.valor_total) == pytest.approx(429.9)


def test_new_item_packaging_needs_the_content(client):
    response = client.post(
        "/api/mobile/documentos-fiscais",
        json=_payload(nova_unidade="Litro", nova_unidade_documental="lata", quantidade=1),
        headers=AUTH,
    )

    assert response.status_code == 400
    assert "conteudo por embalagem" in response.get_json()["message"]
    assert db.session.get(Item, "7891234567895") is None


def test_new_item_needs_a_description(client):
    response = client.post("/api/mobile/documentos-fiscais", json=_payload(nova_descricao=""), headers=AUTH)

    assert response.status_code == 400
    assert "descrição" in response.get_json()["message"]
    assert db.session.get(Item, "7891234567895") is None
