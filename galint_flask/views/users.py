"""Rotas de administração de usuários."""
from __future__ import annotations

from io import BytesIO
import re
from datetime import datetime
from typing import Any

from flask import Blueprint, abort, flash, redirect, jsonify, make_response, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from ..services.inventory import inventory_service
from ..services.tool_custody_service import tool_custody_service
from ..services.users import UserPayload, user_service

blueprint = Blueprint("users", __name__, url_prefix="/usuarios")

_MATRICULA_13_RE = re.compile(r"^\d{13}$")


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _generate_user_history_pdf(*, usuario: dict[str, Any], saidas: list[dict[str, Any]]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise ValueError(
            "Biblioteca de PDF não instalada. Instale 'reportlab' (pip install reportlab)."
        ) from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
        title="Histórico de retiradas",
        author="GALINT",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 9
    body_style.leading = 10
    story: list[Any] = []

    nome = _safe_text(usuario.get("nome"))
    matricula = _safe_text(usuario.get("matricula"))
    from ..utils.time_service import TimeService
    gerado_em = TimeService.now_local().strftime("%d/%m/%Y %H:%M")

    title_style = styles["Title"]
    title_style.alignment = 1
    title_style.fontSize = 16
    subtitle_style = styles["Normal"]
    subtitle_style.alignment = 1
    story.append(Paragraph("RELATÓRIO DIÁRIO DE RETIRADAS DE MATERIAIS", title_style))
    from ..utils.report_branding import get_company_header_html

    story.append(Paragraph(get_company_header_html(), subtitle_style))
    story.append(Paragraph(f"Usuário: <b>{nome}</b> (Matrícula {matricula})", styles["Normal"]))
    story.append(Paragraph(f"Gerado em: {gerado_em}", styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))

    header = ["Código", "Descrição | Obs", "Quantidade", "Data"]
    data: list[list[Any]] = [header]
    for registro in saidas:
        dt = registro.get("data")
        if hasattr(dt, "strftime"):
            dt_str = dt.strftime("%d/%m/%Y %H:%M")
        else:
            dt_str = _safe_text(dt)
        
        descricao = _safe_text(registro.get("descricao") or "Item removido")
        observacao = _safe_text(registro.get("observacao") or "")
        if observacao and observacao != "-":
            descricao += f" | {observacao}"

        data.append(
            [
                _safe_text(registro.get("codigo") or "-"),
                Paragraph(descricao, body_style),
                _safe_text(registro.get("quantidade") or ""),
                dt_str,
            ]
        )

    if len(data) == 1:
        story.append(Paragraph("Nenhuma retirada registrada para este usuário.", styles["Italic"]))
        doc.build(story)
        return buffer.getvalue()

    table = Table(data, colWidths=[1.6 * cm, 22.0 * cm, 2.0 * cm, 3.2 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("ALIGN", (2, 1), (2, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
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


def _require_admin() -> None:
    if not getattr(current_user, "is_admin", False):
        abort(403)


def _build_payload(form, *, matricula: str | None) -> UserPayload:
    return UserPayload(
        matricula=form.get("matricula") if matricula is None else matricula,
        nome=(form.get("nome") or "").strip(),
        setor=(form.get("setor") or "").strip(),
        cargo=(form.get("cargo") or "").strip() or None,
        senha=(form.get("senha") or "").strip() or None,
        is_admin=bool(form.get("is_admin")),
        is_standard=bool(form.get("is_standard")),
    )


def _apply_user_photo_changes(matricula: str) -> tuple[str, str] | None:
    file = request.files.get("photo")
    remove_requested = bool(request.form.get("remove_photo"))

    if file and file.filename:
        try:
            tool_custody_service.upload_employee_photo(file, matricula)
            return ("success", "Foto do usuário atualizada. Ela já passa a aparecer no login para esta matrícula.")
        except ValueError as exc:
            return ("warning", f"Cadastro salvo, mas a foto não foi atualizada: {exc}")
        except Exception as exc:
            return ("warning", f"Cadastro salvo, mas ocorreu um erro ao atualizar a foto: {exc}")

    if remove_requested:
        if tool_custody_service.delete_employee_photo(matricula):
            return ("info", "Foto do usuário removida. O login voltou a usar a imagem global.")
        return ("warning", "Nenhuma foto atual foi encontrada para remover.")

    return None


def _build_user_initials(nome: str | None) -> str:
    parts = [segment for segment in re.split(r"\s+", (nome or "").strip()) if segment]
    if not parts:
        return "SN"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][:1]}{parts[-1][:1]}".upper()


def _build_setor_cards(usuarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    setores: dict[str, dict[str, Any]] = {}
    for usuario in usuarios:
        enriched_user = dict(usuario)
        matricula = str(enriched_user.get("matricula") or "").strip()
        enriched_user["photo_path"] = user_service.get_photo_path(matricula)
        enriched_user["initials"] = _build_user_initials(enriched_user.get("nome"))

        setor = (enriched_user.get("setor") or "Sem setor").strip() or "Sem setor"
        bucket = setores.setdefault(
            setor,
            {
                "setor": setor,
                "membros": [],
                "total": 0,
                "admins": 0,
                "standards": 0,
            },
        )
        bucket["membros"].append(enriched_user)
        bucket["total"] += 1
        bucket["admins"] += 1 if enriched_user.get("is_admin") else 0
        bucket["standards"] += 1 if enriched_user.get("is_standard") else 0

    setor_cards = sorted(setores.values(), key=lambda card: card["setor"].lower())
    for card in setor_cards:
        card["membros"].sort(key=lambda membro: membro.get("nome", "").lower())
        card["preview_members"] = card["membros"][:4]

    return setor_cards


def _resolve_selected_sector(setor_cards: list[dict[str, Any]], selected_sector: str | None = None) -> dict[str, Any] | None:
    if not setor_cards:
        return None
    if selected_sector:
        selected_norm = selected_sector.strip().casefold()
        for card in setor_cards:
            if str(card.get("setor") or "").strip().casefold() == selected_norm:
                return card
    return setor_cards[0]


def _render_users_list(*, selected_sector: str | None = None, sector_page: bool = False):
    _require_admin()
    usuarios = user_service.list_users()
    setor_cards = _build_setor_cards(usuarios)
    selected_sector_card = _resolve_selected_sector(setor_cards, selected_sector)
    if selected_sector and selected_sector_card is None:
        flash("Setor não encontrado.", "warning")
        return redirect(url_for("users.list_users"))

    return render_template(
        "users/list.html",
        usuarios=usuarios,
        setor_cards=setor_cards,
        selected_sector_card=selected_sector_card,
        sector_page=sector_page,
    )


@blueprint.get("/")
@login_required
def list_users():
    selected_sector = (request.args.get("setor") or "").strip() or None
    sector_page = bool(selected_sector) or (request.args.get("visualizacao") == "setor")
    return _render_users_list(selected_sector=selected_sector, sector_page=sector_page)


@blueprint.get("/setor/<path:setor>")
@login_required
def list_users_by_sector(setor: str):
    return redirect(url_for("users.list_users", setor=setor, visualizacao="setor"))


@blueprint.get("/novo")
@login_required
def new_user_form():
    _require_admin()
    sugestao = user_service.generate_unique_matricula("")
    setores = user_service.get_distinct_setores()
    return render_template("users/form.html", usuario=None, matricula_sugerida=sugestao, setores_existentes=setores)


@blueprint.post("/novo")
@login_required
def create_user():
    _require_admin()
    payload = _build_payload(request.form, matricula=None)
    if not payload.nome or not payload.setor:
        flash("Informe nome e setor do usuário.", "danger")
        return redirect(url_for("users.new_user_form"))
    if not payload.is_admin and not payload.is_standard:
        flash("Selecione ao menos um perfil para o usuário.", "danger")
        return redirect(url_for("users.new_user_form"))
    try:
        matricula = user_service.create_user(payload)
        flash(f"Usuário {matricula} cadastrado com sucesso.", "success")
        photo_feedback = _apply_user_photo_changes(matricula)
        if photo_feedback:
            flash(photo_feedback[1], photo_feedback[0])
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("users.new_user_form"))
    return redirect(url_for("users.list_users"))


@blueprint.get("/<matricula>/editar")
@login_required
def edit_user_form(matricula: str):
    _require_admin()
    usuario = user_service.get_user(matricula)
    if not usuario:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("users.list_users"))
    usuario["photo_path"] = user_service.get_photo_path(matricula)
    setores = user_service.get_distinct_setores()
    return render_template("users/form.html", usuario=usuario, setores_existentes=setores)


@blueprint.post("/<matricula>/editar")
@login_required
def update_user(matricula: str):
    _require_admin()
    payload = _build_payload(request.form, matricula=matricula)
    if not payload.nome or not payload.setor:
        flash("Informe nome e setor do usuário.", "danger")
        return redirect(url_for("users.edit_user_form", matricula=matricula))
    if not payload.is_admin and not payload.is_standard:
        flash("Selecione ao menos um perfil para o usuário.", "danger")
        return redirect(url_for("users.edit_user_form", matricula=matricula))
    try:
        user_service.update_user(matricula, payload)
        flash("Usuário atualizado com sucesso.", "success")
        photo_feedback = _apply_user_photo_changes(matricula)
        if photo_feedback:
            flash(photo_feedback[1], photo_feedback[0])
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("users.edit_user_form", matricula=matricula))
    return redirect(url_for("users.list_users"))


@blueprint.get("/matricula-sugerida")
@login_required
def matricula_sugerida():
    _require_admin()
    return jsonify({"matricula": user_service.generate_unique_matricula("")})


@blueprint.post("/<matricula>/excluir")
@login_required
def delete_user(matricula: str):
    _require_admin()
    if matricula == current_user.id:
        flash("Não é possível remover o usuário logado.", "danger")
        return redirect(url_for("users.list_users"))

    try:
        user_service.delete_user(
            matricula,
            deleted_by=getattr(current_user, "matricula", None),
            deleted_by_name=getattr(current_user, "nome", None),
        )
        flash("Usuário removido e histórico arquivado no arquivo morto SQLite.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("users.list_users"))


@blueprint.get("/<matricula>/historico")
@login_required
def user_history(matricula: str):
    _require_admin()
    usuario = user_service.get_user(matricula)
    if not usuario:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("users.list_users"))
    saidas = inventory_service.list_saidas_por_usuario(matricula)
    return render_template("users/history.html", usuario=usuario, saidas=saidas)


@blueprint.get("/<matricula>/historico/pdf")
@login_required
def user_history_pdf(matricula: str):
    _require_admin()
    usuario = user_service.get_user(matricula)
    if not usuario:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("users.list_users"))
    saidas = inventory_service.list_saidas_por_usuario(matricula)
    try:
        pdf_bytes = _generate_user_history_pdf(usuario=usuario, saidas=saidas)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("users.user_history", matricula=matricula))

    filename = f"historico_retiradas_{matricula}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@blueprint.get("/<matricula>/qrcode.svg")
