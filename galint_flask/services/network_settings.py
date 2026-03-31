"""Persistência simples de configurações de rede para o GALINT Mobile.

Armazena em um arquivo JSON dentro de `instance/` para sobreviver a reinícios.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class NetworkSettings:
    server_scheme: str
    server_host: str
    server_port: int | None

    def base_url(self) -> str:
        port = self.server_port
        scheme = (self.server_scheme or "http").strip().lower() or "http"
        if port is None:
            return f"{scheme}://{self.server_host}"
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            return f"{scheme}://{self.server_host}"
        return f"{scheme}://{self.server_host}:{port}"

    @property
    def server_port_display(self) -> str:
        if self.server_port is None:
            return "padrão"
        return str(self.server_port)


_DEFAULT = NetworkSettings(server_scheme="http", server_host="127.0.0.1", server_port=5000)


def _settings_path(app) -> Path:
    return Path(app.instance_path) / "network_settings.json"


def _build_settings_from_base_url(base_url: str) -> NetworkSettings:
    value = str(base_url or "").strip()
    if not value:
        raise ValueError("Informe uma URL base válida.")

    if "://" not in value:
        value = f"http://{value}"

    try:
        parsed = urlparse(value)
    except Exception as exc:
        raise ValueError("URL base inválida.") from exc

    scheme = (parsed.scheme or "http").strip().lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Use apenas http:// ou https:// na URL base.")

    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError("Informe um host/domínio válido na URL base.")

    if parsed.path and parsed.path not in {"", "/"}:
        raise ValueError("Informe apenas a URL base do servidor, sem caminhos como /api.")
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError("Remova parâmetros extras da URL base informada.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Porta inválida na URL base.") from exc

    return NetworkSettings(server_scheme=scheme, server_host=host, server_port=port)


def _build_settings_from_legacy(server_host: str | None, server_port: Any) -> NetworkSettings:
    host = str(server_host or "").strip()
    if not host:
        host = _DEFAULT.server_host

    try:
        port = int(server_port)
    except (TypeError, ValueError):
        port = _DEFAULT.server_port

    if port < 1 or port > 65535:
        port = _DEFAULT.server_port

    return NetworkSettings(server_scheme="http", server_host=host, server_port=port)


def load_network_settings(app) -> NetworkSettings:
    path = _settings_path(app)
    if not path.exists():
        return _DEFAULT
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _DEFAULT

    try:
        if data.get("base_url"):
            return _build_settings_from_base_url(str(data.get("base_url") or ""))
    except ValueError:
        pass

    try:
        if data.get("server_host"):
            return _build_settings_from_legacy(data.get("server_host"), data.get("server_port"))
    except Exception:
        pass

    return _DEFAULT


def save_network_settings(
    app,
    *,
    base_url: str | None = None,
    server_host: str | None = None,
    server_port: int | None = None,
) -> NetworkSettings:
    if base_url is not None and str(base_url).strip():
        settings = _build_settings_from_base_url(str(base_url))
    else:
        settings = _build_settings_from_legacy(server_host, server_port)

    path = _settings_path(app)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "base_url": settings.base_url(),
        "server_scheme": settings.server_scheme,
        "server_host": settings.server_host,
        "server_port": settings.server_port,
    }

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

    return settings
