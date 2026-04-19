"""Authentication views."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required

from ..services.auth import authenticate, end_session
from ..services.config_service import ConfigService
from ..services.users import user_service

blueprint = Blueprint("auth", __name__, url_prefix="/auth")


def _build_versioned_static_url(relative_path: str | None) -> str | None:
    normalized = (relative_path or "").strip().replace("\\", "/")
    if not normalized:
        return None

    try:
        file_path = Path(current_app.static_folder) / Path(*normalized.split("/"))
        version = int(file_path.stat().st_mtime)
    except OSError:
        version = None

    if version is None:
        return url_for("static", filename=normalized)
    return url_for("static", filename=normalized, v=version)


@blueprint.get("/login")
def login_form():
    # Passar configuração da empresa para personalizar login
    empresa_config = ConfigService.get_empresa_config()
    login_branding = ConfigService.get_login_branding_config()
    return render_template(
        "auth/login.html",
        empresa_config=empresa_config,
        login_branding=login_branding,
    )


@blueprint.get("/login-photo")
def login_photo_lookup():
    matricula = (request.args.get("matricula") or "").strip()
    if not matricula:
        return jsonify({"photo_url": None, "has_custom_photo": False})

    usuario = user_service.get_user(matricula)
    if not usuario:
        return jsonify({"photo_url": None, "has_custom_photo": False})

    photo_path = user_service.get_photo_path(matricula)
    return jsonify(
        {
            "photo_url": _build_versioned_static_url(photo_path),
            "has_custom_photo": bool(photo_path),
        }
    )


@blueprint.post("/login")
def login_submit():
    matricula = request.form.get("matricula", "").strip()
    senha = request.form.get("senha", "")
    if not matricula or not senha:
        flash("Informe matrícula e senha.", "danger")
        return redirect(url_for("auth.login_form"))
    usuario = authenticate(matricula, senha)
    if usuario:
        # Guardar flags de autorização na sessão para rotas que precisam evitar consultas ao banco.
        session["galint_is_admin"] = bool(getattr(usuario, "is_admin", 0))
        session["galint_user_id"] = str(getattr(usuario, "matricula", ""))

        # Aviso de contingência: se Telegram estiver fora, informar ao usuário ao entrar.
        try:
            from ..services.telegram_service import TelegramService

            if TelegramService.is_enabled():
                status = TelegramService.read_runtime_status() or {}
                if status and status.get("ok") is False:
                    motivo = status.get("error") or "motivo não informado"
                    flash(
                        f"⚠️ Telegram fora do ar: {motivo}. Notificações podem não ser enviadas.",
                        "warning",
                    )
        except Exception:
            pass

        flash("Bem-vindo!", "success")
        return redirect(url_for("dashboard.index"))
    flash("Credenciais inválidas.", "danger")
    return redirect(url_for("auth.login_form"))


@blueprint.post("/logout")
@login_required
def logout():
    end_session()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("auth.login_form"))


@blueprint.post("/session-activity")
@login_required
def session_activity():
    return jsonify({"success": True})