@login_required
def user_qrcode_svg(matricula: str):
    _require_admin()
    usuario = user_service.get_user(matricula)
    if not usuario:
        abort(404)

    try:
        import segno
    except Exception as exc:
        raise ValueError(
            "Biblioteca de QR Code não instalada. Instale 'segno' (pip install segno)."
        ) from exc

    payload = _safe_text(usuario.get("matricula"))
    if payload != payload.strip() or any(ch.isspace() for ch in payload) or not _MATRICULA_13_RE.fullmatch(payload):
        abort(400)

    qr = segno.make(payload, error="M", micro=False)
    buffer = BytesIO()
    qr.save(
        buffer,
        kind="svg",
        xmldecl=False,
        title=f"Matrícula {payload}",
        border=4,
        scale=10,
    )
    svg_bytes = buffer.getvalue()

    resp = make_response(svg_bytes)
    resp.mimetype = "image/svg+xml"
    resp.headers["Content-Disposition"] = f'inline; filename="qrcode_matricula_{payload}.svg"'
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@blueprint.get("/<matricula>/qrcode.png")
@login_required
def user_qrcode_png(matricula: str):
    _require_admin()
    usuario = user_service.get_user(matricula)
    if not usuario:
        abort(404)

    try:
        import segno
    except Exception as exc:
        raise ValueError(
            "Biblioteca de QR Code não instalada. Instale 'segno' (pip install segno)."
        ) from exc

    payload = _safe_text(usuario.get("matricula"))
    if payload != payload.strip() or any(ch.isspace() for ch in payload) or not _MATRICULA_13_RE.fullmatch(payload):
        abort(400)

    qr = segno.make(payload, error="M", micro=False)
    buffer = BytesIO()
    # PNG tende a ter leitura melhor por câmera e impressão.
    # Aumentamos 'scale' e 'border' para melhorar contraste e quiet zone.
    qr.save(
        buffer,
        kind="png",
        border=4,
        scale=10,
        dark="black",
        light="white",
    )
    png_bytes = buffer.getvalue()

    resp = make_response(png_bytes)
    resp.mimetype = "image/png"
    resp.headers["Content-Disposition"] = f'inline; filename="qrcode_matricula_{payload}.png"'
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@blueprint.get("/<matricula>/barcode.svg")
@login_required
def user_barcode_svg(matricula: str):
    _require_admin()
    usuario = user_service.get_user(matricula)
    if not usuario:
        abort(404)

    try:
        import barcode
        from barcode.writer import SVGWriter
    except Exception as exc:
        raise ValueError(
            "Biblioteca de código de barras não instalada. Instale 'python-barcode' (pip install python-barcode)."
        ) from exc

    payload = _safe_text(usuario.get("matricula"))
    if not payload:
        abort(400)
    if payload != payload.strip() or any(ch.isspace() for ch in payload) or not _MATRICULA_13_RE.fullmatch(payload):
        abort(400)

    code = barcode.get(
        "code128",
        payload,
        writer=SVGWriter(),
    )

    buffer = BytesIO()
    code.write(
        buffer,
        options={
            "write_text": False,
            "module_width": 0.4,
            "module_height": 24.0,
            "quiet_zone": 10.0,
            "background": "white",
            "foreground": "black",
        },
    )
    svg_bytes = buffer.getvalue()

    resp = make_response(svg_bytes)
    resp.mimetype = "image/svg+xml"
    resp.headers["Content-Disposition"] = f'inline; filename="barcode_matricula_{payload}.svg"'
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@blueprint.get("/<matricula>/barcode.png")
@login_required
def user_barcode_png(matricula: str):
    _require_admin()
    usuario = user_service.get_user(matricula)
    if not usuario:
        abort(404)

    try:
        import barcode
        from barcode.writer import ImageWriter
    except Exception as exc:
        raise ValueError(
            "Biblioteca de código de barras não instalada. Instale 'python-barcode' (pip install python-barcode)."
        ) from exc

    payload = _safe_text(usuario.get("matricula"))
    if not payload:
        abort(400)
    if payload != payload.strip() or any(ch.isspace() for ch in payload) or not _MATRICULA_13_RE.fullmatch(payload):
        abort(400)

    code = barcode.get(
        "code128",
        payload,
        writer=ImageWriter(),
    )

    buffer = BytesIO()
    code.write(
        buffer,
        options={
            "write_text": False,
            "module_width": 0.4,
            "module_height": 28.0,
            "quiet_zone": 12.0,
            "background": "white",
            "foreground": "black",
        },
    )
    png_bytes = buffer.getvalue()

    resp = make_response(png_bytes)
    resp.mimetype = "image/png"
    resp.headers["Content-Disposition"] = f'inline; filename="barcode_matricula_{payload}.png"'
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

