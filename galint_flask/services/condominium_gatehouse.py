from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import or_

from ..extensions import db
from ..models import CondominiumAccessLog, CondominiumOwner, CondominiumUnit, ServiceCompany, ServiceProviderEmployee
from .condominium_dossier import search_condominium_units
from .condominium_schedule import today_local
from .condominium_service_providers import contract_status, service_company_document_summary


DIRECTION_OPTIONS = (
    {"value": "entrada", "label": "Entrada"},
    {"value": "saida", "label": "Saida"},
)

ACCESS_STATUS_OPTIONS = (
    {"value": "liberado", "label": "Liberado"},
    {"value": "bloqueado", "label": "Bloqueado"},
    {"value": "observacao", "label": "Liberado com observacao"},
)

PERSON_TYPE_OPTIONS = (
    {"value": "morador", "label": "Morador"},
    {"value": "prestador", "label": "Prestador"},
    {"value": "visitante", "label": "Visitante"},
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize_choice(value: object, allowed: set[str], *, default: str) -> str:
    normalized = _clean(value).lower()
    return normalized if normalized in allowed else default


def _provider_rows(query: str, *, limit: int = 12) -> list[dict[str, object]]:
    normalized = _clean(query)
    providers_query = ServiceProviderEmployee.query.join(ServiceProviderEmployee.company)
    if normalized:
        like = f"%{normalized}%"
        providers_query = providers_query.filter(
            or_(
                ServiceProviderEmployee.full_name.ilike(like),
                ServiceProviderEmployee.cpf.ilike(like),
                ServiceProviderEmployee.rg.ilike(like),
                ServiceProviderEmployee.vehicle_plate.ilike(like),
                ServiceCompany.corporate_name.ilike(like),
                ServiceCompany.trade_name.ilike(like),
                ServiceCompany.cnpj.ilike(like),
            )
        )
    providers = providers_query.order_by(ServiceProviderEmployee.status.asc(), ServiceProviderEmployee.full_name.asc()).limit(limit).all()
    rows: list[dict[str, object]] = []
    for employee in providers:
        company = employee.company
        document_summary = service_company_document_summary(company) if company else {"value": "pendente", "label": "Sem empresa", "css": "secondary"}
        policy = provider_access_policy(employee)
        rows.append(
            {
                "kind": "prestador",
                "employee": employee,
                "company": company,
                "title": employee.full_name,
                "subtitle": company.display_name() if company else "Empresa nao vinculada",
                "status": employee.status,
                "document_summary": document_summary,
                "policy": policy,
            }
        )
    return rows


def provider_access_policy(employee: ServiceProviderEmployee | None) -> dict[str, object]:
    if employee is None:
        return {"allowed": False, "status": "bloqueado", "reason": "Prestador não encontrado."}
    company = employee.company
    if employee.status != "ativo":
        return {"allowed": False, "status": "bloqueado", "reason": "Prestador não está ativo."}
    if company is None:
        return {"allowed": False, "status": "bloqueado", "reason": "Prestador sem empresa vinculada."}
    if company.status != "ativo":
        return {"allowed": False, "status": "bloqueado", "reason": "Empresa prestadora não está ativa."}
    current_contract = contract_status(company)
    if current_contract["value"] == "vencido":
        return {"allowed": False, "status": "bloqueado", "reason": "Contrato da empresa está vencido."}
    current_documents = service_company_document_summary(company)
    if current_documents["value"] == "vencido":
        return {"allowed": False, "status": "bloqueado", "reason": "Empresa possui documento vencido."}
    if current_contract["value"] == "vencendo" or current_documents["value"] == "vencendo":
        return {"allowed": True, "status": "observacao", "reason": "Atenção: contrato ou documento próximo do vencimento."}
    return {"allowed": True, "status": "liberado", "reason": "Prestador liberado."}


def gatehouse_search_results(*, query: str = "", status: str = "") -> dict[str, object]:
    unit_rows = search_condominium_units(query=query, status=status, limit=20)
    provider_rows = _provider_rows(query, limit=12)
    return {"units": unit_rows, "providers": provider_rows, "total": len(unit_rows) + len(provider_rows)}


def recent_access_logs(*, limit: int = 30) -> list[CondominiumAccessLog]:
    return CondominiumAccessLog.query.order_by(CondominiumAccessLog.occurred_at.desc(), CondominiumAccessLog.id.desc()).limit(limit).all()


def gatehouse_today_summary() -> dict[str, int]:
    today = today_local()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)
    rows = CondominiumAccessLog.query.filter(CondominiumAccessLog.occurred_at >= start, CondominiumAccessLog.occurred_at <= end).all()
    return {
        "entries": sum(1 for row in rows if row.direction == "entrada"),
        "exits": sum(1 for row in rows if row.direction == "saida"),
        "blocked": sum(1 for row in rows if row.access_status == "bloqueado"),
        "total": len(rows),
    }


