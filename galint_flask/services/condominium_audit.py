from __future__ import annotations

from typing import Mapping

from flask import has_request_context, request

from ..extensions import db
from ..models import CondominiumAuditLog


def record_condominium_audit(
    *,
    action: str,
    entity_type: str,
    title: str,
    actor_matricula: str | None = None,
    entity_id: int | None = None,
    details: Mapping[str, object] | None = None,
) -> CondominiumAuditLog:
    ip_address = None
    user_agent = None
    if has_request_context():
        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip() or None
        user_agent = (request.user_agent.string if request.user_agent else None) or None
        if user_agent and len(user_agent) > 255:
            user_agent = user_agent[:255]

    log = CondominiumAuditLog(
        action=str(action or "condominium.action")[:80],
        entity_type=str(entity_type or "condominium")[:80],
        entity_id=entity_id,
        title=str(title or "Acao condominial registrada")[:220],
        actor_matricula=actor_matricula,
        details_json=dict(details or {}) or None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.session.add(log)
    return log


def recent_condominium_audit_logs(*, limit: int = 20) -> list[CondominiumAuditLog]:
    return CondominiumAuditLog.query.order_by(CondominiumAuditLog.occurred_at.desc()).limit(limit).all()