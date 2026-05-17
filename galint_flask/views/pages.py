"""Rotas auxiliares: configurações e página sobre."""
from __future__ import annotations

import base64
import binascii
import html
import re
from datetime import date, time as dt_time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import abort
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import CondominiumBuilding, CondominiumOwner, CondominiumScheduleEvent, CondominiumUnit
from ..services.backup import BackupService
from ..services.auth import create_workspace_window_token
from ..services.backup_restore_jobs import get_job_state, start_restore_job
from ..services.category_catalog import DEFAULT_INVENTORY_CATEGORIES, category_catalog_service
from ..services.condominium_schedule import (
    EVENT_TYPE_LABELS,
    PRIORITY_LABELS,
    SCOPE_LABELS,
    STATUS_LABELS,
    build_calendar_context,
    build_schedule_dashboard_summary,
    due_schedule_notifications,
    normalize_event_type,
    normalize_priority,
    normalize_scope,
    normalize_status,
    now_local_naive,
    today_local,
)
from ..services.condominium_structure import UNIT_STATUS_LABELS, build_condominium_block_dashboard, generate_unit_layout, normalize_unit_status, sync_building_units, unit_dashboard_status
from ..services.conversion_engine import ConversionEngineService, get_conversion_job_state, start_conversion_job
from ..services.native_workspace_launcher import launch_workspace_window, launch_workspace_window_auto
from ..services.network_settings import load_network_settings, save_network_settings
from ..services.purchase_projection_runtime_service import purchase_projection_service


blueprint = Blueprint("pages", __name__)


_ABOUT_CATEGORY_REFERENCE_GROUPS = (
    {
        "id": "infraestrutura",
        "title": "Infraestrutura e acabamento",
        "summary": "Tipologias que organizam instalações, acabamento e manutenção predial com leitura rápida no catálogo.",
        "accent": "#38bdf8",
        "items": (
            {"key": "material-eletrico", "usage": "Painéis, filtros e listagens de itens energizados, cabeamento e componentes elétricos."},
            {"key": "material-hidraulico", "usage": "Tubulações, conexões e peças de manutenção hidráulica seguem a mesma assinatura azul técnica."},
            {"key": "mat-pintura-drywall", "usage": "Tintas, massas e acabamentos ficam agrupados sem depender de leitura textual longa."},
            {"key": "material-construcao", "usage": "Materiais estruturais e de obra civil aparecem com identidade própria em telas e relatórios."},
        ),
    },
    {
        "id": "operacao",
        "title": "Operação, ferramentas e proteção",
        "summary": "Faixa usada para o que tem leitura mais operacional, patrimonial ou de segurança no dia a dia.",
        "accent": "#60a5fa",
        "items": (
            {"key": "ferramentas", "usage": "Ferramentas manuais e apoio técnico usam a faixa central da custódia e dos filtros operacionais."},
            {"key": "equipamento", "usage": "Equipamentos permanentes e itens eletrificados mantêm contraste próprio em documentos e painéis."},
            {"key": "material-ep", "usage": "Materiais de proteção individual preservam uma leitura de segurança sem conflitar com ferramentas."},
        ),
    },
    {
        "id": "apoio",
        "title": "Apoio, limpeza e contingência",
        "summary": "Categorias de apoio operacional e a faixa de contingência para itens ainda não classificados de forma definitiva.",
        "accent": "#34d399",
        "items": (
            {"key": "materiais-limpeza", "usage": "Limpeza operacional e consumo recorrente aparecem com identificação uniforme em todo o sistema."},
            {"key": "material-piscina", "usage": "Tratamento e operação de piscina ficam isolados sem contaminar outras leituras de manutenção."},
            {"key": "material-uso-geral", "usage": "Itens transversais de apoio usam uma assinatura distinta para não virar categoria genérica invisível."},
            {"key": "sem-categoria", "usage": "Faixa transitória para itens que ainda exigem saneamento de classificação antes de entrar no fluxo oficial."},
        ),
    },
)

_ENTERPRISE_CATEGORY_ICON_FILE_BY_KEY = {
    "material-eletrico": "logo/icon/eletricos.png",
    "material-hidraulico": "logo/icon/hidraulico.png",
    "material-piscina": "logo/icon/piscina.png",
    "mat-pintura-drywall": "logo/icon/pintura.png",
    "materiais-limpeza": "logo/icon/limpeza.png",
    "material-construcao": "logo/icon/materiais.png",
    "ferramentas": "logo/icon/ferramentas.png",
    "equipamento": "logo/icon/equipamentos.png",
    "equipamento-ti": "logo/icon/equipamentos.png",
    "material-ep": "logo/icon/epi.png",
    "material-uso-geral": "logo/icon/materiais.png",
    "sem-categoria": "logo/icon/estoque.png",
}


def _resolve_enterprise_category_icon_url(category_key: object) -> str | None:
    asset_path = _ENTERPRISE_CATEGORY_ICON_FILE_BY_KEY.get(str(category_key or "").strip())
    if not asset_path:
        return None
    return url_for("static", filename=asset_path, v="20260504-enterprise-categories")


_ADMIN_BLOCKS = (
    {"number": 1, "name": "Itanhangá", "counts": {"default": 10}},
    {"number": 2, "name": "Sernambetiba", "counts": {"default": 8}},
    {"number": 3, "name": "Itaúna", "counts": {"default": 10}},
    {"number": 4, "name": "Reserva", "counts": {"default": 12, 1: 10}},
    {"number": 5, "name": "Recreio", "counts": {"default": 8, 1: 6}},
    {"number": 6, "name": "Pontal", "counts": {"default": 12, 1: 10}},
    {"number": 7, "name": "Prainha", "counts": {"default": 12, 1: 10}},
    {"number": 8, "name": "Grumari", "counts": {"default": 10, 1: 9}},
    {"number": 9, "name": "Pedra Branca", "counts": {"default": 10, 1: 9}},
)

_ADMIN_REFORM_UNITS = {205, 209, 211, 310, 405, 409, 411, 603, 606, 607, 610, 612, 1010}
_ADMIN_VACANT_UNITS = {104, 108, 202, 304, 308, 402, 704, 708, 710, 802, 904, 908, 1002}


def _admin_floor_unit_count(block: dict[str, object], floor: int) -> int:
    counts = block.get("counts") if isinstance(block.get("counts"), dict) else {}
    return int(counts.get(floor) or counts.get("default") or 0)


def _default_admin_block(number: int | None) -> dict[str, object] | None:
    for block in _ADMIN_BLOCKS:
        if int(block["number"]) == int(number or 0):
            return block
    return None


def _default_block_custom_units_text(block: dict[str, object]) -> str:
    lines: list[str] = []
    for floor in range(1, 11):
        unit_count = _admin_floor_unit_count(block, floor)
        units = [str(floor * 100 + position) for position in range(1, unit_count + 1)]
        lines.append(f"{floor}: {', '.join(units)}")
    return "\n".join(lines)


def _build_admin_block_dashboard_from_defaults() -> dict[str, object]:
    cards: list[dict[str, object]] = []
    totals = {"ocupado": 0, "vago": 0, "reforma": 0, "sem_cadastro": 0, "unidades": 0}

    for block in _ADMIN_BLOCKS:
        floor_counts = [_admin_floor_unit_count(block, floor) for floor in range(1, 11)]
        max_columns = max(floor_counts) if floor_counts else 0
        block_totals = {"ocupado": 0, "vago": 0, "reforma": 0, "sem_cadastro": 0, "unidades": 0}
        floors: list[dict[str, object]] = []

        for floor in range(10, 0, -1):
            unit_count = _admin_floor_unit_count(block, floor)
            units: list[dict[str, object]] = []
            for position in range(1, max_columns + 1):
                if position > unit_count:
                    units.append({"empty": True})
                    continue
                unit_number = floor * 100 + position
                status = "sem_cadastro"
                units.append({"empty": False, "number": unit_number, "status": status, "status_label": UNIT_STATUS_LABELS[status]})
                block_totals[status] += 1
                block_totals["unidades"] += 1
                totals[status] += 1
                totals["unidades"] += 1
            floors.append({"floor": floor, "units": units})

        cards.append(
            {
                "building_id": None,
                "editor_model": block["number"],
                "number": block["number"],
                "name": block["name"],
                "max_columns": max_columns,
                "floors": floors,
                "totals": block_totals,
            }
        )

    return {"cards": cards, "totals": totals, "block_count": len(cards)}


def _build_admin_block_dashboard() -> dict[str, object]:
    return build_condominium_block_dashboard() or _build_admin_block_dashboard_from_defaults()


def _current_user_matricula() -> str | None:
    value = str(getattr(current_user, "matricula", "") or "").strip()
    return value or None


