from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any

from werkzeug.datastructures import MultiDict

from ...extensions import db
from ...models import (
    CondominiumOwner,
    CondominiumPackageLog,
    CondominiumResidentRequest,
    CondominiumScheduleEvent,
    CondominiumUnit,
    CondominiumMaintenanceTicket,
)
from ..condominium_schedule import ACTIVE_STATUSES, event_to_view, today_local
from .registry import DOCUMENT_LABELS, owner_attachment_count

RESIDENT_SESSION_OWNER_ID = "condominium_resident_owner_id"

RESIDENT_REQUEST_TYPE_OPTIONS = (
    {"value": "atualizacao_cadastral", "label": "Atualizacao cadastral"},
    {"value": "documento", "label": "Documento"},
    {"value": "manutencao", "label": "Manutencao"},
    {"value": "mensageria", "label": "Mensageria"},
    {"value": "outro", "label": "Outro"},
)

RESIDENT_REQUEST_STATUS_OPTIONS = (
    {"value": "novo", "label": "Novo"},
    {"value": "em_analise", "label": "Em analise"},
    {"value": "resolvido", "label": "Resolvido"},
    {"value": "recusado", "label": "Recusado"},
)

REQUEST_TYPE_LABELS = {option["value"]: option["label"] for option in RESIDENT_REQUEST_TYPE_OPTIONS}
REQUEST_STATUS_VALUES = {option["value"] for option in RESIDENT_REQUEST_STATUS_OPTIONS}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _normalized_contact(value: object) -> str:
    return _clean(value).casefold()


def _owner_contact_matches(owner: CondominiumOwner, contact: object) -> bool:
    contact_text = _normalized_contact(contact)
    contact_digits = _digits(contact)
    if not contact_text:
        return False

    owner_email = _normalized_contact(owner.email)
    if owner_email and contact_text == owner_email:
        return True

    owner_phone_digits = _digits(owner.phone)
    if owner_phone_digits and contact_digits and contact_digits == owner_phone_digits:
        return True

    emergency_digits = _digits(owner.emergency_contact)
    if emergency_digits and contact_digits and contact_digits == emergency_digits:
        return True

    return False


def _unit_matches(owner: CondominiumOwner, unit_number: object) -> bool:
    unit = owner.unit
    if unit is None:
        return False
    wanted = _clean(unit_number).casefold()
    if not wanted:
        return False
    return wanted == _clean(unit.number).casefold()


def authenticate_resident_owner(document_number: object, unit_number: object, contact: object) -> CondominiumOwner:
    document_digits = _digits(document_number)
    if not document_digits:
        raise ValueError("Informe o CPF ou CNPJ do cadastro condominial.")
    if not _clean(unit_number):
        raise ValueError("Informe o numero da unidade.")
    if not _clean(contact):
        raise ValueError("Informe o e-mail ou telefone cadastrado.")

    owners = CondominiumOwner.query.filter(CondominiumOwner.status == "ativo").all()
    document_matches = [owner for owner in owners if _digits(owner.document_number) == document_digits]
    unit_matches = [owner for owner in document_matches if _unit_matches(owner, unit_number)]
    for owner in unit_matches:
        if _owner_contact_matches(owner, contact):
            return owner

    if unit_matches:
        raise ValueError("Documento e unidade encontrados, mas o contato informado nao confere com o cadastro.")
    raise ValueError("Cadastro nao localizado para os dados informados.")


def resident_owner_from_session(owner_id: int | None) -> CondominiumOwner | None:
    if not owner_id:
        return None
    owner = CondominiumOwner.query.get(owner_id)
    if owner is None or owner.status != "ativo" or owner.unit is None:
        return None
    return owner


def _document_summary(owner: CondominiumOwner) -> dict[str, object]:
    checklist = owner.attachment_checklist_json if isinstance(owner.attachment_checklist_json, dict) else {}
    documents = checklist.get("documents") if isinstance(checklist.get("documents"), dict) else {}
    rows = []
    ok_count = 0
    pending_count = 0
    for key, label in DOCUMENT_LABELS.items():
        payload = documents.get(key) if isinstance(documents.get(key), dict) else {}
        present = bool(payload.get("present")) if payload else bool(checklist.get(key))
        ok_count += int(present)
        pending_count += int(not present)
        rows.append({"key": key, "label": label, "present": present, "files": len(payload.get("files") or []) if payload else 0})
    return {"rows": rows, "ok_count": ok_count, "pending_count": pending_count, "attachment_count": owner_attachment_count(owner)}


def _registry(owner: CondominiumOwner) -> dict[str, Any]:
    return owner.registry_data_json if isinstance(owner.registry_data_json, dict) else {}


def _unit_owners(unit: CondominiumUnit | None) -> list[CondominiumOwner]:
    if unit is None:
        return []
    return [owner for owner in unit.owners if str(owner.status or "").lower() == "ativo"]


def _package_rows(unit: CondominiumUnit | None, *, limit: int = 40) -> list[CondominiumPackageLog]:
    if unit is None:
        return []
    return (
        CondominiumPackageLog.query
        .filter(CondominiumPackageLog.unit_id == unit.id)
        .order_by(CondominiumPackageLog.received_at.desc(), CondominiumPackageLog.id.desc())
        .limit(limit)
        .all()
    )


