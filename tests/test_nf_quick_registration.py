import pytest
from datetime import datetime, timedelta, timezone
from flask import Flask
from flask_login import LoginManager
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from galint_flask.extensions import db
from galint_flask.models import (
    DocumentoEntradaEstoque,
    DocumentoEntradaEstoqueItem,
    FinanceSupplier,
    Item,
    NFeDistributionConfig,
    NFeDistributionDocument,
)
from galint_flask.services.nfe_distribution_service import _decrypt, public_config, save_configuration
from galint_flask.views.nf import _calculate_nfe_access_key_digit, blueprint


class _AdminUser:
    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_admin = True
    id = "admin"
    nome = "Administrador de teste"

    def get_id(self):
        return "admin"


@pytest.fixture
def nf_client():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        FEATURE_NOTAS_ENABLED=True,
    )
    manager = LoginManager()
    manager.init_app(app)

    @manager.user_loader
    def load_user(user_id):
        return _AdminUser() if user_id == "admin" else None

    app.register_blueprint(blueprint)
    with app.app_context():
        db.init_app(app)
        db.metadata.create_all(
            bind=db.engine,
            tables=[
                Item.__table__,
                DocumentoEntradaEstoque.__table__,
                DocumentoEntradaEstoqueItem.__table__,
                FinanceSupplier.__table__,
                NFeDistributionConfig.__table__,
                NFeDistributionDocument.__table__,
            ],
        )
        yield app.test_client()
        db.session.remove()
        db.metadata.drop_all(
            bind=db.engine,
            tables=[
                DocumentoEntradaEstoqueItem.__table__,
                DocumentoEntradaEstoque.__table__,
                FinanceSupplier.__table__,
                NFeDistributionConfig.__table__,
                NFeDistributionDocument.__table__,
                Item.__table__,
            ],
        )


def _login(client):
    with client.session_transaction() as session:
        session["_user_id"] = "admin"
        session["_fresh"] = True


def test_quick_registration_creates_non_stock_draft(nf_client):
    _login(nf_client)

    response = nf_client.post(
        "/nf/api/documentos/cadastro-rapido",
        json={"numero_documento": "NF-TESTE-204", "fornecedor_nome": "Fornecedor teste"},
    )

    assert response.status_code == 201
    result = response.get_json()
    assert result["success"] is True
    with nf_client.application.app_context():
        document = db.session.get(DocumentoEntradaEstoque, result["document"]["id_documento"])
        assert document is not None
        assert document.numero_documento == "NF-TESTE-204"
        assert document.status_integracao == "cadastro_rapido_pendente"
        assert document.movimenta_estoque is False

        duplicate = nf_client.post(
            "/nf/api/documentos/cadastro-rapido",
            json={"numero_documento": "NF-TESTE-204"},
        )
        assert duplicate.status_code == 409
        assert duplicate.get_json()["existing_url"]


def test_quick_registration_rejects_empty_document_number(nf_client):
    _login(nf_client)

    response = nf_client.post("/nf/api/documentos/cadastro-rapido", json={})

    assert response.status_code == 400
    assert "número da NF" in response.get_json()["message"]


def test_quick_registration_extracts_number_and_cnpj_from_access_key(nf_client):
    _login(nf_client)
    key_prefix = "35" + "2611" + "11222333000181" + "55" + "001" + "000000123" + "1" + "12345678"
    access_key = key_prefix + str(_calculate_nfe_access_key_digit(key_prefix))

    response = nf_client.post(
        "/nf/api/documentos/cadastro-rapido",
        json={"chave_acesso": access_key},
    )

    assert response.status_code == 201
    with nf_client.application.app_context():
        document = db.session.get(DocumentoEntradaEstoque, response.get_json()["document"]["id_documento"])
        assert document.numero_documento == "123"
        assert document.cnpj_emitente == "11222333000181"
        assert document.chave_acesso == access_key


def test_missing_access_key_can_be_registered_from_global_search(nf_client):
    _login(nf_client)
    key_prefix = "35" + "2611" + "11222333000181" + "55" + "001" + "000000123" + "1" + "12345678"
    access_key = key_prefix + str(_calculate_nfe_access_key_digit(key_prefix))

    response = nf_client.get(f"/nf/api/documentos/busca-modal?q={access_key}")

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "message": "Nota fiscal não encontrada.",
        "can_register": True,
    }


def test_certificate_configuration_is_encrypted(nf_client):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "GALINT test certificate")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(private_key, hashes.SHA256())
    )
    password = b"pfx-test-password"
    pfx_data = pkcs12.serialize_key_and_certificates(
        b"test",
        private_key,
        certificate,
        None,
        serialization.BestAvailableEncryption(password),
    )

    with nf_client.application.app_context():
        save_configuration(
            cnpj_destinatario="11222333000181",
            uf_autor="35",
            ambiente="homologacao",
            enabled=True,
            certificate_data=pfx_data,
            certificate_password=password.decode("ascii"),
        )
        stored = db.session.get(NFeDistributionConfig, 1)
        assert stored is not None
        assert password.decode("ascii") not in stored.senha_certificado_criptografada
        assert _decrypt(stored.certificado_pfx_criptografado) == pfx_data
        assert _decrypt(stored.senha_certificado_criptografada) == password
        assert public_config()["has_certificate"] is True
        stored.ultimo_nsu = "000000000000123"
        stored.maximo_nsu = "000000000000456"
        db.session.commit()

        save_configuration(
            cnpj_destinatario="11222333000181",
            uf_autor="41",
            ambiente="homologacao",
            enabled=True,
        )
        assert stored.ultimo_nsu == "0"
        assert stored.maximo_nsu == "0"
