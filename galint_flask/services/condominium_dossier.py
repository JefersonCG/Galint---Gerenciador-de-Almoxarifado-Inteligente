from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from sqlalchemy import or_

from ..models import CondominiumAuditLog, CondominiumBuilding, CondominiumOwner, CondominiumScheduleEvent, CondominiumUnit
from .condominium.registry import DOCUMENT_LABELS
from .condominium_schedule import ACTIVE_STATUSES, event_to_view, today_local
from .condominium_structure import UNIT_STATUS_LABELS, unit_dashboard_status


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _flatten_json(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_json(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_json(item) for item in value)
    return str(value or "")


def _notes_section(notes: object, label: str) -> str:
    text = str(notes or "")
    if not text:
        return ""
    pattern = rf"\[{re.escape(label)}\]\s*(.*?)(?=\n\n\[[^\]]+\]|\Z)"
    match = re.search(pattern, text, flags=re.S | re.I)
    return match.group(1).strip() if match else ""


def _owner_search_blob(owner: CondominiumOwner) -> str:
    values = [
        owner.full_name,
        owner.document_number,
        owner.rg,
        owner.cnh,
        owner.phone,
        owner.email,
        owner.correspondence_address,
        owner.emergency_contact,
        owner.notes,
        _flatten_json(owner.registry_data_json),
    ]
    return " ".join(str(value or "") for value in values).casefold()


def _unit_search_blob(unit: CondominiumUnit) -> str:
    building = unit.building
    values = [unit.number, unit.status, unit.unit_type, unit.notes]
    if building:
        values.extend([building.code, building.name, building.notes])
    values.extend(_owner_search_blob(owner) for owner in unit.owners)
    return " ".join(str(value or "") for value in values).casefold()


def _matches_query(unit: CondominiumUnit, query: str) -> bool:
    normalized = str(query or "").strip().casefold()
    if not normalized:
        return True
    blob = _unit_search_blob(unit)
    if normalized in blob:
        return True
    query_digits = _digits(normalized)
    if not query_digits:
        return False
    return query_digits in _digits(blob)


def _owner_document_summary(owner: CondominiumOwner) -> dict[str, object]:
    checklist = owner.attachment_checklist_json if isinstance(owner.attachment_checklist_json, dict) else {}
    documents = checklist.get("documents") if isinstance(checklist.get("documents"), dict) else {}
    items = []
    ok_count = 0
    pending_count = 0
    for key, label in DOCUMENT_LABELS.items():
        document_payload = documents.get(key) if isinstance(documents.get(key), dict) else {}
        present = bool(document_payload.get("present")) if document_payload else bool(checklist.get(key))
        attachment_count = len(document_payload.get("files") or []) if document_payload else 0
        ok_count += int(present)
        pending_count += int(not present)
        items.append({"key": key, "label": label, "present": present, "attachment_count": attachment_count})
    return {"items": items, "ok_count": ok_count, "pending_count": pending_count}


def _access_rows_text(access_security: dict[str, object], key: str, fields: tuple[str, ...], *, raw_key: str = "") -> str:
    rows = access_security.get(key)
    if isinstance(rows, list) and rows:
        formatted_rows = []
        for row in rows:
            if isinstance(row, dict):
                values = [str(row.get(field) or "").strip() for field in fields]
                line = " | ".join(value for value in values if value)
                if line:
                    formatted_rows.append(line)
            elif row:
                formatted_rows.append(str(row))
        if formatted_rows:
            return "\n".join(formatted_rows)
    raw = access_security.get("raw") if isinstance(access_security.get("raw"), dict) else {}
    if raw_key and raw.get(raw_key):
        return str(raw.get(raw_key) or "").strip()
    return ""


def _owner_card(owner: CondominiumOwner) -> dict[str, object]:
    registry_data = owner.registry_data_json if isinstance(owner.registry_data_json, dict) else {}
    profile = registry_data.get("owner_profile") if isinstance(registry_data.get("owner_profile"), dict) else {}
    access_security = registry_data.get("access_security") if isinstance(registry_data.get("access_security"), dict) else {}
    residents = _access_rows_text(access_security, "residents", ("name", "relationship", "document"), raw_key="unit_residents_text")
    vehicles = _access_rows_text(access_security, "vehicles", ("brand", "model", "color", "plate", "garage_space"), raw_key="authorized_vehicles_text")
    private_staff = _access_rows_text(access_security, "private_staff", ("name", "document", "role", "frequency"), raw_key="private_staff_text")
    pets = _access_rows_text(access_security, "pets", ("species", "breed", "size", "name"), raw_key="pets_text")
    staff_and_pets = "\n".join(part for part in (private_staff, pets) if part)
    return {
        "owner": owner,
        "relationship_label": "Locatario" if owner.relationship_type == "locatario" else "Proprietario",
        "document_summary": _owner_document_summary(owner),
        "profile": profile,
        "vehicles": vehicles or _notes_section(owner.notes, "Veiculos autorizados") or _notes_section(owner.notes, "Veiculos e condutores"),
        "linked_people": residents or _notes_section(owner.notes, "Moradores da unidade") or _notes_section(owner.notes, "Pessoas vinculadas"),
        "authorized_visitors": staff_and_pets or _notes_section(owner.notes, "Funcionarios particulares") or _notes_section(owner.notes, "Visitantes autorizados"),
    }


def _unit_card(unit: CondominiumUnit) -> dict[str, object]:
    active_owners = [owner for owner in unit.owners if str(owner.status or "").lower() == "ativo"]
    status = unit_dashboard_status(unit)
    pending_documents = sum(int(_owner_document_summary(owner)["pending_count"]) for owner in active_owners)
    return {
        "unit": unit,
        "status": status,
        "status_label": UNIT_STATUS_LABELS.get(status, status.title()),
        "active_owner_count": len(active_owners),
        "pending_documents": pending_documents,
        "owner_names": ", ".join(owner.full_name for owner in active_owners) or "Sem morador ativo",
    }


def search_condominium_units(*, query: str = "", status: str = "", limit: int = 80) -> list[dict[str, object]]:
    units = (
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
    rows: list[dict[str, object]] = []
    wanted_status = str(status or "").strip().lower()
    for unit in units:
        unit_status = unit_dashboard_status(unit)
        if wanted_status and unit_status != wanted_status:
            continue
        if not _matches_query(unit, query):
            continue
        rows.append(_unit_card(unit))
        if len(rows) >= limit:
            break
    return rows


def _upcoming_events_for_unit(unit: CondominiumUnit, owner_ids: list[int], *, limit: int = 8) -> list[dict[str, object]]:
    today = today_local()
    horizon = today + timedelta(days=60)
    filters: list[Any] = [CondominiumScheduleEvent.unit_id == unit.id]
    if unit.building_id:
        filters.append(CondominiumScheduleEvent.building_id == unit.building_id)
    if owner_ids:
        filters.append(CondominiumScheduleEvent.owner_id.in_(owner_ids))
    events = (
        CondominiumScheduleEvent.query
        .filter(
            CondominiumScheduleEvent.event_date >= today,
            CondominiumScheduleEvent.event_date <= horizon,
            CondominiumScheduleEvent.status.in_(ACTIVE_STATUSES),
            or_(*filters),
        )
        .order_by(CondominiumScheduleEvent.event_date.asc(), CondominiumScheduleEvent.start_time.asc(), CondominiumScheduleEvent.title.asc())
        .limit(limit)
        .all()
    )
    return [event_to_view(event) for event in events]


def _audit_logs_for_unit(unit: CondominiumUnit, owner_ids: list[int], *, limit: int = 12) -> list[CondominiumAuditLog]:
    entity_filters: list[Any] = [
        (CondominiumAuditLog.entity_type == "condominium_unit") & (CondominiumAuditLog.entity_id == unit.id),
    ]
    if unit.building_id:
        entity_filters.append((CondominiumAuditLog.entity_type == "condominium_building") & (CondominiumAuditLog.entity_id == unit.building_id))
    if owner_ids:
        entity_filters.append((CondominiumAuditLog.entity_type == "condominium_owner") & (CondominiumAuditLog.entity_id.in_(owner_ids)))
    return (
        CondominiumAuditLog.query
        .filter(or_(*entity_filters))
        .order_by(CondominiumAuditLog.occurred_at.desc())
        .limit(limit)
        .all()
    )


def build_unit_dossier_context(unit_id: int | None, *, query: str = "", status: str = "") -> dict[str, object]:
    rows = search_condominium_units(query=query, status=status)
    selected_unit = CondominiumUnit.query.get(unit_id) if unit_id else None
    if selected_unit is None and rows:
        selected_unit = rows[0]["unit"]

    selected: dict[str, object] | None = None
    if selected_unit is not None:
        owners = [_owner_card(owner) for owner in selected_unit.owners]
        active_owner_ids = [int(owner["owner"].id) for owner in owners if str(owner["owner"].status or "").lower() == "ativo"]
        selected = {
            "unit_card": _unit_card(selected_unit),
            "owners": owners,
            "upcoming_events": _upcoming_events_for_unit(selected_unit, active_owner_ids),
            "audit_logs": _audit_logs_for_unit(selected_unit, active_owner_ids),
        }

    totals = {
        "result_count": len(rows),
        "occupied": sum(1 for row in rows if row["status"] == "ocupado"),
        "pending_documents": sum(int(row["pending_documents"] or 0) for row in rows),
    }
    return {"rows": rows, "selected": selected, "totals": totals, "filters": {"q": query, "status": status}}