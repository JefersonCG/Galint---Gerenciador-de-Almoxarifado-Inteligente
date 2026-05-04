"""Authentication views."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required

from ..services.auth import authenticate, end_session
from ..services.config_service import ConfigService
from ..services.users import user_service

blueprint = Blueprint("auth", __name__, url_prefix="/auth")

_MANAGEMENT_LOGIN_MODULES = {"gestao", "administracao", "mensageria"}


def _normalize_login_module(raw_module: str | None) -> str:
    normalized = str(raw_module or "").strip().lower()
    aliases = {
        "admin": "administracao",
        "administração": "administracao",
        "gestão": "gestao",
    }
    return aliases.get(normalized, normalized)


def _build_login_redirect(*, login_module: str, is_management_login: bool) -> str:
    if is_management_login and login_module == "gestao":
        return url_for("auth.login_form", gestao=1)
    if login_module:
        return url_for("auth.login_form", module=login_module)
    return url_for("auth.login_form")


def _management_landing_url(usuario, *, login_module: str) -> str:
    if login_module == "mensageria":
        admin_value = getattr(usuario, "is_admin", 0)
        is_admin = bool(admin_value) or str(admin_value).strip().lower() in {"1", "true", "sim", "yes"}
        if is_admin:
            return url_for("config.notificacoes")
    return url_for("pages.config")


def _is_management_user(usuario) -> bool:
    if not usuario:
        return False
    admin_value = getattr(usuario, "is_admin", 0)
    if bool(admin_value) or str(admin_value).strip().lower() in {"1", "true", "sim", "yes"}:
        return True
    perfil = " ".join(
        str(getattr(usuario, attr, "") or "").strip().lower()
        for attr in ("cargo", "setor")
    )
    return any(token in perfil for token in ("desenvolvedor", "gerente", "gestor", "gestao", "gestão"))


def _set_session_flags(usuario, *, management_access: bool = False, management_module: str | None = None) -> None:
    session["galint_is_admin"] = bool(getattr(usuario, "is_admin", 0))
    session["galint_user_id"] = str(getattr(usuario, "matricula", ""))
    if management_access:
        session["galint_management_access"] = True
        session["galint_management_module"] = str(management_module or "gestao")
    else:
        session.pop("galint_management_access", None)
        session.pop("galint_management_module", None)


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


@blueprint.route("/gestao", methods=["GET", "POST"])
def management_login():
    return redirect(url_for("auth.login_form", gestao=1))


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
    login_module = _normalize_login_module(request.form.get("modulo", ""))
    is_management_login = login_module in _MANAGEMENT_LOGIN_MODULES
    login_redirect = _build_login_redirect(login_module=login_module, is_management_login=is_management_login)
    if not matricula or not senha:
        flash("Informe matrícula e senha.", "danger")
        return redirect(login_redirect)
    usuario = authenticate(matricula, senha)
    if usuario:
        if is_management_login:
            if not _is_management_user(usuario):
                end_session()
                flash("Acesso restrito a gestores, gerentes e desenvolvedores.", "danger")
                return redirect(login_redirect)
            _set_session_flags(usuario, management_access=True, management_module=login_module)
            flash("Acesso gerencial liberado.", "success")
            return redirect(_management_landing_url(usuario, login_module=login_module))

        _set_session_flags(usuario)

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
    return redirect(login_redirect)


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
