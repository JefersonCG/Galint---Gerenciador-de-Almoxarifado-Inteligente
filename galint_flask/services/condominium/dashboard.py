from __future__ import annotations

from datetime import datetime, time
from statistics import mean

from sqlalchemy import func

from ...extensions import db
from ...models import (
    CondominiumAccessLog,
    CondominiumBuilding,
    CondominiumMaintenanceTicket,
    CondominiumOwner,
    CondominiumPackageLog,
    CondominiumResidentRequest,
    CondominiumUnit,
    ServiceCompany,
)
from ..condominium_gatehouse import gatehouse_today_summary, recent_access_logs
from ..condominium_operations import messenger_analytics, operations_summary
from ..condominium_schedule import due_schedule_notifications, today_local
from ..condominium_service_providers import contract_status, service_company_document_summary
from ..condominium_structure import UNIT_STATUS_LABELS, unit_dashboard_status
from .registry import DOCUMENT_LABELS


def _owner_document_pending_count(owner: CondominiumOwner) -> int:
    checklist = owner.attachment_checklist_json if isinstance(owner.attachment_checklist_json, dict) else {}
    documents = checklist.get("documents") if isinstance(checklist.get("documents"), dict) else {}
    pending = 0
    for key in DOCUMENT_LABELS:
        payload = documents.get(key) if isinstance(documents.get(key), dict) else {}
        present = bool(payload.get("present")) if payload else bool(checklist.get(key))
        pending += int(not present)
    return pending


def _today_bounds() -> tuple[datetime, datetime]:
    current_date = today_local()
    return datetime.combine(current_date, time.min), datetime.combine(current_date, time.max)


def _ticket_resolution_hours(tickets: list[CondominiumMaintenanceTicket]) -> float | None:
    durations = []
    for ticket in tickets:
        if ticket.opened_at and ticket.closed_at:
            durations.append((ticket.closed_at - ticket.opened_at).total_seconds() / 3600)
    if not durations:
        return None
    return round(mean(durations), 1)


def _rank_units_by_packages(*, limit: int = 6) -> list[dict[str, object]]:
    rows = (
        db.session.query(CondominiumUnit.id, CondominiumUnit.number, CondominiumPackageLog.unit_id, func.count(CondominiumPackageLog.id))
        .join(CondominiumPackageLog, CondominiumPackageLog.unit_id == CondominiumUnit.id)
        .group_by(CondominiumUnit.id, CondominiumUnit.number, CondominiumPackageLog.unit_id)
        .order_by(func.count(CondominiumPackageLog.id).desc())
        .limit(limit)
        .all()
    )
    peak = max((int(row[3] or 0) for row in rows), default=1)
    return [
        {"label": f"Unidade {number}", "count": int(count or 0), "percent": round((int(count or 0) / peak) * 100)}
        for _, number, _, count in rows
    ]


def _provider_risk_summary(companies: list[ServiceCompany]) -> dict[str, int]:
    current_date = today_local()
    result = {"contracts_expiring": 0, "contracts_expired": 0, "documents_expiring": 0, "documents_expired": 0, "inactive": 0}
    for company in companies:
        if company.status != "ativo":
            result["inactive"] += 1
        contract = contract_status(company, today=current_date)
        documents = service_company_document_summary(company, today=current_date)
        if contract["value"] == "vencido":
            result["contracts_expired"] += 1
        if contract["value"] == "vencendo":
            result["contracts_expiring"] += 1
        if documents["value"] == "vencido":
            result["documents_expired"] += 1
        if documents["value"] == "vencendo":
            result["documents_expiring"] += 1
    return result


