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
    mobile_panel_enabled = is_admin and bool(current_app.config.get("FEATURE_MOBILE_PANEL_ENABLED", False))
    sections = [
        _section(
            "condominio",
            "Condomínio",
            "bi-buildings",
            "enterpriseCondominioMenu",
            [
                _item("Editor de Blocos", _optional_url("condominium.admin_condominium_blocks_editor"), "bi-building-gear", "ADM-000", "Estrutura", "cyan"),
                _item("Cadastro Mestre", _optional_url("condominium.admin_condominium_registry"), "bi-person-vcard", "ADM-001", "Cadastro", "cyan"),
                _item("Agendamentos", _optional_url("condominium.admin_condominium_schedule"), "bi-calendar2-week", "ADM-002", "Agenda", "amber"),
                _item("Prestadores", _optional_url("condominium.admin_service_providers"), "bi-building-check", "ADM-003", "Serviços", "green"),
            ],
        ),
        _section(
            "suprimentos",
            "Gestão de Suprimentos",
            "bi-briefcase-fill",
            "enterpriseSuprimentosMenu",
            [
                _item("Financeiro", _optional_url("inventory.valor_estoque"), "bi-cash-stack", "SUP-001", "Gestão", "green"),
                _item("Projeção", _optional_url("inventory.purchase_projection_page"), "bi-graph-up-arrow", "SUP-002", "Gestão", "green"),
                _item("Fornecedores", _optional_url("config.fornecedores"), "bi-building-add", "SUP-003", "Cadastro", "amber"),
                _item("Documentos Fiscais", _optional_url("nf.nf_index", enabled=bool(current_app.config.get("FEATURE_NOTAS_ENABLED", True))), "bi-receipt", "SUP-004", "Fiscal", "amber"),
                _item("Laboratório de Lojas", _optional_url("inventory.lojas_lab"), "bi-shop", "SUP-005", "Operação", "cyan"),
                _item("Ajuste Administrativo", _optional_url("config.estoque_ajuste_admin", enabled=is_admin), "bi-shield-lock", "SUP-006", "Controle", "red"),
            ],
        ),
        _section(
            "dashboard",
            "Dashboard",
            "bi-speedometer2",
            "enterpriseDashboardMenu",
            [
                _item("Resumo de Estoque", _optional_url("dashboard.index"), "bi-grid-1x2-fill", "DASH-001", "Leitura", "cyan"),
                _item("Central de Operações", _optional_url("operations.central_operations"), "bi-activity", "DASH-002", "Leitura", "green"),
                _item("Consumo", _optional_url("inventory.consumption_dashboard"), "bi-geo-alt", "DASH-003", "Leitura", "cyan"),
            ],
        ),
        _section(
            "ferramentas",
            "Ferramentas",
            "bi-tools",
            "enterpriseFerramentasMenu",
            [
                _item("Central de Kits", _optional_url("central_kits.index"), "bi-briefcase-fill", "FER-001", "Kits", "cyan"),
                _item("Em Custódia", _optional_url("tool_custody.index"), "bi-person-workspace", "FER-002", "Custódia", "green"),
                _item("Em reparo", _optional_url("reparo.listar_reparos"), "bi-wrench-adjustable", "FER-003", "Reparo", "amber"),
            ],
        ),
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
                _item("Configurações", _optional_url("pages.config"), "bi-gear-fill", "SYS-000", "Sistema", "cyan"),
                _item("Imagens do Sistema", _optional_url("config.imagens"), "bi-images", "SYS-IMG", "Visual", "cyan"),
                _item("Empresa", _optional_url("config.empresa"), "bi-building", "SYS-001", "Core", "cyan"),
                _item("Relatórios", _optional_url("config.relatorios"), "bi-file-earmark-text", "SYS-002", "Core", "cyan"),
                _item("Atualizações", _optional_url("updates.index"), "bi-arrow-clockwise", "SYS-003", "Core", "amber"),
                _item("Rede", _optional_url("pages.config_rede"), "bi-wifi", "SYS-004", "Core", "amber"),
                _item("Checklist Final", _optional_url("pages.backup_final_checklist"), "bi-clipboard2-check", "SYS-005", "Core", "green"),
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
                _item("Histórico Telegram", _optional_url("telegram_config.historico"), "bi-clock-history", "OPS-003", "Integração", "cyan"),
                _item("Backup", _optional_url("pages.config_backup"), "bi-database", "OPS-004", "Infra", "amber"),
                _item("ConversionEngine", _optional_url("pages.config_conversionengine"), "bi-cpu", "OPS-005", "Infra", "violet"),
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
                    _optional_url("mobile_panel.dashboard", enabled=mobile_panel_enabled),
                    "bi-phone-fill",
                    "GOV-002",
                    "Acesso",
                    "violet",
                ),
                _item("Dispositivos Mobile", _optional_url("mobile_panel.devices", enabled=mobile_panel_enabled), "bi-phone", "GOV-003", "Mobile", "cyan"),
                _item("Versões Mobile", _optional_url("mobile_panel.versions", enabled=mobile_panel_enabled), "bi-cloud-download", "GOV-004", "Mobile", "cyan"),
                _item("Features Mobile", _optional_url("mobile_panel.features", enabled=mobile_panel_enabled), "bi-toggles2", "GOV-005", "Mobile", "cyan"),
                _item("Auditoria Mobile", _optional_url("mobile_panel.audit", enabled=mobile_panel_enabled), "bi-shield-check", "GOV-006", "Mobile", "violet"),
                _item("Ajuste de Estoque", _optional_url("config.estoque_ajuste_admin", enabled=is_admin), "bi-shield-lock", "GOV-007", "Controle", "red"),
                _item("Fornecedores", _optional_url("config.fornecedores"), "bi-building-add", "GOV-008", "Cadastro", "amber"),
            ],
        ),
    ]
    return [section for section in sections if section]
