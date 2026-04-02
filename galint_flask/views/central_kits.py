from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..services.central_kits_service import central_kits_service


blueprint = Blueprint("central_kits", __name__, url_prefix="/controle-ferramentas/kits")


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