def _form_int(name: str, *, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw_value = str(request.form.get(name, default) or default).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Campo numerico invalido: {name}.") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"Campo {name} deve ser maior ou igual a {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"Campo {name} deve ser menor ou igual a {maximum}.")
    return value


def _building_form(building: CondominiumBuilding | None = None) -> dict[str, object]:
    if building:
        return {
            "id": building.id,
            "code": building.code,
            "name": building.name,
            "display_order": building.display_order,
            "floor_start": building.floor_start,
            "floor_count": building.floor_count,
            "units_per_floor": building.units_per_floor,
            "unit_suffix_start": building.unit_suffix_start,
            "suffix_width": building.suffix_width,
            "custom_units_text": building.custom_units_text or "",
            "notes": building.notes or "",
            "active": building.active,
        }
    return {
        "id": None,
        "code": "",
        "name": "",
        "display_order": 0,
        "floor_start": 1,
        "floor_count": 10,
        "units_per_floor": 4,
        "unit_suffix_start": 0,
        "suffix_width": 2,
        "custom_units_text": "",
        "notes": "",
        "active": True,
    }


def _building_form_from_default(block: dict[str, object]) -> dict[str, object]:
    block_number = int(block["number"])
    default_count = _admin_floor_unit_count(block, 1)
    return {
        "id": None,
        "code": str(block_number),
        "name": block["name"],
        "display_order": block_number,
        "floor_start": 1,
        "floor_count": 10,
        "units_per_floor": default_count,
        "unit_suffix_start": 1,
        "suffix_width": 2,
        "custom_units_text": _default_block_custom_units_text(block),
        "notes": "",
        "active": True,
        "template_mode": True,
    }


def _building_summaries() -> list[dict[str, object]]:
    buildings = (
        CondominiumBuilding.query
        .order_by(CondominiumBuilding.active.desc(), CondominiumBuilding.display_order.asc(), CondominiumBuilding.id.asc())
        .all()
    )
    summaries: list[dict[str, object]] = []
    for building in buildings:
        units = [unit for unit in building.units if unit.active]
        status_counts = {"ocupado": 0, "vago": 0, "reforma": 0, "sem_cadastro": 0}
        floors = sorted({int(unit.floor_number or 0) for unit in units})
        for unit in units:
            status_counts[unit_dashboard_status(unit)] += 1
        summaries.append(
            {
                "building": building,
                "units_total": len(units),
                "floor_total": len(floors),
                "floor_range": f"{floors[0]} a {floors[-1]}" if floors else "-",
                "status_counts": status_counts,
            }
        )
    return summaries


def _owner_photo_upload(owner_id: int) -> str | None:
    captured_data = str(request.form.get("photo_capture_data") or "").strip()
    file = request.files.get("photo")
    if (not file or not file.filename) and not captured_data:
        return None

    static_root = Path(current_app.static_folder or (Path(current_app.root_path) / "static"))
    upload_dir = static_root / "uploads" / "condominio" / "proprietarios"
    upload_dir.mkdir(parents=True, exist_ok=True)

    if captured_data:
        match = re.match(r"^data:(image\/(?:png|jpeg|webp));base64,(.+)$", captured_data, re.IGNORECASE)
        if not match:
            raise ValueError("Formato da foto capturada e invalido.")
        mime_type = match.group(1).lower()
        encoded = match.group(2)
        extension_by_mime = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }
        extension = extension_by_mime.get(mime_type)
        if not extension:
            raise ValueError("Foto capturada deve ser JPG, PNG ou WEBP.")
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Nao foi possivel processar a foto capturada.") from exc
        if not image_bytes:
            raise ValueError("A foto capturada veio vazia.")
        if len(image_bytes) > 6 * 1024 * 1024:
            raise ValueError("A foto capturada excede o limite de 6 MB.")
        relative_path = Path("uploads") / "condominio" / "proprietarios" / f"proprietario_{owner_id}{extension}"
        (static_root / relative_path).write_bytes(image_bytes)
        return relative_path.as_posix()

    filename = secure_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Foto deve ser JPG, PNG ou WEBP.")
    relative_path = Path("uploads") / "condominio" / "proprietarios" / f"proprietario_{owner_id}{extension}"
    file.save(static_root / relative_path)
    return relative_path.as_posix()


def _condominium_unit_options() -> list[CondominiumUnit]:
    return (
        CondominiumUnit.query
        .join(CondominiumBuilding)
        .filter(CondominiumUnit.active.is_(True), CondominiumBuilding.active.is_(True))
        .order_by(
            CondominiumBuilding.display_order.asc(),
            CondominiumBuilding.id.asc(),
            CondominiumUnit.floor_number.asc(),
            CondominiumUnit.position.asc(),
            CondominiumUnit.number.asc(),
        )
        .all()
    )


def _condominium_owner_rows() -> list[CondominiumOwner]:
    return (
        CondominiumOwner.query
        .outerjoin(CondominiumUnit)
        .outerjoin(CondominiumBuilding)
        .order_by(
            CondominiumOwner.status.asc(),
            CondominiumBuilding.display_order.asc(),
            CondominiumUnit.floor_number.asc(),
            CondominiumUnit.position.asc(),
            CondominiumOwner.full_name.asc(),
        )
        .limit(80)
        .all()
    )


def _parse_iso_date(raw_value: object, *, default: date | None = None) -> date:
    value = str(raw_value or "").strip()
    if not value:
        if default is not None:
            return default
        raise ValueError("Informe uma data valida.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Informe uma data valida.") from exc


def _parse_iso_time(raw_value: object) -> dt_time | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        hour, minute = value.split(":", 1)
        return dt_time(int(hour), int(minute))
    except (ValueError, TypeError) as exc:
        raise ValueError("Informe horario no formato HH:MM.") from exc


def _month_date_from_request(selected_date: date) -> date:
    raw_month = str(request.args.get("mes") or "").strip()
    if raw_month:
        try:
            year_raw, month_raw = raw_month.split("-", 1)
            return date(int(year_raw), int(month_raw), 1)
        except ValueError:
            return date(selected_date.year, selected_date.month, 1)
    return date(selected_date.year, selected_date.month, 1)


def _schedule_form_options() -> dict[str, object]:
    return {
        "event_types": EVENT_TYPE_LABELS,
        "scopes": SCOPE_LABELS,
        "statuses": STATUS_LABELS,
        "priorities": PRIORITY_LABELS,
        "buildings": (
            CondominiumBuilding.query
            .filter_by(active=True)
            .order_by(CondominiumBuilding.display_order.asc(), CondominiumBuilding.id.asc())
            .all()
        ),
        "units": _condominium_unit_options(),
        "owners": (
            CondominiumOwner.query
            .filter_by(status="ativo")
            .order_by(CondominiumOwner.full_name.asc())
            .all()
        ),
    }


def _schedule_event_form(event: CondominiumScheduleEvent | None, *, selected_date: date) -> dict[str, object]:
    if event:
        return {
            "id": event.id,
            "event_date": event.event_date.isoformat(),
            "start_time": event.start_time.strftime("%H:%M") if event.start_time else "",
            "end_time": event.end_time.strftime("%H:%M") if event.end_time else "",
            "title": event.title,
            "event_type": event.event_type,
            "scope": event.scope,
            "status": event.status,
            "priority": event.priority,
            "building_id": event.building_id or "",
            "unit_id": event.unit_id or "",
            "owner_id": event.owner_id or "",
            "contact_name": event.contact_name or "",
            "contact_phone": event.contact_phone or "",
            "location": event.location or "",
            "description": event.description or "",
            "notify_enabled": event.notify_enabled,
            "reminder_minutes": event.reminder_minutes,
        }
    return {
        "id": None,
        "event_date": selected_date.isoformat(),
        "start_time": "",
        "end_time": "",
        "title": "",
        "event_type": "compromisso",
        "scope": "administracao",
        "status": "agendado",
        "priority": "normal",
        "building_id": "",
        "unit_id": "",
        "owner_id": "",
        "contact_name": "",
        "contact_phone": "",
        "location": "",
        "description": "",
        "notify_enabled": True,
        "reminder_minutes": 30,
    }


def _apply_schedule_event_form(event: CondominiumScheduleEvent) -> None:
    event_date = _parse_iso_date(request.form.get("event_date"))
    start_time = _parse_iso_time(request.form.get("start_time"))
    end_time = _parse_iso_time(request.form.get("end_time"))
    if start_time and end_time and end_time <= start_time:
        raise ValueError("Horario final precisa ser depois do horario inicial.")

    title = str(request.form.get("title") or "").strip()
    if not title:
        raise ValueError("Informe o titulo do compromisso.")

    unit_id = request.form.get("unit_id", type=int)
    owner_id = request.form.get("owner_id", type=int)
    building_id = request.form.get("building_id", type=int)
    unit = CondominiumUnit.query.get(unit_id) if unit_id else None
    owner = CondominiumOwner.query.get(owner_id) if owner_id else None
    if owner and owner.unit and unit and owner.unit_id != unit.id:
        raise ValueError("O proprietario selecionado nao pertence a unidade escolhida.")
    if owner and owner.unit and not unit:
        unit = owner.unit
    building = unit.building if unit else (CondominiumBuilding.query.get(building_id) if building_id else None)

    reminder_minutes = _form_int("reminder_minutes", default=30, minimum=0, maximum=10080)
    contact_name = str(request.form.get("contact_name") or "").strip() or (owner.full_name if owner else None)
    contact_phone = str(request.form.get("contact_phone") or "").strip() or (owner.phone if owner else None)

    event.event_date = event_date
    event.start_time = start_time
    event.end_time = end_time
    event.title = title
    event.event_type = normalize_event_type(request.form.get("event_type"))
    event.scope = normalize_scope(request.form.get("scope"))
    event.status = normalize_status(request.form.get("status"))
    event.priority = normalize_priority(request.form.get("priority"))
    event.building = building
    event.unit = unit
    event.owner = owner
    event.contact_name = contact_name
    event.contact_phone = contact_phone
    event.location = str(request.form.get("location") or "").strip() or None
    event.description = str(request.form.get("description") or "").strip() or None
    event.notify_enabled = bool(request.form.get("notify_enabled"))
    event.reminder_minutes = reminder_minutes
    event.notification_acknowledged_at = None
    event.updated_by_matricula = _current_user_matricula()


def _system_setting_item(label: str, endpoint: str, icon: str, family: str, *, enabled: bool = True) -> dict[str, str] | None:
    if not enabled or endpoint not in current_app.view_functions:
        return None
    return {"label": label, "href": url_for(endpoint), "icon": icon, "family": family}


def _system_setting_section(label: str, icon: str, items: list[dict[str, str] | None]) -> dict[str, object] | None:
    visible_items = [item for item in items if item]
    if not visible_items:
        return None
    return {"label": label, "icon": icon, "items": visible_items}


