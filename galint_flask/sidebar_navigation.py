from __future__ import annotations

from typing import Any

from flask import current_app, request, url_for
from flask_login import current_user


def _endpoint_exists(endpoint: str) -> bool:
    return endpoint in current_app.view_functions


def _optional_url(endpoint: str, *, enabled: bool = True) -> str | None:
    if not enabled or not _endpoint_exists(endpoint):
        return None
    return url_for(endpoint)


def _path_matches(path: str, target: str | None) -> bool:
    return bool(target) and path.startswith(target)


def _path_matches_any(path: str, targets: list[str | None]) -> bool:
    return any(_path_matches(path, target) for target in targets)


def _link_item(label: str, href: str, icon: str, active: bool) -> dict[str, Any]:
    return {
        "type": "link",
        "label": label,
        "href": href,
        "icon": icon,
        "active": active,
    }


def _group_item(label: str, icon: str, collapse_id: str, active: bool, children: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "group",
        "label": label,
        "icon": icon,
        "collapse_id": collapse_id,
        "active": active,
        "children": children,
    }


def build_sidebar_navigation() -> dict[str, Any]:
    path = request.path
    is_authenticated = bool(getattr(current_user, "is_authenticated", False))
    is_admin = bool(is_authenticated and getattr(current_user, "is_admin", False))

    dashboard_url = _optional_url("dashboard.index")
    movements_index_url = _optional_url("movements.index")
    saidas_hub_url = _optional_url("movements.saidas_hub") or movements_index_url
    saida_page_url = _optional_url("movements.saida_page")
    saida_fracionada_url = _optional_url("movements.saida_fracionada_page")
    entrada_page_url = _optional_url("movements.entrada_page")

    inventory_list_url = _optional_url("inventory.list_items")
    barcode_studio_url = _optional_url("inventory.barcode_studio_page")
    consumo_painel_url = _optional_url("inventory.consumption_dashboard")
    central_operacoes_url = _optional_url("operations.central_operations")

    valor_estoque_url = _optional_url("inventory.valor_estoque")
    fornecedores_url = _optional_url("config.fornecedores")
    admin_stock_adjust_url = _optional_url("config.estoque_ajuste_admin")
    lojas_lab_url = _optional_url("inventory.lojas_lab")
    nf_url = _optional_url("nf.nf_index", enabled=current_app.config.get("FEATURE_NOTAS_ENABLED", True))
    projection_url = _optional_url("inventory.purchase_projection_page")

    central_kits_url = _optional_url("central_kits.index")
    tool_custody_url = _optional_url("tool_custody.index")
    reparo_url = _optional_url("reparo.listar_reparos")

    analytics_url = _optional_url("analytics.index")
    users_list_url = _optional_url("users.list_users")
    mobile_panel_url = "/mobile-panel" if is_admin and current_app.config.get("FEATURE_MOBILE_PANEL_ENABLED", False) else None

    config_root_url = _optional_url("pages.config")
    empresa_url = _optional_url("config.empresa")
    relatorios_config_url = _optional_url("config.relatorios")
    updates_url = _optional_url("updates.index")
    rede_url = _optional_url("pages.config_rede")
    telegram_url = _optional_url("telegram_config.index")
    notificacoes_url = _optional_url("config.notificacoes")
    backup_url = _optional_url("pages.config_backup")
    restore_backup_url = _optional_url("pages.restore_backup")
    conversionengine_url = _optional_url("pages.config_conversionengine")
    sobre_url = _optional_url("pages.sobre")

    inventory_list_active = _path_matches(path, inventory_list_url) and not _path_matches(path, barcode_studio_url)

    lancamentos_active = _path_matches_any(
        path,
        [saidas_hub_url, movements_index_url, saida_page_url, saida_fracionada_url, entrada_page_url],
    )
    estoque_active = _path_matches_any(
        path,
        [inventory_list_url, barcode_studio_url, consumo_painel_url, central_operacoes_url],
    ) or path.startswith("/estoque")
    suprimentos_active = _path_matches_any(
        path,
        [valor_estoque_url, fornecedores_url, admin_stock_adjust_url, lojas_lab_url, nf_url, projection_url],
    )
    ferramentas_active = _path_matches_any(path, [central_kits_url, tool_custody_url, reparo_url])
    configuracoes_active = _path_matches_any(
        path,
        [
            config_root_url,
            empresa_url,
            relatorios_config_url,
            updates_url,
            rede_url,
            telegram_url,
            notificacoes_url,
            backup_url,
            restore_backup_url,
            conversionengine_url,
        ],
    )

    entries: list[dict[str, Any]] = []

    if dashboard_url:
        entries.append(_link_item("Dashboard", dashboard_url, "bi-speedometer2", path == dashboard_url))

    lancamentos_children: list[dict[str, Any]] = []
    if saidas_hub_url:
        lancamentos_children.append(
            _link_item(
                "Registro de Saídas",
                saidas_hub_url,
                "bi-box-arrow-up-right",
                _path_matches(path, saidas_hub_url) or path == (movements_index_url or ""),
            )
        )
    if lancamentos_children:
        entries.append(_group_item("Lançamentos", "bi-box-seam", "lancamentosMenu", lancamentos_active, lancamentos_children))

    estoque_children: list[dict[str, Any]] = []
    if inventory_list_url:
        estoque_children.append(_link_item("Itens Cadastrados", inventory_list_url, "bi-card-list", inventory_list_active))
    if barcode_studio_url:
        estoque_children.append(_link_item("Editor de Etiquetas", barcode_studio_url, "bi-upc-scan", _path_matches(path, barcode_studio_url)))
    if consumo_painel_url:
        estoque_children.append(_link_item("Painel de Consumo", consumo_painel_url, "bi-geo-alt", _path_matches(path, consumo_painel_url)))
    if central_operacoes_url:
        estoque_children.append(_link_item("Central de Operações", central_operacoes_url, "bi-activity", _path_matches(path, central_operacoes_url)))
    if estoque_children:
        entries.append(_group_item("Estoque", "bi-boxes", "estoqueMenu", estoque_active, estoque_children))

    suprimentos_children: list[dict[str, Any]] = []
    if valor_estoque_url:
        suprimentos_children.append(_link_item("Financeiro", valor_estoque_url, "bi-cash-stack", _path_matches(path, valor_estoque_url)))
    if fornecedores_url:
        suprimentos_children.append(_link_item("Cadastrar fornecedor", fornecedores_url, "bi-building-add", _path_matches(path, fornecedores_url)))
    if is_admin and admin_stock_adjust_url:
        suprimentos_children.append(_link_item("Ajuste Administrativo", admin_stock_adjust_url, "bi-shield-lock", _path_matches(path, admin_stock_adjust_url)))
    if lojas_lab_url:
        suprimentos_children.append(_link_item("Laboratório de Lojas", lojas_lab_url, "bi-shop", _path_matches(path, lojas_lab_url)))
    if nf_url:
        suprimentos_children.append(_link_item("Documentos Fiscais", nf_url, "bi-receipt", _path_matches(path, nf_url)))
    if projection_url:
        suprimentos_children.append(_link_item("Projeção de Compras", projection_url, "bi-graph-up-arrow", _path_matches(path, projection_url)))
    if suprimentos_children:
        entries.append(_group_item("Gestão de Suprimentos", "bi-briefcase-fill", "suprimentosMenu", suprimentos_active, suprimentos_children))

    ferramentas_children: list[dict[str, Any]] = []
    if central_kits_url:
        ferramentas_children.append(_link_item("Central de Kits", central_kits_url, "bi-briefcase-fill", _path_matches(path, central_kits_url)))
    if tool_custody_url:
        ferramentas_children.append(_link_item("Auditar Ferramentas", tool_custody_url, "bi-search", _path_matches(path, tool_custody_url)))
    if reparo_url:
        ferramentas_children.append(_link_item("Em reparo...", reparo_url, "bi-wrench-adjustable", _path_matches(path, reparo_url)))
    if ferramentas_children:
        entries.append(_group_item("Ferramentas", "bi-tools", "ferramentasMenu", ferramentas_active, ferramentas_children))

    if analytics_url and is_admin:
        entries.append(_link_item("Central Analítica", analytics_url, "bi-bar-chart-line", _path_matches(path, analytics_url)))

    if is_admin and users_list_url:
        entries.append(_link_item("Usuários", users_list_url, "bi-people-fill", _path_matches(path, users_list_url)))
    if is_admin and mobile_panel_url:
        entries.append(_link_item("Painel Mobile", mobile_panel_url, "bi-phone-fill", path.startswith(mobile_panel_url)))

    if is_admin:
        entries.append({"type": "divider"})
        configuracoes_children: list[dict[str, Any]] = []
        if empresa_url:
            configuracoes_children.append(_link_item("Empresa", empresa_url, "bi-building", _path_matches(path, empresa_url)))
        if relatorios_config_url:
            configuracoes_children.append(_link_item("Relatórios", relatorios_config_url, "bi-file-earmark-text", _path_matches(path, relatorios_config_url)))
        if updates_url:
            configuracoes_children.append(_link_item("Atualizações", updates_url, "bi-arrow-clockwise", _path_matches(path, updates_url)))
        if rede_url:
            configuracoes_children.append(_link_item("Rede", rede_url, "bi-wifi", _path_matches(path, rede_url)))
        if telegram_url:
            configuracoes_children.append(_link_item("Telegram", telegram_url, "bi-telegram", _path_matches(path, telegram_url)))
        if notificacoes_url:
            configuracoes_children.append(_link_item("Notificações", notificacoes_url, "bi-broadcast-pin", _path_matches(path, notificacoes_url)))
        if backup_url:
            configuracoes_children.append(_link_item("Backup", backup_url, "bi-database", _path_matches(path, backup_url) or _path_matches(path, restore_backup_url)))
        if conversionengine_url:
            configuracoes_children.append(_link_item("ConversionEngine", conversionengine_url, "bi-cpu", _path_matches(path, conversionengine_url)))
        if configuracoes_children:
            entries.append(_group_item("Configurações", "bi-gear-fill", "configuracoesMenu", configuracoes_active, configuracoes_children))

    if is_authenticated:
        entries.append({
            "type": "toggle",
            "label": "Assistente",
            "icon": "bi-robot",
            "input_id": "assistant-toggle",
        })

    entries.append({"type": "divider"})
    if sobre_url:
        entries.append(_link_item("Sobre", sobre_url, "", path == sobre_url))

    return {
        "entries": entries,
        "footer_user_label": getattr(current_user, "nome", "Visitante") if is_authenticated else "Visitante",
    }


__all__ = ["build_sidebar_navigation"]