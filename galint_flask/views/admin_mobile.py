"""Admin API para Painel Mobile."""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import wraps
import ipaddress

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
    Usuario,
)


blueprint = Blueprint("admin_mobile", __name__, url_prefix="/admin")
MOBILE_ACCESS_FLAG_KEY = "mobile_access"


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not bool(getattr(current_user, "is_admin", False)):
            return jsonify({"error": "Acesso negado. Apenas administradores."}), 403
        return view(*args, **kwargs)

    return wrapper


def _classify_network_scope(ip_value: str | None) -> str:
    if not ip_value:
        return "desconhecida"
    try:
        ip = ipaddress.ip_address(str(ip_value))
        if ip.is_loopback:
            return "loopback"
        if ip.is_private:
            return "local"
        return "externa"
    except ValueError:
        return "desconhecida"


def _get_version_context() -> dict[str, object]:
    versions = ApkVersion.query.order_by(ApkVersion.version_code.desc()).all()
    latest_by_channel: dict[str, ApkVersion] = {}
    blocked_versions: set[tuple[str, str]] = set()

    for version in versions:
        latest_by_channel.setdefault(version.channel, version)
        if version.is_blocked:
            blocked_versions.add((version.channel, version.version_name))

    return {
        "latest_by_channel": latest_by_channel,
        "blocked_versions": blocked_versions,
    }


def _get_mobile_access_flag(create: bool = False) -> FeatureFlag | None:
    flag = FeatureFlag.query.filter_by(flag_key=MOBILE_ACCESS_FLAG_KEY).first()
    if flag or not create:
        return flag

    flag = FeatureFlag(
        flag_key=MOBILE_ACCESS_FLAG_KEY,
        display_name="Acesso Mobile",
        description="Permite ou bloqueia o login do usuário no app GALINT Mobile.",
        is_enabled=True,
        flag_type="boolean",
        default_value="true",
        requires_app_restart=False,
        created_by=current_user.matricula,
    )
    db.session.add(flag)
    db.session.flush()
    return flag


def _mobile_user_assignment_map() -> dict[str, FeatureAssignment]:
    flag = _get_mobile_access_flag(create=False)
    if not flag:
        return {}

    now = datetime.utcnow()
    assignments = (
        FeatureAssignment.query.filter_by(feature_flag_id=flag.id, target_type="user")
        .filter(FeatureAssignment.deleted_at.is_(None))
        .filter((FeatureAssignment.expires_at.is_(None)) | (FeatureAssignment.expires_at > now))
        .all()
    )
    return {assignment.target_id: assignment for assignment in assignments}


def _user_mobile_block_info(user_id: str, assignment_map: dict[str, FeatureAssignment] | None = None) -> tuple[bool, str | None, str | None]:
    assignment_map = assignment_map or _mobile_user_assignment_map()
    assignment = assignment_map.get(user_id)
    if not assignment or assignment.is_enabled:
        return False, None, None
    blocked_at = assignment.assigned_at.isoformat() if assignment.assigned_at else None
    return True, assignment.override_value or "Acesso mobile bloqueado pelo administrador.", blocked_at


