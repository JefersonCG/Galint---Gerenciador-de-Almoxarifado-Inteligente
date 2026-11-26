""""Será que temos!?" (26/11/2026): foto do app → itens parecidos (DINOv2 + OpenCLIP), sem ligar o serviço de verdade.

- rotas do app: foto inválida, serviço ainda carregando ({"pronto": false}), resultado com saldo e o 4º só quando
  empata com o 3º, confirmação virando foto de referência;
- índice do serviço (busca_visual/servico.py): poda do que saiu/mudou, busca pela média das duas notas e a melhor
  foto de cada item.
"""
import importlib.util
import io
import json
from pathlib import Path

import numpy as np
import pytest
from flask import Flask
from PIL import Image
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles

from galint_flask.extensions import db
from galint_flask.models import BuscaVisualReferencia, Item, Usuario
from galint_flask.services import busca_visual
from galint_flask.views import api_mobile

AUTH = {"Authorization": "Bearer token-ok"}


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kwargs):
    return "JSON"


@compiles(INET, "sqlite")
def _inet_as_text_on_sqlite(element, compiler, **kwargs):
    return "TEXT"


def _jpeg() -> bytes:
    saida = io.BytesIO()
    Image.new("RGB", (1600, 900), (200, 120, 40)).save(saida, format="JPEG")
    return saida.getvalue()


@pytest.fixture
def client(monkeypatch, tmp_path):
    app = Flask(__name__, instance_path=str(tmp_path / "instance"))
    app.config.update(SECRET_KEY="sera-que-temos", SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False,
                      TESTING=True, BUSCA_VISUAL_TESTE=True)
    app.register_blueprint(api_mobile.blueprint)
    with app.app_context():
        db.init_app(app)
        for table in db.metadata.sorted_tables:
            try:
                table.create(bind=db.engine, checkfirst=True)
            except CompileError:
                pass
        db.session.add(Usuario(matricula="9001", nome="RAPHAEL", setor="SUPERVISOR", is_admin=False))
        for codigo, nome in [("C32", "CURVA 90 32MM"), ("C40", "CURVA 90 40MM"), ("C50", "CURVA 90 50MM"), ("C60", "CURVA 90 60MM"), ("LUVA", "LUVA 60MM")]:
            db.session.add(Item(codigo_item=codigo, descricao=nome, unidade="Unidade", categoria="Hidráulica", setor="ALMOXARIFADO"))
        db.session.commit()
        monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: Usuario.query.get("9001") if token == "token-ok" else None)
        monkeypatch.setattr(busca_visual, "garantir_ligado", lambda: None)
        yield app.test_client()
        db.session.remove()


def test_foto_invalida_e_sem_foto(client):
    assert client.post("/api/mobile/sera-que-temos", headers=AUTH, data={}).status_code == 400
    resposta = client.post("/api/mobile/sera-que-temos", headers=AUTH,
                           data={"foto": (io.BytesIO(b"isto nao e foto"), "x.jpg")}, content_type="multipart/form-data")
    assert resposta.status_code == 400
    assert resposta.get_json()["message"] == "Foto inválida."
    assert client.post("/api/mobile/sera-que-temos", data={}).status_code == 401


def test_enquanto_o_servico_liga_o_app_pergunta_de_novo(client, monkeypatch):
    monkeypatch.setattr(busca_visual, "_chamar", lambda *args, **kwargs: None)
    monkeypatch.setattr(busca_visual, "iniciar", lambda: None)
    resposta = client.post("/api/mobile/sera-que-temos", headers=AUTH, data={"foto": (io.BytesIO(_jpeg()), "f.jpg")},
                           content_type="multipart/form-data")
    corpo = resposta.get_json()
    assert resposta.status_code == 200 and corpo["pronto"] is False
    consulta = corpo["consulta"]
    # A foto ficou guardada reduzida (até 1024 px).
    with Image.open(Path(busca_visual.pasta()) / "consultas" / f"{consulta}.jpg") as foto:
        assert max(foto.size) == 1024

    notas = [{"codigo": "C32", "nota": 0.81}, {"codigo": "C40", "nota": 0.81}, {"codigo": "C50", "nota": 0.808},
             {"codigo": "C60", "nota": 0.806}, {"codigo": "LUVA", "nota": 0.62}]
    monkeypatch.setattr(busca_visual, "_chamar", lambda *args, **kwargs: (200, {"pronto": True, "resultados": notas, "ms": 640}))
    corpo = client.get(f"/api/mobile/sera-que-temos/{consulta}", headers=AUTH).get_json()
    assert corpo["pronto"] is True
    # Os 3 primeiros e o 4º que empata com o 3º; a LUVA (bem atrás) não.
    assert [item["codigo_barras"] for item in corpo["itens"]] == ["C32", "C40", "C50", "C60"]
    assert corpo["itens"][0]["descricao"] == "CURVA 90 32MM" and corpo["itens"][0]["nota"] == 0.81
    catalogo = json.loads((Path(busca_visual.pasta()) / "catalogo.json").read_text(encoding="utf-8"))
    assert catalogo["fotos"] == []  # nenhum item com foto no teste


