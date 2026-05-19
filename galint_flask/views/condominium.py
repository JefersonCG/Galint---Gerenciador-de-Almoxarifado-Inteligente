"""Rotas do dominio condominial do GALINT."""
from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import login_required

from ..extensions import db
from ..models import CondominiumBuilding, CondominiumOwner, CondominiumScheduleEvent, ServiceCompany, ServiceProviderEmployee
from ..services.condominium import (
    active_building_options,
    condominium_owner_rows,
    condominium_unit_options,
    create_condominium_owner_from_form,
    lookup_company_owner_payload_by_cnpj,
    owner_attachment_count,
)
from ..services.condominium.dashboard import build_condominium_general_dashboard
from ..services.condominium.portal import update_resident_request_status
from ..services.condominium_audit import record_condominium_audit
from ..services.condominium_dossier import build_unit_dossier_context
from ..services.condominium_gatehouse import build_gatehouse_context, save_gatehouse_access_from_form
from ..services.condominium_operations import (
    build_operations_context,
    save_maintenance_ticket_from_form,
    save_package_from_form,
    update_package_status,
)
from ..services.condominium_service_providers import (
    COMPANY_STATUS_OPTIONS,
    DOCUMENT_TYPE_OPTIONS,
    EMPLOYEE_STATUS_OPTIONS,
    SERVICE_TYPE_OPTIONS,
    WEEKDAY_OPTIONS,
    service_company_document_download_payload,
    service_company_form,
    service_company_rows,
    service_employee_form,
    service_employee_rows,
    save_service_company_from_form,
    save_service_provider_employee_from_form,
)
from ..services.condominium_schedule import (
    build_calendar_context,
    due_schedule_notifications,
    normalize_status,
    now_local_naive,
    today_local,
)
from ..services.condominium_structure import generate_unit_layout, sync_building_units
from .pages import (
    _apply_schedule_event_form,
    _build_admin_service_providers_blueprint,
    _building_form,
    _building_form_from_default,
    _building_summaries,
    _current_user_matricula,
    _default_admin_block,
    _form_int,
    _has_management_access,
    _is_messenger_session,
    _is_registered_admin,
    _mask_sensitive_document,
    _month_date_from_request,
    _parse_iso_date,
    _schedule_event_form,
    _schedule_form_options,
)


blueprint = Blueprint("condominium", __name__)


@blueprint.get("/administracao/condominio/dashboard-geral")
@login_required
def admin_condominium_general_dashboard():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))
    return render_template(
        "condominium_general_dashboard.html",
        dashboard=build_condominium_general_dashboard(),
    )


