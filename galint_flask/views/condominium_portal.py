from __future__ import annotations

from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..extensions import db
from ..services.condominium_audit import record_condominium_audit
from ..services.condominium.portal import (
    RESIDENT_SESSION_OWNER_ID,
    authenticate_resident_owner,
    build_resident_portal_context,
    create_resident_request_from_form,
    resident_owner_from_session,
)

blueprint = Blueprint("condominium_portal", __name__)


def _current_resident_owner():
    return resident_owner_from_session(session.get(RESIDENT_SESSION_OWNER_ID))


def resident_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        owner = _current_resident_owner()
        if owner is None:
            session.pop(RESIDENT_SESSION_OWNER_ID, None)
            flash("Identifique-se para acessar o Portal do Morador.", "warning")
            return redirect(url_for("condominium_portal.login"))
        return view(owner, *args, **kwargs)

    return wrapper


@blueprint.get("/portal/morador")
def index():
    owner = _current_resident_owner()
    if owner is None:
        return redirect(url_for("condominium_portal.login"))
    return redirect(url_for("condominium_portal.dashboard"))


@blueprint.route("/portal/morador/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            owner = authenticate_resident_owner(
                request.form.get("document_number"),
                request.form.get("unit_number"),
                request.form.get("contact"),
            )
            session[RESIDENT_SESSION_OWNER_ID] = int(owner.id)
            record_condominium_audit(
                action="resident_portal.login",
                entity_type="condominium_owner",
                entity_id=owner.id,
                title=f"Portal do morador acessado: {owner.full_name}",
                actor_matricula=None,
                details={"unit_id": owner.unit_id, "source": "resident_portal"},
            )
            db.session.commit()
            flash("Acesso ao Portal do Morador liberado.", "success")
            return redirect(url_for("condominium_portal.dashboard"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("condominium_portal.login"))
    if _current_resident_owner() is not None:
        return redirect(url_for("condominium_portal.dashboard"))
    return render_template("resident_portal_login.html")


@blueprint.get("/portal/morador/painel")
@resident_required
def dashboard(owner):
    context = build_resident_portal_context(owner)
    record_condominium_audit(
        action="resident_portal.view",
        entity_type="condominium_unit",
        entity_id=owner.unit_id,
        title=f"Portal do morador consultado: {owner.full_name}",
        actor_matricula=None,
        details={"owner_id": owner.id},
    )
    db.session.commit()
    return render_template("resident_portal_dashboard.html", portal=context)


@blueprint.post("/portal/morador/solicitacoes")
@resident_required
def create_request(owner):
    try:
        resident_request = create_resident_request_from_form(
            request.form,
            owner,
            created_ip=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=request.headers.get("User-Agent"),
        )
        db.session.flush()
        record_condominium_audit(
            action="resident_request.create",
            entity_type="condominium_resident_request",
            entity_id=resident_request.id,
            title=f"Solicitacao do morador: {resident_request.title}",
            actor_matricula=None,
            details={"owner_id": owner.id, "unit_id": owner.unit_id, "request_type": resident_request.request_type},
        )
        db.session.commit()
        flash("Solicitacao enviada para a administracao.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("condominium_portal.dashboard"))


@blueprint.post("/portal/morador/logout")
def logout():
    session.pop(RESIDENT_SESSION_OWNER_ID, None)
    flash("Sessao do Portal do Morador encerrada.", "info")
    return redirect(url_for("condominium_portal.login"))
