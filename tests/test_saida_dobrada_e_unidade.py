"""NF 28498 em "Erro: Saldo insuficiente" (26/11/2026): 1 FARDO de BAMBU (24 un) com o saldo em -432.

O saldo estava negativo porque duas saídas antigas estavam no razão duas vezes (a saída múltipla e a reconstrução
"ledger_backfill", 3 horas depois por causa do fuso). Aqui:
- a entrada não é mais recusada por saldo negativo (só o que tira do estoque esbarra no saldo);
- a saída em dobro é achada, a compensada por ajuste posterior fica de fora e a correção vale uma vez só;
- o "Corrigir" do documento troca a unidade da linha (FARDO ↔ UNIDADE) e refaz a conta;
- a lista de zerados traz NF e data das entradas.
"""
from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import (
    DocumentoEntradaEstoque,
    DocumentoEntradaEstoqueItem,
    Entrada,
    Item,
    ProductUnit,
    StockBalance,
    StockMovement,
    Usuario,
)

BAMBU = "789987456654101"


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@compiles(INET, "sqlite")
def _inet_as_text_on_sqlite(element, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="saida-dobrada", SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    with app.app_context():
        db.init_app(app)
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        db.session.add(Usuario(matricula="9001", nome="ADMINISTRADOR", is_admin=True))
        db.session.add(Item(codigo_item=BAMBU, descricao="BAMBU RACHADO (2 METROS", unidade="Unidade", categoria="Material Construção",
                            setor="ALMOXARIFADO", tipo_embalagem_novo="fardo", unidades_por_embalagem=24))
        db.session.add_all([
            ProductUnit(product_id=BAMBU, unit_code="unidade", unit_label="Unidade", dimension="unit", is_base=True, active=True),
            ProductUnit(product_id=BAMBU, unit_code="fardo", unit_label="Fardo", dimension="unit", is_base=False, active=True),
        ])
        db.session.commit()
        from galint_flask.services import notification_router

        monkeypatch.setattr(notification_router.NotificationRouterService, "route_inventory_event", staticmethod(lambda *args, **kwargs: None))
        yield app
        db.session.remove()


def _mov(tipo, quantidade, quando, *, ref_type, ref_id=None, fonte="inventory_engine", **extra):
    movimento = StockMovement(product_id=BAMBU, movement_type=tipo, quantity_base=quantidade, unit_base="un",
                              reference_type=ref_type, reference_id=ref_id, metadata_json={"source": fonte, **extra}, created_at=quando)
    db.session.add(movimento)
    return movimento


def _bambu_como_em_producao():
    """432 un entraram (18 fardos); saíram 288 + 144, cada saída gravada duas vezes."""
    for n in range(18):
        _mov("entrada", 24, datetime(2026, 3, 25, 13, 0) + timedelta(minutes=n), ref_type="entrada_documento_item", ref_id=str(300 + n), fonte="documento_fiscal")
    _mov("saida", -288, datetime(2026, 4, 24, 16, 21, 8), ref_type="movements_saida_multipla", ref_id=None, local_servico="INSTALAÇÃO NA CHURRASQUEIRA 1")
    _mov("saida", -144, datetime(2026, 5, 11, 16, 0, 43), ref_type="movements_saida_multipla", ref_id="2060")
    _mov("saida", -288, datetime(2026, 4, 24, 13, 21, 8), ref_type="saida", ref_id="1653", fonte="ledger_backfill", local_servico="INSTALAÇÃO NA CHURRASQUEIRA 1")
    _mov("saida", -144, datetime(2026, 5, 11, 13, 0, 43), ref_type="saida", ref_id="2060", fonte="ledger_backfill")
    db.session.add(StockBalance(product_id=BAMBU, quantity_base=-432, read_model_ready=True))
    db.session.commit()


def _saldo():
    from galint_flask.services.balance_provider import balance_provider

    return float(balance_provider.get_balance(BAMBU).quantity_base)


def test_entrada_passa_com_saldo_negativo_e_a_saida_continua_barrada(app):
    from galint_flask.services.inventory_engine import InventoryEngineError, inventory_engine

    _bambu_como_em_producao()
    inventory_engine.register_entry(product_id=BAMBU, quantity=1, from_unit="fardo", metadata={"source": "teste"})
    assert _saldo() == pytest.approx(-408)
    with pytest.raises(InventoryEngineError, match="Saldo insuficiente"):
        inventory_engine.register_exit(product_id=BAMBU, quantity=1, from_unit="unidade", metadata={"source": "teste"})


def test_saida_em_dobro_e_achada_e_corrigida_uma_vez(app):
    from galint_flask.services import saida_dobrada

    _bambu_como_em_producao()
    resumo = saida_dobrada.resumo_por_item()[BAMBU]
    assert (resumo["pares"], resumo["quantidade"]) == (2, 432)
    assert resumo["saidas"][0]["local"] == "INSTALAÇÃO NA CHURRASQUEIRA 1"

    resultado = saida_dobrada.corrigir_item(BAMBU, matricula="9001")
    assert (resultado["corrigidas"], resultado["saldo_antes"], resultado["saldo_depois"]) == (2, -432, 0)
    correcoes = StockMovement.query.filter_by(product_id=BAMBU, reference_type=saida_dobrada.REFERENCIA).all()
    assert sorted(float(m.quantity_base) for m in correcoes) == [144, 288]

    assert saida_dobrada.resumo_por_item() == {}
    with pytest.raises(ValueError, match="não tem saída contada duas vezes"):
        saida_dobrada.corrigir_item(BAMBU, matricula="9001")


def _cabe_nas_colunas(modelo, linhas):
    """O SQLite não confere o tamanho do texto; o PostgreSQL recusa (StringDataRightTruncation)."""
    for linha in linhas:
        for coluna in modelo.__table__.columns:
            tamanho = getattr(coluna.type, "length", None)
            valor = getattr(linha, coluna.key, None)
            if tamanho and isinstance(valor, str):
                assert len(valor) <= tamanho, f"{modelo.__tablename__}.{coluna.key} = {valor!r} passa de {tamanho}"


def test_correcao_cabe_nas_colunas_do_postgres(app):
    """27/11/2026: o primeiro CORRIGIR do bambu falhou no PostgreSQL porque operation_logs.source (20) recebeu
    "correcao_saida_dobrada" (22). Nada foi gravado pela metade; agora a origem é "saida_dobrada"."""
    from galint_flask.models import OperationLog
    from galint_flask.services import saida_dobrada

    _bambu_como_em_producao()
    saida_dobrada.corrigir_item(BAMBU, matricula="9001")
    _cabe_nas_colunas(OperationLog, OperationLog.query.all())
    _cabe_nas_colunas(StockMovement, StockMovement.query.filter_by(reference_type=saida_dobrada.REFERENCIA).all())
    assert {log.source for log in OperationLog.query.all()} >= {"saida_dobrada"}


def test_modal_mostra_o_saldo_do_razao(app):
    """O saldo da lista de itens de item com embalagem não fica negativo (o bambu com -432 aparecia como 0, e a
    correção mostrava "0 → 432"). O modal usa o razão: "-432 → 0"."""
    from galint_flask.services import itens_zerados

    _bambu_como_em_producao()
    dados = itens_zerados.montar([{"codigo": BAMBU, "descricao": "BAMBU RACHADO (2 METROS", "saldo": 0.0}], no_carrinho=set())
    assert dados["zerados"][0]["saldo"] == -432
    assert dados["zerados"][0]["dobro"]["saldo_corrigido"] == 0
    assert (dados["dobradas"][0]["saldo"], dados["dobradas"][0]["dobro"]["saldo_corrigido"]) == (-432, 0)


def test_saida_compensada_pela_conferencia_fica_de_fora(app):
    from galint_flask.services import saida_dobrada

    _bambu_como_em_producao()
    # Conferência de 20/04... não compensa (antes das duas); de 01/05 compensa só a de 24/04.
    _mov("ajuste", 5, datetime(2026, 4, 20, 9, 0), ref_type="admin_balance_override", fonte="admin_balance_portal")
    _mov("ajuste", 288, datetime(2026, 5, 1, 9, 0), ref_type="admin_balance_override", fonte="admin_balance_portal")
    db.session.commit()
    resumo = saida_dobrada.resumo_por_item([BAMBU])[BAMBU]
    assert (resumo["pares"], resumo["quantidade"]) == (1, 144)


def test_corrigir_troca_a_unidade_da_linha(app):
    from galint_flask.services.unidade_da_linha import opcoes_de_unidade, trocar_unidade

    documento = DocumentoEntradaEstoque(tipo_documento="nf", numero_documento="28498", data_emissao=date(2026, 11, 20), data_recebimento=date(2026, 11, 26))
    db.session.add(documento)
    db.session.flush()
    linha = DocumentoEntradaEstoqueItem(documento_id=documento.id_documento, codigo_item=BAMBU, quantidade=1, valor_unitario=119.39,
                                        valor_total=119.39, unidade_quantidade="fardo", quantidade_base=24, status_processamento="erro")
    db.session.add(linha)
    db.session.commit()

    opcoes = opcoes_de_unidade(db.session.get(Item, BAMBU))
    assert [(o["codigo"], o["fator"], o["base"]) for o in opcoes] == [("unidade", 1.0, "UN"), ("fardo", 24.0, "UN")]

    from galint_flask.services.document_integrity_service import allow_document_quantity_update

    # Como na rota "nf.editar_documento": a quantidade da NF só muda dentro do fluxo autorizado.
    with allow_document_quantity_update("teste"):
        linha.quantidade = 24
        assert trocar_unidade(linha, "unidade") is True
        db.session.flush()
    assert (linha.unidade_quantidade, linha.quantidade_base, linha.valor_total) == ("unidade", 24, 119.39)
    assert linha.valor_unitario == pytest.approx(119.39 / 24, abs=0.01)
    assert trocar_unidade(linha, "unidade") is False

    linha.status_processamento = "processado"
    with pytest.raises(ValueError, match="já entrou no estoque"):
        trocar_unidade(linha, "fardo")
    with pytest.raises(ValueError, match="não existe"):
        trocar_unidade(linha, "caixa")


def test_zerados_trazem_nf_e_data_da_entrada(app):
    from galint_flask.services import itens_zerados

    documento = DocumentoEntradaEstoque(tipo_documento="nf", numero_documento="3891", data_recebimento=date(2026, 11, 23))
    db.session.add(documento)
    db.session.flush()
    entrada_da_nf = Entrada(codigo_item=BAMBU, matricula="9001", quantidade=24, nota_fiscal="3891", data_entrada=datetime(2026, 11, 23, 9))
    db.session.add(entrada_da_nf)
    db.session.flush()
    db.session.add(DocumentoEntradaEstoqueItem(documento_id=documento.id_documento, entrada_id=entrada_da_nf.id_entrada, codigo_item=BAMBU,
                                               quantidade=1, unidade_quantidade="fardo", status_processamento="processado"))
    db.session.add(Entrada(codigo_item=BAMBU, matricula="9001", quantidade=96, nota_fiscal="", data_entrada=datetime(2026, 1, 30, 21)))
    db.session.commit()

    itens = [
        {"codigo": BAMBU, "descricao": "BAMBU RACHADO (2 METROS", "saldo": 0.0, "categoria": "Material Construção"},
        {"codigo": "OUTRO", "descricao": "COM SALDO", "saldo": 3.0},
        {"codigo": "PRE", "descricao": "PRÉ-CADASTRO", "saldo": 0.0, "pre_cadastro_pendente": True},
    ]
    dados = itens_zerados.montar(itens, no_carrinho={BAMBU})
    assert [z["codigo"] for z in dados["zerados"]] == [BAMBU]
    bambu = dados["zerados"][0]
    assert bambu["na_projecao"] is True
    assert [(e["nf"], e["data"]) for e in bambu["entradas"]] == [("NF 3891", "2026-11-23"), ("SEM NF", "2026-01-30")]
