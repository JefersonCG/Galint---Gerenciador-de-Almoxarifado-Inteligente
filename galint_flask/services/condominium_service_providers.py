"""Service layer for condominium service provider registrations."""
from __future__ import annotations

from datetime import date
import re
from typing import Any, Mapping

from sqlalchemy import or_
from sqlalchemy.orm import selectinload


from ..extensions import db
from ..models import ServiceCompany, ServiceProviderEmployee


SERVICE_TYPE_OPTIONS: tuple[dict[str, str], ...] = (
    {"value": "limpeza", "label": "Limpeza"},
    {"value": "eletrica", "label": "Elétrica"},
    {"value": "hidraulica", "label": "Hidráulica"},
    {"value": "pintura", "label": "Pintura"},
    {"value": "dedetizacao", "label": "Dedetização"},
    {"value": "seguranca", "label": "Segurança"},
    {"value": "jardinagem", "label": "Jardinagem"},
    {"value": "piscina", "label": "Piscina"},
    {"value": "elevador", "label": "Elevador"},
    {"value": "ti", "label": "TI"},
    {"value": "obras", "label": "Obras"},
    {"value": "outros", "label": "Outros"},
)

COMPANY_STATUS_OPTIONS: tuple[dict[str, str], ...] = (
    {"value": "ativo", "label": "Ativo"},
    {"value": "inativo", "label": "Inativo"},
    {"value": "suspenso", "label": "Suspenso"},
)

EMPLOYEE_STATUS_OPTIONS: tuple[dict[str, str], ...] = (
    {"value": "ativo", "label": "Ativo"},
    {"value": "bloqueado", "label": "Bloqueado"},
    {"value": "inativo", "label": "Inativo"},
)

WEEKDAY_OPTIONS: tuple[dict[str, str], ...] = (
    {"value": "seg", "label": "Seg"},
    {"value": "ter", "label": "Ter"},
    {"value": "qua", "label": "Qua"},
    {"value": "qui", "label": "Qui"},
    {"value": "sex", "label": "Sex"},
    {"value": "sab", "label": "Sáb"},
    {"value": "dom", "label": "Dom"},
)

_SERVICE_LABELS = {option["value"]: option["label"] for option in SERVICE_TYPE_OPTIONS}
_COMPANY_STATUS_VALUES = {option["value"] for option in COMPANY_STATUS_OPTIONS}
_EMPLOYEE_STATUS_VALUES = {option["value"] for option in EMPLOYEE_STATUS_OPTIONS}
_WEEKDAY_LABELS = {option["value"]: option["label"] for option in WEEKDAY_OPTIONS}


