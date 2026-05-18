from __future__ import annotations

from datetime import date, datetime

from ..extensions import db
from ..models import (
    CondominiumMaintenanceTicket,
    CondominiumOwner,
    CondominiumPackageLog,
    CondominiumUnit,
    ServiceCompany,
    ServiceProviderEmployee,
)


TICKET_STATUS_OPTIONS = (
    {"value": "aberto", "label": "Aberto"},
    {"value": "em_andamento", "label": "Em andamento"},
    {"value": "aguardando", "label": "Aguardando peça/prestador"},
    {"value": "concluido", "label": "Concluído"},
    {"value": "cancelado", "label": "Cancelado"},
)

TICKET_PRIORITY_OPTIONS = (
    {"value": "baixa", "label": "Baixa"},
    {"value": "normal", "label": "Normal"},
    {"value": "alta", "label": "Alta"},
    {"value": "critica", "label": "Crítica"},
)

TICKET_CATEGORY_OPTIONS = (
    {"value": "manutencao", "label": "Manutenção"},
    {"value": "hidraulica", "label": "Hidráulica"},
    {"value": "eletrica", "label": "Elétrica"},
    {"value": "limpeza", "label": "Limpeza"},
    {"value": "seguranca", "label": "Segurança"},
    {"value": "outros", "label": "Outros"},
)

PACKAGE_STATUS_OPTIONS = (
    {"value": "recebido", "label": "Recebido"},
    {"value": "notificado", "label": "Notificado"},
    {"value": "retirado", "label": "Retirado"},
    {"value": "devolvido", "label": "Devolvido"},
)