def _ticket_rows(unit: CondominiumUnit | None, owner: CondominiumOwner, *, limit: int = 30) -> list[CondominiumMaintenanceTicket]:
    if unit is None:
        return []
    return (
        CondominiumMaintenanceTicket.query
        .filter((CondominiumMaintenanceTicket.unit_id == unit.id) | (CondominiumMaintenanceTicket.owner_id == owner.id))
        .order_by(CondominiumMaintenanceTicket.status.asc(), CondominiumMaintenanceTicket.opened_at.desc())
        .limit(limit)
        .all()
    )


def _upcoming_events(unit: CondominiumUnit | None, owner: CondominiumOwner, *, limit: int = 8) -> list[dict[str, object]]:
    if unit is None:
        return []
    today = today_local()
    horizon = today + timedelta(days=45)
    events = (
        CondominiumScheduleEvent.query
        .filter(
            CondominiumScheduleEvent.event_date >= today,
            CondominiumScheduleEvent.event_date <= horizon,
            CondominiumScheduleEvent.status.in_(ACTIVE_STATUSES),
            (CondominiumScheduleEvent.unit_id == unit.id) | (CondominiumScheduleEvent.owner_id == owner.id),
        )
        .order_by(CondominiumScheduleEvent.event_date.asc(), CondominiumScheduleEvent.start_time.asc(), CondominiumScheduleEvent.title.asc())
        .limit(limit)
        .all()
    )
    return [event_to_view(event) for event in events]


def _request_rows(owner: CondominiumOwner, *, limit: int = 20) -> list[CondominiumResidentRequest]:
    return (
        CondominiumResidentRequest.query
        .filter(CondominiumResidentRequest.owner_id == owner.id)
        .order_by(CondominiumResidentRequest.opened_at.desc(), CondominiumResidentRequest.id.desc())
        .limit(limit)
        .all()
    )


def build_resident_portal_context(owner: CondominiumOwner) -> dict[str, object]:
    unit = owner.unit
    packages = _package_rows(unit)
    tickets = _ticket_rows(unit, owner)
    requests = _request_rows(owner)
    pending_packages = [package for package in packages if package.status in {"recebido", "armazenado", "notificado"}]
    open_tickets = [ticket for ticket in tickets if ticket.status in {"aberto", "em_andamento", "aguardando"}]
    open_requests = [row for row in requests if row.status in {"novo", "em_analise"}]
    registry = _registry(owner)
    document_summary = _document_summary(owner)
    return {
        "owner": owner,
        "unit": unit,
        "unit_owners": _unit_owners(unit),
        "registry": registry,
        "document_summary": document_summary,
        "packages": {"pending": pending_packages, "history": packages},
        "tickets": tickets,
        "events": _upcoming_events(unit, owner),
        "requests": requests,
        "request_type_options": RESIDENT_REQUEST_TYPE_OPTIONS,
        "summary": {
            "pending_packages": len(pending_packages),
            "open_tickets": len(open_tickets),
            "open_requests": len(open_requests),
            "pending_documents": int(document_summary["pending_count"]),
        },
    }


def create_resident_request_from_form(
    form_data: MultiDict[str, Any],
    owner: CondominiumOwner,
    *,
    created_ip: str | None = None,
    user_agent: str | None = None,
) -> CondominiumResidentRequest:
    request_type = _clean(form_data.get("request_type")) or "atualizacao_cadastral"
    if request_type not in REQUEST_TYPE_LABELS:
        request_type = "outro"
    description = _clean(form_data.get("description"))
    if not description:
        raise ValueError("Descreva a solicitacao para a administracao.")

    requested_data = {
        key: value
        for key, value in {
            "new_email": _clean(form_data.get("new_email")),
            "new_phone": _clean(form_data.get("new_phone")),
            "residents_update": _clean(form_data.get("residents_update")),
            "vehicles_update": _clean(form_data.get("vehicles_update")),
            "package_reference": _clean(form_data.get("package_reference")),
            "preferred_contact": _clean(form_data.get("preferred_contact")),
        }.items()
        if value
    }

    resident_request = CondominiumResidentRequest(
        request_type=request_type,
        status="novo",
        priority="normal",
        title=REQUEST_TYPE_LABELS.get(request_type, "Solicitacao"),
        description=description,
        requested_data_json=requested_data or None,
        unit=owner.unit,
        owner=owner,
        created_ip=created_ip,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.session.add(resident_request)
    return resident_request


def update_resident_request_status(
    request_id: int | None,
    status: object,
    *,
    response_notes: object = None,
    actor_matricula: str | None = None,
) -> CondominiumResidentRequest:
    resident_request = CondominiumResidentRequest.query.get(request_id)
    if resident_request is None:
        raise ValueError("Solicitacao do morador nao encontrada.")
    normalized_status = _clean(status).lower()
    if normalized_status not in REQUEST_STATUS_VALUES:
        raise ValueError("Status de solicitacao invalido.")
    resident_request.status = normalized_status
    resident_request.response_notes = _clean(response_notes) or resident_request.response_notes
    resident_request.handled_by_matricula = actor_matricula
    if normalized_status in {"resolvido", "recusado"}:
        resident_request.closed_at = resident_request.closed_at or datetime.utcnow()
    else:
        resident_request.closed_at = None
    return resident_request