def _clean_text(value: object, *, max_length: int | None = None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if max_length is not None:
        return text[:max_length]
    return text


def _digits(value: object) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _selected_values(form_data: Mapping[str, Any], field_name: str, allowed_values: set[str]) -> list[str]:
    if hasattr(form_data, "getlist"):
        raw_values = form_data.getlist(field_name)  # type: ignore[attr-defined]
    else:
        value = form_data.get(field_name)
        raw_values = value if isinstance(value, list) else [value]
    selected: list[str] = []
    for raw_value in raw_values:
        value = str(raw_value or "").strip().lower()
        if value in allowed_values and value not in selected:
            selected.append(value)
    return selected


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("Informe datas do contrato em formato válido.") from exc


def _parse_money(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        parsed = float(normalized)
    except ValueError as exc:
        raise ValueError("Informe o valor mensal do contrato em formato válido.") from exc
    if parsed < 0:
        raise ValueError("O valor mensal do contrato não pode ser negativo.")
    return parsed


def mask_document(value: object) -> str:
    digits = _digits(value)
    if len(digits) == 14:
        return f"{digits[:2]}.***.***/{digits[8:12]}-{digits[12:]}"
    if len(digits) == 11:
        return f"{digits[:3]}.***.***-{digits[-2:]}"
    if len(digits) <= 4:
        return "Documento não informado" if not digits else "***"
    return f"{digits[:3]}***{digits[-2:]}"


def service_types_label(values: object) -> str:
    service_values = values if isinstance(values, list) else []
    labels = [_SERVICE_LABELS.get(str(value), str(value)) for value in service_values]
    return ", ".join(labels) if labels else "Serviço não classificado"


def weekday_label(values: object) -> str:
    weekday_values = values if isinstance(values, list) else []
    labels = [_WEEKDAY_LABELS.get(str(value), str(value)) for value in weekday_values]
    return ", ".join(labels) if labels else "Sem recorrência definida"


def contract_status(company: ServiceCompany, *, today: date | None = None) -> dict[str, str]:
    current_date = today or date.today()
    if company.status != "ativo":
        return {"value": company.status, "label": "Inativo" if company.status == "inativo" else "Suspenso", "css": "muted"}
    if company.contract_end_date and company.contract_end_date < current_date:
        return {"value": "vencido", "label": "Contrato vencido", "css": "danger"}
    if company.contract_end_date and (company.contract_end_date - current_date).days <= 30:
        return {"value": "vencendo", "label": "Vencendo", "css": "warning"}
    return {"value": "ativo", "label": "Ativo", "css": "success"}


def service_company_form(company: ServiceCompany | None = None) -> dict[str, object]:
    return {
        "id": company.id if company else None,
        "corporate_name": company.corporate_name if company else "",
        "trade_name": company.trade_name if company else "",
        "cnpj": company.cnpj if company else "",
        "state_registration": company.state_registration if company else "",
        "municipal_registration": company.municipal_registration if company else "",
        "phone": company.phone if company else "",
        "whatsapp": company.whatsapp if company else "",
        "email": company.email if company else "",
        "address": company.address if company else "",
        "legal_representative_name": company.legal_representative_name if company else "",
        "legal_representative_cpf": company.legal_representative_cpf if company else "",
        "contract_start_date": company.contract_start_date.isoformat() if company and company.contract_start_date else "",
        "contract_end_date": company.contract_end_date.isoformat() if company and company.contract_end_date else "",
        "service_types": company.service_types_json or [] if company else [],
        "monthly_contract_value": company.monthly_contract_value if company and company.monthly_contract_value is not None else "",
        "status": company.status if company else "ativo",
        "notes": company.notes if company else "",
        "lgpd_authorized": bool(company.lgpd_authorized) if company else False,
    }


def service_employee_form(company_id: int | None = None) -> dict[str, object]:
    return {
        "company_id": company_id,
        "full_name": "",
        "cpf": "",
        "rg": "",
        "role": "",
        "phone": "",
        "vehicle_plate": "",
        "recurring_days": [],
        "usual_schedule": "",
        "status": "ativo",
        "notes": "",
        "lgpd_authorized": False,
    }


def save_service_company_from_form(
    form_data: Mapping[str, Any],
    *,
    actor_matricula: str | None,
    company: ServiceCompany | None = None,
) -> ServiceCompany:
    corporate_name = _clean_text(form_data.get("corporate_name"), max_length=180)
    cnpj = _digits(form_data.get("cnpj"))
    if not corporate_name:
        raise ValueError("Informe a razão social da empresa prestadora.")
    if len(cnpj) != 14:
        raise ValueError("Informe um CNPJ com 14 dígitos.")

    duplicate = ServiceCompany.query.filter(ServiceCompany.cnpj == cnpj).first()
    if duplicate and (company is None or duplicate.id != company.id):
        raise ValueError("Já existe uma empresa prestadora com esse CNPJ.")

    current_company = company or ServiceCompany(created_by_matricula=actor_matricula)
    current_company.corporate_name = corporate_name
    current_company.trade_name = _clean_text(form_data.get("trade_name"), max_length=180)
    current_company.cnpj = cnpj
    current_company.state_registration = _clean_text(form_data.get("state_registration"), max_length=40)
    current_company.municipal_registration = _clean_text(form_data.get("municipal_registration"), max_length=40)
    current_company.phone = _clean_text(form_data.get("phone"), max_length=40)
    current_company.whatsapp = _clean_text(form_data.get("whatsapp"), max_length=40)
    current_company.email = _clean_text(form_data.get("email"), max_length=160)
    current_company.address = _clean_text(form_data.get("address"))
    current_company.legal_representative_name = _clean_text(form_data.get("legal_representative_name"), max_length=180)
    current_company.legal_representative_cpf = _digits(form_data.get("legal_representative_cpf")) or None
    current_company.contract_start_date = _parse_date(form_data.get("contract_start_date"))
    current_company.contract_end_date = _parse_date(form_data.get("contract_end_date"))
    current_company.service_types_json = _selected_values(form_data, "service_types", set(_SERVICE_LABELS)) or None
    current_company.monthly_contract_value = _parse_money(form_data.get("monthly_contract_value"))
    current_company.status = str(form_data.get("status") or "ativo").strip().lower()
    if current_company.status not in _COMPANY_STATUS_VALUES:
        current_company.status = "ativo"
    current_company.notes = _clean_text(form_data.get("notes"))
    current_company.lgpd_authorized = bool(form_data.get("lgpd_authorized"))
    current_company.updated_by_matricula = actor_matricula
    if current_company.id is None:
        db.session.add(current_company)
    return current_company


def save_service_provider_employee_from_form(
    form_data: Mapping[str, Any],
    *,
    actor_matricula: str | None,
) -> ServiceProviderEmployee:
    company_id = int(form_data.get("company_id") or 0)
    company = ServiceCompany.query.get(company_id) if company_id else None
    if company is None:
        raise ValueError("Selecione uma empresa prestadora para vincular o funcionário.")
    if company.status != "ativo":
        raise ValueError("Não é possível vincular funcionário a uma empresa inativa ou suspensa.")

    full_name = _clean_text(form_data.get("employee_full_name"), max_length=180)
    cpf = _digits(form_data.get("employee_cpf"))
    if not full_name:
        raise ValueError("Informe o nome completo do funcionário/prestador.")
    if len(cpf) != 11:
        raise ValueError("Informe um CPF com 11 dígitos para o funcionário/prestador.")

    duplicate = ServiceProviderEmployee.query.filter(ServiceProviderEmployee.cpf == cpf).first()
    if duplicate:
        raise ValueError("Já existe funcionário/prestador cadastrado com esse CPF.")

    employee = ServiceProviderEmployee(
        company=company,
        full_name=full_name,
        cpf=cpf,
        rg=_clean_text(form_data.get("employee_rg"), max_length=32),
        role=_clean_text(form_data.get("employee_role"), max_length=120),
        phone=_clean_text(form_data.get("employee_phone"), max_length=40),
        vehicle_plate=_clean_text(form_data.get("employee_vehicle_plate"), max_length=16),
        recurring_days_json=_selected_values(form_data, "employee_recurring_days", set(_WEEKDAY_LABELS)) or None,
        usual_schedule=_clean_text(form_data.get("employee_usual_schedule"), max_length=80),
        status=str(form_data.get("employee_status") or "ativo").strip().lower(),
        notes=_clean_text(form_data.get("employee_notes")),
        lgpd_authorized=bool(form_data.get("employee_lgpd_authorized")),
        created_by_matricula=actor_matricula,
        updated_by_matricula=actor_matricula,
    )
    if employee.status not in _EMPLOYEE_STATUS_VALUES:
        employee.status = "ativo"
    db.session.add(employee)
    return employee


def service_company_rows(*, search: str = "", status: str = "", service_type: str = "") -> list[dict[str, object]]:
    query = ServiceCompany.query.options(selectinload(ServiceCompany.employees))
    normalized_search = search.strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        digit_pattern = f"%{_digits(normalized_search)}%" if _digits(normalized_search) else pattern
        query = query.filter(
            or_(
                ServiceCompany.corporate_name.ilike(pattern),
                ServiceCompany.trade_name.ilike(pattern),
                ServiceCompany.cnpj.ilike(digit_pattern),
                ServiceCompany.legal_representative_name.ilike(pattern),
            )
        )

    companies = query.order_by(ServiceCompany.status.asc(), ServiceCompany.corporate_name.asc()).all()
    rows: list[dict[str, object]] = []
    for company in companies:
        status_payload = contract_status(company)
        company_services = company.service_types_json or []
        if status and status_payload["value"] != status:
            continue
        if service_type and service_type not in company_services:
            continue
        rows.append(
            {
                "company": company,
                "contract_status": status_payload,
                "services_label": service_types_label(company_services),
                "worker_count": len(company.employees),
                "active_worker_count": sum(1 for employee in company.employees if employee.status == "ativo"),
                "cnpj_masked": mask_document(company.cnpj),
            }
        )
    return rows


def service_employee_rows(company_id: int | None = None) -> list[dict[str, object]]:
    query = ServiceProviderEmployee.query.options(selectinload(ServiceProviderEmployee.company))
    if company_id:
        query = query.filter(ServiceProviderEmployee.company_id == company_id)
    employees = query.order_by(ServiceProviderEmployee.status.asc(), ServiceProviderEmployee.full_name.asc()).all()
    return [
        {
            "employee": employee,
            "cpf_masked": mask_document(employee.cpf),
            "days_label": weekday_label(employee.recurring_days_json),
            "company_name": employee.company.display_name() if employee.company else "Empresa não vinculada",
        }
        for employee in employees
    ]