def _build_alerts(payload: dict[str, object]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    administration = payload["administration"]
    portaria = payload["gatehouse"]
    messenger = payload["messenger"]
    maintenance = payload["maintenance"]
    providers = payload["providers"]
    resident_portal = payload["resident_portal"]

    if int(administration["pending_documents"]):
        alerts.append({"tone": "warn", "title": "Documentos pendentes", "text": f"{administration['pending_documents']} pendencia(s) em cadastros ativos."})
    if int(messenger["pending_packages"]):
        alerts.append({"tone": "warn", "title": "Mensageria com fila", "text": f"{messenger['pending_packages']} volume(s) aguardando retirada ou tratativa."})
    if int(maintenance["critical_open"]):
        alerts.append({"tone": "danger", "title": "Chamados criticos", "text": f"{maintenance['critical_open']} chamado(s) critico(s) ainda aberto(s)."})
    if int(portaria["blocked_today"]):
        alerts.append({"tone": "danger", "title": "Bloqueios hoje", "text": f"{portaria['blocked_today']} acesso(s) bloqueado(s) registrado(s) hoje."})
    if int(providers["documents_expired"]) or int(providers["contracts_expired"]):
        alerts.append({"tone": "danger", "title": "Prestadores em risco", "text": "Ha contrato ou documento vencido em empresa prestadora."})
    if int(resident_portal["new_requests"]):
        alerts.append({"tone": "info", "title": "Solicitacoes de moradores", "text": f"{resident_portal['new_requests']} nova(s) solicitacao(oes) aguardando triagem."})
    if not alerts:
        alerts.append({"tone": "ok", "title": "Operacao sem gargalo critico", "text": "Nenhum alerta executivo critico foi detectado agora."})
    return alerts


def build_condominium_general_dashboard() -> dict[str, object]:
    buildings = CondominiumBuilding.query.filter(CondominiumBuilding.active.is_(True)).all()
    units = CondominiumUnit.query.join(CondominiumBuilding).filter(CondominiumUnit.active.is_(True), CondominiumBuilding.active.is_(True)).all()
    owners = CondominiumOwner.query.filter(CondominiumOwner.status == "ativo").all()
    tickets = CondominiumMaintenanceTicket.query.all()
    packages = CondominiumPackageLog.query.all()
    companies = ServiceCompany.query.all()
    resident_requests = CondominiumResidentRequest.query.order_by(CondominiumResidentRequest.opened_at.desc(), CondominiumResidentRequest.id.desc()).limit(12).all()

    status_counts = {status: 0 for status in UNIT_STATUS_LABELS}
    for unit in units:
        status_counts[unit_dashboard_status(unit)] += 1

    pending_documents = sum(_owner_document_pending_count(owner) for owner in owners)
    start_today, end_today = _today_bounds()
    today_packages = [package for package in packages if package.received_at and start_today <= package.received_at <= end_today]
    open_tickets = [ticket for ticket in tickets if ticket.status in {"aberto", "em_andamento", "aguardando"}]
    closed_tickets = [ticket for ticket in tickets if ticket.status == "concluido"]
    critical_open = [ticket for ticket in open_tickets if ticket.priority == "critica"]
    provider_risks = _provider_risk_summary(companies)
    gatehouse_summary = gatehouse_today_summary()
    operations = operations_summary()
    new_resident_requests = CondominiumResidentRequest.query.filter(CondominiumResidentRequest.status == "novo").count()
    open_resident_requests = CondominiumResidentRequest.query.filter(CondominiumResidentRequest.status.in_({"novo", "em_analise"})).count()

    payload: dict[str, object] = {
        "administration": {
            "buildings": len(buildings),
            "units": len(units),
            "owners": len(owners),
            "tenants": sum(1 for owner in owners if owner.occupancy_status == "imovel_locado" or owner.relationship_type == "locatario"),
            "pending_documents": pending_documents,
            "unit_statuses": status_counts,
        },
        "gatehouse": {
            "entries_today": gatehouse_summary["entries"],
            "exits_today": gatehouse_summary["exits"],
            "blocked_today": gatehouse_summary["blocked"],
            "total_today": gatehouse_summary["total"],
            "recent_logs": recent_access_logs(limit=8),
            "frequent_providers": (
                db.session.query(CondominiumAccessLog.person_name, func.count(CondominiumAccessLog.id))
                .filter(CondominiumAccessLog.person_type == "prestador")
                .group_by(CondominiumAccessLog.person_name)
                .order_by(func.count(CondominiumAccessLog.id).desc())
                .limit(5)
                .all()
            ),
        },
        "messenger": {
            "received_today": len(today_packages),
            "pending_packages": operations["pending_packages"],
            "stored_packages": operations["stored_packages"],
            "delivered_packages": operations["delivered_packages"],
            "analytics": messenger_analytics(limit=6),
            "unit_rank": _rank_units_by_packages(),
            "recent_packages": sorted(packages, key=lambda package: (package.received_at or datetime.min, package.id or 0), reverse=True)[:8],
        },
        "maintenance": {
            "open": len(open_tickets),
            "critical_open": len(critical_open),
            "closed": len(closed_tickets),
            "avg_resolution_hours": _ticket_resolution_hours(closed_tickets),
            "recent_tickets": sorted(tickets, key=lambda ticket: (ticket.opened_at or datetime.min, ticket.id or 0), reverse=True)[:8],
        },
        "providers": {"total": len(companies), **provider_risks},
        "resident_portal": {
            "new_requests": int(new_resident_requests),
            "open_requests": int(open_resident_requests),
            "recent_requests": resident_requests,
        },
        "agenda_notifications": due_schedule_notifications(limit=6),
    }
    payload["alerts"] = _build_alerts(payload)
    return payload
