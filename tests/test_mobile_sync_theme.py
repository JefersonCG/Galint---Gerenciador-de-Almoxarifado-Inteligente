"""App 2.2.0 (21/11/2026): base do celular sempre igual à do servidor, avisos e Aparência.

- /api/mobile/estoque/mudancas: sem cursor manda tudo; com cursor, só o que mudou (e nada quando
  nada mudou). Até a 2.1.1 a base do celular nunca abria (expo-sqlite sem openDatabase) e o app
  baixava a lista inteira de tempos em tempos.
- /api/mobile/notifications/inbox/read-all: havia 18 mil avisos sem ler.
- theme_service e /api/mobile/tema: a Aparência do Pipocas trazida para o GALINT (escuro).
"""
from types import SimpleNamespace

from flask import Flask
import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import (
    EmpresaConfig,
    Entrada,
    GalintNotifyRecipient,
    InventarioEvento,
    Item,
    ProductUnit,
    Saida,
    StockBalance,
    StockMovement,
    Usuario,
)
from galint_flask.services import theme_service
from galint_flask.services.users import UserPayload, UserService
from galint_flask.views import api_mobile

TABLES = [
    Usuario.__table__,
    Item.__table__,
    StockBalance.__table__,
    ProductUnit.__table__,
    Entrada.__table__,
    Saida.__table__,
    InventarioEvento.__table__,
    StockMovement.__table__,
    GalintNotifyRecipient.__table__,
    EmpresaConfig.__table__,
]
AUTH = {"Authorization": "Bearer token-ok"}


@compiles(JSONB, "sqlite")
def _jsonb_as_sqlite_json(_type, _compiler, **_kwargs):
    # stock_movements e a caixa de avisos usam JSONB (PostgreSQL); no SQLite do teste vira JSON.
    return "JSON"


class _MobileUser:
    matricula = "op-7"
    nome = "Operador do App"
    is_admin = 0
    pode_ajustar_estoque = 0


@pytest.fixture
def app(monkeypatch):
    flask_app = Flask(__name__)
    flask_app.config.update(
        SECRET_KEY="mobile-sync-test",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    flask_app.register_blueprint(api_mobile.blueprint)
    monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: _MobileUser() if token == "token-ok" else None)
    monkeypatch.setattr(api_mobile, "_mobile_user_block_info", lambda user: (False, None))
    monkeypatch.setattr(api_mobile, "_validate_mobile_session_token", lambda token, user: (True, None))
    with flask_app.app_context():
        db.init_app(flask_app)
        db.metadata.create_all(bind=db.engine, tables=TABLES)
        db.session.add_all([
            Item(codigo_item="A-MIGRADO", descricao="ALFA", setor="Estoque", categoria="Geral", unidade="Unidade"),
            Item(codigo_item="B-PENDENTE", descricao="BETA", setor="Estoque", categoria="Geral", unidade="Unidade"),
            Item(codigo_item="C-SEM-SALDO", descricao="GAMA", setor="Estoque", categoria="Geral", unidade="Unidade"),
        ])
        db.session.flush()
        db.session.add_all([
            StockBalance(product_id="A-MIGRADO", quantity_base=7.0, read_model_ready=True),
            StockBalance(product_id="B-PENDENTE", quantity_base=3.0, read_model_ready=False),
        ])
        db.session.commit()
        yield flask_app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=TABLES)


def _changes(client, cursor=None):
    response = client.get("/api/mobile/estoque/mudancas", query_string={"cursor": cursor} if cursor else None, headers=AUTH)
    assert response.status_code == 200
    return response.get_json()


def test_changes_without_cursor_send_whole_stock_then_nothing(app):
    client = app.test_client()
    first = _changes(client)
    second = _changes(client, first["cursor"])

    assert first["full"] is True
    assert {row["id"]: row["quantidade"] for row in first["items"]} == {"A-MIGRADO": 7.0, "B-PENDENTE": 3.0, "C-SEM-SALDO": 0.0}
    assert first["total_itens"] == 3
    assert second["full"] is False
    assert second["items"] == []


def test_changes_send_only_the_item_of_a_new_withdrawal(app):
    client = app.test_client()
    cursor = _changes(client)["cursor"]
    with app.app_context():
        db.session.add(Saida(codigo_item="C-SEM-SALDO", quantidade=1.0))
        db.session.commit()

    delta = _changes(client, cursor)

    assert delta["full"] is False
    assert [row["id"] for row in delta["items"]] == ["C-SEM-SALDO"]


def test_changes_follow_balance_read_model_updates(app):
    client = app.test_client()
    cursor = _changes(client)["cursor"]
    with app.app_context():
        balance = db.session.get(StockBalance, "A-MIGRADO")
        balance.quantity_base = 2.0
        db.session.commit()

    delta = _changes(client, cursor)

    by_code = {row["id"]: row["quantidade"] for row in delta["items"]}
    assert by_code["A-MIGRADO"] == 2.0
    assert "C-SEM-SALDO" not in by_code  # sem saldo gravado, não foi tocado


def test_new_or_removed_item_forces_full_list(app):
    client = app.test_client()
    cursor = _changes(client)["cursor"]
    with app.app_context():
        db.session.add(Item(codigo_item="D-NOVO", descricao="DELTA", setor="Estoque", categoria="Geral", unidade="Unidade"))
        db.session.commit()

    delta = _changes(client, cursor)

    assert delta["full"] is True
    assert len(delta["items"]) == 4