@blueprint.post("/administracao/condominio/portal/solicitacoes/<int:request_id>/status")
@login_required
def admin_condominium_resident_request_status(request_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    try:
        resident_request = update_resident_request_status(
            request_id,
            request.form.get("status"),
            response_notes=request.form.get("response_notes"),
            actor_matricula=_current_user_matricula(),
        )
        record_condominium_audit(
            action="resident_request.status",
            entity_type="condominium_resident_request",
            entity_id=resident_request.id,
            title=f"Solicitacao do morador atualizada: {resident_request.title}",
            actor_matricula=_current_user_matricula(),
            details={"status": resident_request.status, "owner_id": resident_request.owner_id, "unit_id": resident_request.unit_id},
        )
        db.session.commit()
        flash("Solicitação do morador atualizada.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("condominium.admin_condominium_general_dashboard"))


@blueprint.route("/administracao/condominio/cadastros", methods=["GET", "POST"])
@login_required
def admin_condominium_registry():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))
    if request.method == "POST":
        try:
            owner = create_condominium_owner_from_form(
                request.form,
                request.files,
                actor_matricula=_current_user_matricula(),
            )
            record_condominium_audit(
                action="owner.create",
                entity_type="condominium_owner",
                entity_id=owner.id,
                title=f"Cadastro condominial criado: {owner.full_name}",
                actor_matricula=_current_user_matricula(),
                details={
                    "unit_id": owner.unit_id,
                    "relationship_type": owner.relationship_type,
                    "occupancy_status": owner.occupancy_status,
                    "attachments": owner_attachment_count(owner),
                },
            )
            db.session.commit()
            flash("Cadastro mestre salvo com dossiê, anexos, LGPD e status da unidade atualizados.", "success")
            return redirect(url_for("condominium.admin_condominium_registry"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("condominium.admin_condominium_registry"))
    return render_template(
        "condominium_owners.html",
        buildings=active_building_options(),
        units=condominium_unit_options(),
        owners=condominium_owner_rows(),
        mask_sensitive_document=_mask_sensitive_document,
        owner_attachment_count=owner_attachment_count,
    )


@blueprint.get("/administracao/condominio/api/proprietario/cnpj/<cnpj>")
@login_required
def admin_condominium_owner_cnpj_lookup(cnpj: str):
    if not _has_management_access():
        return jsonify({"success": False, "message": "Acesso restrito."}), 403
    try:
        return jsonify(lookup_company_owner_payload_by_cnpj(cnpj))
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502


@blueprint.route("/administracao/condominio/editor-blocos", methods=["GET", "POST"])
@login_required
def admin_condominium_blocks_editor():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))
    if not _is_registered_admin():
        flash("Somente administrador cadastrado no sistema pode editar os cards dos edifícios.", "danger")
        return redirect(url_for("pages.administration_dashboard"))

    edit_id = request.args.get("editar", type=int)
    model_number = request.args.get("modelo", type=int)
    edit_building = CondominiumBuilding.query.get(edit_id) if edit_id else None
    template_block = _default_admin_block(model_number) if not edit_building else None

    if request.method == "POST":
        building_id = request.form.get("building_id", type=int)
        building = CondominiumBuilding.query.get(building_id) if building_id else CondominiumBuilding()
        if building is None:
            flash("Bloco nao encontrado.", "danger")
            return redirect(url_for("condominium.admin_condominium_blocks_editor"))

        try:
            code = str(request.form.get("code") or "").strip()
            name = str(request.form.get("name") or "").strip()
            display_order = _form_int("display_order", default=0, minimum=0, maximum=999)
            if not name:
                raise ValueError("Informe o nome do edifício.")
            if not code:
                code = f"B{display_order:02d}" if display_order else name[:12].upper()
            duplicate = CondominiumBuilding.query.filter(CondominiumBuilding.code == code).first()
            if duplicate and duplicate.id != building.id:
                raise ValueError("Já existe um edifício com esse código.")

            building.code = code
            building.name = name
            building.display_order = display_order
            building.floor_start = _form_int("floor_start", default=1, minimum=-10, maximum=300)
            building.floor_count = _form_int("floor_count", default=1, minimum=1, maximum=300)
            building.units_per_floor = _form_int("units_per_floor", default=0, minimum=0, maximum=300)
            building.unit_suffix_start = _form_int("unit_suffix_start", default=0, minimum=0, maximum=9999)
            building.suffix_width = _form_int("suffix_width", default=2, minimum=1, maximum=4)
            building.numbering_mode = "floor_suffix"
            building.custom_units_text = str(request.form.get("custom_units_text") or "").strip() or None
            building.notes = str(request.form.get("notes") or "").strip() or None
            building.active = bool(request.form.get("active"))
            building.updated_by_matricula = _current_user_matricula()
            if not building.id:
                building.created_by_matricula = _current_user_matricula()
                db.session.add(building)

            layout = generate_unit_layout(
                floor_start=building.floor_start,
                floor_count=building.floor_count,
                units_per_floor=building.units_per_floor,
                unit_suffix_start=building.unit_suffix_start,
                suffix_width=building.suffix_width,
                custom_units_text=building.custom_units_text or "",
            )
            sync_building_units(building, layout, default_status=request.form.get("initial_status") or "vago")
            db.session.flush()
            record_condominium_audit(
                action="building.save",
                entity_type="condominium_building",
                entity_id=building.id,
                title=f"Edificio salvo: {building.display_name()}",
                actor_matricula=_current_user_matricula(),
                details={"active": building.active, "units": len(layout)},
            )
            db.session.commit()
            flash("Editor de edifícios atualizado.", "success")
            return redirect(url_for("condominium.admin_condominium_blocks_editor"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(
                url_for("condominium.admin_condominium_blocks_editor", editar=building_id)
                if building_id else url_for("condominium.admin_condominium_blocks_editor")
            )

    return render_template(
        "condominium_blocks_editor.html",
        building_form=_building_form(edit_building) if not template_block else _building_form_from_default(template_block),
        building_summaries=_building_summaries(),
        edit_building=edit_building,
    )


@blueprint.post("/administracao/condominio/editor-blocos/<int:building_id>/arquivar")
@login_required
def admin_condominium_archive_building(building_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if not _is_registered_admin():
        flash("Somente administrador cadastrado no sistema pode editar os cards dos edifícios.", "danger")
        return redirect(url_for("pages.administration_dashboard"))
    building = CondominiumBuilding.query.get_or_404(building_id)
    building.active = False
    building.updated_by_matricula = _current_user_matricula()
    for unit in building.units:
        unit.active = False
    record_condominium_audit(
        action="building.archive",
        entity_type="condominium_building",
        entity_id=building.id,
        title=f"Edificio arquivado: {building.display_name()}",
        actor_matricula=_current_user_matricula(),
        details={"unit_count": len(building.units)},
    )
    db.session.commit()
    flash("Edifício arquivado. Ele saiu do dashboard e da lista de unidades ativas.", "info")
    return redirect(url_for("condominium.admin_condominium_blocks_editor"))


@blueprint.post("/administracao/condominio/editor-blocos/<int:building_id>/excluir")
@login_required
def admin_condominium_delete_building(building_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if not _is_registered_admin():
        flash("Somente administrador cadastrado no sistema pode editar os cards dos edifícios.", "danger")
        return redirect(url_for("pages.administration_dashboard"))

    building = CondominiumBuilding.query.get_or_404(building_id)
    actor_id = _current_user_matricula()
    unit_ids = [int(unit.id) for unit in building.units]

    if unit_ids:
        owners = CondominiumOwner.query.filter(CondominiumOwner.unit_id.in_(unit_ids)).all()
        for owner in owners:
            owner.unit_id = None
            owner.updated_by_matricula = actor_id

    related_events = CondominiumScheduleEvent.query.filter(CondominiumScheduleEvent.building_id == building.id).all()
    if unit_ids:
        seen_event_ids = {int(event.id) for event in related_events}
        unit_events = CondominiumScheduleEvent.query.filter(CondominiumScheduleEvent.unit_id.in_(unit_ids)).all()
        for event in unit_events:
            if int(event.id) not in seen_event_ids:
                related_events.append(event)
                seen_event_ids.add(int(event.id))

    for event in related_events:
        if event.building_id == building.id:
            event.building_id = None
        if event.unit_id in unit_ids:
            event.unit_id = None
        event.updated_by_matricula = actor_id

    record_condominium_audit(
        action="building.delete",
        entity_type="condominium_building",
        entity_id=building.id,
        title=f"Edificio excluido: {building.display_name()}",
        actor_matricula=actor_id,
        details={"detached_owners": len(unit_ids), "detached_events": len(related_events)},
    )
    db.session.delete(building)
    db.session.commit()
    flash("Edifício excluído com sucesso.", "info")
    return redirect(url_for("condominium.admin_condominium_blocks_editor"))


@blueprint.route("/administracao/condominio/proprietarios", methods=["GET", "POST"])
@login_required
def admin_condominium_owners():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))

    if request.method == "POST":
        try:
            owner = create_condominium_owner_from_form(
                request.form,
                request.files,
                actor_matricula=_current_user_matricula(),
            )
            record_condominium_audit(
                action="owner.create",
                entity_type="condominium_owner",
                entity_id=owner.id,
                title=f"Cadastro condominial criado: {owner.full_name}",
                actor_matricula=_current_user_matricula(),
                details={
                    "unit_id": owner.unit_id,
                    "relationship_type": owner.relationship_type,
                    "occupancy_status": owner.occupancy_status,
                    "attachments": owner_attachment_count(owner),
                },
            )
            db.session.commit()
            flash("Cadastro mestre salvo com dossiê, anexos, LGPD e status da unidade atualizados.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return redirect(url_for("condominium.admin_condominium_registry"))


@blueprint.post("/administracao/condominio/proprietarios/<int:owner_id>/encerrar")
@login_required
def admin_condominium_close_owner(owner_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    owner = CondominiumOwner.query.get_or_404(owner_id)
    owner.status = "encerrado"
    owner.updated_by_matricula = _current_user_matricula()
    if owner.unit:
        has_active_owner = CondominiumOwner.query.filter(
            CondominiumOwner.unit_id == owner.unit_id,
            CondominiumOwner.id != owner.id,
            CondominiumOwner.status == "ativo",
        ).first()
        if not has_active_owner:
            owner.unit.status = "vago"
    record_condominium_audit(
        action="owner.close",
        entity_type="condominium_owner",
        entity_id=owner.id,
        title=f"Vinculo encerrado: {owner.full_name}",
        actor_matricula=_current_user_matricula(),
        details={"unit_id": owner.unit_id, "relationship_type": owner.relationship_type},
    )
    db.session.commit()
    flash("Vinculo encerrado.", "info")
    return redirect(url_for("condominium.admin_condominium_registry"))


@blueprint.route("/administracao/condominio/agendamentos", methods=["GET", "POST"])
@login_required
def admin_condominium_schedule():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))

    if request.method == "POST":
        event_id = request.form.get("event_id", type=int)
        event = CondominiumScheduleEvent.query.get(event_id) if event_id else CondominiumScheduleEvent()
        if event is None:
            flash("Compromisso nao encontrado.", "danger")
            return redirect(url_for("condominium.admin_condominium_schedule"))
        try:
            if not event.id:
                event.created_by_matricula = _current_user_matricula()
                db.session.add(event)
            _apply_schedule_event_form(event)
            db.session.flush()
            record_condominium_audit(
                action="schedule.save",
                entity_type="condominium_schedule_event",
                entity_id=event.id,
                title=f"Agenda salva: {event.title}",
                actor_matricula=_current_user_matricula(),
                details={"unit_id": event.unit_id, "building_id": event.building_id, "event_date": event.event_date.isoformat()},
            )
            db.session.commit()
            flash("Compromisso salvo na agenda.", "success")
            return redirect(url_for("condominium.admin_condominium_schedule", data=event.event_date.isoformat(), mes=event.event_date.strftime("%Y-%m")))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("condominium.admin_condominium_schedule", data=request.form.get("event_date") or today_local().isoformat(), editar=event_id or None))

    selected_date = _parse_iso_date(request.args.get("data"), default=today_local())
    month_date = _month_date_from_request(selected_date)
    edit_id = request.args.get("editar", type=int)
    edit_event = CondominiumScheduleEvent.query.get(edit_id) if edit_id else None
    return render_template(
        "condominium_schedule.html",
        calendar_page=build_calendar_context(month_date=month_date, selected_date=selected_date),
        form_options=_schedule_form_options(),
        event_form=_schedule_event_form(edit_event, selected_date=selected_date),
        edit_event=edit_event,
        agenda_notifications=due_schedule_notifications(),
    )


@blueprint.post("/administracao/condominio/agendamentos/<int:event_id>/status")
@login_required
def admin_condominium_schedule_status(event_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    event = CondominiumScheduleEvent.query.get_or_404(event_id)
    event.status = normalize_status(request.form.get("status"))
    event.updated_by_matricula = _current_user_matricula()
    record_condominium_audit(
        action="schedule.status",
        entity_type="condominium_schedule_event",
        entity_id=event.id,
        title=f"Status da agenda atualizado: {event.title}",
        actor_matricula=_current_user_matricula(),
        details={"status": event.status, "unit_id": event.unit_id},
    )
    db.session.commit()
    flash("Status do compromisso atualizado.", "success")
    return redirect(url_for("condominium.admin_condominium_schedule", data=event.event_date.isoformat(), mes=event.event_date.strftime("%Y-%m")))


@blueprint.post("/administracao/condominio/agendamentos/<int:event_id>/notificacao")
@login_required
def admin_condominium_schedule_acknowledge(event_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    event = CondominiumScheduleEvent.query.get_or_404(event_id)
    event.notification_acknowledged_at = now_local_naive()
    event.updated_by_matricula = _current_user_matricula()
    record_condominium_audit(
        action="schedule.notification_ack",
        entity_type="condominium_schedule_event",
        entity_id=event.id,
        title=f"Notificacao confirmada: {event.title}",
        actor_matricula=_current_user_matricula(),
        details={"unit_id": event.unit_id, "event_date": event.event_date.isoformat()},
    )
    db.session.commit()
    flash("Notificacao da agenda confirmada.", "info")
    return redirect(request.referrer or url_for("condominium.admin_condominium_schedule", data=event.event_date.isoformat()))


@blueprint.route("/administracao/condominio/prestadores", methods=["GET", "POST"])
@login_required
def admin_service_providers():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))

    if request.method == "POST":
        company_id = request.form.get("company_id", type=int)
        company = ServiceCompany.query.get(company_id) if company_id else None
        try:
            saved_company = save_service_company_from_form(
                request.form,
                actor_matricula=_current_user_matricula(),
                company=company,
                files=request.files,
            )
            db.session.flush()
            record_condominium_audit(
                action="service_company.save",
                entity_type="service_company",
                entity_id=saved_company.id,
                title=f"Prestadora salva: {saved_company.display_name()}",
                actor_matricula=_current_user_matricula(),
                details={"status": saved_company.status, "cnpj": saved_company.cnpj},
            )
            db.session.commit()
            flash("Empresa prestadora salva com sucesso.", "success")
            return redirect(url_for("condominium.admin_service_providers", empresa=saved_company.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("condominium.admin_service_providers", editar=company_id) if company_id else url_for("condominium.admin_service_providers"))

    edit_id = request.args.get("editar", type=int)
    selected_company_id = request.args.get("empresa", type=int) or edit_id
    edit_company = ServiceCompany.query.get(edit_id) if edit_id else None

    return render_template(
        "config_service_providers_blueprint.html",
        service_provider_page=_build_admin_service_providers_blueprint(),
        company_rows=service_company_rows(
            search=str(request.args.get("q") or "").strip(),
            status=str(request.args.get("status") or "").strip(),
            service_type=str(request.args.get("tipo") or "").strip(),
        ),
        employee_rows=service_employee_rows(selected_company_id),
        company_form=service_company_form(edit_company),
        employee_form=service_employee_form(selected_company_id),
        edit_company=edit_company,
        selected_company_id=selected_company_id,
        service_type_options=SERVICE_TYPE_OPTIONS,
        company_status_options=COMPANY_STATUS_OPTIONS,
        document_type_options=DOCUMENT_TYPE_OPTIONS,
        employee_status_options=EMPLOYEE_STATUS_OPTIONS,
        weekday_options=WEEKDAY_OPTIONS,
        filters={
            "q": str(request.args.get("q") or "").strip(),
            "status": str(request.args.get("status") or "").strip(),
            "tipo": str(request.args.get("tipo") or "").strip(),
        },
    )


@blueprint.post("/administracao/condominio/prestadores/funcionarios")
@login_required
def admin_service_provider_employee_create():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    try:
        employee = save_service_provider_employee_from_form(
            request.form,
            actor_matricula=_current_user_matricula(),
        )
        db.session.flush()
        record_condominium_audit(
            action="service_employee.save",
            entity_type="service_provider_employee",
            entity_id=employee.id,
            title=f"Prestador vinculado: {employee.full_name}",
            actor_matricula=_current_user_matricula(),
            details={"company_id": employee.company_id, "status": employee.status},
        )
        db.session.commit()
        flash("Funcionário/prestador vinculado com sucesso.", "success")
        return redirect(url_for("condominium.admin_service_providers", empresa=employee.company_id))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("condominium.admin_service_providers", empresa=request.form.get("company_id") or None))


@blueprint.post("/administracao/condominio/prestadores/<int:company_id>/desativar")
@login_required
def admin_service_provider_company_deactivate(company_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    company = ServiceCompany.query.get_or_404(company_id)
    company.status = "inativo"
    company.updated_by_matricula = _current_user_matricula()
    for employee in company.employees:
        if employee.status == "ativo":
            employee.status = "inativo"
            employee.updated_by_matricula = _current_user_matricula()
    record_condominium_audit(
        action="service_company.deactivate",
        entity_type="service_company",
        entity_id=company.id,
        title=f"Prestadora desativada: {company.display_name()}",
        actor_matricula=_current_user_matricula(),
        details={"employees": len(company.employees)},
    )
    db.session.commit()
    flash("Empresa prestadora desativada. Funcionários ativos foram marcados como inativos.", "info")
    return redirect(url_for("condominium.admin_service_providers"))


@blueprint.post("/administracao/condominio/prestadores/funcionarios/<int:employee_id>/status")
@login_required
def admin_service_provider_employee_status(employee_id: int):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    employee = ServiceProviderEmployee.query.get_or_404(employee_id)
    requested_status = str(request.form.get("status") or "").strip().lower()
    employee.status = requested_status if requested_status in {"ativo", "bloqueado", "inativo"} else "ativo"
    employee.updated_by_matricula = _current_user_matricula()
    record_condominium_audit(
        action="service_employee.status",
        entity_type="service_provider_employee",
        entity_id=employee.id,
        title=f"Status do prestador atualizado: {employee.full_name}",
        actor_matricula=_current_user_matricula(),
        details={"company_id": employee.company_id, "status": employee.status},
    )
    db.session.commit()
    flash("Status do funcionário/prestador atualizado.", "success")
    return redirect(url_for("condominium.admin_service_providers", empresa=employee.company_id))


@blueprint.get("/administracao/condominio/prestadores/<int:company_id>/documentos/<document_key>")
@login_required
def admin_service_provider_document_download(company_id: int, document_key: str):
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    company = ServiceCompany.query.get_or_404(company_id)
    payload = service_company_document_download_payload(company, document_key)
    if payload is None:
        flash("Documento da prestadora não encontrado.", "warning")
        return redirect(url_for("condominium.admin_service_providers", editar=company.id, empresa=company.id))
    record_condominium_audit(
        action="service_company.document_download",
        entity_type="service_company",
        entity_id=company.id,
        title=f"Download de documento da prestadora: {company.display_name()}",
        actor_matricula=_current_user_matricula(),
        details={"document_key": document_key},
    )
    db.session.commit()
    return send_file(payload["path"], as_attachment=True, download_name=str(payload["download_name"]))


@blueprint.get("/administracao/condominio/dossie")
@login_required
def admin_condominium_dossier():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))

    selected_unit_id = request.args.get("unidade", type=int)
    context = build_unit_dossier_context(
        selected_unit_id,
        query=str(request.args.get("q") or "").strip(),
        status=str(request.args.get("status") or "").strip(),
    )
    selected = context.get("selected")
    if selected:
        unit = selected["unit_card"]["unit"]
        record_condominium_audit(
            action="unit_dossier.view",
            entity_type="condominium_unit",
            entity_id=unit.id,
            title=f"Dossie consultado: {unit.full_label()}",
            actor_matricula=_current_user_matricula(),
            details={"query": context["filters"]["q"], "status": context["filters"]["status"]},
        )
        db.session.commit()
    return render_template(
        "condominium_unit_dossier.html",
        dossier=context,
        mask_sensitive_document=_mask_sensitive_document,
    )