def _build_system_settings_hub(*, is_admin: bool) -> dict[str, object]:
    mobile_panel_enabled = is_admin and bool(current_app.config.get("FEATURE_MOBILE_PANEL_ENABLED", False))
    sections = [
        _system_setting_section(
            "Sistema",
            "bi-sliders",
            [
                _system_setting_item("Empresa", "config.empresa", "bi-building", "Core"),
                _system_setting_item("Imagens do Sistema", "config.imagens", "bi-images", "Visual"),
                _system_setting_item("Relatórios", "config.relatorios", "bi-file-earmark-text", "Core"),
                _system_setting_item("Atualizações", "updates.index", "bi-arrow-clockwise", "Core"),
                _system_setting_item("Rede", "pages.config_rede", "bi-wifi", "Core"),
                _system_setting_item("Checklist Final", "pages.backup_final_checklist", "bi-clipboard2-check", "Core"),
            ],
        ),
        _system_setting_section(
            "Operações Técnicas",
            "bi-terminal",
            [
                _system_setting_item("Notificações", "config.notificacoes", "bi-bell", "Alertas"),
                _system_setting_item("Telegram", "telegram_config.index", "bi-telegram", "Mensageria"),
                _system_setting_item("Histórico Telegram", "telegram_config.historico", "bi-clock-history", "Mensageria"),
                _system_setting_item("Backup", "pages.config_backup", "bi-database", "Dados"),
                _system_setting_item("ConversionEngine", "pages.config_conversionengine", "bi-cpu", "Restore", enabled=is_admin),
            ],
        ),
        _system_setting_section(
            "Governança",
            "bi-shield-check",
            [
                _system_setting_item("Usuários", "users.list_users", "bi-people-fill", "Permissões", enabled=is_admin),
                _system_setting_item("Painel Mobile", "mobile_panel.dashboard", "bi-phone-fill", "Mobile", enabled=mobile_panel_enabled),
                _system_setting_item("Dispositivos Mobile", "mobile_panel.devices", "bi-phone", "Mobile", enabled=mobile_panel_enabled),
                _system_setting_item("Versões Mobile", "mobile_panel.versions", "bi-cloud-download", "Mobile", enabled=mobile_panel_enabled),
                _system_setting_item("Features Mobile", "mobile_panel.features", "bi-toggles2", "Mobile", enabled=mobile_panel_enabled),
                _system_setting_item("Auditoria Mobile", "mobile_panel.audit", "bi-shield-check", "Mobile", enabled=mobile_panel_enabled),
                _system_setting_item("Ajuste de Estoque", "config.estoque_ajuste_admin", "bi-shield-lock", "Controle", enabled=is_admin),
                _system_setting_item("Fornecedores", "config.fornecedores", "bi-building-add", "Cadastro"),
            ],
        ),
    ]
    visible_sections = [section for section in sections if section]
    return {"sections": visible_sections, "total_items": sum(len(section["items"]) for section in visible_sections)}

_ABOUT_CATEGORY_REFERENCE_FLOW = (
    {
        "step": "01",
        "icon": "bi-tags",
        "title": "Catalogar a tipologia",
        "text": "O item nasce com categoria canônica, nome consistente, ícone e cor oficial definidos pelo catálogo central.",
    },
    {
        "step": "02",
        "icon": "bi-palette2",
        "title": "Propagar a identidade visual",
        "text": "A mesma tipologia é reaproveitada em chips, filtros, cards, classificadores e resumos financeiros sem criar versões paralelas.",
    },
    {
        "step": "03",
        "icon": "bi-grid-1x2-fill",
        "title": "Aplicar nos painéis certos",
        "text": "No dashboard ficam só os blocos operacionais. A explicação detalhada da taxonomia sai do fluxo principal e vai para o Sobre.",
    },
    {
        "step": "04",
        "icon": "bi-file-earmark-bar-graph",
        "title": "Ler e decidir sem ambiguidade",
        "text": "Relatórios, financeiro e documentação passam a ler a mesma taxonomia, reduzindo ruído visual e divergência de interpretação.",
    },
)

_ABOUT_CATEGORY_REFERENCE_SURFACES = (
    {
        "icon": "bi-card-checklist",
        "title": "Cadastro do item",
        "text": "É onde a tipologia entra oficialmente e evita descrições improvisadas ou filtros quebrados no restante do produto.",
    },
    {
        "icon": "bi-funnel",
        "title": "Filtros e busca",
        "text": "Os chips de categoria e os filtros de classificação dependem desse catálogo para manter leitura coerente na operação.",
    },
    {
        "icon": "bi-columns-gap",
        "title": "Painéis e cards",
        "text": "Dashboard, laboratórios visuais e cards de apoio devem usar a mesma assinatura, mas só quando isso ajuda a decisão operacional.",
    },
    {
        "icon": "bi-cash-stack",
        "title": "Financeiro e relatórios",
        "text": "KPIs, totais por categoria, planilhas e documentos precisam preservar a mesma semântica visual e textual.",
    },
)

_ABOUT_CATEGORY_REFERENCE_RULES = (
    {
        "title": "Nome canônico primeiro",
        "text": "Cada tipologia oficial tem nome, ícone e cor padronizados. O produto não deve reinventar isso em cada tela.",
    },
    {
        "title": "Mesma paleta em superfícies compartilhadas",
        "text": "Cadastro, filtros, dashboards, financeiro e relatórios devem repetir a mesma cor para a mesma categoria.",
    },
    {
        "title": "Sem categoria é contingência, não destino final",
        "text": "A faixa cinza existe para saneamento operacional e não deve virar categoria definitiva do catálogo saudável.",
    },
    {
        "title": "Documentação separada do fluxo diário",
        "text": "O dashboard fica com leitura operacional enxuta; a explicação completa da taxonomia e das regras vive no Sobre em aba própria.",
    },
)

_ABOUT_DOCUMENT_GUIDE_STEPS = (
    {
        "step": "01",
        "icon": "bi-search",
        "title": "Localize o item e escolha o modo",
        "text": "Busque o item primeiro. Se ele ainda nao existir, crie o item novo na mesma rotina e so depois complete o documento.",
    },
    {
        "step": "02",
        "icon": "bi-receipt-cutoff",
        "title": "Preencha so o que comprova a compra",
        "text": "NF usa numero, datas e fornecedor. Cupom usa comprovacao simples sem chave. Sem NF ou cupom usa referencia interna e observacao.",
    },
    {
        "step": "03",
        "icon": "bi-kanban",
        "title": "Acompanhe pelas abas operacionais",
        "text": "Depois de salvar, o documento segue para Processaveis, Erros ou Historico, sem abrir uma aba separada so para pendencias.",
    },
)

_ABOUT_DOCUMENT_GUIDE_MODES = (
    {
        "icon": "bi-file-earmark-text",
        "title": "Lancar com NF",
        "badge": "Comprovacao fiscal completa",
        "summary": "Use quando a compra ja tem nota fiscal. Se existir chave de acesso, ela entra no mesmo lancamento.",
        "items": (
            "Numero da NF",
            "Datas de emissao e recebimento",
            "Fornecedor e CNPJ",
            "Chave de acesso, se houver",
        ),
    },
    {
        "icon": "bi-receipt",
        "title": "Lancar com cupom",
        "badge": "Comprovacao fiscal simples",
        "summary": "Use para cupom ou comprovante simples de balcao, sem exigir chave de acesso.",
        "items": (
            "Numero do cupom",
            "Datas",
            "Fornecedor ou CNPJ da loja",
            "Itens e valores",
        ),
    },
    {
        "icon": "bi-journal-minus",
        "title": "Lancar sem NF ou cupom",
        "badge": "Sem comprovacao fiscal",
        "summary": "Use quando ainda nao existe comprovante formal. O registro continua rastreavel, mas com status compativel com ausencia de comprovacao fiscal.",
        "items": (
            "Referencia interna compartilhada",
            "Valor e itens",
            "Observacao financeira",
            "Origem do valor",
        ),
    },
)

_ABOUT_DOCUMENT_GUIDE_RULES = (
    {
        "title": "NF e o fluxo mais completo",
        "text": "Quando houver nota fiscal, prefira esse modo para manter o vinculo documental mais forte desde o cadastro.",
    },
    {
        "title": "Cupom nao usa chave de acesso",
        "text": "Cupom serve para compra simples com comprovacao direta, sem abrir um fluxo pesado de nota fiscal.",
    },
    {
        "title": "Sem NF ou cupom usa o modo manual",
        "text": "Quando nao houver comprovacao fiscal, use o lancamento sem NF ou cupom. O sistema continua registrando a compra sem inventar numero fiscal.",
    },
    {
        "title": "A triagem continua nas abas",
        "text": "Depois da gravacao, o acompanhamento segue em Processaveis, Erros e Historico. A explicacao saiu da tela pratica, nao o controle operacional.",
    },
)

_ABOUT_PURCHASE_PROJECTION_FORMULAS = (
    {
        "icon": "bi-speedometer2",
        "title": "Dias restantes",
        "formula": "dias_restantes = saldo_base / consumo_medio",
        "text": "Mostra quantos dias o saldo do ledger ainda cobre quando existe consumo medio valido em unidade base.",
    },
    {
        "icon": "bi-cart-plus",
        "title": "Quantidade sugerida",
        "formula": "quantidade_sugerida = max((consumo_medio x dias_cobertura) - saldo_base, 0)",
        "text": "A sugestao nasce da cobertura desejada menos o saldo atual, sempre sem deixar valor negativo entrar no pedido.",
    },
    {
        "icon": "bi-activity",
        "title": "Consumo medio",
        "formula": "consumo_medio = consumo_liquido_periodo / janela_dias",
        "text": "A media diaria sai do historico real de saidas no ledger dentro da janela escolhida pelo operador.",
    },
)

_ABOUT_PURCHASE_PROJECTION_FILTERS = (
    {
        "icon": "bi-search",
        "title": "Busca livre",
        "text": "Use codigo ou descricao quando precisar localizar um item especifico sem depender da tabela inteira.",
    },
    {
        "icon": "bi-tags",
        "title": "Categoria guiada",
        "text": "A categoria agora entra por seletor com lista pronta, no mesmo estilo do filtro de status, sem obrigar digitacao manual.",
    },
    {
        "icon": "bi-bookmark-star",
        "title": "Marca guiada",
        "text": "A marca tambem entra por seletor proprio para separar familias de compra sem ruir a busca livre.",
    },
    {
        "icon": "bi-sliders",
        "title": "Janela, cobertura e status",
        "text": "Os parametros operacionais continuam independentes para ajustar horizonte de leitura, risco e itens visiveis.",
    },
)

_ABOUT_PURCHASE_PROJECTION_STEPS = (
    {
        "step": "01",
        "icon": "bi-funnel",
        "title": "Filtre o recorte certo",
        "text": "Comece por categoria, marca, status e janela antes de selecionar o que realmente vai para o pedido.",
    },
    {
        "step": "02",
        "icon": "bi-exclamation-diamond",
        "title": "Leia os bloqueios",
        "text": "Status, validacoes, fornecedor e preco coerente decidem se o item pode virar pedido ou so alerta operacional.",
    },
    {
        "step": "03",
        "icon": "bi-file-earmark-spreadsheet",
        "title": "Consolide e exporte",
        "text": "A quantidade final continua ajustavel em unidade base e o XLS sai apenas quando o carrinho estiver consistente.",
    },
)


