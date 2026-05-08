"""Smoke test read-only para dashboard, custodia e devolucao expressa."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any


os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_TELEGRAM_STARTUP_GREETING", "false")


from flask import url_for

from galint_flask import create_app
from galint_flask.models import Usuario


@dataclass
class CheckResult:
    level: str
    label: str
    detail: str


class SmokeCollector:
    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    def pass_(self, label: str, detail: str) -> None:
        self.results.append(CheckResult("PASS", label, detail))

    def warn(self, label: str, detail: str) -> None:
        self.results.append(CheckResult("WARN", label, detail))

    def fail(self, label: str, detail: str) -> None:
        self.results.append(CheckResult("FAIL", label, detail))

    @property
    def failures(self) -> list[CheckResult]:
        return [result for result in self.results if result.level == "FAIL"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [result for result in self.results if result.level == "WARN"]

    def print_summary(self) -> None:
        for result in self.results:
            print(f"[{result.level}] {result.label}: {result.detail}")
        print(
            f"\nResumo: {len(self.results)} checks, "
            f"{len(self.failures)} falha(s), {len(self.warnings)} aviso(s)."
        )


def _build_routes(app) -> dict[str, str]:
    with app.test_request_context():
        return {
            "dashboard": url_for("dashboard.index"),
            "custody": url_for("dashboard.custody_active"),
            "tool_collaborators": url_for("ferramentas.devolucao_expressa_colaboradores_api"),
            "tool_items": url_for("ferramentas.devolucao_expressa_itens_api"),
            "movement_collaborators": url_for("movements.devolucao_expressa_collaborators_payload"),
            "movement_items": url_for("movements.devolucao_expressa_payload"),
        }


def _login_as_first_admin(app, client, collector: SmokeCollector) -> Usuario | None:
    admin = Usuario.query.filter(Usuario.is_admin == 1).order_by(Usuario.nome).first()
    if not admin:
        collector.fail("Autenticacao", "Nenhum usuario admin foi encontrado para executar os checks.")
        return None

    with client.session_transaction() as session:
        session["_user_id"] = admin.matricula
        session["_fresh"] = True
        session["galint_is_admin"] = True
        session["galint_user_id"] = admin.matricula

    collector.pass_("Autenticacao", f"Sessao de teste montada com admin {admin.nome} ({admin.matricula}).")
    return admin


def _read_json(response) -> dict[str, Any]:
    payload = response.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _validate_required_keys(payload: dict[str, Any], required_keys: set[str]) -> tuple[bool, list[str]]:
    missing = sorted(key for key in required_keys if key not in payload)
    return (not missing, missing)


def check_dashboard(client, route: str, collector: SmokeCollector) -> None:
    response = client.get(route)
    if response.status_code != 200:
        collector.fail("Dashboard", f"Status inesperado: {response.status_code}.")
        return

    body = response.get_data(as_text=True)
    expected_markers = {
        "Dar baixa": "acao de custodia",
        "Ver ficha": "atalho para ficha do colaborador",
        "Cores oficiais das categorias": "legenda visual oficial",
    }
    missing_markers = [label for label in expected_markers if label not in body]
    if missing_markers:
        collector.fail("Dashboard", f"Marcadores ausentes no HTML: {', '.join(missing_markers)}.")
        return

    collector.pass_("Dashboard", "Pagina principal respondeu 200 e manteve os marcadores esperados.")


def check_custody_feed(client, route: str, collector: SmokeCollector) -> None:
    response = client.get(route, headers={"Accept": "application/json"})
    if response.status_code != 200:
        collector.fail("Custodia dashboard", f"Status inesperado: {response.status_code}.")
        return

    payload = _read_json(response)
    items = payload.get("items")
    if not isinstance(items, list):
        collector.fail("Custodia dashboard", "Payload nao trouxe a chave items como lista.")
        return

    if not items:
        collector.warn("Custodia dashboard", "Feed respondeu 200, mas nao ha ferramentas temporarias em custodia no momento.")
        return

    valid, missing = _validate_required_keys(
        items[0],
        {
            "id",
            "source",
            "codigo",
            "descricao",
            "usuario",
            "matricula_full",
            "dias_em_uso",
            "data_retirada_iso",
        },
    )
    if not valid:
        collector.fail("Custodia dashboard", f"Primeiro item sem chaves esperadas: {', '.join(missing)}.")
        return

    collector.pass_("Custodia dashboard", f"Feed respondeu 200 com {len(items)} item(ns) ativo(s).")


def check_tool_express_return(client, collaborators_route: str, items_route: str, collector: SmokeCollector) -> None:
    response = client.get(collaborators_route, headers={"Accept": "application/json"})
    if response.status_code != 200:
        collector.fail("Devolucao expressa ferramentas", f"Colaboradores retornaram {response.status_code}.")
        return

    payload = _read_json(response)
    collaborators = payload.get("collaborators")
    if not isinstance(collaborators, list):
        collector.fail("Devolucao expressa ferramentas", "Payload de colaboradores nao trouxe uma lista valida.")
        return

    if not collaborators:
        collector.warn("Devolucao expressa ferramentas", "Endpoint respondeu 200, mas nao ha colaboradores com ferramentas em aberto.")
        return

    collector.pass_(
        "Devolucao expressa ferramentas",
        f"Colaboradores responderam 200 com {len(collaborators)} colaborador(es) disponivel(is).",
    )

    sample = collaborators[0]
    matricula = str(sample.get("matricula") or "").strip()
    items_response = client.get(items_route, query_string={"matricula": matricula}, headers={"Accept": "application/json"})
    if items_response.status_code != 200:
        collector.fail("Itens devolucao ferramentas", f"Itens do colaborador {matricula} retornaram {items_response.status_code}.")
        return

    items_payload = _read_json(items_response)
    items = items_payload.get("items")
    if not isinstance(items, list):
        collector.fail("Itens devolucao ferramentas", "Payload de itens nao trouxe uma lista valida.")
        return

    if not items:
        collector.warn("Itens devolucao ferramentas", f"Colaborador {matricula} foi listado, mas a consulta de itens voltou vazia.")
        return

    valid, missing = _validate_required_keys(
        items[0],
        {
            "saida_id",
            "codigo",
            "descricao",
            "data_saida_label",
            "days_in_use",
            "tipo_custodia",
        },
    )
    if not valid:
        collector.fail("Itens devolucao ferramentas", f"Primeira ferramenta sem chaves esperadas: {', '.join(missing)}.")
        return

    collector.pass_("Itens devolucao ferramentas", f"Consulta do colaborador {matricula} respondeu com {len(items)} ferramenta(s).")


def check_material_express_return(
    client,
    collaborators_route: str,
    items_route: str,
    scope: str,
    collector: SmokeCollector,
) -> None:
    response = client.get(collaborators_route, query_string={"scope": scope}, headers={"Accept": "application/json"})
    if response.status_code != 200:
        collector.fail(f"Devolucao expressa materiais/{scope}", f"Colaboradores retornaram {response.status_code}.")
        return

    payload = _read_json(response)
    collaborators = payload.get("collaborators")
    if not isinstance(collaborators, list):
        collector.fail(f"Devolucao expressa materiais/{scope}", "Payload de colaboradores nao trouxe uma lista valida.")
        return

    window_open = payload.get("window_open")
    if window_open is False:
        collector.warn(
            f"Devolucao expressa materiais/{scope}",
            payload.get("message") or "Janela da devolucao expressa fechada para este escopo.",
        )
        return

    if not collaborators:
        collector.warn(
            f"Devolucao expressa materiais/{scope}",
            payload.get("message") or "Nenhum colaborador elegivel foi encontrado no momento.",
        )
        return

    collector.pass_(
        f"Devolucao expressa materiais/{scope}",
        f"Colaboradores responderam 200 com {len(collaborators)} colaborador(es) para o escopo {scope}.",
    )

    sample = collaborators[0]
    matricula = str(sample.get("matricula") or "").strip()
    items_response = client.get(
        items_route,
        query_string={"scope": scope, "usuario": matricula},
        headers={"Accept": "application/json"},
    )
    if items_response.status_code != 200:
        collector.fail(
            f"Itens devolucao materiais/{scope}",
            f"Itens do colaborador {matricula} retornaram {items_response.status_code}.",
        )
        return

    items_payload = _read_json(items_response)
    items = items_payload.get("items")
    if not isinstance(items, list):
        collector.fail(f"Itens devolucao materiais/{scope}", "Payload de itens nao trouxe uma lista valida.")
        return

    if not items:
        collector.warn(
            f"Itens devolucao materiais/{scope}",
            items_payload.get("message") or f"Colaborador {matricula} nao possui itens elegiveis no escopo {scope}.",
        )
        return

    valid, missing = _validate_required_keys(
        items[0],
        {
            "codigo",
            "descricao",
            "retirado_hoje_display",
            "pendente_hoje_display",
            "devolucao_unidade_codigo",
            "devolucao_unidades_opcoes",
        },
    )
    if not valid:
        collector.fail(
            f"Itens devolucao materiais/{scope}",
            f"Primeiro item sem chaves esperadas: {', '.join(missing)}.",
        )
        return

    collector.pass_(
        f"Itens devolucao materiais/{scope}",
        f"Consulta do colaborador {matricula} respondeu com {len(items)} item(ns) elegivel(is).",
    )


def main() -> int:
    collector = SmokeCollector()
    app = create_app()
    routes = _build_routes(app)

    with app.app_context():
        with app.test_client() as client:
            admin = _login_as_first_admin(app, client, collector)
            if admin is None:
                collector.print_summary()
                return 1

            check_dashboard(client, routes["dashboard"], collector)
            check_custody_feed(client, routes["custody"], collector)
            check_tool_express_return(client, routes["tool_collaborators"], routes["tool_items"], collector)
            check_material_express_return(
                client,
                routes["movement_collaborators"],
                routes["movement_items"],
                "padrao",
                collector,
            )
            check_material_express_return(
                client,
                routes["movement_collaborators"],
                routes["movement_items"],
                "fracionada",
                collector,
            )

    collector.print_summary()
    return 1 if collector.failures else 0


if __name__ == "__main__":
    sys.exit(main())
