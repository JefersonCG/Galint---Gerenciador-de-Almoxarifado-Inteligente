"""Rotas para gerenciamento da fila de contingência (cadastros off-line)."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..services.contingency import contingency_service

blueprint = Blueprint("contingency", __name__, url_prefix="/contingencia")


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


@blueprint.get("/")
@login_required
def index():
    _require_admin()
    entries = contingency_service.list_entries()
    return render_template("contingency/index.html", entries=entries)


@blueprint.post("/sync")
@login_required
def sync_queue():
    _require_admin()
    result = contingency_service.sync_queue()
    flash(f"Sincronização concluída: {result.get('sucesso')} criados, {result.get('erros')} erros.", "success")
    return redirect(url_for("contingency.index"))


@blueprint.post("/<int:entry_id>/delete")
@login_required
def delete_entry(entry_id: int):
    _require_admin()
    try:
        contingency_service.delete_entry(entry_id)
        flash("Registro de contingência removido.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("contingency.index"))