PACKAGE_TYPE_OPTIONS = (
    {"value": "encomenda", "label": "Encomenda"},
    {"value": "correspondencia", "label": "Correspondência"},
    {"value": "documento", "label": "Documento"},
    {"value": "volume", "label": "Volume"},
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize(value: object, allowed: set[str], *, default: str) -> str:
    normalized = _clean(value).lower()
    return normalized if normalized in allowed else default


def _parse_date(value: object) -> date | None:
    raw_value = _clean(value)
    if not raw_value:
        return None
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError("Informe uma data válida.") from exc


def unit_options() -> list[CondominiumUnit]:
    return CondominiumUnit.query.order_by(CondominiumUnit.number.asc()).all()


def owner_options() -> list[CondominiumOwner]:
    return CondominiumOwner.query.filter_by(status="ativo").order_by(CondominiumOwner.full_name.asc()).all()


def company_options() -> list[ServiceCompany]:
    return ServiceCompany.query.order_by(ServiceCompany.trade_name.asc(), ServiceCompany.corporate_name.asc()).all()


def provider_options() -> list[ServiceProviderEmployee]:
    return ServiceProviderEmployee.query.order_by(ServiceProviderEmployee.full_name.asc()).all()


def maintenance_ticket_rows(*, limit: int = 60) -> list[CondominiumMaintenanceTicket]:
    return (
        CondominiumMaintenanceTicket.query
        .order_by(CondominiumMaintenanceTicket.status.asc(), CondominiumMaintenanceTicket.priority.desc(), CondominiumMaintenanceTicket.opened_at.desc())
        .limit(limit)
        .all()
    )


def package_rows(*, limit: int = 60) -> list[CondominiumPackageLog]:
    return CondominiumPackageLog.query.order_by(CondominiumPackageLog.received_at.desc(), CondominiumPackageLog.id.desc()).limit(limit).all()


def operations_summary() -> dict[str, int]:
    tickets = maintenance_ticket_rows(limit=500)
    packages = package_rows(limit=500)
    return {
        "open_tickets": sum(1 for ticket in tickets if ticket.status in {"aberto", "em_andamento", "aguardando"}),
        "critical_tickets": sum(1 for ticket in tickets if ticket.priority == "critica" and ticket.status not in {"concluido", "cancelado"}),
        "pending_packages": sum(1 for package in packages if package.status in {"recebido", "notificado"}),
        "received_packages": sum(1 for package in packages if package.status == "recebido"),
    }


def save_maintenance_ticket_from_form(form_data, *, actor_matricula: str | None = None) -> CondominiumMaintenanceTicket:
    title = _clean(form_data.get("title"))
    if not title:
        raise ValueError("Informe o título do chamado.")

    unit = CondominiumUnit.query.get(form_data.get("unit_id", type=int)) if form_data.get("unit_id", type=int) else None
    owner = CondominiumOwner.query.get(form_data.get("owner_id", type=int)) if form_data.get("owner_id", type=int) else None
    company = ServiceCompany.query.get(form_data.get("service_company_id", type=int)) if form_data.get("service_company_id", type=int) else None
    provider = ServiceProviderEmployee.query.get(form_data.get("service_employee_id", type=int)) if form_data.get("service_employee_id", type=int) else None
    if owner and unit is None:
        unit = owner.unit
    if provider and company is None:
        company = provider.company

    ticket = CondominiumMaintenanceTicket(
        title=title,
        description=_clean(form_data.get("description")) or None,
        category=_normalize(form_data.get("category"), {option["value"] for option in TICKET_CATEGORY_OPTIONS}, default="manutencao"),
        priority=_normalize(form_data.get("priority"), {option["value"] for option in TICKET_PRIORITY_OPTIONS}, default="normal"),
        status=_normalize(form_data.get("status"), {option["value"] for option in TICKET_STATUS_OPTIONS}, default="aberto"),
        due_date=_parse_date(form_data.get("due_date")),
        unit=unit,
        building=unit.building if unit else None,
        owner=owner,
        service_company=company,
        service_employee=provider,
        notes=_clean(form_data.get("notes")) or None,
        created_by_matricula=actor_matricula,
        updated_by_matricula=actor_matricula,
    )
    if ticket.status in {"concluido", "cancelado"}:
        ticket.closed_at = datetime.utcnow()
    db.session.add(ticket)
    return ticket


def save_package_from_form(form_data, *, actor_matricula: str | None = None) -> CondominiumPackageLog:
    unit = CondominiumUnit.query.get(form_data.get("unit_id", type=int)) if form_data.get("unit_id", type=int) else None
    owner = CondominiumOwner.query.get(form_data.get("owner_id", type=int)) if form_data.get("owner_id", type=int) else None
    if owner and unit is None:
        unit = owner.unit

    recipient_name = _clean(form_data.get("recipient_name")) or (owner.full_name if owner else "")
    if not recipient_name:
        raise ValueError("Informe o destinatário da encomenda/correspondência.")
    if unit is None:
        raise ValueError("Selecione a unidade vinculada ao recebimento.")

    package = CondominiumPackageLog(
        recipient_name=recipient_name,
        tracking_code=_clean(form_data.get("tracking_code")) or None,
        carrier=_clean(form_data.get("carrier")) or None,
        package_type=_normalize(form_data.get("package_type"), {option["value"] for option in PACKAGE_TYPE_OPTIONS}, default="encomenda"),
        status=_normalize(form_data.get("status"), {option["value"] for option in PACKAGE_STATUS_OPTIONS}, default="recebido"),
        unit=unit,
        owner=owner,
        notes=_clean(form_data.get("notes")) or None,
        created_by_matricula=actor_matricula,
    )
    if package.status in {"retirado", "devolvido"}:
        package.delivered_at = datetime.utcnow()
        package.delivered_by_matricula = actor_matricula
    db.session.add(package)
    return package


def update_package_status(package_id: int, status: str, *, actor_matricula: str | None = None) -> CondominiumPackageLog:
    package = CondominiumPackageLog.query.get(package_id)
    if package is None:
        raise ValueError("Recebimento não encontrado.")
    package.status = _normalize(status, {option["value"] for option in PACKAGE_STATUS_OPTIONS}, default=package.status)
    if package.status in {"retirado", "devolvido"} and package.delivered_at is None:
        package.delivered_at = datetime.utcnow()
        package.delivered_by_matricula = actor_matricula
    return package


def build_operations_context() -> dict[str, object]:
    return {
        "summary": operations_summary(),
        "tickets": maintenance_ticket_rows(),
        "packages": package_rows(),
        "units": unit_options(),
        "owners": owner_options(),
        "companies": company_options(),
        "providers": provider_options(),
        "ticket_status_options": TICKET_STATUS_OPTIONS,
        "ticket_priority_options": TICKET_PRIORITY_OPTIONS,
        "ticket_category_options": TICKET_CATEGORY_OPTIONS,
        "package_status_options": PACKAGE_STATUS_OPTIONS,
        "package_type_options": PACKAGE_TYPE_OPTIONS,
    }