"""Configuration helpers for the GALINT Flask app."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from sqlalchemy.engine import make_url

# Diretório base do projeto (usado para resolver caminhos relativos)
BASE_DIR = Path(__file__).resolve().parents[1]


def _get_or_create_secret_key() -> str:
    explicit = os.environ.get("GALINT_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if explicit:
        return explicit.strip()

    instance_dir = BASE_DIR / "instance"
    secret_path = instance_dir / "secret_key.txt"

    try:
        instance_dir.mkdir(parents=True, exist_ok=True)
        if secret_path.exists():
            value = secret_path.read_text(encoding="utf-8").strip()
            if value:
                return value

        value = os.urandom(32).hex()
        secret_path.write_text(value, encoding="utf-8")
        return value
    except Exception:
        # Fallback: mantém o app funcional mesmo se não conseguir gravar no disco.
        return os.urandom(24).hex()


def _env_flag(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _resolve_database_uri() -> str:
    """Resolve e valida a URI do banco (PostgreSQL-only)."""
    explicit = os.environ.get("GALINT_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if explicit:
        explicit = explicit.strip()
        if (explicit.startswith('"') and explicit.endswith('"')) or (
            explicit.startswith("'") and explicit.endswith("'")
        ):
            explicit = explicit[1:-1].strip()

        if explicit.startswith("postgres://"):
            explicit = "postgresql://" + explicit[len("postgres://") :]

    if not explicit:
        raise ValueError(
            "Banco não configurado. Defina GALINT_DATABASE_URI (ou DATABASE_URL) com uma URL postgresql://..."
        )

    url = make_url(explicit)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("Somente PostgreSQL é suportado. Use uma URL postgresql://...")
    return explicit


class BaseConfig:
    SECRET_KEY = _get_or_create_secret_key()
    SQLALCHEMY_DATABASE_URI = ""
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    PREFERRED_URL_SCHEME = "https"
    # Timeout de inatividade da sessão web: 2 horas (em segundos)
    PERMANENT_SESSION_LIFETIME = 2 * 60 * 60
    SESSION_REFRESH_EACH_REQUEST = True
    DASHBOARD_SHARE_TOKEN = os.environ.get("GALINT_DASHBOARD_TOKEN")
    BACKUP_PG_DUMP = (
        os.environ.get("GALINT_PG_DUMP")
        or os.environ.get("BACKUP_PG_DUMP")
        or "pg_dump"
    )
    BACKUP_PSQL = (
        os.environ.get("GALINT_PSQL")
        or os.environ.get("BACKUP_PSQL")
        or "psql"
    )
    BACKUP_RETENTION_DAYS = int(os.environ.get("GALINT_BACKUP_RETENTION_DAYS") or os.environ.get("BACKUP_RETENTION_DAYS") or 30)
    BACKUP_RETENTION_COUNT = int(os.environ.get("GALINT_BACKUP_RETENTION_COUNT") or os.environ.get("BACKUP_RETENTION_COUNT") or 20)
    FEATURE_NOTAS_ENABLED = _env_flag("GALINT_FEATURE_NOTAS", True)
    FEATURE_LIVE_FEED_ENABLED = _env_flag("GALINT_FEATURE_LIVE_FEED", False)
    FEATURE_MOBILE_PANEL_ENABLED = _env_flag("GALINT_FEATURE_MOBILE_PANEL", True)
    FEATURE_WORKSPACE_WINDOWS_ENABLED = _env_flag("GALINT_FEATURE_WORKSPACE_WINDOWS", False)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"


CONFIG_MAP: Final[dict[str, type[BaseConfig]]] = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def load_config(app, config_name: str | None) -> None:
    """Apply configuration class to the Flask app."""
    target = config_name or os.environ.get("GALINT_FLASK_CONFIG", "default")
    config_class = CONFIG_MAP.get(target, DevelopmentConfig)
    app.config.from_object(config_class)
    app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_database_uri()