@blueprint.route("/administracao/condominio/portaria", methods=["GET", "POST"])
@login_required
def admin_condominium_gatehouse():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))
    if _is_messenger_session():
        return redirect(url_for("pages.mensageria_maintenance"))

    if request.method == "POST":
        try:
            access_log = save_gatehouse_access_from_form(request.form, actor_matricula=_current_user_matricula())
            db.session.flush()
            record_condominium_audit(
                action="gatehouse.access_log",
                entity_type="condominium_access_log",
                entity_id=access_log.id,
                title=f"Portaria registrou {access_log.direction_label().lower()}: {access_log.person_name}",
                actor_matricula=_current_user_matricula(),
                details={
                    "direction": access_log.direction,
                    "status": access_log.access_status,
                    "person_type": access_log.person_type,
                    "unit_id": access_log.unit_id,
                    "owner_id": access_log.owner_id,
                    "service_employee_id": access_log.service_employee_id,
                },
            )
            db.session.commit()
            flash(f"Portaria registrada: {access_log.direction_label()} de {access_log.person_name}.", "success")
            return redirect(url_for("condominium.admin_condominium_gatehouse", q=request.form.get("return_query") or ""))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("condominium.admin_condominium_gatehouse", q=request.form.get("return_query") or ""))

    context = build_gatehouse_context(
        query=str(request.args.get("q") or "").strip(),
        status=str(request.args.get("status") or "").strip(),
    )
    return render_template(
        "condominium_gatehouse.html",
        gatehouse=context,
        mask_sensitive_document=_mask_sensitive_document,
    )