def _inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def _markdown_file_to_html(file_path: Path) -> str:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    parts: list[str] = []
    in_ul = False
    in_ol = False
    in_pre = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        if in_ol:
            parts.append("</ol>")
            in_ol = False

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            close_lists()
            if in_pre:
                parts.append("</code></pre>")
                in_pre = False
            else:
                parts.append('<pre class="doc-code"><code>')
                in_pre = True
            continue

        if in_pre:
            parts.append(html.escape(line))
            continue

        if not stripped:
            close_lists()
            continue

        if stripped == "---":
            close_lists()
            parts.append("<hr>")
            continue

        if stripped.startswith("### "):
            close_lists()
            parts.append(f"<h3>{_inline_markdown_to_html(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            close_lists()
            parts.append(f"<h2>{_inline_markdown_to_html(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            close_lists()
            parts.append(f"<h1>{_inline_markdown_to_html(stripped[2:])}</h1>")
            continue

        if re.match(r"^\d+\.\s+", stripped):
            if not in_ol:
                close_lists()
                parts.append('<ol class="doc-list">')
                in_ol = True
            item_text = re.sub(r"^\d+\.\s+", "", stripped)
            parts.append(f"<li>{_inline_markdown_to_html(item_text)}</li>")
            continue

        if stripped.startswith("- "):
            if not in_ul:
                close_lists()
                parts.append('<ul class="doc-list">')
                in_ul = True
            parts.append(f"<li>{_inline_markdown_to_html(stripped[2:])}</li>")
            continue

        close_lists()
        parts.append(f"<p>{_inline_markdown_to_html(stripped)}</p>")

    close_lists()
    if in_pre:
        parts.append("</code></pre>")

    return "\n".join(parts)


def _build_about_category_reference() -> dict[str, object]:
    default_rows_by_key = {row.key: row for row in DEFAULT_INVENTORY_CATEGORIES}
    visual_catalog = category_catalog_service.list_visual_catalog(include_inactive=True)
    visuals_by_key = {str(row.get("key") or ""): row for row in visual_catalog}

    groups: list[dict[str, object]] = []
    total_categories = 0

    for group in _ABOUT_CATEGORY_REFERENCE_GROUPS:
        group_items: list[dict[str, object]] = []
        for index, item_meta in enumerate(group["items"]):
            key = str(item_meta["key"])
            default_row = default_rows_by_key.get(key)
            if default_row is not None:
                visual = visuals_by_key.get(key) or category_catalog_service.get_visual(default_row.nome, fallback_index=index)
                description = default_row.descricao
            else:
                visual = visuals_by_key.get(key) or category_catalog_service.get_visual("Sem categoria", fallback_index=index)
                description = "Faixa transitória para itens que ainda aguardam classificação canônica no catálogo oficial."

            group_items.append(
                {
                    "key": key,
                    "label": visual.get("label") or (default_row.nome if default_row is not None else "Sem categoria"),
                    "icon": visual.get("icon") or "📁",
                    "color": visual.get("color") or "#94a3b8",
                    "soft": visual.get("soft") or visual.get("soft_strong") or "rgba(148, 163, 184, 0.18)",
                    "description": description,
                    "usage": item_meta["usage"],
                }
            )

        total_categories += len(group_items)
        groups.append(
            {
                "id": group["id"],
                "title": group["title"],
                "summary": group["summary"],
                "accent": group["accent"],
                "items": group_items,
                "count": len(group_items),
            }
        )

    for group in groups:
        count = int(group["count"] or 0)
        group["share_pct"] = round((count / total_categories) * 100, 1) if total_categories else 0.0

    return {
        "catalog": visual_catalog,
        "groups": groups,
        "flow": list(_ABOUT_CATEGORY_REFERENCE_FLOW),
        "surfaces": list(_ABOUT_CATEGORY_REFERENCE_SURFACES),
        "rules": list(_ABOUT_CATEGORY_REFERENCE_RULES),
        "total_categories": total_categories,
        "group_count": len(groups),
        "surface_count": len(_ABOUT_CATEGORY_REFERENCE_SURFACES),
        "rule_count": len(_ABOUT_CATEGORY_REFERENCE_RULES),
    }


def _build_about_document_guide() -> dict[str, object]:
    return {
        "steps": list(_ABOUT_DOCUMENT_GUIDE_STEPS),
        "modes": list(_ABOUT_DOCUMENT_GUIDE_MODES),
        "rules": list(_ABOUT_DOCUMENT_GUIDE_RULES),
    }


def _build_about_purchase_projection_guide() -> dict[str, object]:
    compatibility = purchase_projection_service.get_architecture_compatibility()
    return {
        "formulas": list(_ABOUT_PURCHASE_PROJECTION_FORMULAS),
        "filters": list(_ABOUT_PURCHASE_PROJECTION_FILTERS),
        "steps": list(_ABOUT_PURCHASE_PROJECTION_STEPS),
        "compatibility_cards": [
            {
                "title": "Resposta arquitetural",
                "text": compatibility["answer"],
                "items": list(compatibility.get("safe_because") or []),
            },
            {
                "title": "Conflitos",
                "text": "O modo seguro existe para nao misturar leituras parcialmente reconciliadas como se fossem equivalentes.",
                "items": list(compatibility.get("conflicts") or []),
            },
            {
                "title": "Adaptacoes aplicadas",
                "text": "Estas regras mantem a projeção operacional sem fingir que a base ja esta totalmente irrestrita.",
                "items": list(compatibility.get("required_adaptations") or []),
            },
            {
                "title": "Risco evitado",
                "text": "O objetivo e impedir que o pedido final repita os mesmos erros de conciliacao ja conhecidos na base.",
                "items": list(compatibility.get("risk_of_repeating_existing_inconsistencies") or []),
            },
        ],
    }


def _build_about_category_reference_fallback() -> dict[str, object]:
    groups: list[dict[str, object]] = []
    total_categories = 0

    for group in _ABOUT_CATEGORY_REFERENCE_GROUPS:
        group_items: list[dict[str, object]] = []
        for item_meta in group["items"]:
            key = str(item_meta["key"])
            label = key.replace("-", " ").strip().title() or "Sem categoria"
            group_items.append(
                {
                    "key": key,
                    "label": label,
                    "icon": "🏷️",
                    "color": group["accent"],
                    "soft": "rgba(148, 163, 184, 0.18)",
                    "description": "Referencia visual carregada em modo reduzido.",
                    "usage": item_meta["usage"],
                }
            )

        total_categories += len(group_items)
        groups.append(
            {
                "id": group["id"],
                "title": group["title"],
                "summary": group["summary"],
                "accent": group["accent"],
                "items": group_items,
                "count": len(group_items),
            }
        )

    for group in groups:
        count = int(group["count"] or 0)
        group["share_pct"] = round((count / total_categories) * 100, 1) if total_categories else 0.0

    return {
        "catalog": [],
        "groups": groups,
        "flow": list(_ABOUT_CATEGORY_REFERENCE_FLOW),
        "surfaces": list(_ABOUT_CATEGORY_REFERENCE_SURFACES),
        "rules": list(_ABOUT_CATEGORY_REFERENCE_RULES),
        "total_categories": total_categories,
        "group_count": len(groups),
        "surface_count": len(_ABOUT_CATEGORY_REFERENCE_SURFACES),
        "rule_count": len(_ABOUT_CATEGORY_REFERENCE_RULES),
        "fallback_mode": True,
    }


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


def _is_admin_value(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "sim", "yes"}


def _has_management_access() -> bool:
    if not bool(getattr(current_user, "is_authenticated", False)):
        return False
    if _is_admin_value(getattr(current_user, "is_admin", 0)):
        return True
    return bool(session.get("galint_management_access"))


def _is_registered_admin() -> bool:
    return _is_admin_value(getattr(current_user, "is_admin", 0))


def _management_module() -> str:
    return str(session.get("galint_management_module") or "").strip().lower()


def _is_messenger_session() -> bool:
    return _management_module() == "mensageria"


def _prime_admin_session() -> None:
    try:
        session.setdefault("galint_is_admin", bool(getattr(current_user, "is_admin", 0)))
        session.setdefault("galint_user_id", str(getattr(current_user, "matricula", "")))
    except Exception:
        pass


def _require_admin_session_json() -> tuple[str | None, tuple[object, int] | None]:
    """Auth leve (sem DB) para endpoints JSON de restore.

    Retorna (user_key, error_response). Se error_response não for None,
    deve ser retornado diretamente pela view.
    """
    user_id = session.get("_user_id")
    if not user_id:
        return None, (jsonify({"ok": False, "error": "Não autenticado. Faça login novamente."}), 401)
    if not bool(session.get("galint_is_admin")):
        return None, (jsonify({"ok": False, "error": "Acesso negado. Apenas administradores."}), 403)
    return str(user_id), None


def _normalize_workspace_slot(raw_value: object) -> int:
    try:
        value = int(raw_value or 2)
    except (TypeError, ValueError):
        value = 2
    return value if value in (2, 3) else 2


def _workspace_slot_request_mode(raw_value: object) -> tuple[bool, int | None]:
    normalized = str(raw_value or "").strip().lower()
    if not normalized or normalized == "auto":
        return True, None
    return False, _normalize_workspace_slot(raw_value)


def _build_workspace_window_url(path: str, token: str) -> str:
    raw_path = str(path or "").strip() or url_for("dashboard.index")
    split = urlsplit(raw_path)

    if split.scheme or split.netloc:
        if split.scheme not in {"http", "https"}:
            raise ValueError("A janela auxiliar aceita apenas URLs HTTP locais do GALINT.")
        if split.netloc != request.host:
            raise ValueError("A janela auxiliar so pode abrir paginas do proprio GALINT.")
        normalized_path = split.path or "/"
        query_pairs = parse_qsl(split.query, keep_blank_values=True)
    else:
        normalized = raw_path if raw_path.startswith("/") else f"/{raw_path.lstrip('/')}"
        normalized_split = urlsplit(normalized)
        normalized_path = normalized_split.path or "/"
        query_pairs = parse_qsl(normalized_split.query, keep_blank_values=True)

    query_pairs = [(key, value) for key, value in query_pairs if key not in {"workspace_token", "workspace_window"}]
    query_pairs.append(("workspace_window", "1"))
    query_pairs.append(("workspace_token", token))
    return urlunsplit((request.scheme, request.host, normalized_path, urlencode(query_pairs, doseq=True), ""))


def _build_condominium_blocks() -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for block in _ADMIN_BLOCKS:
        floor_counts = [_admin_floor_unit_count(block, floor) for floor in range(1, 11)]
        blocks.append(
            {
                "code": f"B{int(block['number']):02d}",
                "title": f"Bloco {block['number']} - Ed. {block['name']}",
                "floors": 10,
                "columns": (f"{min(floor_counts)} a {max(floor_counts)} unidades por andar",),
                "coverage": f"Cobertura com {floor_counts[-1]} unidades",
                "parking_mode": "Mapa visual do bloco usa a numeracao real informada pelo condominio",
            }
        )
    return blocks


def _build_admin_condominium_blueprint(*, mode: str) -> dict[str, object]:
    schedule_mode = mode == "schedule"
    hero = {
        "kicker": "Agenda condominial" if schedule_mode else "Cadastro mestre",
        "title": "Agendamento de Mudancas e Reservas" if schedule_mode else "Cadastros Relacionais do Condominio",
        "summary": (
            "A agenda nasce amarrada ao cadastro principal: responsavel, unidade, janela de acesso, placa do veiculo, apoio de prestadores e historico operacional."
            if schedule_mode
            else "O cadastro principal nasce como Proprietario ou Locatario. Pessoas da casa, visitantes recorrentes, veiculos, condutores e observacoes entram como vinculos do titular e da unidade."
        ),
        "badge": "Mudanca de entrada e saida" if schedule_mode else "Sem menu principal Morador",
    }
    return {
        "mode": mode,
        "hero": hero,
        "focus_section": "agendamentos" if schedule_mode else "cadastro-mestre",
        "anchors": [
            {"id": "cadastro-mestre", "label": "Cadastro mestre"},
            {"id": "estrutura", "label": "Blocos e unidades"},
            {"id": "vinculos", "label": "Vinculos e acessos"},
            {"id": "agendamentos", "label": "Agendamento"},
            {"id": "detalhe-relacional", "label": "Tela relacional"},
            {"id": "lgpd", "label": "LGPD"},
        ],
        "quick_facts": [
            {"label": "Blocos iniciais", "value": "9", "note": "Modelo parametrico para outros condominios"},
            {"label": "Andares", "value": "10", "note": "10o pavimento como cobertura"},
            {"label": "Unidades", "value": "Variavel", "note": "Cada bloco usa sua propria contagem real por andar"},
            {"label": "Agenda", "value": "Entrada + saida", "note": "Mudanca com janela operacional"},
        ],
        "principles": [
            {
                "title": "Titular principal sem menu Morador",
                "text": "O cadastro principal nasce como Proprietario ou Locatario. Filhos, pais, conjuges e demais pessoas da casa entram como vinculados do titular e da unidade.",
            },
            {
                "title": "Visitante entra uma vez e ganha permissao depois",
                "text": "Domestica, cuidador, pintor ou visitante recorrente ganham cadastro proprio e depois recebem acesso por unidade, bloco, periodo e finalidade.",
            },
            {
                "title": "Veiculos ficam dentro do cadastro",
                "text": "Carro, moto, bicicleta e bicicleta eletrica vivem no cadastro da unidade, preparados para vaga livre, fixa ou mista conforme a regra do condominio.",
            },
        ],
        "field_rules": [
            {"label": "Nome completo ou razao social", "rule": "Obrigatorio", "note": "Base primaria de identificacao"},
            {"label": "Tipo de pessoa", "rule": "Obrigatorio", "note": "Fisica ou juridica"},
            {"label": "CPF ou CNPJ", "rule": "Obrigatorio conforme tipo", "note": "Documento principal do titular"},
            {"label": "RG", "rule": "Fluxo residencial", "note": "Mantido quando fizer parte da identificacao civil"},
            {"label": "CNH", "rule": "Obrigatorio para condutor", "note": "So entra quando a pessoa puder dirigir veiculo vinculado"},
            {"label": "Foto", "rule": "Obrigatoria no cadastro principal", "note": "Base para identificacao visual e futuras integracoes"},
            {"label": "Telefone e e-mail", "rule": "Opcional", "note": "Nao devem travar o cadastro"},
            {"label": "Situacao cadastral", "rule": "Enxuta", "note": "Ativo, bloqueado ou encerrado apenas quando impactar a operacao"},
        ],
        "relationship_cards": [
            {
                "title": "Titular da unidade",
                "items": [
                    "Proprietario ou Locatario como responsavel principal",
                    "Vigencia do vinculo com a unidade",
                    "Observacoes e historico do contrato ou posse",
                ],
            },
            {
                "title": "Pessoas vinculadas",
                "items": [
                    "Dependentes e pessoas da casa",
                    "Conjuge, filhos, pais e moradores vinculados",
                    "Permissoes herdadas ou individualizadas por acesso",
                ],
            },
            {
                "title": "Visitantes autorizados",
                "items": [
                    "Visitante recorrente cadastrado uma unica vez",
                    "Prestador recorrente com bloco e unidade definidos",
                    "Controle por periodo, finalidade e observacao operacional",
                ],
            },
        ],
        "vehicle_cards": [
            {
                "title": "Tipos de veiculo",
                "items": ["Carro", "Moto", "Bicicleta", "Bicicleta eletrica"],
            },
            {
                "title": "Condutores autorizados",
                "items": [
                    "Pessoa vinculada ao titular ou a unidade",
                    "CNH quando o tipo de veiculo exigir habilitacao",
                    "Historico de quem pode usar cada veiculo",
                ],
            },
            {
                "title": "Regra de vaga versatil",
                "items": [
                    "Modo livre para o condominio atual",
                    "Modo fixo para empreendimentos com vaga definida",
                    "Modo misto para excecoes e reservas futuras",
                ],
            },
        ],
        "schedule_cards": [
            {
                "title": "Mudanca de entrada",
                "text": "Reserva o dia de chegada, janela de uso, apoio de elevador, placa do veiculo, responsavel e observacoes da portaria.",
            },
            {
                "title": "Mudanca de saida",
                "text": "Repete a logica de agenda com historico proprio, checklist de liberacao e registro do encerramento do uso da unidade.",
            },
            {
                "title": "Reservas de areas comuns",
                "text": "A mesma agenda pode crescer para salao, espaco gourmet e outras areas comuns sem quebrar a relacao com unidade e responsavel.",
            },
        ],
        "detail_cards": [
            {
                "title": "Quem e a pessoa",
                "text": "Leitura consolidada de identidade, documentos, foto, contatos e vinculo principal com a unidade.",
            },
            {
                "title": "Quem responde pela unidade",
                "text": "Mostra se o titular atual e Proprietario ou Locatario, quem foi o anterior e quais observacoes ainda impactam a operacao.",
            },
            {
                "title": "Veiculos e condutores",
                "text": "Lista placas, tipos, condutores autorizados, regras de vaga e observacoes de acesso por veiculo.",
            },
            {
                "title": "Visitantes e acessos",
                "text": "Mostra visitantes recorrentes, prestadores vinculados e o recorte de unidade ou bloco liberado para cada pessoa.",
            },
            {
                "title": "Ocorrencias e observacoes",
                "text": "A tela deve consolidar historico operacional, alertas internos e fatos relevantes do cadastro sem espalhar informacao em varias rotinas.",
            },
            {
                "title": "Reservas e mudancas",
                "text": "Ao abrir o cadastro, a pessoa tambem enxerga reservas futuras, mudancas de entrada e saida e o que ja foi concluido.",
            },
        ],
        "lgpd_cards": [
            {
                "title": "Mascaramento por perfil",
                "text": "CPF, RG, CNH, placa e outros dados sensiveis aparecem mascarados por padrao e so abrem integralmente para perfil autorizado.",
            },
            {
                "title": "Auditoria de leitura e edicao",
                "text": "Nao basta registrar quem alterou. O modulo precisa registrar tambem quem consultou dado sensivel, liberou acesso ou exportou cadastro.",
            },
            {
                "title": "Minimizacao de coleta",
                "text": "Contato nao pode ser obrigatorio sem finalidade. O sistema coleta o necessario para operar, nao um volume indiscriminado de dados.",
            },
            {
                "title": "Integracao por adapter",
                "text": "Facial, portaria ou cancela devem ser integrados por camada separada. O cadastro do GALINT continua como fonte principal de verdade.",
            },
        ],
        "integration_notes": [
            "Integracao futura com facial e controle de acesso entra por adapter, sem acoplar o cadastro ao fornecedor.",
            "Mensageria e app de ocorrencias devem consumir o mesmo vinculo entre titular, unidade, visitante, veiculo e agenda.",
            "A mesma base suporta o condominio atual com vaga livre e tambem futuros empreendimentos com regras fixas.",
        ],
        "blocks": _build_condominium_blocks(),
    }


def _build_admin_service_providers_blueprint() -> dict[str, object]:
    return {
        "hero": {
            "kicker": "Prestadores de Servicos",
            "title": "Empresas, equipes recorrentes e autorizacoes de acesso",
            "summary": "O cadastro de prestadores nasce no nivel da empresa e desce ate os funcionarios que entram no condominio com frequencia para manutencao, reparo, limpeza, tecnologia, seguranca ou apoio operacional.",
            "badge": "CNPJ + funcionarios vinculados",
        },
        "company_fields": [
            {"label": "Razao social e nome fantasia", "note": "Identificacao principal da empresa prestadora."},
            {"label": "CNPJ", "note": "Consulta futura na Receita para preencher dados cadastrais e situacao."},
            {"label": "Endereco e contatos", "note": "Telefone, e-mail, responsavel e canal de emergencia."},
            {"label": "Contrato e area de atuacao", "note": "Elevador, piscina, portaria, TI, obras, pintura, hidraulica ou outro dominio."},
            {"label": "Situacao operacional", "note": "Ativa, suspensa, bloqueada ou encerrada, sem apagar historico."},
        ],
        "worker_fields": [
            {"label": "Nome, CPF, RG e foto", "note": "Documento mascarado por padrao e foto para conferencia visual."},
            {"label": "Empresa vinculada", "note": "Funcionario nao fica solto no sistema; ele pertence a uma prestadora."},
            {"label": "Funcao e validade", "note": "Eletricista, tecnico, jardineiro, piscineiro, seguranca ou outro papel com periodo autorizado."},
            {"label": "Escopo de acesso", "note": "Bloco, unidade, setor tecnico, casa de maquinas, horario e finalidade."},
            {"label": "Historico e bloqueios", "note": "Eventos de entrada, ocorrencias, restricoes e observacoes administrativas."},
        ],
        "automation_cards": [
            {"title": "Receita/CNPJ", "text": "Preenchimento assistido para empresas prestadoras e proprietarios pessoa juridica, com validacao de situacao cadastral quando a API estiver disponivel."},
            {"title": "Portaria e acesso", "text": "Base preparada para liberar prestador por agenda, unidade, bloco ou chamado, sem depender de anotacao manual."},
            {"title": "OS e ocorrencias", "text": "Funcionario recorrente pode ser ligado a reparos, manutencoes e futuras ordens de servico."},
        ],
        "security_cards": [
            {"title": "Menor exposicao possivel", "text": "A tela mostra documento mascarado e revela dados completos apenas com motivo e perfil autorizado."},
            {"title": "Auditoria forte", "text": "Consulta, edicao, autorizacao e bloqueio precisam registrar operador, data, motivo e entidade afetada."},
            {"title": "Acesso temporario", "text": "Prestador eventual pode ter janela definida sem virar cadastro permanente indevido."},
        ],
    }

@blueprint.post("/workspace/native-open")
@login_required
def workspace_native_open_api():
    if not bool(current_app.config.get("FEATURE_WORKSPACE_WINDOWS_ENABLED", False)):
        return jsonify({
            "success": False,
            "code": "workspace-windows-disabled",
            "message": "As janelas auxiliares estao desativadas nesta instalacao.",
        }), 404

    payload = request.get_json(silent=True)
    request_data = payload if isinstance(payload, dict) else request.form

    try:
        token = create_workspace_window_token(current_user)
        target_url = _build_workspace_window_url(str((request_data or {}).get("path") or ""), token)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    title = str((request_data or {}).get("title") or "").strip() or current_app.config.get("SYSTEM_NAME", "GALINT")
    auto_mode, slot = _workspace_slot_request_mode((request_data or {}).get("slot"))
    owner_key = getattr(current_user, "matricula", None)
    if auto_mode:
        result = launch_workspace_window_auto(target_url, title[:120], owner_key=owner_key)
    else:
        result = launch_workspace_window(target_url, title[:120], slot=slot, owner_key=owner_key)

    if result.get("success"):
        status_code = 200
    elif result.get("code") in {"slot-limit-reached", "slot-occupied"}:
        status_code = 409
    else:
        status_code = 503
    return jsonify(result), status_code


@blueprint.get("/configuracoes")
@login_required
def config():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))
    is_admin = bool(getattr(current_user, "is_admin", 0))
    return render_template(
        "system_config.html",
        system_settings=_build_system_settings_hub(is_admin=is_admin),
    )


