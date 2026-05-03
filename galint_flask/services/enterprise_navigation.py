from __future__ import annotations

from typing import Any

from flask import current_app, url_for


def _endpoint_exists(endpoint: str) -> bool:
    return endpoint in current_app.view_functions


def _optional_url(endpoint: str, *, enabled: bool = True) -> str | None:
    if not enabled or not _endpoint_exists(endpoint):
        return None
    return url_for(endpoint)


def _item(label: str, href: str | None, icon: str, code: str, family: str, tone: str = "cyan") -> dict[str, str] | None:
    if not href:
        return None
    return {
        "label": label,
        "href": href,
        "icon": icon,
        "code": code,
        "family": family,
        "tone": tone,
    }


def _section(section_id: str, label: str, icon: str, collapse_id: str, items: list[dict[str, str] | None]) -> dict[str, Any] | None:
    visible_items = [item for item in items if item]
    if not visible_items:
        return None
    return {
        "id": section_id,
        "label": label,
        "icon": icon,
        "collapse_id": collapse_id,
        "items": visible_items,
    }


def build_enterprise_sections(*, is_admin: bool) -> list[dict[str, Any]]:
    sections = [
        _section(
            "power-bi",
            "Power BI",
            "bi-pie-chart-fill",
            "enterprisePowerBiMenu",
            [
                _item("Central Analítica", _optional_url("analytics.index"), "bi-bar-chart-line", "BI-001", "Analytics", "cyan"),
                _item("Consumo", _optional_url("inventory.consumption_dashboard"), "bi-geo-alt", "BI-002", "Analytics", "cyan"),
                _item("Financeiro", _optional_url("inventory.valor_estoque"), "bi-cash-stack", "BI-003", "Analytics", "green"),
                _item("Projeção", _optional_url("inventory.purchase_projection_page"), "bi-graph-up-arrow", "BI-004", "Analytics", "green"),
            ],
        ),
        _section(
            "sistema",
            "Sistema",
            "bi-sliders",
            "enterpriseSistemaMenu",
            [
                _item("Empresa", _optional_url("config.empresa"), "bi-building", "SYS-001", "Core", "cyan"),
                _item("Relatórios", _optional_url("config.relatorios"), "bi-file-earmark-text", "SYS-002", "Core", "cyan"),
                _item("Atualizações", _optional_url("updates.index"), "bi-arrow-clockwise", "SYS-003", "Core", "amber"),
                _item("Rede", _optional_url("pages.config_rede"), "bi-wifi", "SYS-004", "Core", "amber"),
            ],
        ),
        _section(
            "operacao-tecnica",
            "Operação Técnica",
            "bi-terminal",
            "enterpriseOperacaoMenu",
            [
                _item("Notificações", _optional_url("config.notificacoes"), "bi-broadcast-pin", "OPS-001", "Integração", "green"),
                _item("Telegram", _optional_url("telegram_config.index"), "bi-telegram", "OPS-002", "Integração", "cyan"),
                _item("Backup", _optional_url("pages.config_backup"), "bi-database", "OPS-003", "Infra", "amber"),
                _item("ConversionEngine", _optional_url("pages.config_conversionengine"), "bi-cpu", "OPS-004", "Infra", "violet"),
            ],
        ),
        _section(
            "governanca",
            "Governança",
            "bi-shield-check",
            "enterpriseGovernancaMenu",
            [
                _item("Usuários", _optional_url("users.list_users"), "bi-people-fill", "GOV-001", "Acesso", "violet"),
                _item(
                    "Painel Mobile",
                    "/mobile-panel" if is_admin and current_app.config.get("FEATURE_MOBILE_PANEL_ENABLED", False) else None,
                    "bi-phone-fill",
                    "GOV-002",
                    "Acesso",
                    "violet",
                ),
                _item("Ajuste de Estoque", _optional_url("config.estoque_ajuste_admin", enabled=is_admin), "bi-shield-lock", "GOV-003", "Controle", "red"),
                _item("Fornecedores", _optional_url("config.fornecedores"), "bi-building-add", "GOV-004", "Cadastro", "amber"),
            ],
        ),
    ]
    return [section for section in sections if section]