@blueprint.route("/administracao/condominio/operacao", methods=["GET", "POST"])
@blueprint.route("/administracao/condominio/mensageria", methods=["GET", "POST"])
@login_required
def admin_condominium_operations():
    if not _has_management_access():
        flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        action = str(request.form.get("action") or "").strip()
        try:
            if action == "ticket_create":
                ticket = save_maintenance_ticket_from_form(request.form, actor_matricula=_current_user_matricula())
                db.session.flush()
                record_condominium_audit(
                    action="maintenance_ticket.create",
                    entity_type="condominium_maintenance_ticket",
                    entity_id=ticket.id,
                    title=f"Chamado criado: {ticket.title}",
                    actor_matricula=_current_user_matricula(),
                    details={"unit_id": ticket.unit_id, "status": ticket.status, "priority": ticket.priority},
                )
                db.session.commit()
                flash("Chamado de manutenção criado.", "success")
            elif action == "package_create":
                package = save_package_from_form(request.form, actor_matricula=_current_user_matricula())
                db.session.flush()
                record_condominium_audit(
                    action="package.create",
                    entity_type="condominium_package_log",
                    entity_id=package.id,
                    title=f"Recebimento registrado: {package.recipient_name}",
                    actor_matricula=_current_user_matricula(),
                    details={"unit_id": package.unit_id, "status": package.status, "tracking_code": package.tracking_code},
                )
                db.session.commit()
                flash("Recebimento da mensageria registrado.", "success")
            elif action == "package_status":
                package = update_package_status(
                    request.form.get("package_id", type=int),
                    request.form.get("status"),
                    actor_matricula=_current_user_matricula(),
                    delivered_to=request.form.get("delivered_to"),
                )
                record_condominium_audit(
                    action="package.status",
                    entity_type="condominium_package_log",
                    entity_id=package.id,
                    title=f"Status de mensageria atualizado: {package.recipient_name}",
                    actor_matricula=_current_user_matricula(),
                    details={"status": package.status, "unit_id": package.unit_id, "delivered_to": package.delivered_to},
                )
                db.session.commit()
                flash("Status da mensageria atualizado.", "success")
            else:
                raise ValueError("Ação operacional inválida.")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        return redirect(url_for("condominium.admin_condominium_operations"))

    return render_template("condominium_operations.html", operations=build_operations_context())


@blueprint.get("/configuracoes/condominio/cadastros")
@login_required
def legacy_admin_condominium_registry():
    return redirect(url_for("condominium.admin_condominium_registry"))


@blueprint.get("/configuracoes/condominio/agendamentos")
@login_required
def legacy_admin_condominium_schedule():
    return redirect(url_for("condominium.admin_condominium_schedule"))


@blueprint.get("/configuracoes/condominio/dossie")
@login_required
def legacy_admin_condominium_dossier():
    return redirect(url_for("condominium.admin_condominium_dossier"))


@blueprint.get("/configuracoes/condominio/portaria")
@login_required
def legacy_admin_condominium_gatehouse():
    return redirect(url_for("condominium.admin_condominium_gatehouse"))


@blueprint.get("/configuracoes/condominio/operacao")
@login_required
def legacy_admin_condominium_operations():
    return redirect(url_for("condominium.admin_condominium_operations"))


@blueprint.get("/configuracoes/condominio/prestadores")
@login_required
def legacy_admin_service_providers():
    return redirect(url_for("condominium.admin_service_providers"))