def test_invalid_cursor_falls_back_to_full_list(app):
    delta = _changes(app.test_client(), "nao-e-um-cursor")
    assert delta["full"] is True
    assert len(delta["items"]) == 3


def test_changes_require_login(app):
    assert app.test_client().get("/api/mobile/estoque/mudancas").status_code == 401


def test_mark_all_notifications_read(app):
    with app.app_context():
        db.session.add_all([GalintNotifyRecipient(message_id=index, matricula="op-7") for index in range(1, 4)])
        db.session.add(GalintNotifyRecipient(message_id=9, matricula="outra"))
        db.session.commit()

    response = app.test_client().post("/api/mobile/notifications/inbox/read-all", headers=AUTH)

    assert response.status_code == 200
    assert response.get_json()["updated"] == 3
    with app.app_context():
        statuses = {(row.matricula, row.status) for row in GalintNotifyRecipient.query.all()}
    assert statuses == {("op-7", "read"), ("outra", "unread")}


def test_mobile_theme_is_public_and_default_without_customization(app):
    response = app.test_client().get("/api/mobile/tema")

    tema = response.get_json()["tema"]
    assert response.status_code == 200
    assert tema["personalizada"] is False
    assert tema["destaque"] == theme_service.DEFAULTS["destaque"]


def test_theme_defaults_keep_site_identical():
    assert theme_service.stylesheet(None).startswith("/*")
    assert theme_service.problems(dict(theme_service.DEFAULTS)) == ([], [])
    preview = theme_service.preview(dict(theme_service.DEFAULTS))
    skin = {name: value for name, value in preview["variables"].items() if name.startswith("--skin-")}
    assert set(skin.values()) == {"initial"}
    # As variáveis do próprio Bootstrap voltam aos valores dele (initial apagaria a cor primária).
    assert preview["variables"]["--bs-primary"] == "#0d6efd"


def test_theme_refuses_dark_background_like_pipocas():
    # O conteúdo do GALINT é claro (textos escuros): o fundo só aceita tons claros.
    config = SimpleNamespace(tema_menu=None, tema_destaque=None, tema_fundo=None)
    with pytest.raises(ValueError, match="fundo está escuro demais"):
        theme_service.save(config, {"menu": "#111827", "destaque": "#2563eb", "fundo": "#15120e"})
    assert config.tema_fundo is None
    # O menu aceita qualquer cor, pastel inclusive: o texto dele fica escuro sozinho.
    saved = theme_service.save(config, {"menu": "#f7c6e8", "destaque": "#bfe3ff", "fundo": "#fff8fc"})
    assert saved["menu"] == "#f7c6e8"
    assert theme_service.derive(**saved)["--skin-on-menu"] == theme_service.DARK_TEXT


def test_dark_background_saved_by_first_version_falls_back_to_default():
    # Skin "Brasa" salva em 21/11/2026 na primeira versão (fundo escuro): o conteúdo ficaria ilegível.
    config = SimpleNamespace(tema_menu="#1f1a14", tema_destaque="#f47c20", tema_fundo="#15120e")
    colors = theme_service.current(config)
    assert colors == {"menu": "#1f1a14", "destaque": "#f47c20", "fundo": theme_service.DEFAULTS["fundo"]}
    assert "--skin-content-bg:radial-gradient" in theme_service.stylesheet(config)


def test_custom_theme_reaches_site_cards_and_app_with_readable_tones():
    config = SimpleNamespace(tema_menu=None, tema_destaque=None, tema_fundo=None)
    saved = theme_service.save(config, {"menu": "#1b2a4a", "destaque": "#0fa3b1", "fundo": "#f3f8fb"})

    css = theme_service.stylesheet(config)
    palette = theme_service.app_palette(config)

    assert saved == {"menu": "#1b2a4a", "destaque": "#0fa3b1", "fundo": "#f3f8fb"}
    for name in ("--skin-accent:#0fa3b1", "--skin-bg:#f3f8fb", "--skin-panel-line:", "--bs-primary:", "--skin-content-bg:", "--skin-modal-bg:"):
        assert name in css
    # Os modais seguem o tema por uma folha que só entra com aparência personalizada (23/11/2026).
    assert css.startswith('@import url("/static/css/galint-skin-modais.css')
    assert "galint-skin-modais" not in theme_service.stylesheet(None)
    # Links e text-primary sobre o fundo claro ficam legíveis.
    derived = theme_service.derive(**saved)
    assert theme_service.contrast(derived["--bs-primary"], "#f3f8fb") >= 4.5
    # O app segue escuro, no matiz do menu, e os botões (texto escuro) leem bem sobre o fundo dele.
    assert palette["personalizada"] is True
    assert theme_service.luminance(palette["app"]["bg"]) < 0.02
    assert theme_service.contrast(palette["app"]["primaryStrong"], palette["app"]["bg"]) >= 4.5

    theme_service.save(config, {"acao": "padrao"})
    assert config.tema_menu is None and theme_service.app_palette(config)["personalizada"] is False


def test_user_stock_permission_is_saved(app):
    service = UserService()
    with app.app_context():
        matricula = service.create_user(UserPayload(
            matricula=None, nome="Fulano", setor="Estoque", cargo=None, senha=None,
            is_admin=False, is_standard=True, pode_ajustar_estoque=True,
        ))
        assert db.session.get(Usuario, matricula).pode_ajustar_estoque == 1
        service.update_user(matricula, UserPayload(
            matricula=matricula, nome="Fulano", setor="Estoque", cargo=None, senha=None,
            is_admin=False, is_standard=True,
        ))
        assert db.session.get(Usuario, matricula).pode_ajustar_estoque == 0