@blueprint.get("/administracao")
@login_required
def administration_dashboard():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))
    return render_template(
        "config.html",
        condominium_block_dashboard=_build_admin_block_dashboard(),
        agenda_summary=build_schedule_dashboard_summary(),
        agenda_notifications=due_schedule_notifications(),
    )


@blueprint.get("/mensageria/manutencao")
@login_required
def mensageria_maintenance():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    return render_template("mensageria_maintenance.html")


def _mask_sensitive_document(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Documento nao informado"
    if len(text) <= 5:
        return "***"
    return f"{text[:3]}***{text[-2:]}"


def _owner_notes_from_form() -> str | None:
    base_notes = str(request.form.get("notes") or "").strip()
    sections = []
    for label, field_name in (
        ("Pessoas vinculadas", "linked_people"),
        ("Visitantes autorizados", "authorized_visitors"),
        ("Veiculos e condutores", "vehicles_drivers"),
    ):
        value = str(request.form.get(field_name) or "").strip()
        if value:
            sections.append(f"[{label}]\n{value}")
    content = [part for part in (base_notes, *sections) if part]
    return "\n\n".join(content) or None


def _owner_correspondence_payload() -> tuple[str | None, dict[str, str]]:
    cep = str(request.form.get("correspondence_cep") or "").strip()
    street = str(request.form.get("correspondence_street") or "").strip()
    number = str(request.form.get("correspondence_number") or "").strip()
    complement = str(request.form.get("correspondence_complement") or "").strip()
    neighborhood = str(request.form.get("correspondence_neighborhood") or "").strip()
    city = str(request.form.get("correspondence_city") or "").strip()
    state = str(request.form.get("correspondence_state") or "").strip().upper()
    reference = str(request.form.get("correspondence_reference") or "").strip()

    structured = {
        key: value
        for key, value in {
            "cep": cep,
            "street": street,
            "number": number,
            "complement": complement,
            "neighborhood": neighborhood,
            "city": city,
            "state": state,
            "reference": reference,
        }.items()
        if value
    }

    address_lines: list[str] = []
    first_line_parts = [part for part in (street, number) if part]
    first_line = ", ".join(first_line_parts)
    if complement:
        first_line = f"{first_line} - {complement}" if first_line else complement
    if first_line:
        address_lines.append(first_line)
    if neighborhood:
        address_lines.append(neighborhood)
    city_state = " - ".join(part for part in (city, state) if part)
    if city_state:
        address_lines.append(city_state)
    if cep:
        address_lines.append(f"CEP {cep}")
    if reference:
        address_lines.append(reference)

    composed = "\n".join(address_lines).strip()
    if composed:
        return composed, structured

    fallback_text = str(request.form.get("correspondence_address") or "").strip()
    return fallback_text or None, structured


def _owner_registry_data_from_form() -> dict[str, object]:
    _, correspondence_structured = _owner_correspondence_payload()
    owner_profile = {
        key: value
        for key, value in {
            "rg_issuer": str(request.form.get("rg_issuer") or "").strip(),
            "civil_status": str(request.form.get("civil_status") or "").strip(),
            "property_regime": str(request.form.get("property_regime") or "").strip(),
            "nationality": str(request.form.get("nationality") or "").strip(),
            "profession": str(request.form.get("profession") or "").strip(),
        }.items()
        if value
    }
    data: dict[str, object] = {}
    if owner_profile:
        data["owner_profile"] = owner_profile
    if correspondence_structured:
        data["correspondence_address"] = correspondence_structured
    return data


def _create_condominium_owner_from_request() -> CondominiumOwner:
    unit_id = request.form.get("unit_id", type=int)
    unit = CondominiumUnit.query.get(unit_id) if unit_id else None
    if unit is None or not unit.active or not unit.building or not unit.building.active:
        raise ValueError("Selecione uma unidade ativa.")

    full_name = str(request.form.get("full_name") or "").strip()
    document_number = str(request.form.get("document_number") or "").strip()
    if not full_name:
        raise ValueError("Informe o nome completo ou razao social.")
    if not document_number:
        raise ValueError("Informe CPF ou CNPJ.")

    correspondence_address, registry_data = _owner_correspondence_payload()[0], _owner_registry_data_from_form()

    owner = CondominiumOwner(
        unit=unit,
        relationship_type=str(request.form.get("relationship_type") or "proprietario").strip() or "proprietario",
        person_type=str(request.form.get("person_type") or "fisica").strip() or "fisica",
        full_name=full_name,
        document_number=document_number,
        rg=str(request.form.get("rg") or "").strip() or None,
        cnh=str(request.form.get("cnh") or "").strip() or None,
        phone=str(request.form.get("phone") or "").strip() or None,
        email=str(request.form.get("email") or "").strip() or None,
        correspondence_address=correspondence_address,
        emergency_contact=str(request.form.get("emergency_contact") or "").strip() or None,
        occupancy_status=str(request.form.get("occupancy_status") or "nao_informado").strip() or "nao_informado",
        registry_data_json=registry_data or None,
        lgpd_authorized=bool(request.form.get("lgpd_authorized")),
        notes=_owner_notes_from_form(),
        created_by_matricula=_current_user_matricula(),
        updated_by_matricula=_current_user_matricula(),
    )
    db.session.add(owner)
    db.session.flush()
    photo_path = _owner_photo_upload(owner.id)
    if photo_path:
        owner.photo_path = photo_path
    unit.status = "ocupado"
    return owner


@blueprint.route("/administracao/condominio/cadastros", methods=["GET", "POST"])
@login_required
def admin_condominium_registry():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))
    if request.method == "POST":
        try:
            _create_condominium_owner_from_request()
            db.session.commit()
            flash("Cadastro mestre salvo e unidade marcada como ocupada.", "success")
            return redirect(url_for("pages.admin_condominium_registry"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("pages.admin_condominium_registry"))
    return render_template(
        "condominium_owners.html",
        units=_condominium_unit_options(),
        owners=_condominium_owner_rows(),
        mask_sensitive_document=_mask_sensitive_document,
    )


@blueprint.route("/administracao/condominio/editor-blocos", methods=["GET", "POST"])
@login_required
def admin_condominium_blocks_editor():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))
    if not _is_registered_admin():
        flash("Somente administrador cadastrado no sistema pode editar os cards dos edifícios.", "danger")
        return redirect(url_for("pages.administration_dashboard"))

    edit_id = request.args.get("editar", type=int)
    model_number = request.args.get("modelo", type=int)
    edit_building = CondominiumBuilding.query.get(edit_id) if edit_id else None
    template_block = _default_admin_block(model_number) if not edit_building else None

    if request.method == "POST":
        building_id = request.form.get("building_id", type=int)
        building = CondominiumBuilding.query.get(building_id) if building_id else CondominiumBuilding()
        if building is None:
            flash("Bloco nao encontrado.", "danger")
            return redirect(url_for("pages.admin_condominium_blocks_editor"))

        try:
            code = str(request.form.get("code") or "").strip()
            name = str(request.form.get("name") or "").strip()
            display_order = _form_int("display_order", default=0, minimum=0, maximum=999)
            if not name:
                raise ValueError("Informe o nome do edifício.")
            if not code:
                code = f"B{display_order:02d}" if display_order else name[:12].upper()
            duplicate = CondominiumBuilding.query.filter(CondominiumBuilding.code == code).first()
            if duplicate and duplicate.id != building.id:
                raise ValueError("Já existe um edifício com esse código.")

            building.code = code
            building.name = name
            building.display_order = display_order
            building.floor_start = _form_int("floor_start", default=1, minimum=-10, maximum=300)
            building.floor_count = _form_int("floor_count", default=1, minimum=1, maximum=300)
            building.units_per_floor = _form_int("units_per_floor", default=0, minimum=0, maximum=300)
            building.unit_suffix_start = _form_int("unit_suffix_start", default=0, minimum=0, maximum=9999)
            building.suffix_width = _form_int("suffix_width", default=2, minimum=1, maximum=4)
            building.numbering_mode = "floor_suffix"
            building.custom_units_text = str(request.form.get("custom_units_text") or "").strip() or None
            building.notes = str(request.form.get("notes") or "").strip() or None
            building.active = bool(request.form.get("active"))
            building.updated_by_matricula = _current_user_matricula()
            if not building.id:
                building.created_by_matricula = _current_user_matricula()
                db.session.add(building)

            layout = generate_unit_layout(
                floor_start=building.floor_start,
                floor_count=building.floor_count,
                units_per_floor=building.units_per_floor,
                unit_suffix_start=building.unit_suffix_start,
                suffix_width=building.suffix_width,
                custom_units_text=building.custom_units_text or "",
            )
            sync_building_units(building, layout, default_status=request.form.get("initial_status") or "vago")
            db.session.commit()
            flash("Editor de edifícios atualizado.", "success")
            return redirect(url_for("pages.admin_condominium_blocks_editor"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("pages.admin_condominium_blocks_editor", editar=building_id) if building_id else url_for("pages.admin_condominium_blocks_editor"))

    return render_template(
        "condominium_blocks_editor.html",
        building_form=_building_form(edit_building) if not template_block else _building_form_from_default(template_block),
        building_summaries=_building_summaries(),
        edit_building=edit_building,
    )


@blueprint.post("/administracao/condominio/editor-blocos/<int:building_id>/arquivar")
@login_required
def admin_condominium_archive_building(building_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if not _is_registered_admin():
        flash("Somente administrador cadastrado no sistema pode editar os cards dos edifícios.", "danger")
        return redirect(url_for("pages.administration_dashboard"))
    building = CondominiumBuilding.query.get_or_404(building_id)
    building.active = False
    building.updated_by_matricula = _current_user_matricula()
    for unit in building.units:
        unit.active = False
    db.session.commit()
    flash("Edifício arquivado. Ele saiu do dashboard e da lista de unidades ativas.", "info")
    return redirect(url_for("pages.admin_condominium_blocks_editor"))


@blueprint.post("/administracao/condominio/editor-blocos/<int:building_id>/excluir")
@login_required
def admin_condominium_delete_building(building_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if not _is_registered_admin():
        flash("Somente administrador cadastrado no sistema pode editar os cards dos edifícios.", "danger")
        return redirect(url_for("pages.administration_dashboard"))

    building = CondominiumBuilding.query.get_or_404(building_id)
    actor_id = _current_user_matricula()
    unit_ids = [int(unit.id) for unit in building.units]

    if unit_ids:
        owners = CondominiumOwner.query.filter(CondominiumOwner.unit_id.in_(unit_ids)).all()
        for owner in owners:
            owner.unit_id = None
            owner.updated_by_matricula = actor_id

    related_events = CondominiumScheduleEvent.query.filter(CondominiumScheduleEvent.building_id == building.id).all()
    if unit_ids:
        seen_event_ids = {int(event.id) for event in related_events}
        unit_events = CondominiumScheduleEvent.query.filter(CondominiumScheduleEvent.unit_id.in_(unit_ids)).all()
        for event in unit_events:
            if int(event.id) not in seen_event_ids:
                related_events.append(event)
                seen_event_ids.add(int(event.id))

    for event in related_events:
        if event.building_id == building.id:
            event.building_id = None
        if event.unit_id in unit_ids:
            event.unit_id = None
        event.updated_by_matricula = actor_id

    db.session.delete(building)
    db.session.commit()
    flash("Edifício excluído com sucesso.", "info")
    return redirect(url_for("pages.admin_condominium_blocks_editor"))


@blueprint.route("/administracao/condominio/proprietarios", methods=["GET", "POST"])
@login_required
def admin_condominium_owners():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))

    if request.method == "POST":
        try:
            _create_condominium_owner_from_request()
            db.session.commit()
            flash("Cadastro mestre salvo e unidade marcada como ocupada.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return redirect(url_for("pages.admin_condominium_registry"))


@blueprint.post("/administracao/condominio/proprietarios/<int:owner_id>/encerrar")
@login_required
def admin_condominium_close_owner(owner_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    owner = CondominiumOwner.query.get_or_404(owner_id)
    owner.status = "encerrado"
    owner.updated_by_matricula = _current_user_matricula()
    if owner.unit:
        has_active_owner = CondominiumOwner.query.filter(
            CondominiumOwner.unit_id == owner.unit_id,
            CondominiumOwner.id != owner.id,
            CondominiumOwner.status == "ativo",
        ).first()
        if not has_active_owner:
            owner.unit.status = "vago"
    db.session.commit()
    flash("Vinculo encerrado.", "info")
    return redirect(url_for("pages.admin_condominium_registry"))


@blueprint.route("/administracao/condominio/agendamentos", methods=["GET", "POST"])
@login_required
def admin_condominium_schedule():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))

    if request.method == "POST":
        event_id = request.form.get("event_id", type=int)
        event = CondominiumScheduleEvent.query.get(event_id) if event_id else CondominiumScheduleEvent()
        if event is None:
            flash("Compromisso nao encontrado.", "danger")
            return redirect(url_for("pages.admin_condominium_schedule"))
        try:
            if not event.id:
                event.created_by_matricula = _current_user_matricula()
                db.session.add(event)
            _apply_schedule_event_form(event)
            db.session.commit()
            flash("Compromisso salvo na agenda.", "success")
            return redirect(url_for("pages.admin_condominium_schedule", data=event.event_date.isoformat(), mes=event.event_date.strftime("%Y-%m")))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("pages.admin_condominium_schedule", data=request.form.get("event_date") or today_local().isoformat(), editar=event_id or None))

    selected_date = _parse_iso_date(request.args.get("data"), default=today_local())
    month_date = _month_date_from_request(selected_date)
    edit_id = request.args.get("editar", type=int)
    edit_event = CondominiumScheduleEvent.query.get(edit_id) if edit_id else None
    return render_template(
        "condominium_schedule.html",
        calendar_page=build_calendar_context(month_date=month_date, selected_date=selected_date),
        form_options=_schedule_form_options(),
        event_form=_schedule_event_form(edit_event, selected_date=selected_date),
        edit_event=edit_event,
        agenda_notifications=due_schedule_notifications(),
    )


