"""Authentication views."""
from __future__ import annotations

from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required

from ..services.auth import authenticate, end_session
from ..services.config_service import ConfigService

blueprint = Blueprint("auth", __name__, url_prefix="/auth")


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
