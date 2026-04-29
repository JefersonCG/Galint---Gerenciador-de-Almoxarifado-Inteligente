from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
import webbrowser

from .barcode_studio_service import barcode_studio_service


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_base_url(base_url: str | None = None) -> str:
    explicit = str(base_url or os.environ.get("GALINT_LAYOUT_OPEN_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    port = str(os.environ.get("PORT") or "5000").strip() or "5000"
    return f"http://localhost:{port}"


def _build_editor_url(base_url: str, token: str) -> str:
    query = urlencode({"layout_import_token": token})
    return f"{base_url}/itens/barcodes/estudio?{query}"


def _build_server_command() -> tuple[list[str], Path]:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        return [str(executable)], executable.parent

    executable = Path(sys.executable).resolve()
    root = _project_root()
    return [str(executable), str(root / "app.py")], root


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    flags = 0
    flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return flags


def _is_server_available(base_url: str) -> bool:
    probe_url = f"{base_url}/"
    try:
        with urlopen(probe_url, timeout=1.8) as response:
            return int(getattr(response, "status", 0) or 200) < 500
    except Exception:
        return False


def _wait_for_server(base_url: str, *, timeout_seconds: float = 18.0) -> bool:
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    while time.monotonic() < deadline:
        if _is_server_available(base_url):
            return True
        time.sleep(0.6)
    return _is_server_available(base_url)


def _ensure_server_available(base_url: str) -> dict[str, Any]:
    if _is_server_available(base_url):
        return {"available": True, "started": False, "pid": None}

    command, working_directory = _build_server_command()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(working_directory),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_creation_flags(),
        )
    except Exception as exc:
        return {
            "available": False,
            "started": False,
            "pid": None,
            "message": f"Não foi possível iniciar o GALINT automaticamente: {exc}",
        }

    ready = _wait_for_server(base_url)
    return {
        "available": ready,
        "started": True,
        "pid": process.pid,
        "message": None if ready else "O GALINT foi iniciado, mas o editor ainda não respondeu a tempo.",
    }


def prepare_layout_file_launch(file_path: str | Path, *, base_url: str | None = None) -> dict[str, Any]:
    pending = barcode_studio_service.register_pending_import(file_path)
    normalized_base_url = _normalize_base_url(base_url)
    return {
        "success": True,
        "token": pending["token"],
        "source_name": pending["source_name"],
        "name": pending["name"],
        "base_url": normalized_base_url,
        "url": _build_editor_url(normalized_base_url, pending["token"]),
    }


def open_layout_file(
    file_path: str | Path,
    *,
    base_url: str | None = None,
    ensure_server: bool = True,
    open_browser: bool = True,
) -> dict[str, Any]:
    prepared = prepare_layout_file_launch(file_path, base_url=base_url)
    if ensure_server:
        server_state = _ensure_server_available(prepared["base_url"])
        prepared["server_started"] = bool(server_state.get("started"))
        prepared["server_pid"] = server_state.get("pid")
        if not server_state.get("available"):
            return {
                **prepared,
                "success": False,
                "message": server_state.get("message") or "Não foi possível preparar o editor para abrir o arquivo.",
            }
    else:
        prepared["server_started"] = False
        prepared["server_pid"] = None

    if open_browser:
        prepared["browser_opened"] = bool(webbrowser.open(prepared["url"], new=1, autoraise=True))
        prepared["message"] = "Arquivo enviado ao Editor de Etiquetas."
    else:
        prepared["browser_opened"] = False
        prepared["message"] = "Arquivo preparado para abertura no Editor de Etiquetas."

    return prepared