@blueprint.post("/administracao/condominio/agendamentos/<int:event_id>/status")
@login_required
def admin_condominium_schedule_status(event_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    event = CondominiumScheduleEvent.query.get_or_404(event_id)
    event.status = normalize_status(request.form.get("status"))
    event.updated_by_matricula = _current_user_matricula()
    db.session.commit()
    flash("Status do compromisso atualizado.", "success")
    return redirect(url_for("pages.admin_condominium_schedule", data=event.event_date.isoformat(), mes=event.event_date.strftime("%Y-%m")))


@blueprint.post("/administracao/condominio/agendamentos/<int:event_id>/notificacao")
@login_required
def admin_condominium_schedule_acknowledge(event_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    event = CondominiumScheduleEvent.query.get_or_404(event_id)
    event.notification_acknowledged_at = now_local_naive()
    event.updated_by_matricula = _current_user_matricula()
    db.session.commit()
    flash("Notificacao da agenda confirmada.", "info")
    return redirect(request.referrer or url_for("pages.admin_condominium_schedule", data=event.event_date.isoformat()))


@blueprint.get("/administracao/condominio/prestadores")
@login_required
def admin_service_providers():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))
    return render_template(
        "config_service_providers_blueprint.html",
        service_provider_page=_build_admin_service_providers_blueprint(),
    )


