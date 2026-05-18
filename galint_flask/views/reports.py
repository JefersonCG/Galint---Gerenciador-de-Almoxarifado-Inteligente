"""Views da Pesquisa geral e aliases legados de relatorios."""
from __future__ import annotations

import unicodedata
import re
from io import BytesIO
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, jsonify, redirect, request, send_file, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from galint_flask.utils.time_service import TimeService

from ..services.general_search_service import general_search_service
from ..models import CondominiumBuilding, CondominiumOwner, CondominiumScheduleEvent, CondominiumUnit
from ..services.condominium_schedule import event_to_view

bp = Blueprint("reports", __name__, url_prefix="/relatorios")


def _redirect_reports_surface(*, message: str | None = None, category: str = "info", **query_args):
    target_endpoint = "analytics.index" if bool(getattr(current_user, "is_admin", 0)) else "dashboard.index"
    if message:
        flash(message, category)
    return redirect(url_for(target_endpoint, **query_args))


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _get_item_value(item: object, key: str, default: object = None) -> object:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _format_codigo_barra(value: object) -> str:
    if value is None:
        return "N/D"
    text = str(value).strip()
    if not text:
        return "N/D"
    return text[-4:] if len(text) >= 4 else text


def _normalize_search(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_compact(value: object) -> str:
    normalized = _normalize_search(str(value or "")).upper()
    return re.sub(r"[^A-Z0-9]", "", normalized)


def _has_administration_search_access() -> bool:
    if not bool(getattr(current_user, "is_authenticated", False)):
        return False
    admin_value = getattr(current_user, "is_admin", 0)
    if str(admin_value or "").strip().lower() in {"1", "true", "sim", "yes"}:
        return True
    return bool(session.get("galint_management_access")) and str(session.get("galint_management_module") or "").strip().lower() == "administracao"


def _owner_unit_label(owner: CondominiumOwner) -> str:
    if owner.unit:
        return owner.unit.full_label()
    return "Sem unidade vinculada"


def _event_date_label(event: CondominiumScheduleEvent) -> str:
    return event.event_date.strftime("%d/%m/%Y") if event.event_date else "Sem data"


def _admin_like_filters(search_term: str):
    like_term = f"%{search_term}%"
    compact_term = _normalize_compact(search_term)
    return like_term, compact_term


def _extract_plate_matches(text: object, fallback_query: str = "") -> list[str]:
    source = _normalize_compact(text)
    matches = re.findall(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", source)
    query = _normalize_compact(fallback_query)
    if query and len(query) >= 5 and query in source and query not in matches:
        matches.append(query)
    return matches[:4]


def _admin_search_payload(query: str, *, limit: int = 12) -> dict[str, object]:
    search_term = str(query or "").strip()
    limit = max(int(limit or 0), 1)
    like_term, compact_term = _admin_like_filters(search_term)

    owners_query = (
        CondominiumOwner.query
        .outerjoin(CondominiumUnit, CondominiumOwner.unit_id == CondominiumUnit.id)
        .outerjoin(CondominiumBuilding, CondominiumUnit.building_id == CondominiumBuilding.id)
    )
    if search_term:
        owners_query = owners_query.filter(
            or_(
                CondominiumOwner.full_name.ilike(like_term),
                CondominiumOwner.document_number.ilike(like_term),
                CondominiumOwner.rg.ilike(like_term),
                CondominiumOwner.cnh.ilike(like_term),
                CondominiumOwner.phone.ilike(like_term),
                CondominiumOwner.email.ilike(like_term),
                CondominiumOwner.emergency_contact.ilike(like_term),
                CondominiumOwner.notes.ilike(like_term),
                CondominiumUnit.number.ilike(like_term),
                CondominiumBuilding.code.ilike(like_term),
                CondominiumBuilding.name.ilike(like_term),
            )
        )
    owners = owners_query.order_by(CondominiumOwner.status.asc(), CondominiumOwner.full_name.asc()).limit(limit).all()

    units_query = CondominiumUnit.query.join(CondominiumBuilding, CondominiumUnit.building_id == CondominiumBuilding.id)
    if search_term:
        units_query = units_query.filter(
            or_(
                CondominiumUnit.number.ilike(like_term),
                CondominiumUnit.status.ilike(like_term),
                CondominiumUnit.notes.ilike(like_term),
                CondominiumBuilding.code.ilike(like_term),
                CondominiumBuilding.name.ilike(like_term),
            )
        )
    units = units_query.order_by(CondominiumBuilding.display_order.asc(), CondominiumUnit.floor_number.asc(), CondominiumUnit.position.asc()).limit(limit).all()

    events_query = (
        CondominiumScheduleEvent.query
        .outerjoin(CondominiumUnit, CondominiumScheduleEvent.unit_id == CondominiumUnit.id)
        .outerjoin(CondominiumBuilding, CondominiumScheduleEvent.building_id == CondominiumBuilding.id)
        .outerjoin(CondominiumOwner, CondominiumScheduleEvent.owner_id == CondominiumOwner.id)
    )
    if search_term:
        events_query = events_query.filter(
            or_(
                CondominiumScheduleEvent.title.ilike(like_term),
                CondominiumScheduleEvent.event_type.ilike(like_term),
                CondominiumScheduleEvent.scope.ilike(like_term),
                CondominiumScheduleEvent.status.ilike(like_term),
                CondominiumScheduleEvent.contact_name.ilike(like_term),
                CondominiumScheduleEvent.contact_phone.ilike(like_term),
                CondominiumScheduleEvent.location.ilike(like_term),
                CondominiumScheduleEvent.description.ilike(like_term),
                CondominiumUnit.number.ilike(like_term),
                CondominiumBuilding.code.ilike(like_term),
                CondominiumBuilding.name.ilike(like_term),
                CondominiumOwner.full_name.ilike(like_term),
            )
        )
    events = events_query.order_by(CondominiumScheduleEvent.event_date.desc(), CondominiumScheduleEvent.start_time.asc()).limit(limit).all()

    owner_rows = [
        {
            "id": owner.id,
            "title": owner.full_name,
            "subtitle": _owner_unit_label(owner),
            "badge": owner.relationship_type.replace("_", " ").title(),
            "document": owner.document_number,
            "phone": owner.phone,
            "email": owner.email,
            "status": owner.status,
            "unit_label": _owner_unit_label(owner),
            "url": url_for("condominium.admin_condominium_registry"),
        }
        for owner in owners
    ]

    unit_rows = [
        {
            "id": unit.id,
            "title": unit.full_label(),
            "subtitle": f"Status {unit.status or 'N/D'}",
            "badge": unit.status,
            "number": unit.number,
            "building": unit.building.display_name() if unit.building else "Bloco",
            "floor": unit.floor_number,
            "owner_count": len([owner for owner in unit.owners if owner.status == "ativo"]),
            "url": url_for("condominium.admin_condominium_blocks_editor", editar=unit.building_id) if unit.building_id else url_for("condominium.admin_condominium_blocks_editor"),
        }
        for unit in units
    ]

    event_rows = []
    for event in events:
        view = event_to_view(event)
        event_rows.append(
            {
                **view,
                "title": event.title,
                "subtitle": f"{_event_date_label(event)} · {event.time_label()} · {event.related_label()}",
                "badge": view.get("event_type_label"),
                "date_label": _event_date_label(event),
                "url": url_for("condominium.admin_condominium_schedule", data=event.event_date.isoformat()) if event.event_date else url_for("condominium.admin_condominium_schedule"),
            }
        )

    vehicle_matches: list[dict[str, object]] = []
    if compact_term:
        for owner in owners:
            context = " ".join(str(value or "") for value in (owner.notes, owner.cnh, owner.emergency_contact))
            plates = _extract_plate_matches(context, search_term)
            if plates or compact_term in _normalize_compact(context):
                vehicle_matches.append(
                    {
                        "title": owner.full_name,
                        "subtitle": _owner_unit_label(owner),
                        "badge": ", ".join(plates) if plates else "Cadastro",
                        "source": "Morador/proprietário",
                        "context": context[:220],
                        "url": url_for("condominium.admin_condominium_registry"),
                    }
                )
        for event in events:
            context = " ".join(str(value or "") for value in (event.title, event.location, event.description, event.contact_name, event.contact_phone))
            plates = _extract_plate_matches(context, search_term)
            if plates or compact_term in _normalize_compact(context):
                vehicle_matches.append(
                    {
                        "title": event.title,
                        "subtitle": f"{_event_date_label(event)} · {event.related_label()}",
                        "badge": ", ".join(plates) if plates else "Agenda",
                        "source": "Agenda",
                        "context": context[:220],
                        "url": url_for("condominium.admin_condominium_schedule", data=event.event_date.isoformat()) if event.event_date else url_for("condominium.admin_condominium_schedule"),
                    }
                )
    vehicle_matches = vehicle_matches[:limit]

    suggestions = []
    for row in owner_rows[:5]:
        suggestions.append({"entity_type": "morador", **row})
    for row in unit_rows[:4]:
        suggestions.append({"entity_type": "unidade", **row})
    for row in vehicle_matches[:3]:
        suggestions.append({"entity_type": "placa", **row})
    for row in event_rows[:4]:
        suggestions.append({"entity_type": "agenda", **row})

    return {
        "scope": "administracao",
        "query": search_term,
        "results": suggestions[:limit],
        "owners": owner_rows,
        "units": unit_rows,
        "vehicles": vehicle_matches,
        "events": event_rows,
        "summary": {
            "owners_count": len(owner_rows),
            "units_count": len(unit_rows),
            "vehicles_count": len(vehicle_matches),
            "events_count": len(event_rows),
        },
    }


def _parse_period_days_arg(raw_value: object, *, default: int = 0) -> int:
    try:
        return int(str(raw_value or default).strip())
    except (TypeError, ValueError):
        return default


def _generate_item_report_pdf(*, item, saidas, period_days: int, time_service) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise ValueError(
            "Biblioteca de PDF nao instalada. Instale 'reportlab' (pip install reportlab)."
        ) from exc

    from ..utils.report_branding import get_company_header_html

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
        title="Relatorio por item",
        author="GALINT",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 8
    body_style.leading = 9
    story = []

    title_style = styles["Title"]
    title_style.alignment = 1
    title_style.fontSize = 16
    subtitle_style = styles["Normal"]
    subtitle_style.alignment = 1

    story.append(Paragraph("RELATORIO DE RETIRADAS POR ITEM", title_style))
    story.append(Paragraph(get_company_header_html(), subtitle_style))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(f"Gerado em: {TimeService.now_local().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))

    period_label = "Todo historico" if period_days <= 0 else f"Ultimos {period_days} dias"
    item_descricao = _get_item_value(item, "descricao")
    item_codigo = _get_item_value(item, "codigo") or _get_item_value(item, "codigo_item")
    item_categoria = _get_item_value(item, "categoria")
    item_marca = _get_item_value(item, "marca")
    total_quantity = sum(float(getattr(row, "quantidade", 0) or 0) for row in saidas) if saidas else 0

    story.append(Paragraph(f"Item: <b>{_safe_text(item_descricao)}</b>", styles["Normal"]))
    story.append(Paragraph(f"Codigo: {_format_codigo_barra(item_codigo)}", styles["Normal"]))
    story.append(Paragraph(f"Categoria: {_safe_text(item_categoria or 'N/D')}", styles["Normal"]))
    story.append(Paragraph(f"Marca: {_safe_text(item_marca or 'N/D')}", styles["Normal"]))
    story.append(Paragraph(f"Periodo: {period_label}", styles["Normal"]))
    story.append(Paragraph(f"Total de movimentacoes: {len(saidas)}", styles["Normal"]))
    story.append(Paragraph(f"Quantidade total movimentada: {total_quantity}", styles["Normal"]))
    story.append(Spacer(1, 0.4 * cm))

    header = ["Data", "Hora", "Usuario", "Qtd.", "Periodo", "Local"]
    data = [header]
    for saida in saidas:
        local_info = getattr(saida, "local_servico", None) or "N/D"
        observacao = getattr(saida, "observacao", None)
        if observacao and str(observacao).strip():
            local_info = f"{local_info} | {str(observacao).strip()}"
        usuario_nome = getattr(saida, "usuario_nome", None)
        saida_matricula = getattr(saida, "saida_matricula", None)
        if not usuario_nome and saida_matricula:
            usuario_nome = f"Matricula {saida_matricula}"
        data.append(
            [
                time_service.format_local(saida.data_saida, "%d/%m/%Y"),
                time_service.format_local(saida.data_saida, "%H:%M"),
                Paragraph(_safe_text(usuario_nome or "N/D"), body_style),
                _safe_text(getattr(saida, "quantidade", "")),
                _safe_text(time_service.get_business_day_tag(saida.data_saida) or "Expediente"),
                Paragraph(_safe_text(local_info[:200]), body_style),
            ]
        )

    if len(data) == 1:
        story.append(Paragraph("Nenhuma retirada registrada para este item.", styles["Italic"]))
        doc.build(story)
        return buffer.getvalue()

    table = Table(
        data,
        colWidths=[2.2 * cm, 1.6 * cm, 8.5 * cm, 1.5 * cm, 3.0 * cm, 11.9 * cm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def _generate_usuario_report_pdf(*, usuario, saidas, period_days: int, time_service) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise ValueError(
            "Biblioteca de PDF nao instalada. Instale 'reportlab' (pip install reportlab)."
        ) from exc

    from ..utils.report_branding import get_company_header_html

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
        title="Relatorio por funcionario",
        author="GALINT",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 8
    body_style.leading = 9
    story = []

    title_style = styles["Title"]
    title_style.alignment = 1
    title_style.fontSize = 16
    subtitle_style = styles["Normal"]
    subtitle_style.alignment = 1

    story.append(Paragraph("RELATORIO DE RETIRADAS E DEVOLUCOES POR FUNCIONARIO", title_style))
    story.append(Paragraph(get_company_header_html(), subtitle_style))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(f"Gerado em: {TimeService.now_local().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))

    period_label = "Todo historico" if period_days <= 0 else f"Ultimos {period_days} dias"
    total_quantity = sum((row.get("quantidade", 0) if isinstance(row, dict) else getattr(row, "quantidade", 0)) for row in saidas) if saidas else 0
    story.append(Paragraph(f"Funcionario: <b>{_safe_text(usuario['nome'])}</b>", styles["Normal"]))
    story.append(Paragraph(f"Matricula: {_safe_text(usuario['matricula'])}", styles["Normal"]))
    story.append(Paragraph(f"Cargo: {_safe_text(usuario['cargo'])}", styles["Normal"]))
    story.append(Paragraph(f"Periodo: {period_label}", styles["Normal"]))
    story.append(Paragraph(f"Total de movimentacoes: {len(saidas)}", styles["Normal"]))
    story.append(Paragraph(f"Quantidade total movimentada: {total_quantity}", styles["Normal"]))
    story.append(Spacer(1, 0.4 * cm))

    header = ["Data", "Hora", "Item", "Codigo", "Qtd.", "Tipo", "Periodo", "Local"]
    data = [header]
    for saida in saidas:
        data_saida = saida.get("data") if isinstance(saida, dict) else getattr(saida, "data_saida", None)
        item_descricao = saida.get("item_descricao") if isinstance(saida, dict) else getattr(saida, "item_descricao", None)
        codigo_item = saida.get("codigo_item") if isinstance(saida, dict) else getattr(saida, "codigo_item", None)
        quantidade = saida.get("quantidade") if isinstance(saida, dict) else getattr(saida, "quantidade", None)
        periodo = saida.get("periodo") if isinstance(saida, dict) else time_service.get_business_day_tag(data_saida)
        observacao = saida.get("observacao") if isinstance(saida, dict) else getattr(saida, "observacao", None)
        local_servico = saida.get("local_servico") if isinstance(saida, dict) else getattr(saida, "local_servico", None)
        local_info = local_servico or "N/D"
        if observacao and str(observacao).strip():
            local_info = f"{local_info} | {str(observacao).strip()}"
        tipo_movimentacao = saida.get("tipo") if isinstance(saida, dict) else "Retirada"

        data.append(
            [
                time_service.format_local(data_saida, "%d/%m/%Y"),
                time_service.format_local(data_saida, "%H:%M"),
                Paragraph(_safe_text(item_descricao or "Item removido"), body_style),
                _format_codigo_barra(codigo_item),
                _safe_text(quantidade or ""),
                tipo_movimentacao,
                _safe_text(periodo or "Expediente"),
                Paragraph(_safe_text(local_info[:200]), body_style),
            ]
        )

    if len(data) == 1:
        story.append(Paragraph("Nenhuma retirada registrada para este funcionario.", styles["Italic"]))
        doc.build(story)
        return buffer.getvalue()

    table = Table(
        data,
        colWidths=[2.1 * cm, 1.5 * cm, 9.0 * cm, 1.3 * cm, 1.3 * cm, 1.7 * cm, 2.5 * cm, 9.3 * cm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


@bp.route("/")
@login_required
def index():
    """Alias legado da area removida de Relatorios Gerais."""
    return _redirect_reports_surface(
        message="A pagina Relatorios Gerais foi removida. Use a Central Analitica ou a Pesquisa geral.",
        category="info",
    )


@bp.route("/percentual-movimentos")
@login_required
def percentual_movimentos():
    """Alias legado para a Central Analitica."""
    flash("A pagina Percentual Movimentos foi incorporada a Central Analitica.", "info")
    return redirect(url_for("analytics.index"))


@bp.route("/download/<path:filename>")
@login_required
def download(filename: str):
    """Alias legado para a superficie analitica atual."""
    return _redirect_reports_surface(
        message="Os downloads da antiga pagina Relatorios Gerais foram desativados.",
        category="warning",
    )


@bp.route("/delete/<path:filename>", methods=["POST"])
@login_required
def delete(filename: str):
    """Alias legado para a superficie analitica atual."""
    return _redirect_reports_surface(
        message="A exclusao pela antiga pagina Relatorios Gerais foi removida.",
        category="warning",
    )


@bp.route("/gerar", methods=["POST"])
@login_required
def gerar_relatorio():
    """Alias legado para a superficie analitica atual."""
    return _redirect_reports_surface(
        message="A geracao pela antiga pagina Relatorios Gerais foi removida. Use a Central Analitica.",
        category="warning",
    )


def _redirect_to_general_search(*, scope: str, query: str | None = None, period: int | None = None, selected_date: str | None = None):
    redirect_kwargs: dict[str, object] = {
        "open_general_search": "1",
        "general_scope": scope,
    }
    normalized_query = str(query or "").strip()
    if normalized_query:
        redirect_kwargs["general_query"] = normalized_query
    if period is not None:
        redirect_kwargs["general_period"] = int(period)
    normalized_date = str(selected_date or "").strip()
    if normalized_date:
        redirect_kwargs["general_date"] = normalized_date

    return _redirect_reports_surface(
        message="A consulta foi incorporada a Pesquisa geral da barra superior.",
        category="info",
        **redirect_kwargs,
    )


@bp.route("/api/pesquisa-geral/sugestoes")
@login_required
def general_search_suggestions_api():
    scope = (request.args.get("scope") or "funcionario").strip().lower()
    query = (request.args.get("q") or "").strip()

    if scope == "funcionario":
        results = general_search_service.search_employees(query)
    elif scope == "item":
        results = general_search_service.search_items(query)
    else:
        return jsonify({"success": False, "message": "Escopo de sugestao invalido."}), 400

    return jsonify({"success": True, "scope": scope, "results": results})


@bp.route("/api/pesquisa-geral/funcionario/<matricula>")
@login_required
def general_search_employee_api(matricula: str):
    try:
        payload = general_search_service.build_employee_payload(matricula)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404

    return jsonify({"success": True, **payload})


@bp.route("/api/pesquisa-geral/item/<codigo_item>")
@login_required
def general_search_item_api(codigo_item: str):
    period_days = _parse_period_days_arg(request.args.get("period", "0"))
    if period_days not in [0, 7, 30, 90, 180, 365]:
        period_days = 0

    try:
        payload = general_search_service.build_item_payload(codigo_item, period_days=period_days)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404

    return jsonify({"success": True, **payload})


@bp.route("/api/pesquisa-geral/diario")
@login_required
def general_search_daily_api():
    raw_date = (request.args.get("date") or "").strip()
    selected_date = TimeService.now_local().date()
    if raw_date:
        try:
            selected_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "message": "Data invalida informada."}), 400

    payload = general_search_service.build_daily_payload(
        selected_date=selected_date,
        search_term=(request.args.get("search") or "").strip(),
    )
    return jsonify({"success": True, **payload})


@bp.route("/api/pesquisa-geral/administracao")
@login_required
def general_search_administration_api():
    if not _has_administration_search_access():
        return jsonify({"success": False, "message": "Acesso restrito ao setor Administração."}), 403
    payload = _admin_search_payload((request.args.get("q") or request.args.get("search") or "").strip())
    return jsonify({"success": True, **payload})


@bp.route("/by-item")
@login_required
def by_item():
    """Alias legado da Pesquisa geral para item ou funcionario."""
    search_type = (request.args.get("type") or "item").strip().lower()
    search_term = (request.args.get("search") or "").strip()
    period_days = _parse_period_days_arg(request.args.get("period", "0"))
    if period_days not in [0, 7, 30, 90, 180, 365]:
        period_days = 0

    target_scope = "funcionario" if search_type == "usuario" else "item"
    redirect_period = None if target_scope == "funcionario" else period_days
    return _redirect_to_general_search(scope=target_scope, query=search_term, period=redirect_period)


@bp.route("/by-item-day")
@login_required
def by_item_day():
    """Alias legado da Pesquisa geral para a visao diaria agrupada."""
    selected_date_raw = (request.args.get("date") or "").strip()
    selected_date = TimeService.now_local().date().isoformat()
    if selected_date_raw:
        try:
            selected_date = datetime.strptime(selected_date_raw, "%Y-%m-%d").date().isoformat()
        except ValueError:
            flash("Data invalida informada. Exibindo o dia atual.", "warning")

    return _redirect_to_general_search(
        scope="diario",
        query=(request.args.get("search") or "").strip(),
        selected_date=selected_date,
    )


@bp.route("/by_item_download")
@login_required
def by_item_download():
    """Download do relatorio por item ou funcionario em PDF."""
    from ..extensions import db
    from ..models import InventarioEvento, Item, Saida, Usuario

    search_term = request.args.get("search", "").strip()
    search_type = (request.args.get("type") or "item").strip().lower()
    requested_format = (request.args.get("format") or "pdf").strip().lower()

    if requested_format != "pdf":
        abort(400, "Formato invalido. Use pdf.")
    if not search_term:
        abort(400, "Termo de busca nao fornecido")

    if search_type == "usuario":
        period_days = 0
    else:
        period_days = _parse_period_days_arg(request.args.get("period", "0"))
        if period_days not in [0, 7, 30, 90, 180, 365]:
            period_days = 0

    item_info = None
    usuario_info = None
    saidas = []

    if search_type == "usuario":
        usuario = Usuario.query.filter(
            db.or_(
                Usuario.nome.ilike(f"%{search_term}%"),
                Usuario.matricula.ilike(f"%{search_term}%"),
            )
        ).first()
        if not usuario:
            abort(404, "Funcionario nao encontrado")

        usuario_info = {
            "matricula": usuario.matricula,
            "nome": usuario.nome,
            "cargo": usuario.setor if usuario.setor else (usuario.cargo if usuario.cargo else "N/D"),
        }

        query = (
            db.session.query(
                Saida.quantidade,
                Saida.data_saida,
                Saida.observacao,
                Saida.local_servico,
                Saida.codigo_item,
                Item.descricao.label("item_descricao"),
                Item.categoria.label("item_categoria"),
                Item.marca.label("item_marca"),
            )
            .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
            .filter(Saida.matricula == usuario.matricula)
            .order_by(Saida.data_saida.desc())
        )

        movimentos = []
        for saida in query.all():
            movimentos.append(
                {
                    "data": saida.data_saida,
                    "quantidade": saida.quantidade,
                    "observacao": saida.observacao or "",
                    "local_servico": saida.local_servico or "",
                    "codigo_item": saida.codigo_item,
                    "item_descricao": saida.item_descricao or "Item removido",
                    "item_categoria": saida.item_categoria or "N/D",
                    "item_marca": saida.item_marca or "N/D",
                    "periodo": TimeService.get_business_day_tag(saida.data_saida),
                    "tipo": "Retirada",
                }
            )

        devolucoes = (
            db.session.query(
                InventarioEvento.quantidade,
                InventarioEvento.data_evento,
                InventarioEvento.descricao,
                InventarioEvento.codigo_item,
                Item.descricao.label("item_descricao"),
                Item.categoria.label("item_categoria"),
                Item.marca.label("item_marca"),
            )
            .join(Item, InventarioEvento.codigo_item == Item.codigo_item, isouter=True)
            .filter(
                InventarioEvento.matricula == usuario.matricula,
                InventarioEvento.tipo.in_(["devolucao_ferramenta", "devolucao_material"]),
            )
            .all()
        )
        for devolucao in devolucoes:
            movimentos.append(
                {
                    "data": devolucao.data_evento,
                    "quantidade": devolucao.quantidade,
                    "observacao": devolucao.descricao or "",
                    "local_servico": "",
                    "codigo_item": devolucao.codigo_item,
                    "item_descricao": devolucao.item_descricao or "Item removido",
                    "item_categoria": devolucao.item_categoria or "N/D",
                    "item_marca": devolucao.item_marca or "N/D",
                    "periodo": TimeService.get_business_day_tag(devolucao.data_evento),
                    "tipo": "Devolucao",
                }
            )

        movimentos.sort(key=lambda mov: mov["data"] or datetime.min, reverse=True)
        saidas = movimentos
    else:
        item = Item.query.filter(
            db.or_(
                Item.descricao.ilike(f"%{search_term}%"),
                Item.codigo_item.ilike(f"%{search_term}%"),
            )
        ).first()

        if not item:
            search_normalized = _normalize_search(search_term).lower()
            for candidate in Item.query.all():
                description = _normalize_search(candidate.descricao or "").lower()
                code = str(candidate.codigo_item or "").lower()
                if search_normalized in description or search_normalized in code:
                    item = candidate
                    break

        if not item:
            abort(404, "Item nao encontrado")

        item_info = {
            "codigo": item.codigo_item,
            "descricao": item.descricao,
            "categoria": item.categoria or "N/D",
            "marca": item.marca or "N/D",
        }

        query = (
            db.session.query(
                Saida.quantidade,
                Saida.data_saida,
                Saida.observacao,
                Saida.local_servico,
                Saida.matricula.label("saida_matricula"),
                Usuario.nome.label("usuario_nome"),
            )
            .join(Usuario, Saida.matricula == Usuario.matricula, isouter=True)
            .filter(Saida.codigo_item == item.codigo_item)
        )
        if period_days > 0:
            cutoff = datetime.utcnow() - timedelta(days=period_days)
            query = query.filter(Saida.data_saida >= cutoff)
        saidas = query.order_by(Saida.data_saida.desc()).all()

    timestamp = TimeService.now_local().strftime("%Y%m%d_%H%M%S")
    try:
        if search_type == "usuario":
            safe_filename = "".join(c for c in usuario_info["matricula"] if c.isalnum() or c in ("-", "_"))
            pdf_bytes = _generate_usuario_report_pdf(
                usuario=usuario_info,
                saidas=saidas,
                period_days=period_days,
                time_service=TimeService,
            )
            pdf_filename = f"relatorio_funcionario_{safe_filename}_{timestamp}.pdf"
        else:
            safe_filename = "".join(c for c in item_info["codigo"] if c.isalnum() or c in ("-", "_"))
            pdf_bytes = _generate_item_report_pdf(
                item=item_info,
                saidas=saidas,
                period_days=period_days,
                time_service=TimeService,
            )
            pdf_filename = f"relatorio_item_{safe_filename}_{timestamp}.pdf"
    except ValueError as exc:
        abort(500, str(exc))

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=pdf_filename,
    )
