"""App 2.2.4 (23/11/2026): atualização sozinha do app e foto do item pelo link.

- /api/mobile/app/atualizacao e /api/mobile/app/apk/<código>: o GALINT distribui o APK que estiver
  em instance/apks/ (como o Pipocas), e o app se atualiza sem instalar à mão celular por celular.
- /api/mobile/itens/<código>/foto/url: a foto do item pelo link copiado da busca de imagens, como em
  Documentos Fiscais do site.
"""
import base64

from flask import Flask
import pytest

from galint_flask.extensions import db
from galint_flask.models import Item, StockBalance
from galint_flask.services.item_foto_service import ItemFotoService
from galint_flask.views import api_mobile


class _Admin:
    matricula = "adm-1"
    nome = "Administrador"
    is_admin = 1


class _Worker:
    matricula = "op-1"
    nome = "Operador"
    is_admin = 0


@pytest.fixture
def app(monkeypatch, tmp_path):
    flask_app = Flask(__name__, instance_path=str(tmp_path / "instance"))
    flask_app.config.update(
        SECRET_KEY="app-release-test",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    flask_app.register_blueprint(api_mobile.blueprint)
    users = {"token-adm": _Admin, "token-op": _Worker}
    monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: users[token]() if token in users else None)
    monkeypatch.setattr(api_mobile, "_mobile_user_block_info", lambda user: (False, None))
    monkeypatch.setattr(api_mobile, "_validate_mobile_session_token", lambda token, user: (True, None))
    apks = tmp_path / "instance" / "apks"
    apks.mkdir(parents=True)
    (apks / "GALINT-2.2.3-codigo16-entrada-nf.apk").write_bytes(b"apk-16")
    (apks / "GALINT-2.2.4-codigo17-foto-e-atualizacao.apk").write_bytes(b"apk-17")
    (apks / "GALINT-2.2.4-codigo17-foto-e-atualizacao.txt").write_text("Foto do item pelo link.", encoding="utf-8")
    (apks / "outro-arquivo.apk").write_bytes(b"ignorado")
    tables = [Item.__table__, StockBalance.__table__]
    with flask_app.app_context():
        db.init_app(flask_app)
        db.metadata.create_all(bind=db.engine, tables=tables)
        db.session.add(Item(codigo_item="7896231701129", descricao="COLA JUNTAS", setor="Estoque", foto_path="uploads/itens/antiga.webp"))
        db.session.commit()
        yield flask_app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=tables)


def test_app_asks_for_update_and_downloads_latest_apk(app):
    client = app.test_client()

    old = client.get("/api/mobile/app/atualizacao", query_string={"code": 16}).get_json()
    current = client.get("/api/mobile/app/atualizacao", query_string={"code": 17}).get_json()
    apk = client.get(old["url"])

    assert old["disponivel"] is True
    assert (old["version_name"], old["version_code"]) == ("2.2.4", 17)
    assert old["notas"] == "Foto do item pelo link."
    assert len(old["sha256"]) == 64
    assert current["disponivel"] is False
    assert apk.status_code == 200
    assert apk.data == b"apk-17"
    assert apk.mimetype == "application/vnd.android.package-archive"
    assert client.get("/api/mobile/app/apk/99").status_code == 404


def test_no_published_apk_means_no_update(app, tmp_path):
    for path in (tmp_path / "instance" / "apks").iterdir():
        path.unlink()
    payload = app.test_client().get("/api/mobile/app/atualizacao", query_string={"code": 1}).get_json()
    assert payload == {"success": True, "disponivel": False}


def test_item_photo_from_google_images_link(app, monkeypatch):
    calls, deleted = [], []
    monkeypatch.setattr(ItemFotoService, "download_foto_from_url", staticmethod(lambda url, codigo: calls.append((url, codigo)) or "uploads/itens/nova.webp"))
    monkeypatch.setattr(ItemFotoService, "deletar_foto", staticmethod(lambda path: deleted.append(path) or True))
    google = "https://www.google.com/imgres?imgurl=https%3A%2F%2Floja.com%2Fcola.jpg&imgrefurl=https%3A%2F%2Floja.com"

    response = app.test_client().post(
        "/api/mobile/itens/7896231701129/foto/url",
        json={"url": google},
        headers={"Authorization": "Bearer token-adm"},
    )

    assert response.status_code == 200
    assert calls == [("https://loja.com/cola.jpg", "7896231701129")]
    assert deleted == ["uploads/itens/antiga.webp"]
    assert response.get_json()["foto_url"].endswith("uploads/itens/nova.webp")
    with app.app_context():
        item = db.session.get(Item, "7896231701129")
        assert item.foto_path == "uploads/itens/nova.webp"
        assert item.ultima_edicao_em is not None


def test_item_photo_from_base64_copied_image(app, monkeypatch):
    received = []
    monkeypatch.setattr(ItemFotoService, "_process_image_bytes", staticmethod(lambda raw, codigo: received.append(raw) or "uploads/itens/b64.webp"))
    monkeypatch.setattr(ItemFotoService, "deletar_foto", staticmethod(lambda path: True))
    data_url = "data:image/jpeg;base64," + base64.b64encode(b"jpeg-bytes").decode()

    response = app.test_client().post(
        "/api/mobile/itens/7896231701129/foto/url",
        json={"url": data_url},
        headers={"Authorization": "Bearer token-adm"},
    )

    assert response.status_code == 200
    assert received == [b"jpeg-bytes"]


def test_only_admins_change_item_photo(app):
    response = app.test_client().post(
        "/api/mobile/itens/7896231701129/foto/url",
        json={"url": "https://loja.com/cola.jpg"},
        headers={"Authorization": "Bearer token-op"},
    )
    assert response.status_code == 403