@blueprint.get("/configuracoes/condominio/cadastros")
@login_required
def legacy_admin_condominium_registry():
    return redirect(url_for("pages.admin_condominium_registry"))


@blueprint.get("/configuracoes/condominio/agendamentos")
@login_required
def legacy_admin_condominium_schedule():
    return redirect(url_for("pages.admin_condominium_schedule"))


@blueprint.get("/configuracoes/condominio/prestadores")
@login_required
def legacy_admin_service_providers():
    return redirect(url_for("pages.admin_service_providers"))


@blueprint.get("/configuracoes/backup")
@login_required
def config_backup():
    # Preencher flag de admin na sessão para compatibilidade com sessões existentes.
    # (Esse request ainda usa login_required e pode consultar DB; é antes da restauração começar.)
    _prime_admin_session()

    service = BackupService(current_app)
    backups = service.list_backups()
    diagnostic = service.diagnostic_report()
    return render_template("config_backup.html", backups=backups, diagnostic=diagnostic)


@blueprint.get("/configuracoes/backup/checklist-final")
@login_required
def backup_final_checklist():
    checklist_path = Path(current_app.root_path).parent / "CHECKLIST_FINAL_BACKUP_GALINT.md"
    if not checklist_path.exists():
        abort(404)
    return send_file(checklist_path, as_attachment=True, download_name=checklist_path.name)


@blueprint.get("/configuracoes/conversionengine")
@login_required
def config_conversionengine():
    _require_admin()
    _prime_admin_session()
    service = ConversionEngineService(current_app)
    doc_path = Path(current_app.root_path).parent / "CONVERSIONENGINE.md"
    content_html = _markdown_file_to_html(doc_path) if doc_path.exists() else ""
    return render_template(
        "config_conversionengine.html",
        dashboard=service.dashboard_payload(),
        content_html=content_html,
        initial_job_id=(request.args.get("job_id") or "").strip(),
    )


@blueprint.post("/configuracoes/backup")
@login_required
def create_backup():
    _require_admin()
    service = BackupService(current_app)
    backup_kind = (
        request.form.get("selected_backup_kind")
        or request.form.get("backup_kind")
        or BackupService.DATABASE_BACKUP_KIND
    ).strip().lower()
    try:
        backup_name = service.create_backup(backup_kind=backup_kind)
        flash(f"Backup criado: {backup_name}", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("pages.config_backup"))


@blueprint.post("/configuracoes/restaurar")
@login_required
def restore_backup():
    _require_admin()
    backup_name = request.form.get("backup_name")
    if not backup_name:
        flash("Selecione um backup para restaurar.", "warning")
        return redirect(url_for("pages.config_backup"))
    service = BackupService(current_app)
    try:
        restored = service.restore_backup(backup_name)
        flash(f"Backup restaurado: {restored}", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("pages.config_backup"))


@blueprint.post("/configuracoes/restaurar/iniciar")
def start_restore_backup():
    """Inicia restauração em background e retorna um job_id."""
    user_key, error = _require_admin_session_json()
    if error:
        return error
    backup_name = (request.form.get("backup_name") or "").strip()
    if not backup_name:
        return jsonify({"ok": False, "error": "Selecione um backup para restaurar."}), 400

    app = current_app._get_current_object()

    def _restore(reporter):
        service = BackupService(app)
        service.restore_backup_with_progress(backup_name, reporter)

    try:
        job_id = start_restore_job(
            app=app,
            backup_name=backup_name,
            user_key=user_key,
            restore_callable=_restore,
        )
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, "job_id": job_id})


