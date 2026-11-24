"""Troca do código de barras na edição do item (24/11/2026).

Pedido do usuário: "quero poder reeditar o código de barras, foi errado". A tela de edição ganhou
Editar / Gerar / Aplicar (só administrador) e o POST /itens/<codigo>/editar, quando o código do
formulário muda, chama primeiro a troca auditada (change_item_code_admin, a mesma da página de ajuste
administrativo extinta) e salva o resto já no código novo. O serviço é simulado; a rota é a real.
"""
import pytest
from flask import Flask
from flask_login import LoginManager

from galint_flask.services.inventory import inventory_service
from galint_flask.views import inventory

ANTIGO = "7891040104086"
NOVO = "2000000000015"


class _User:
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def __init__(self, *, admin: bool):
        self.is_admin = admin
        self.id = "9001" if admin else "1002"
        self.nome = "ADMINISTRADOR" if admin else "SUPERVISOR"
        self.is_supervisor = not admin
        self.role = "admin" if admin else "supervisor"

    def get_id(self):
        return self.id


def _make_client(monkeypatch, *, admin=True, change_error=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="item-code-change", TESTING=True)
    manager = LoginManager(app)
    user = _User(admin=admin)
    manager.request_loader(lambda request: user)
    app.register_blueprint(inventory.blueprint)
    monkeypatch.setattr(inventory, "_require_admin_or_supervisor", lambda: None)

    calls = {"change": [], "update": []}
    items = {ANTIGO: {"codigo": ANTIGO, "descricao": "FITA ALTA FUSÃO 10M", "pre_cadastro_pendente": False}}

    def fake_get_item(codigo):
        return items.get(codigo)

    def fake_change(**kwargs):
        calls["change"].append(kwargs)
        if change_error:
            raise ValueError(change_error)
        items[kwargs["novo_codigo"]] = {**items.pop(kwargs["codigo_atual"]), "codigo": kwargs["novo_codigo"]}
        return {"changed": True}

    def fake_update(codigo, payload):
        # O resto da edição não interessa aqui: registra o código e para.
        calls["update"].append(codigo)
        raise ValueError("parou no update")

    monkeypatch.setattr(inventory_service, "get_item", fake_get_item)
    monkeypatch.setattr(inventory_service, "change_item_code_admin", fake_change)
    monkeypatch.setattr(inventory_service, "update_item", fake_update)
    client = app.test_client()
    client.calls = calls
    return client


def _flashes(client):
    with client.session_transaction() as session:
        return [message for _, message in session.get("_flashes", [])]


def test_admin_changes_code_then_saves_the_rest_on_the_new_code(monkeypatch):
    client = _make_client(monkeypatch)
    response = client.post(f"/itens/{ANTIGO}/editar", data={"codigo": f" {NOVO} ", "descricao": "FITA ALTA FUSÃO 10M"})

    assert len(client.calls["change"]) == 1
    change = client.calls["change"][0]
    assert (change["codigo_atual"], change["novo_codigo"], change["matricula"]) == (ANTIGO, NOVO, "9001")
    assert change["allow_pre_cadastro"] is True
    assert change["audit_context"]["source"] == "inventory.update_item"
    assert client.calls["update"] == [NOVO]
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/itens/{NOVO}/editar")
    assert f"O código já foi trocado de {ANTIGO} para {NOVO}." in _flashes(client)


def test_same_code_does_not_call_the_code_change(monkeypatch):
    client = _make_client(monkeypatch)
    client.post(f"/itens/{ANTIGO}/editar", data={"codigo": ANTIGO, "descricao": "FITA ALTA FUSÃO 10M"})

    assert client.calls["change"] == []
    assert client.calls["update"] == [ANTIGO]


def test_code_already_registered_goes_back_to_the_old_code(monkeypatch):
    client = _make_client(monkeypatch, change_error="Código já cadastrado")
    response = client.post(f"/itens/{ANTIGO}/editar", data={"codigo": NOVO, "descricao": "X"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/itens/{ANTIGO}/editar")
    assert client.calls["update"] == []
    assert "Código já cadastrado" in _flashes(client)


def test_only_admin_changes_the_code(monkeypatch):
    client = _make_client(monkeypatch, admin=False)
    response = client.post(f"/itens/{ANTIGO}/editar", data={"codigo": NOVO, "descricao": "X"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/itens/{ANTIGO}/editar")
    assert client.calls["change"] == []
    assert client.calls["update"] == []
    assert "Só administrador troca o código do item." in _flashes(client)
