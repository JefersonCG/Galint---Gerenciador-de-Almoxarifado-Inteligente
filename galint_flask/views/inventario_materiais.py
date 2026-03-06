"""Rotas gerenciando o Inventário de Materiais Danificados."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, current_app, send_from_directory
from flask_login import current_user, login_required

from ..services.inventario_materiais import material_inventory_service
from ..services.inventory import inventory_service


blueprint = Blueprint("inventario_materiais", __name__, url_prefix="/inventario-materiais")


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


@blueprint.get("/")
@login_required
def index():
    _require_admin()
    entries = material_inventory_service.list_reports()
    saidas = material_inventory_service.list_available_saidas()
    return render_template("inventario_materiais/index.html", entries=entries, saidas=saidas)


@blueprint.post("/")
@login_required
def register_damage():
    _require_admin()
    saida_id = request.form.get("saida_id")
    quantidade = request.form.get("quantidade")
    descricao = request.form.get("descricao")
    observacoes = request.form.get("observacoes")
    if not saida_id or not quantidade:
        flash("Informe a saída e a quantidade.", "warning")
        return redirect(url_for("inventario_materiais.index"))
    try:
        material_inventory_service.record_damage(
            int(saida_id), int(quantidade), descricao, observacoes
        )
        flash("Registro salvo no Inventário de Materiais Danificados.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("inventario_materiais.index"))


@blueprint.get("/avariados")
@login_required
def avariados():
    _require_admin()
    entries = material_inventory_service.list_reports(limit=500)
    authorizations = material_inventory_service.list_authorizations(limit=10)
    inventory_items = inventory_service.list_items()
    return render_template(
        "inventario_materiais/avariados.html",
        entries=entries,
        authorizations=authorizations,
        inventory_items=inventory_items,
    )


@blueprint.post("/avariados/autorizar")
@login_required
def autorizar_avariados():
    _require_admin()
    gerente = request.form.get("gerente_nome")
    comentario = request.form.get("comentario")
    relatorio_html = request.form.get("relatorio_html")
    entries = material_inventory_service.list_reports(limit=500)
    try:
        material_inventory_service.authorize_disposal(gerente, comentario, relatorio_html, entries)
        flash("Relatório autorizado e salvo como Word.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("inventario_materiais.avariados"))


@blueprint.get("/relatorios/<path:filename>")
@login_required
def download_relatorio(filename):
    _require_admin()
    reports_dir = Path(current_app.instance_path) / "reports"
    if not reports_dir.exists():
        abort(404)
    safe_name = Path(filename).name
    return send_from_directory(str(reports_dir), safe_name, as_attachment=True)