@blueprint.get("/configuracoes/restaurar/status/<job_id>")
def restore_backup_status(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job não encontrado."}), 404
    return jsonify({"ok": True, "state": state})


@blueprint.post("/configuracoes/conversionengine/iniciar")
def conversionengine_start():
    user_key, error = _require_admin_session_json()
    if error:
        return error

    upload = request.files.get("source_dump")
    if upload is None:
        return jsonify({"ok": False, "error": "Envie um arquivo .sql, .zip, .sqlite ou .db para análise."}), 400

    try:
        service = ConversionEngineService(current_app)
        stored = service.store_upload(upload)
        job_id = start_conversion_job(
            app=current_app._get_current_object(),
            user_key=user_key,
            source_name=stored["source_name"],
            stored_name=stored["stored_name"],
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "job_id": job_id})


@blueprint.post("/configuracoes/conversionengine/analisar-backup")
@login_required
def conversionengine_start_from_backup():
    _require_admin()
    _prime_admin_session()

    selected_names = [str(name).strip() for name in request.form.getlist("backup_names") if str(name).strip()]
    backup_name = selected_names[0] if len(selected_names) == 1 else ""
    if not backup_name:
        flash("Selecione um backup para enviar ao ConversionEngine.", "warning")
        return redirect(url_for("pages.config_backup"))

    user_key = str(session.get("_user_id") or "").strip()
    if not user_key:
        flash("Sessão administrativa inválida para iniciar o ConversionEngine.", "danger")
        return redirect(url_for("pages.config_backup"))

    try:
        service = ConversionEngineService(current_app)
        stored = service.register_existing_backup(backup_name)
        job_id = start_conversion_job(
            app=current_app._get_current_object(),
            user_key=user_key,
            source_name=stored["source_name"],
            stored_name=stored["stored_name"],
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("pages.config_backup"))

    flash(f"Backup enviado ao ConversionEngine: {backup_name}", "success")
    return redirect(url_for("pages.config_conversionengine", job_id=job_id))


@blueprint.get("/configuracoes/conversionengine/status/<job_id>")
def conversionengine_status(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_conversion_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job do ConversionEngine não encontrado."}), 404
    return jsonify({"ok": True, "state": state})


@blueprint.get("/configuracoes/conversionengine/download/<job_id>")
def conversionengine_download_sql(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_conversion_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job do ConversionEngine não encontrado."}), 404
    sql_name = (((state.get("result") or {}).get("artifacts") or {}).get("converted_sql_name") or "").strip()
    if not sql_name:
        return jsonify({"ok": False, "error": "Nenhuma base convertida apta para download foi gerada."}), 409

    target = ConversionEngineService(current_app).outputs_dir / sql_name
    if not target.exists():
        return jsonify({"ok": False, "error": "Arquivo convertido não encontrado."}), 404
    return send_file(target, mimetype="application/sql", as_attachment=True, download_name=target.name)


@blueprint.get("/configuracoes/conversionengine/pacote/<job_id>")
def conversionengine_download_package(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_conversion_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job do ConversionEngine não encontrado."}), 404
    package_name = (((state.get("result") or {}).get("artifacts") or {}).get("package_name") or "").strip()
    if not package_name:
        return jsonify({"ok": False, "error": "Nenhum pacote técnico disponível para download."}), 409

    target = ConversionEngineService(current_app).outputs_dir / package_name
    if not target.exists():
        return jsonify({"ok": False, "error": "Pacote técnico não encontrado."}), 404
    return send_file(target, mimetype="application/zip", as_attachment=True, download_name=target.name)


@blueprint.post("/configuracoes/conversionengine/implantar/<job_id>")
def conversionengine_deploy(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_conversion_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job do ConversionEngine não encontrado."}), 404

    summary = ((state.get("result") or {}).get("summary") or {})
    artifacts = ((state.get("result") or {}).get("artifacts") or {})
    backup_name = (artifacts.get("deploy_backup_name") or "").strip()
    source_kind = str(summary.get("source_kind") or "")
    package_backup_kind = str(summary.get("package_backup_kind") or "")
    if not summary.get("deployable"):
        return jsonify({"ok": False, "error": "Esta conversão não foi liberada para implantação direta."}), 409

    app = current_app._get_current_object()
    conversion_service = ConversionEngineService(current_app)

    def _restore(reporter):
        service = BackupService(app)
        if source_kind == "zip_package" and package_backup_kind == BackupService.COMPLETE_BACKUP_KIND:
            source_path = conversion_service.sources_dir / str(state.get("stored_name") or "")
            service.restore_complete_package(source_path, reporter)
            return
        if not backup_name:
            raise ValueError("Nenhum artefato de restore foi gerado para esta conversão.")
        service.restore_backup_with_progress(backup_name, reporter)

    try:
        restore_job_id = start_restore_job(
            app=app,
            backup_name=backup_name,
            user_key=user_key,
            restore_callable=_restore,
        )
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409

    return jsonify({"ok": True, "restore_job_id": restore_job_id})


@blueprint.post("/configuracoes/backup/excluir")
@login_required
def delete_backup():
    _require_admin()
    backup_names = [str(name).strip() for name in request.form.getlist("backup_names") if str(name).strip()]
    if not backup_names:
        flash("Selecione ao menos um backup para apagar.", "warning")
        return redirect(url_for("pages.config_backup"))

    service = BackupService(current_app)
    removed_names: list[str] = []
    failed_messages: list[str] = []
    for backup_name in backup_names:
        try:
            removed_names.append(service.delete_backup(backup_name))
        except ValueError as exc:
            failed_messages.append(f"{backup_name}: {exc}")

    if removed_names:
        if len(removed_names) == 1:
            flash(f"Backup removido: {removed_names[0]}", "success")
        else:
            flash(f"{len(removed_names)} backups removidos com sucesso.", "success")

    for message in failed_messages:
        flash(message, "danger")

    return redirect(url_for("pages.config_backup"))


@blueprint.get("/configuracoes/rede")
@login_required
def config_rede():
    token = current_app.config.get("DASHBOARD_SHARE_TOKEN")
    share_url = None
    if token:
        share_url = url_for("dashboard.rede_galint", token=token, _external=True)

    settings = load_network_settings(current_app)
    return render_template(
        "config_rede.html",
        share_url=share_url,
        token_configured=bool(token),
        settings=settings,
    )


def _test_mobile_endpoint(url: str) -> tuple[bool, str]:
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=5) as response:
            body = response.read(1024).decode("utf-8", errors="replace")
            return True, f"OK (HTTP {response.status}). Resposta: {body}"
    except HTTPError as exc:
        try:
            body = exc.read(1024).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return False, f"Falhou (HTTP {exc.code}). {body}".strip()
    except URLError as exc:
        return False, f"Falhou (rede). {exc.reason}"
    except Exception as exc:
        return False, f"Falhou. {exc}"


@blueprint.post("/configuracoes/rede")
@login_required
def update_rede():
    _require_admin()

    base_url = (request.form.get("base_url") or "").strip()
    intent = (request.form.get("intent") or "save").strip().lower()

    try:
        settings = save_network_settings(
            current_app,
            base_url=base_url,
        )
        flash("Configurações de rede salvas.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("pages.config_rede"))

    if intent == "test":
        url = f"{settings.base_url()}/api/mobile/health"
        ok, message = _test_mobile_endpoint(url)
        flash(f"Teste de comunicação: {message}", "success" if ok else "danger")

    return redirect(url_for("pages.config_rede"))


@blueprint.get("/sobre")
@login_required
def sobre():
    kit_readme_path = Path(current_app.root_path).parent / "README_CENTRAL_KITS_FERRAMENTAS.md"
    kit_doc_html = _markdown_file_to_html(kit_readme_path) if kit_readme_path.exists() else ""
    try:
        about_category_reference = _build_about_category_reference()
    except Exception:
        current_app.logger.exception("Falha ao montar a referencia visual do Sobre; usando fallback reduzido.")
        about_category_reference = _build_about_category_reference_fallback()

    try:
        about_document_guide = _build_about_document_guide()
    except Exception:
        current_app.logger.exception("Falha ao montar o guia documental do Sobre; usando fallback reduzido.")
        about_document_guide = {
            "steps": list(_ABOUT_DOCUMENT_GUIDE_STEPS),
            "modes": list(_ABOUT_DOCUMENT_GUIDE_MODES),
            "rules": list(_ABOUT_DOCUMENT_GUIDE_RULES),
        }

    try:
        about_purchase_projection_guide = _build_about_purchase_projection_guide()
    except Exception:
        current_app.logger.exception("Falha ao montar o guia da Projecao de Compras no Sobre; usando fallback reduzido.")
        about_purchase_projection_guide = {
            "formulas": list(_ABOUT_PURCHASE_PROJECTION_FORMULAS),
            "filters": list(_ABOUT_PURCHASE_PROJECTION_FILTERS),
            "steps": list(_ABOUT_PURCHASE_PROJECTION_STEPS),
            "compatibility_cards": [],
        }

    return render_template(
        "sobre.html",
        kit_doc_html=kit_doc_html,
        about_category_reference=about_category_reference,
        about_document_guide=about_document_guide,
        about_purchase_projection_guide=about_purchase_projection_guide,
        category_visual_catalog=about_category_reference.get("catalog") or [],
    )


@blueprint.get("/documentacao")
@login_required
def documentacao():
    return render_template("documentacao.html")


@blueprint.get("/documentacao/percentual-movimentos")
@login_required
def documentacao_percentual_movimentos():
    readme_path = Path(current_app.root_path).parent / "README_PERCENTUAL_MOVIMENTOS.md"
    if not readme_path.exists():
        abort(404)
    content_html = _markdown_file_to_html(readme_path)
    return render_template(
        "documentacao_percentual_movimentos.html",
        content_html=content_html,
    )


@blueprint.get("/documentacao/central-kits")
@login_required
def documentacao_central_kits():
    readme_path = Path(current_app.root_path).parent / "README_CENTRAL_KITS_FERRAMENTAS.md"
    if not readme_path.exists():
        abort(404)
    content_html = _markdown_file_to_html(readme_path)
    return render_template(
        "documentacao_central_kits.html",
        content_html=content_html,
    )
