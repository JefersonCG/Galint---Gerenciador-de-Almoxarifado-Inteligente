"""Authentication helpers for the Flask migration."""
from __future__ import annotations

import os
import sys

from flask_login import login_user, logout_user
from werkzeug.security import check_password_hash
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import current_app

# Allow running this module as a script during debugging.
if __package__ in {None, ""}:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from galint_flask.models import Usuario
from galint_flask.services.users import user_service

_mobile_tokens: dict[str, str] = {}


def _mobile_token_serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY não configurada; não é possível assinar tokens do mobile")
    return URLSafeTimedSerializer(secret_key=secret, salt="galint-mobile-token")


def _mobile_token_max_age_seconds() -> int:
    raw = os.environ.get("GALINT_MOBILE_TOKEN_MAX_AGE_SECONDS")
    if not raw:
        return 60 * 60 * 24 * 30  # 30 dias
    try:
        value = int(raw)
        return max(60, value)
    except ValueError:
        return 60 * 60 * 24 * 30


def _mirror_panel_token_serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY nao configurada; nao e possivel assinar tokens do painel")
    return URLSafeTimedSerializer(secret_key=secret, salt="galint-mirror-panel-token")


def _mirror_panel_token_max_age_seconds() -> int:
    raw = os.environ.get("GALINT_MIRROR_TOKEN_MAX_AGE_SECONDS")
    if not raw:
        return 60 * 60 * 24
    try:
        value = int(raw)
        return max(300, value)
    except ValueError:
        return 60 * 60 * 24


def _workspace_window_token_serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY nao configurada; nao e possivel assinar tokens de janela")
    return URLSafeTimedSerializer(secret_key=secret, salt="galint-workspace-window-token")


def _workspace_window_token_max_age_seconds() -> int:
    raw = os.environ.get("GALINT_WORKSPACE_WINDOW_TOKEN_MAX_AGE_SECONDS")
    if not raw:
        return 60 * 60 * 2
    try:
        value = int(raw)
        return max(300, value)
    except ValueError:
        return 60 * 60 * 2


def create_mobile_token(usuario: Usuario) -> str:
    serializer = _mobile_token_serializer()
    return serializer.dumps({"matricula": usuario.matricula})


def create_mirror_panel_token(usuario: Usuario, *, mode: str | None = None) -> str:
    serializer = _mirror_panel_token_serializer()
    normalized_mode = str(mode or "").strip().lower()
    return serializer.dumps(
        {
            "matricula": usuario.matricula,
            "scope": "mirror_panel",
            "mode": normalized_mode,
        }
    )


def create_workspace_window_token(usuario: Usuario) -> str:
    serializer = _workspace_window_token_serializer()
    return serializer.dumps(
        {
            "matricula": usuario.matricula,
            "scope": "workspace_window",
        }
    )


def get_mobile_user(token: str) -> Usuario | None:
    # Compatibilidade: tokens antigos (pré-migração) existiam apenas em memória.
    matricula = _mobile_tokens.get(token)
    if matricula:
        return Usuario.query.get(matricula)

    serializer = _mobile_token_serializer()
    try:
        data = serializer.loads(token, max_age=_mobile_token_max_age_seconds())
    except (BadSignature, SignatureExpired):
        return None

    matricula = (data or {}).get("matricula")
    if not matricula:
        return None
    return Usuario.query.get(matricula)


def get_mirror_panel_user(token: str, *, mode: str | None = None) -> Usuario | None:
    serializer = _mirror_panel_token_serializer()
    try:
        data = serializer.loads(token, max_age=_mirror_panel_token_max_age_seconds())
    except (BadSignature, SignatureExpired):
        return None

    if (data or {}).get("scope") != "mirror_panel":
        return None

    expected_mode = str(mode or "").strip().lower()
    token_mode = str((data or {}).get("mode") or "").strip().lower()
    if expected_mode and token_mode != expected_mode:
        return None

    matricula = (data or {}).get("matricula")
    if not matricula:
        return None
    return Usuario.query.get(matricula)


def get_workspace_window_user(token: str) -> Usuario | None:
    serializer = _workspace_window_token_serializer()
    try:
        data = serializer.loads(token, max_age=_workspace_window_token_max_age_seconds())
    except (BadSignature, SignatureExpired):
        return None

    if (data or {}).get("scope") != "workspace_window":
        return None

    matricula = (data or {}).get("matricula")
    if not matricula:
        return None
    return Usuario.query.get(matricula)


def authenticate(matricula: str, senha: str):
    from galint_flask.extensions import db
    user_service.ensure_default_admin()
    usuario = Usuario.query.get(matricula)
    if not usuario or not usuario.senha_hash:
        return None
    if check_password_hash(usuario.senha_hash, senha):
        # Invalidar sessão anterior (web)
        if usuario.active_session_id:
            current_app.logger.info(f"[Auth] Invalidando sessão web anterior de {matricula}")
            usuario.active_session_id = None
        
        login_user(usuario)
        
        # Registrar nova sessão web (usa session ID do Flask)
        from flask import session
        from datetime import datetime

        now = datetime.utcnow().isoformat()
        session_id = session.get('_id')
        session['login_at'] = now
        session['last_activity'] = now
        session.permanent = True
        if session_id:
            usuario.active_session_id = f"web:{session_id}"
        
        db.session.commit()
        return usuario
    return None


def end_session() -> None:
    from flask_login import current_user
    from galint_flask.extensions import db
    
    if current_user and current_user.is_authenticated:
        try:
            usuario = Usuario.query.get(current_user.matricula)
            if usuario:
                usuario.active_session_id = None
                db.session.commit()
        except Exception:
            pass
    
    logout_user()
