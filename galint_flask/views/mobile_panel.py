"""Painel Mobile (admin)."""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, jsonify, render_template
from flask import current_app


from flask_login import current_user, login_required


blueprint = Blueprint("mobile_panel", __name__, url_prefix="/mobile-panel")


def _mobile_panel_enabled() -> bool:
    return bool(current_app.config.get("FEATURE_MOBILE_PANEL_ENABLED", False))


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not _mobile_panel_enabled():
            return jsonify({"error": "Painel mobile desativado"}), 404
        if not current_user.is_authenticated or not bool(getattr(current_user, "is_admin", False)):
            return jsonify({"error": "Acesso negado. Apenas administradores."}), 403
        return view(*args, **kwargs)

    return wrapper


@blueprint.get("/")
@login_required
@admin_required
def dashboard():
    return render_template("mobile_panel/dashboard.html")


@blueprint.get("/devices")
@login_required
@admin_required
def devices():
    return render_template("mobile_panel/devices.html")


@blueprint.get("/versions")
@login_required
@admin_required
def versions():
    return render_template("mobile_panel/versions.html")


@blueprint.get("/features")
@login_required
@admin_required
def features():
    return render_template("mobile_panel/features.html")


@blueprint.get("/audit")
@login_required
@admin_required
def audit():
    return render_template("mobile_panel/audit.html")
