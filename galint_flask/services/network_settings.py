"""Persistência simples de configurações de rede para o GALINT Mobile.

Armazena em um arquivo JSON dentro de `instance/` para sobreviver a reinícios.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NetworkSettings:
    server_host: str
    server_port: int

    def base_url(self) -> str:
        return f"http://{self.server_host}:{self.server_port}"


_DEFAULT = NetworkSettings(server_host="127.0.0.1", server_port=5000)


def _settings_path(app) -> Path:
    return Path(app.instance_path) / "network_settings.json"


def load_network_settings(app) -> NetworkSettings:
    path = _settings_path(app)
    if not path.exists():
        return _DEFAULT
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _DEFAULT

    server_host = str(data.get("server_host") or _DEFAULT.server_host).strip()
    server_port = int(data.get("server_port") or _DEFAULT.server_port)

    if not server_host:
        server_host = _DEFAULT.server_host
    if server_port < 1 or server_port > 65535:
        server_port = _DEFAULT.server_port

    return NetworkSettings(server_host=server_host, server_port=server_port)


def save_network_settings(app, *, server_host: str, server_port: int) -> NetworkSettings:
    server_host = str(server_host or "").strip()
    if not server_host:
        raise ValueError("Informe um IP/host válido.")

    try:
        server_port = int(server_port)
    except (TypeError, ValueError):
        raise ValueError("Porta inválida.")

    if server_port < 1 or server_port > 65535:
        raise ValueError("Porta inválida (use 1-65535).")

    settings = NetworkSettings(server_host=server_host, server_port=server_port)

    path = _settings_path(app)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "server_host": settings.server_host,
        "server_port": settings.server_port,
    }

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

    return settings
