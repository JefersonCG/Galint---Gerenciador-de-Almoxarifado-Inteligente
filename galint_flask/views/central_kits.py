from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..services.central_kits_service import central_kits_service


blueprint = Blueprint("central_kits", __name__, url_prefix="/controle-ferramentas/kits")


def _current_user_is_admin() -> bool:
    try:
        return int(getattr(current_user, "is_admin", 0) or 0) == 1
    except (TypeError, ValueError):
        return False


def _build_photo_url(photo_path: str | None) -> str | None:
    if not photo_path:
        return None
    return url_for("static", filename=photo_path)


def _serialize_assignment_row(row: dict) -> dict:
    payload = dict(row)
    payload["foto_url"] = _build_photo_url(payload.get("foto_path"))
    return payload


def _require_admin_json():
    if not _current_user_is_admin():
        return jsonify({"success": False, "message": "Acesso negado."}), 403
    return None


@blueprint.get("/")
@login_required
def index():
    search = (request.args.get("search") or "").strip()
    group_filter = (request.args.get("group") or "todos").strip() or "todos"
    custody_filter = (request.args.get("custody") or "todos").strip() or "todos"
    alert_only = (request.args.get("alert_only") or "").strip().lower() == "true"

    dashboard = central_kits_service.get_dashboard(
        search=search,
        group_filter=group_filter,
        custody_filter=custody_filter,
        alert_only=alert_only,
    )

    return render_template(
        "central_kits/index.html",
        kits=dashboard["kits"],
        stats=dashboard["stats"],
        groups=dashboard["groups"],
        search=search,
        group_filter=group_filter,
        custody_filter=custody_filter,
        alert_only=alert_only,
    )


@blueprint.get("/<matricula>")
@login_required
def detail(matricula: str):
    kit = central_kits_service.get_kit_detail(matricula)
    if kit is None:
        flash("Kit não encontrado para este colaborador.", "warning")
        return redirect(url_for("central_kits.index"))

    return render_template("central_kits/detail.html", kit=kit)


@blueprint.get("/<matricula>/associacao")
@login_required
def assignment_data(matricula: str):
    search = (request.args.get("search") or "").strip()
    payload = central_kits_service.get_assignment_modal_payload(matricula, search=search)
    if payload is None:
        return jsonify({"success": False, "message": "Kit não encontrado para este colaborador."}), 404

    return jsonify(
        {
            "success": True,
            "can_manage": _current_user_is_admin(),
            "employee": payload["employee"],
            "available_tools": [_serialize_assignment_row(row) for row in payload.get("available_tools", [])],
            "assigned_tools": [_serialize_assignment_row(row) for row in payload.get("assigned_tools", [])],
            "search": payload.get("search", ""),
        }
    )


@blueprint.post("/<matricula>/associacao")
@login_required
def assignment_save(matricula: str):
    access_error = _require_admin_json()
    if access_error is not None:
        return access_error

    payload = request.get_json(silent=True) or {}
    additions = payload.get("additions") or []
    removals = payload.get("removals") or []

    try:
        result = central_kits_service.apply_assignment_changes(
            matricula,
            additions=additions,
            removals=removals,
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    success = len(result.get("errors", [])) == 0
    message = "Associação atualizada com sucesso."
    if not success and result.get("applied_changes"):
        message = "Alterações aplicadas parcialmente. Revise os avisos retornados."
    elif not success:
        message = result.get("errors", ["Nenhuma alteração foi aplicada."])[0]

    return jsonify(
        {
            "success": success,
            "message": message,
            "details": result,
        }
    )