def _diagnose_device(device: Device, version_context: dict[str, object] | None = None) -> dict[str, object]:
    version_context = version_context or _get_version_context()
    latest_by_channel: dict[str, ApkVersion] = version_context.get("latest_by_channel", {})  # type: ignore[assignment]
    blocked_versions: set[tuple[str, str]] = version_context.get("blocked_versions", set())  # type: ignore[assignment]

    issues: list[str] = []
    score = 100
    now = datetime.utcnow()
    last_heartbeat = device.last_heartbeat_at
    heartbeat_age_minutes = None

    if last_heartbeat:
        heartbeat_age_minutes = max(0, int((now - last_heartbeat).total_seconds() // 60))
    else:
        issues.append("Sem heartbeat recebido")
        score -= 25

    if device.status == "blocked":
        issues.append("Dispositivo bloqueado")
        score -= 60
    elif heartbeat_age_minutes is not None and heartbeat_age_minutes > 10:
        issues.append("Heartbeat atrasado")
        score -= 25
    elif heartbeat_age_minutes is not None and heartbeat_age_minutes > 5:
        issues.append("Heartbeat em atenção")
        score -= 10

    if not device.current_user_id:
        issues.append("Sem usuário vinculado")
        score -= 10

    if not device.os_version:
        issues.append("Versão do Android não informada")
        score -= 8

    if not device.last_ip_address:
        issues.append("Sem IP reportado")
        score -= 5

    version_status = "desconhecida"
    latest_version = latest_by_channel.get(device.apk_channel)
    if (device.apk_channel, device.apk_version) in blocked_versions:
        version_status = "bloqueada"
        issues.append("Versão do app bloqueada")
        score -= 35
    elif latest_version and device.apk_build_number and latest_version.version_code > device.apk_build_number:
        version_status = "desatualizada"
        issues.append("Versão do app abaixo da mais recente do canal")
        score -= 18
    elif latest_version:
        version_status = "ok"

    if score >= 85:
        health = "saudavel"
        summary = "Operando normalmente"
    elif score >= 60:
        health = "atencao"
        summary = "Operabilidade parcial ou com risco"
    else:
        health = "critico"
        summary = "Intervenção recomendada"

    return {
        "score": max(score, 0),
        "health": health,
        "summary": summary,
        "issues": issues,
        "heartbeat_age_minutes": heartbeat_age_minutes,
        "network_scope": _classify_network_scope(device.last_ip_address),
        "version_status": version_status,
    }


def _device_payload(device: Device, version_context: dict[str, object] | None = None) -> dict:
    diagnostic = _diagnose_device(device, version_context)
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
        "is_online": device.is_online and device.status != "blocked",
        "network_scope": diagnostic["network_scope"],
        "diagnostic": diagnostic,
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
    limit = min(int(request.args.get("limit") or 1000), 2000)
    devices = (
        Device.query
        .filter(Device.deleted_at.is_(None))
        .order_by(Device.updated_at.desc())
        .limit(limit)
        .all()
    )
    version_context = _get_version_context()
    return jsonify({"success": True, "data": [_device_payload(d, version_context) for d in devices]})


@blueprint.get("/devices/<int:device_id>")
@login_required
@admin_required
def get_device(device_id: int):
    device = Device.query.get_or_404(device_id)
    sessions = DeviceSession.query.filter_by(device_id=device_id).order_by(DeviceSession.logged_in_at.desc()).limit(50)
    version_context = _get_version_context()
    return jsonify({
        "success": True,
        "data": {
            "device": _device_payload(device, version_context),
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


def _user_payload(user: Usuario, devices_by_user: dict[str, list[Device]], sessions_by_user: dict[str, list[DeviceSession]], assignment_map: dict[str, FeatureAssignment]) -> dict[str, object]:
    devices = devices_by_user.get(user.matricula, [])
    sessions = sessions_by_user.get(user.matricula, [])
    blocked, block_reason, blocked_at = _user_mobile_block_info(user.matricula, assignment_map)
    online_devices = sum(1 for device in devices if device.is_online and device.status != "blocked")
    active_sessions = sum(1 for session in sessions if session.status == "active")
    last_activity_candidates = [device.last_heartbeat_at for device in devices if device.last_heartbeat_at]
    last_activity = max(last_activity_candidates) if last_activity_candidates else None

    android_versions = sorted({device.os_version for device in devices if device.os_version})
    apk_versions = sorted({device.apk_version for device in devices if device.apk_version})

    return {
        "matricula": user.matricula,
        "nome": user.nome,
        "setor": user.setor,
        "cargo": user.cargo,
        "is_admin": bool(user.is_admin),
        "has_password": bool(user.senha_hash),
        "mobile_blocked": blocked,
        "mobile_block_reason": block_reason,
        "mobile_blocked_at": blocked_at,
        "devices_count": len(devices),
        "online_devices_count": online_devices,
        "active_sessions_count": active_sessions,
        "last_mobile_activity": last_activity.isoformat() if last_activity else None,
        "android_versions": android_versions,
        "apk_versions": apk_versions,
    }


@blueprint.get("/mobile-users")
@login_required
@admin_required
def list_mobile_users():
    users = Usuario.query.order_by(Usuario.nome.asc()).limit(1000).all()
    devices = Device.query.filter(Device.deleted_at.is_(None)).all()
    sessions = DeviceSession.query.order_by(DeviceSession.logged_in_at.desc()).limit(2000).all()
    assignment_map = _mobile_user_assignment_map()

    devices_by_user: dict[str, list[Device]] = {}
    for device in devices:
        if not device.current_user_id:
            continue
        devices_by_user.setdefault(device.current_user_id, []).append(device)

    sessions_by_user: dict[str, list[DeviceSession]] = {}
    for session in sessions:
        sessions_by_user.setdefault(session.user_id, []).append(session)

    data = [_user_payload(user, devices_by_user, sessions_by_user, assignment_map) for user in users]
    return jsonify({"success": True, "data": data})


@blueprint.put("/mobile-users/<string:matricula>")
@login_required
@admin_required
def update_mobile_user(matricula: str):
    user = Usuario.query.get_or_404(matricula)
    payload = request.get_json() or {}

    nome = (payload.get("nome") or user.nome or "").strip()
    if nome:
        user.nome = nome

    if "setor" in payload:
        user.setor = (payload.get("setor") or "").strip() or None
    if "cargo" in payload:
        user.cargo = (payload.get("cargo") or "").strip() or None

    senha = (payload.get("senha") or "").strip()
    if senha:
        user.set_password(senha)

    db.session.commit()
    ApkAuditLog.log_action(
        action_type="update_mobile_user",
        action_result="success",
        admin_id=current_user.matricula,
        user_id=user.matricula,
        details={"updated_fields": [field for field in ["nome", "setor", "cargo", "senha"] if payload.get(field)]},
    )
    return jsonify({"success": True})


@blueprint.post("/mobile-users/<string:matricula>/block")
@login_required
@admin_required
def block_mobile_user(matricula: str):
    user = Usuario.query.get_or_404(matricula)
    payload = request.get_json() or {}
    reason = (payload.get("reason") or "Acesso mobile bloqueado pelo administrador.").strip()

    flag = _get_mobile_access_flag(create=True)
    assignment = FeatureAssignment.query.filter_by(
        feature_flag_id=flag.id,
        target_type="user",
        target_id=user.matricula,
    ).filter(FeatureAssignment.deleted_at.is_(None)).first()

    if assignment is None:
        assignment = FeatureAssignment(
            feature_flag_id=flag.id,
            target_type="user",
            target_id=user.matricula,
            is_enabled=False,
            override_value=reason,
            assigned_by=current_user.matricula,
        )
        db.session.add(assignment)
    else:
        assignment.is_enabled = False
        assignment.override_value = reason
        assignment.assigned_by = current_user.matricula
        assignment.assigned_at = datetime.utcnow()

    active_sessions = DeviceSession.query.filter_by(user_id=user.matricula, status="active").all()
    for session in active_sessions:
        session.revoke(reason=reason, admin_id=current_user.matricula)

    if user.active_session_id and user.active_session_id.startswith("mobile:"):
        user.active_session_id = None

    db.session.commit()
    ApkAuditLog.log_action(
        action_type="block_mobile_user",
        action_result="success",
        admin_id=current_user.matricula,
        user_id=user.matricula,
        details={"reason": reason},
    )
    return jsonify({"success": True})


@blueprint.post("/mobile-users/<string:matricula>/unblock")
@login_required
@admin_required
def unblock_mobile_user(matricula: str):
    user = Usuario.query.get_or_404(matricula)
    assignment_map = _mobile_user_assignment_map()
    assignment = assignment_map.get(user.matricula)
    if assignment:
        assignment.soft_delete()
    db.session.commit()
    ApkAuditLog.log_action(
        action_type="unblock_mobile_user",
        action_result="success",
        admin_id=current_user.matricula,
        user_id=user.matricula,
    )
    return jsonify({"success": True})


@blueprint.post("/mobile-users/<string:matricula>/logout")
@login_required
@admin_required
def logout_mobile_user(matricula: str):
    user = Usuario.query.get_or_404(matricula)
    active_sessions = DeviceSession.query.filter_by(user_id=user.matricula, status="active").all()
    for session in active_sessions:
        session.revoke(reason="Logout forçado pelo administrador", admin_id=current_user.matricula)

    if user.active_session_id and user.active_session_id.startswith("mobile:"):
        user.active_session_id = None

    db.session.commit()
    ApkAuditLog.log_action(
        action_type="force_logout_mobile_user",
        action_result="success",
        admin_id=current_user.matricula,
        user_id=user.matricula,
        details={"sessions": len(active_sessions)},
    )
    return jsonify({"success": True})


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