def test_confirmar_vira_foto_de_referencia(client, monkeypatch):
    monkeypatch.setattr(busca_visual, "_chamar", lambda *args, **kwargs: None)
    monkeypatch.setattr(busca_visual, "iniciar", lambda: None)
    consulta = client.post("/api/mobile/sera-que-temos", headers=AUTH, data={"foto": (io.BytesIO(_jpeg()), "f.jpg")},
                           content_type="multipart/form-data").get_json()["consulta"]

    assert client.post(f"/api/mobile/sera-que-temos/{consulta}/confirmar", headers=AUTH, json={"codigo": "NAOEXISTE"}).status_code == 400
    assert client.post(f"/api/mobile/sera-que-temos/{consulta}/confirmar", headers=AUTH, json={"codigo": "C40"}).status_code == 200
    assert client.post(f"/api/mobile/sera-que-temos/{consulta}/confirmar", headers=AUTH, json={"codigo": "C40"}).status_code == 200
    referencias = BuscaVisualReferencia.query.all()
    assert [(r.codigo_item, r.criado_por) for r in referencias] == [("C40", "9001")]
    assert (Path(busca_visual.pasta()) / referencias[0].arquivo).is_file()
    catalogo = json.loads((Path(busca_visual.pasta()) / "catalogo.json").read_text(encoding="utf-8"))
    assert [(f["codigo"], f["origem"]) for f in catalogo["fotos"]] == [("C40", "referencia")]
    assert client.get("/api/mobile/sera-que-temos/../../etc", headers=AUTH).status_code in (400, 404)


def _servico():
    caminho = Path(__file__).resolve().parents[1] / "busca_visual" / "servico.py"
    especificacao = importlib.util.spec_from_file_location("servico_busca_visual", caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return modulo


def _unitario(dimensao: int, posicao: int) -> np.ndarray:
    vetor = np.zeros(dimensao, dtype=np.float32)
    vetor[posicao] = 1.0
    return vetor


def test_indice_poda_busca_e_guarda(tmp_path):
    servico = _servico()
    fotos = {}
    for nome in ("a.jpg", "b.jpg", "c.jpg"):
        fotos[nome] = tmp_path / nome
        fotos[nome].write_bytes(b"x")
    indice = servico.Indice(tmp_path)
    catalogo = [
        {"codigo": "A", "arquivo": str(fotos["a.jpg"])},
        {"codigo": "A", "arquivo": str(fotos["b.jpg"]), "origem": "referencia"},
        {"codigo": "C", "arquivo": str(fotos["c.jpg"])},
    ]
    faltam = indice.podar(catalogo)
    assert len(faltam) == 3
    dino = np.stack([_unitario(768, 0), _unitario(768, 1), _unitario(768, 2)])
    clip = np.stack([_unitario(512, 0), _unitario(512, 1), _unitario(512, 2)])
    indice.acrescentar(faltam, dino, clip)

    # A foto b do item A é a mais parecida; o item aparece uma vez só, com a nota da melhor foto.
    resultados = indice.buscar(_unitario(768, 1), _unitario(512, 1), quantos=5)
    assert [(r["codigo"], r["nota"]) for r in resultados] == [("A", 1.0), ("C", 0.0)]

    indice.salvar()
    de_novo = servico.Indice(tmp_path)
    assert de_novo.resumo() == {"fotos": 3, "itens": 2}
    # Foto c trocada e a foto a fora do catálogo: só a c volta para a fila.
    fotos["c.jpg"].write_bytes(b"outra foto")
    faltam = de_novo.podar(catalogo[1:])
    assert [f["codigo"] for f in faltam] == ["C"]
    assert de_novo.resumo() == {"fotos": 1, "itens": 1}
