"""Lançamento rápido de entrada pelo app (21/11/2026): /api/mobile/chave-acesso.

A chave lida pela câmera (código de barras do DANFE ou QR da NFC-e) vira número da NF, série e CNPJ
do emitente, com o fornecedor achado pelo CNPJ. Só administradores, como os documentos fiscais.
"""
from flask import Flask
import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import DocumentoEntradaEstoque, FinanceSupplier
from galint_flask.services.finance_service import finance_service
from galint_flask.views import api_mobile
from galint_flask.views import nf as nf_views


@compiles(JSONB, "sqlite")
def _jsonb_as_sqlite_json(_type, _compiler, **_kwargs):
    return "JSON"


class _Admin:
    matricula = "adm-1"
    nome = "Administrador"
    is_admin = 1


class _Worker:
    matricula = "op-1"
    nome = "Operador"
    is_admin = 0


def _valid_key(numero="000123456"):
    first = "31" + "2511" + "12345678000195" + "55" + "001" + numero + "1" + "12345678"
    return first + str(nf_views._calculate_nfe_access_key_digit(first))


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="access-key-test",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    app.register_blueprint(api_mobile.blueprint)
    users = {"token-adm": _Admin, "token-op": _Worker}
    monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: users[token]() if token in users else None)
    monkeypatch.setattr(api_mobile, "_mobile_user_block_info", lambda user: (False, None))
    monkeypatch.setattr(api_mobile, "_validate_mobile_session_token", lambda token, user: (True, None))
    tables = [FinanceSupplier.__table__, DocumentoEntradaEstoque.__table__]
    with app.app_context():
        db.init_app(app)
        db.metadata.create_all(bind=db.engine, tables=tables)
        db.session.add(FinanceSupplier(razao_social="CASA DAS TINTAS LTDA", nome_fantasia="Casa das Tintas",
                                       cnpj=finance_service.normalize_cnpj("12345678000195")))
        db.session.commit()
        yield app.test_client()
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=tables)


def _get(client, chave, token="token-adm"):
    return client.get("/api/mobile/chave-acesso", query_string={"chave": chave}, headers={"Authorization": f"Bearer {token}"})


def test_key_from_danfe_barcode_fills_number_series_cnpj_and_supplier(client):
    response = _get(client, _valid_key())

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["chave"]["numero_documento"] == "123456"
    assert payload["chave"]["serie"] == "1"
    assert payload["chave"]["cnpj_emitente"] == finance_service.normalize_cnpj("12345678000195")
    assert payload["fornecedor"]["nome"] == "Casa das Tintas"
    assert payload["documento"] is None


def test_key_inside_nfce_qr_code_url_is_found(client):
    qr = f"https://www.fazenda.mg.gov.br/nfce/qrcode?p={_valid_key('000000789')}|2|1|1|ABCDEF"
    response = _get(client, qr)

    assert response.status_code == 200
    assert response.get_json()["chave"]["numero_documento"] == "789"


def test_key_with_wrong_check_digit_is_refused(client):
    key = _valid_key()
    wrong = key[:-1] + str((int(key[-1]) + 1) % 10)
    response = _get(client, wrong)

    assert response.status_code == 400
    assert "dígito verificador" in response.get_json()["message"]


def test_only_admins_read_keys(client):
    response = _get(client, _valid_key(), token="token-op")
    assert response.status_code == 403
