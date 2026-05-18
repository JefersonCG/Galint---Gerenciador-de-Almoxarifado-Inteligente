"""Service layer for condominium service provider registrations."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
from typing import Any, Mapping

from flask import current_app
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from werkzeug.utils import secure_filename

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

DOCUMENT_TYPE_OPTIONS: tuple[dict[str, str], ...] = (
    {"value": "contract", "label": "Contrato", "description": "Contrato principal, aditivos e termo comercial."},
    {"value": "art", "label": "ART", "description": "ART, RRT ou responsabilidade técnica equivalente."},
    {"value": "insurance", "label": "Seguro", "description": "Seguro de responsabilidade civil e coberturas operacionais."},
    {"value": "certificates", "label": "Certificados", "description": "Certificados, licenças e documentos operacionais."},
)

DOCUMENT_WARNING_DAYS = 30
ALLOWED_PROVIDER_DOCUMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
_PROVIDER_DOCUMENT_PREFIX = Path("uploads") / "condominio" / "prestadores"
_SERVICE_LABELS = {option["value"]: option["label"] for option in SERVICE_TYPE_OPTIONS}
_COMPANY_STATUS_VALUES = {option["value"] for option in COMPANY_STATUS_OPTIONS}
_EMPLOYEE_STATUS_VALUES = {option["value"] for option in EMPLOYEE_STATUS_OPTIONS}
_WEEKDAY_LABELS = {option["value"]: option["label"] for option in WEEKDAY_OPTIONS}
_DOCUMENT_TYPE_MAP = {option["value"]: option for option in DOCUMENT_TYPE_OPTIONS}


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


def _parse_date(value: object, *, error_message: str = "Informe datas do contrato em formato válido.") -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(error_message) from exc


def _safe_parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _format_date(value: object) -> str:
    parsed = value if isinstance(value, date) else _safe_parse_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else "Sem vencimento"


def _format_datetime(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    return parsed.strftime("%d/%m/%Y %H:%M")


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


def _provider_static_root() -> Path:
    return Path(current_app.static_folder or (Path(current_app.root_path) / "static"))


def _document_storage_path(relative_path: str) -> Path | None:
    normalized = Path(str(relative_path or "").replace("\\", "/"))
    if normalized.is_absolute():
        return None
    normalized_text = normalized.as_posix()
    expected_prefix = _PROVIDER_DOCUMENT_PREFIX.as_posix() + "/"
    if not normalized_text.startswith(expected_prefix):
        return None
    static_root = _provider_static_root().resolve()
    candidate = (static_root / normalized).resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        return None
    return candidate


def _delete_provider_document(relative_path: str | None) -> None:
    if not relative_path:
        return
    target = _document_storage_path(relative_path)
    if target and target.exists():
        target.unlink()


def _validate_provider_document_uploads(files: Mapping[str, Any] | None) -> None:
    if not files:
        return
    allowed = ", ".join(sorted(ALLOWED_PROVIDER_DOCUMENT_EXTENSIONS))
    for option in DOCUMENT_TYPE_OPTIONS:
        upload = files.get(f"document_{option['value']}_file")
        filename = str(getattr(upload, "filename", "") or "").strip()
        if not filename:
            continue
        extension = Path(secure_filename(filename)).suffix.lower()
        if extension not in ALLOWED_PROVIDER_DOCUMENT_EXTENSIONS:
            raise ValueError(f"Arquivo de {option['label']} inválido. Use: {allowed}.")


def _store_provider_document(file: Any, company_id: int, document_key: str) -> dict[str, str]:
    filename = secure_filename(str(getattr(file, "filename", "") or "").strip())
    if not filename:
        raise ValueError("Selecione um documento válido para upload.")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_PROVIDER_DOCUMENT_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_PROVIDER_DOCUMENT_EXTENSIONS))
        raise ValueError(f"Extensão não permitida. Use: {allowed}.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    relative_dir = _PROVIDER_DOCUMENT_PREFIX / f"empresa_{company_id}"
    relative_path = relative_dir / f"prestador_{company_id}_{document_key}_{timestamp}{extension}"
    target_dir = _provider_static_root() / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    file.save(_provider_static_root() / relative_path)
    return {
        "file_path": relative_path.as_posix(),
        "original_name": filename,
        "uploaded_at": datetime.utcnow().isoformat(timespec="seconds"),
    }


def _normalize_company_documents(company: ServiceCompany | None) -> dict[str, dict[str, object]]:
    raw_documents = company.documents_json if company and isinstance(company.documents_json, dict) else {}
    normalized: dict[str, dict[str, object]] = {}
    for key, value in raw_documents.items():
        if isinstance(key, str) and isinstance(value, dict):
            normalized[key] = dict(value)
    return normalized


def _parse_company_document_fields(form_data: Mapping[str, Any]) -> dict[str, dict[str, object]]:
    parsed: dict[str, dict[str, object]] = {}
    for option in DOCUMENT_TYPE_OPTIONS:
        doc_key = option["value"]
        parsed[doc_key] = {
            "expires_on": _parse_date(
                form_data.get(f"document_{doc_key}_expires_on"),
                error_message=f"Informe a data de vencimento de {option['label']} em formato válido.",
            ),
            "notes": _clean_text(form_data.get(f"document_{doc_key}_notes"), max_length=240),
        }
    return parsed


def _apply_company_documents(
    company: ServiceCompany,
    *,
    document_fields: Mapping[str, dict[str, object]],
    files: Mapping[str, Any] | None,
) -> None:
    existing_documents = _normalize_company_documents(company)
    updated_documents: dict[str, dict[str, object]] = {}

    for option in DOCUMENT_TYPE_OPTIONS:
        doc_key = option["value"]
        existing_entry = dict(existing_documents.get(doc_key) or {})
        current_entry: dict[str, object] = {}

        file_path = str(existing_entry.get("file_path") or "").strip()
        if file_path:
            current_entry["file_path"] = file_path
        original_name = str(existing_entry.get("original_name") or "").strip()
        if original_name:
            current_entry["original_name"] = original_name
        uploaded_at = str(existing_entry.get("uploaded_at") or "").strip()
        if uploaded_at:
            current_entry["uploaded_at"] = uploaded_at

        upload = files.get(f"document_{doc_key}_file") if files else None
        if upload is not None and str(getattr(upload, "filename", "") or "").strip():
            stored_payload = _store_provider_document(upload, int(company.id), doc_key)
            if file_path and file_path != stored_payload["file_path"]:
                _delete_provider_document(file_path)
            current_entry.update(stored_payload)

        parsed_fields = dict(document_fields.get(doc_key) or {})
        expires_on = parsed_fields.get("expires_on")
        notes = parsed_fields.get("notes")
        if isinstance(expires_on, date):
            current_entry["expires_on"] = expires_on.isoformat()
        if notes:
            current_entry["notes"] = str(notes)

        if current_entry:
            updated_documents[doc_key] = current_entry

    company.documents_json = updated_documents or None


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
    if company.contract_end_date and (company.contract_end_date - current_date).days <= DOCUMENT_WARNING_DAYS:
        return {"value": "vencendo", "label": "Vencendo", "css": "warning"}
    return {"value": "ativo", "label": "Ativo", "css": "success"}


def service_company_document_status(document_entry: Mapping[str, object] | None, *, today: date | None = None) -> dict[str, str]:
    current_date = today or date.today()
    payload = dict(document_entry or {})
    file_path = str(payload.get("file_path") or "").strip()
    if not file_path:
        return {"value": "pendente", "label": "Sem anexo", "css": "muted"}
    expires_on = _safe_parse_date(payload.get("expires_on"))
    if expires_on and expires_on < current_date:
        return {"value": "vencido", "label": "Vencido", "css": "danger"}
    if expires_on and (expires_on - current_date).days <= DOCUMENT_WARNING_DAYS:
        return {"value": "vencendo", "label": "Vencendo", "css": "warning"}
    return {"value": "ativo", "label": "Ativo", "css": "success"}


def service_company_documents(company: ServiceCompany | None, *, today: date | None = None) -> list[dict[str, object]]:
    current_date = today or date.today()
    raw_documents = _normalize_company_documents(company)
    rows: list[dict[str, object]] = []

    for option in DOCUMENT_TYPE_OPTIONS:
        doc_key = option["value"]
        entry = dict(raw_documents.get(doc_key) or {})
        file_path = str(entry.get("file_path") or "").strip() or None
        original_name = str(entry.get("original_name") or "").strip() or (Path(file_path).name if file_path else None)
        expires_on = str(entry.get("expires_on") or "").strip()
        notes = str(entry.get("notes") or "").strip()
        uploaded_at = str(entry.get("uploaded_at") or "").strip()
        status_payload = service_company_document_status(entry, today=current_date)
        rows.append(
            {
                "key": doc_key,
                "label": option["label"],
                "description": option["description"],
                "file_path": file_path,
                "original_name": original_name,
                "expires_on": expires_on,
                "expires_on_display": _format_date(expires_on),
                "notes": notes,
                "uploaded_at": uploaded_at,
                "uploaded_at_display": _format_datetime(uploaded_at),
                "has_file": bool(file_path),
                "status": status_payload,
            }
        )
    return rows


def service_company_document_summary(company: ServiceCompany | None, *, today: date | None = None) -> dict[str, object]:
    documents = service_company_documents(company, today=today)
    counts = {"ativo": 0, "vencendo": 0, "vencido": 0, "pendente": 0}
    for document in documents:
        counts[str(document["status"]["value"])] += 1

    if counts["vencido"]:
        return {"value": "vencido", "label": f"{counts['vencido']} doc. vencido(s)", "css": "danger", "counts": counts}
    if counts["vencendo"]:
        return {"value": "vencendo", "label": f"{counts['vencendo']} doc. vencendo", "css": "warning", "counts": counts}
    if counts["ativo"] and not counts["pendente"]:
        return {"value": "ativo", "label": "Documentação em dia", "css": "success", "counts": counts}
    return {"value": "pendente", "label": "Documentação pendente", "css": "muted", "counts": counts}


def service_company_document_download_payload(company: ServiceCompany, document_key: str) -> dict[str, object] | None:
    if document_key not in _DOCUMENT_TYPE_MAP:
        return None
    raw_documents = _normalize_company_documents(company)
    entry = dict(raw_documents.get(document_key) or {})
    file_path = str(entry.get("file_path") or "").strip()
    if not file_path:
        return None
    absolute_path = _document_storage_path(file_path)
    if absolute_path is None or not absolute_path.exists():
        return None
    return {
        "path": absolute_path,
        "download_name": str(entry.get("original_name") or absolute_path.name),
        "document_key": document_key,
        "label": _DOCUMENT_TYPE_MAP[document_key]["label"],
    }


def service_company_form(company: ServiceCompany | None = None) -> dict[str, object]:
    documents = {document["key"]: document for document in service_company_documents(company)}
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
        "documents": documents,
        "documents_summary": service_company_document_summary(company),
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
    files: Mapping[str, Any] | None = None,
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

    document_fields = _parse_company_document_fields(form_data)
    _validate_provider_document_uploads(files)

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
        db.session.flush()

    _apply_company_documents(current_company, document_fields=document_fields, files=files)
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
        contract_payload = contract_status(company)
        documents_summary = service_company_document_summary(company)
        company_services = company.service_types_json or []
        status_values = {company.status, contract_payload["value"], str(documents_summary["value"])}
        if status and status not in status_values:
            continue
        if service_type and service_type not in company_services:
            continue
        rows.append(
            {
                "company": company,
                "contract_status": contract_payload,
                "documents_summary": documents_summary,
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