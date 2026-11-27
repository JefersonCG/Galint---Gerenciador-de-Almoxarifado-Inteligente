"""Login do app pelo nome e plantão (27/11/2026).

Pedido do usuário: no celular da supervisão e da zeladoria "o login dele seja pelo primeiro nome"; "todos eles são
plantonista 12 por 36, pegam de 07h às 19h; sempre que encerrar essa carga horária o sistema deslogará o usuário,
para ninguém usar o usuário dele". Regra em galint_flask/services/plantao.py.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import jwt
import pytest
from flask import Flask
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import Usuario
from galint_flask.services import plantao
from galint_flask.views import api_mobile

SP = ZoneInfo("America/Sao_Paulo")


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@compiles(INET, "sqlite")
def _inet_as_text_on_sqlite(element, compiler, **kwargs):
    return "TEXT"


def _agora(hora, minuto=0, dia=27):
    return datetime(2026, 11, dia, hora, minuto, tzinfo=SP)


# ---------- regra do horário ----------
def test_window_with_half_hour_before_start():
    assert plantao.janela("07:00", "19:00", _agora(6, 29)) is None
    assert plantao.janela("07:00", "19:00", _agora(6, 30)) == (_agora(7), _agora(19))
    assert plantao.janela("07:00", "19:00", _agora(18, 59)) == (_agora(7), _agora(19))
    assert plantao.janela("07:00", "19:00", _agora(19, 0)) is None
    assert plantao.janela("", "19:00", _agora(10)) is None


def test_night_shift_crosses_midnight():
    assert plantao.janela("19:00", "07:00", _agora(2, dia=28)) == (_agora(19), _agora(7, dia=28))
    assert plantao.janela("19:00", "07:00", _agora(12)) is None


def test_hour_formats_and_label():
    assert [plantao.normalizar_hora(v) for v in ("7:00", "07:00", "7h", "19", "25:00", "", None)] == ["07:00", "07:00", "07:00", "19:00", None, None, None]

    class Pessoa:
        plantao_inicio = "07:00"
        plantao_fim = "19:30"

    assert plantao.rotulo(Pessoa()) == "07h às 19h30"


# ---------- login ----------
@pytest.fixture
def app_e_cliente(monkeypatch):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="plantao", SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    app.register_blueprint(api_mobile.blueprint)
    with app.app_context():
        db.init_app(app)
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        pessoas = [
            Usuario(matricula="1001", nome="ISAÍAS", setor="SUPERVISÃO", plantao_inicio="07:00", plantao_fim="19:00", app_so_retirada=1),
            Usuario(matricula="1002", nome="JÚLIO ( LBM )", setor="LBM"),
            Usuario(matricula="1003", nome="JÚLIO CESAR", setor="LBM"),
            Usuario(matricula="1004", nome="LEONARDO", setor="LBM"),
            Usuario(matricula="1005", nome="LEONARDO ( LBM )", setor="LBM"),
        ]
        for pessoa in pessoas:
            pessoa.set_password("1234")
            db.session.add(pessoa)
        db.session.commit()
        relogio = {"agora": _agora(10)}
        monkeypatch.setattr(api_mobile.TimeService, "now_local", classmethod(lambda cls: relogio["agora"]))
        monkeypatch.setattr(api_mobile.TimeService, "now_db", classmethod(lambda cls: relogio["agora"].replace(tzinfo=None)))
        yield app, app.test_client(), relogio
        db.session.remove()


def _login(cliente, nome, senha="1234"):
    return cliente.post("/api/mobile/login", json={"matricula": nome, "senha": senha})


def test_first_name_without_accent_logs_in_and_token_ends_with_the_shift(app_e_cliente):
    app, cliente, _relogio = app_e_cliente
    resposta = _login(cliente, "isaias")
    assert resposta.status_code == 200, resposta.get_json()
    dados = resposta.get_json()["data"]
    assert dados["user"]["matricula"] == "1001"
    assert dados["user"]["plantao"] == {"inicio": "07:00", "fim": "19:00", "ate": int(_agora(19).timestamp() * 1000)}
    exp = jwt.decode(dados["token"], "plantao", algorithms=["HS256"], options={"verify_exp": False})["exp"]
    assert exp == int(_agora(19).timestamp())


def test_out_of_shift_login_is_refused(app_e_cliente):
    _app, cliente, relogio = app_e_cliente
    relogio["agora"] = _agora(20)
    resposta = _login(cliente, "ISAÍAS")
    assert resposta.status_code == 403
    assert resposta.get_json()["message"] == "Fora do seu plantão (07h às 19h)."


def test_requests_after_the_shift_are_refused(app_e_cliente):
    _app, cliente, relogio = app_e_cliente
    token = _login(cliente, "ISAÍAS").get_json()["data"]["token"]
    relogio["agora"] = _agora(19, 1)
    resposta = cliente.get("/api/mobile/custodia", headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 401
    assert resposta.get_json()["plantao_encerrado"] is True


def test_full_name_wins_and_same_first_name_is_ambiguous(app_e_cliente):
    _app, cliente, _relogio = app_e_cliente
    leonardo = _login(cliente, "Leonardo")
    assert leonardo.status_code == 200 and leonardo.get_json()["data"]["user"]["matricula"] == "1004"
    assert leonardo.get_json()["data"]["user"]["plantao"] is None
    julio = _login(cliente, "julio")
    assert julio.status_code == 400 and julio.get_json()["ambiguous"] is True
    assert _login(cliente, "júlio cesar").get_json()["data"]["user"]["matricula"] == "1003"
