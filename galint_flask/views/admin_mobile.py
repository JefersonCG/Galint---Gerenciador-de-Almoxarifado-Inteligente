"""Admin API para Painel Mobile."""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..models import (
    ApkAuditLog,
    ApkVersion,
    Device,
    DeviceSession,
    FeatureAssignment,
    FeatureFlag,
)


blueprint = Blueprint("admin_mobile", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not bool(getattr(current_user, "is_admin", False)):
            return jsonify({"error": "Acesso negado. Apenas administradores."}), 403
        return view(*args, **kwargs)

    return wrapper


def _device_payload(device: Device) -> dict:
    return {
        "id": device.id,
        "device_uuid": device.device_uuid,
        "status": device.status,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "platform": device.platform,
        "os_version": device.os_version,
        "apk_version": device.apk_version,
        "apk_build_number": device.apk_build_number,
        "apk_channel": device.apk_channel,
        "current_user_id": device.current_user_id,
        "current_user_name": device.current_user.nome if device.current_user else None,
        "last_heartbeat_at": device.last_heartbeat_at.isoformat() if device.last_heartbeat_at else None,
        "last_ip_address": device.last_ip_address,
        "blocked_reason": device.blocked_reason,
        "blocked_by": device.blocked_by,
        "blocked_at": device.blocked_at.isoformat() if device.blocked_at else None,
        "created_at": device.created_at.isoformat() if device.created_at else None,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
    }


def _session_payload(session: DeviceSession) -> dict:
    return {
        "id": session.id,
        "device_id": session.device_id,
        "user_id": session.user_id,
        "status": session.status,
        "logged_in_at": session.logged_in_at.isoformat() if session.logged_in_at else None,
        "logged_out_at": session.logged_out_at.isoformat() if session.logged_out_at else None,
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        "revoked_by": session.revoked_by,
        "revoked_at": session.revoked_at.isoformat() if session.revoked_at else None,
        "revoke_reason": session.revoke_reason,
    }


@blueprint.get("/devices")
@login_required
@admin_required
def list_devices():
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    devices = (
        Device.query
        .filter(Device.last_heartbeat_at.isnot(None))
        .filter(Device.last_heartbeat_at >= cutoff)
        .order_by(Device.last_heartbeat_at.desc())
        .limit(500)
        .all()
    )
    return jsonify({"success": True, "data": [_device_payload(d) for d in devices]})


@blueprint.get("/devices/<int:device_id>")
@login_required
@admin_required
def get_device(device_id: int):
    device = Device.query.get_or_404(device_id)
    sessions = DeviceSession.query.filter_by(device_id=device_id).order_by(DeviceSession.logged_in_at.desc()).limit(50)
    return jsonify({
        "success": True,
        "data": {
            "device": _device_payload(device),
            "sessions": [_session_payload(s) for s in sessions],
        },
    })


@blueprint.post("/devices/<int:device_id>/block")
@login_required
@admin_required
def block_device(device_id: int):
    device = Device.query.get_or_404(device_id)
    payload = request.get_json() or {}
    reason = (payload.get("reason") or "Bloqueado pelo administrador").strip()
    device.block(reason=reason, admin_id=current_user.matricula)
    db.session.commit()
    return jsonify({"success": True, "data": _device_payload(device)})


@blueprint.post("/devices/<int:device_id>/unblock")
@login_required
@admin_required
def unblock_device(device_id: int):
    device = Device.query.get_or_404(device_id)
    device.status = "active"
    device.blocked_reason = None
    device.blocked_by = None
    device.blocked_at = None
    ApkAuditLog.log_action(
        action_type="unblock_device",
        action_result="success",
        device_id=device.id,
        admin_id=current_user.matricula,
    )
    db.session.commit()
    return jsonify({"success": True, "data": _device_payload(device)})


@blueprint.post("/devices/<int:device_id>/logout")
@login_required
@admin_required
def logout_device(device_id: int):
    device = Device.query.get_or_404(device_id)
    device.force_logout(admin_id=current_user.matricula)
    db.session.commit()
    return jsonify({"success": True})


@blueprint.get("/sessions")
@login_required
@admin_required
def list_sessions():
    status = (request.args.get("status") or "active").strip().lower()
    query = DeviceSession.query
    if status:
        query = query.filter(DeviceSession.status == status)
    sessions = query.order_by(DeviceSession.logged_in_at.desc()).limit(500).all()
    return jsonify({"success": True, "data": [_session_payload(s) for s in sessions]})


@blueprint.post("/sessions/<int:session_id>/revoke")
@login_required
@admin_required
def revoke_session(session_id: int):
    session = DeviceSession.query.get_or_404(session_id)
    payload = request.get_json() or {}
    reason = (payload.get("reason") or "Revogado pelo administrador").strip()
    session.revoke(reason=reason, admin_id=current_user.matricula)
    db.session.commit()
    return jsonify({"success": True, "data": _session_payload(session)})


@blueprint.get("/versions")
@login_required
@admin_required
def list_versions():
    versions = ApkVersion.query.order_by(ApkVersion.version_code.desc()).limit(200).all()
    data = [
        {
            "id": v.id,
            "version_name": v.version_name,
            "version_code": v.version_code,
            "channel": v.channel,
            "is_mandatory": v.is_mandatory,
            "is_blocked": v.is_blocked,
            "release_date": v.release_date.isoformat() if v.release_date else None,
        }
        for v in versions
    ]
    return jsonify({"success": True, "data": data})


@blueprint.post("/versions/<int:version_id>/block")
@login_required
@admin_required
def block_version(version_id: int):
    version = ApkVersion.query.get_or_404(version_id)
    version.is_blocked = True
    db.session.commit()
    ApkAuditLog.log_action(
        action_type="block_version",
        action_result="success",
        admin_id=current_user.matricula,
        details={"version_id": version.id, "version_name": version.version_name},
    )
    return jsonify({"success": True})


@blueprint.get("/features")
@login_required
@admin_required
def list_features():
    flags = FeatureFlag.active_query().order_by(FeatureFlag.flag_key.asc()).all()
    data = [
        {
            "id": f.id,
            "flag_key": f.flag_key,
            "display_name": f.display_name,
            "description": f.description,
            "is_enabled": f.is_enabled,
            "flag_type": f.flag_type,
            "default_value": f.default_value,
            "requires_app_restart": f.requires_app_restart,
            "min_app_version": f.min_app_version,
        }
        for f in flags
    ]
    return jsonify({"success": True, "data": data})


@blueprint.put("/features/<int:flag_id>")
@login_required
@admin_required
def update_feature(flag_id: int):
    flag = FeatureFlag.query.get_or_404(flag_id)
    payload = request.get_json() or {}

    for field in [
        "display_name",
        "description",
        "flag_type",
        "default_value",
        "min_app_version",
    ]:
        if field in payload:
            setattr(flag, field, payload.get(field))

    if "is_enabled" in payload:
        flag.is_enabled = bool(payload.get("is_enabled"))
    if "requires_app_restart" in payload:
        flag.requires_app_restart = bool(payload.get("requires_app_restart"))

    db.session.commit()
    ApkAuditLog.log_action(
        action_type="update_feature",
        action_result="success",
        admin_id=current_user.matricula,
        details={"flag_id": flag.id, "flag_key": flag.flag_key},
    )
    return jsonify({"success": True})


@blueprint.get("/audit")
@login_required
@admin_required
def list_audit_logs():
    """Lista logs de auditoria com filtros avançados."""
    from datetime import datetime, timedelta
    
    limit = int(request.args.get("limit") or 500)
    device_id = request.args.get("device_id")
    user_id = request.args.get("user_id")
    admin_id = request.args.get("admin_id")
    action_type = request.args.get("action_type")
    action_result = request.args.get("action_result")
    time_range = request.args.get("time_range")

    query = ApkAuditLog.query
    
    # Filtros diretos
    if device_id:
        query = query.filter(ApkAuditLog.device_id == int(device_id))
    if user_id:
        query = query.filter(ApkAuditLog.user_id == str(user_id))
    if admin_id:
        query = query.filter(ApkAuditLog.admin_id == str(admin_id))
    if action_type:
        query = query.filter(ApkAuditLog.action_type == action_type)
    if action_result:
        query = query.filter(ApkAuditLog.action_result == action_result)
    
    # Filtro por período
    if time_range:
        cutoff = None
        if time_range == "24h":
            cutoff = datetime.utcnow() - timedelta(hours=24)
        elif time_range == "7d":
            cutoff = datetime.utcnow() - timedelta(days=7)
        elif time_range == "30d":
            cutoff = datetime.utcnow() - timedelta(days=30)
        
        if cutoff:
            query = query.filter(ApkAuditLog.occurred_at >= cutoff)

    logs = query.order_by(ApkAuditLog.occurred_at.desc()).limit(limit).all()
    data = [
        {
            "id": log.id,
            "occurred_at": log.occurred_at.isoformat() if log.occurred_at else None,
            "user_id": log.user_id,
            "device_id": log.device_id,
            "admin_id": log.admin_id,
            "action_type": log.action_type,
            "action_result": log.action_result,
            "apk_version": log.apk_version,
            "details": log.details,
        }
        for log in logs
    ]
    return jsonify({"success": True, "data": data})