def _owner_from_form(owner_id: int | None) -> CondominiumOwner | None:
    return CondominiumOwner.query.get(owner_id) if owner_id else None


def _unit_from_form(unit_id: int | None) -> CondominiumUnit | None:
    return CondominiumUnit.query.get(unit_id) if unit_id else None


def _provider_from_form(employee_id: int | None) -> ServiceProviderEmployee | None:
    return ServiceProviderEmployee.query.get(employee_id) if employee_id else None


def save_gatehouse_access_from_form(form_data, *, actor_matricula: str | None = None) -> CondominiumAccessLog:
    direction = _normalize_choice(form_data.get("direction"), {"entrada", "saida"}, default="entrada")
    access_status = _normalize_choice(form_data.get("access_status"), {"liberado", "bloqueado", "observacao"}, default="liberado")
    person_type = _normalize_choice(form_data.get("person_type"), {"morador", "prestador", "visitante"}, default="visitante")

    unit = _unit_from_form(form_data.get("unit_id", type=int))
    owner = _owner_from_form(form_data.get("owner_id", type=int))
    provider = _provider_from_form(form_data.get("service_employee_id", type=int))

    person_name = _clean(form_data.get("person_name"))
    document_number = _clean(form_data.get("document_number")) or None
    vehicle_plate = _clean(form_data.get("vehicle_plate")).upper() or None

    if owner:
        person_type = "morador"
        person_name = person_name or owner.full_name
        document_number = document_number or owner.document_number
        unit = unit or owner.unit
    if provider:
        person_type = "prestador"
        person_name = person_name or provider.full_name
        document_number = document_number or provider.cpf
        vehicle_plate = vehicle_plate or provider.vehicle_plate
        policy = provider_access_policy(provider)
        if not policy["allowed"]:
            access_status = "bloqueado"
        elif access_status == "liberado" and policy["status"] == "observacao":
            access_status = "observacao"
        policy_reason = str(policy.get("reason") or "")
        if policy_reason and policy_reason not in _clean(form_data.get("notes")):
            base_notes = _clean(form_data.get("notes"))
            form_notes = f"{base_notes} | {policy_reason}" if base_notes else policy_reason
        else:
            form_notes = _clean(form_data.get("notes"))
    else:
        form_notes = _clean(form_data.get("notes"))

    if not person_name:
        raise ValueError("Informe o nome da pessoa liberada na portaria.")
    if person_type == "morador" and unit is None:
        raise ValueError("Selecione a unidade do morador ou visitante.")
    if access_status == "bloqueado" and not form_notes:
        raise ValueError("Informe uma observacao para acesso bloqueado.")

    log = CondominiumAccessLog(
        direction=direction,
        access_status=access_status,
        person_type=person_type,
        person_name=person_name,
        document_number=document_number,
        vehicle_plate=vehicle_plate,
        purpose=_clean(form_data.get("purpose")) or None,
        notes=form_notes or None,
        unit=unit,
        owner=owner,
        service_company=provider.company if provider else None,
        service_employee=provider,
        authorized_by_matricula=actor_matricula,
    )
    db.session.add(log)
    return log


def build_gatehouse_context(*, query: str = "", status: str = "") -> dict[str, object]:
    return {
        "filters": {"q": _clean(query), "status": _clean(status)},
        "results": gatehouse_search_results(query=query, status=status),
        "recent_logs": recent_access_logs(),
        "summary": gatehouse_today_summary(),
        "direction_options": DIRECTION_OPTIONS,
        "access_status_options": ACCESS_STATUS_OPTIONS,
        "person_type_options": PERSON_TYPE_OPTIONS,
    }