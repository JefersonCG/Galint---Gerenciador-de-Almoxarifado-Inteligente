"""Launches the native mirror panel process."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _gui_python_executable() -> str:
    executable = Path(sys.executable).resolve()
    if executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(executable)


def _build_command(url: str, title: str) -> tuple[list[str], Path]:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        return [str(executable), "native-mirror", "--url", url, "--title", title], executable.parent

    root = _project_root()
    return [_gui_python_executable(), str(root / "app.py"), "native-mirror", "--url", url, "--title", title], root


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def is_available() -> tuple[bool, str | None]:
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except Exception as exc:
        return False, str(exc)
    return True, None


def launch_panel(url: str, title: str) -> dict[str, Any]:
    available, error = is_available()
    if not available:
        return {
            "success": False,
            "message": f"Painel nativo indisponivel: {error or 'PySide6 nao encontrado'}",
        }

    command, working_directory = _build_command(url, title)
    env = os.environ.copy()
    env.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
    env.setdefault("GALINT_TELEGRAM_POLLING", "false")

    try:
        process = subprocess.Popen(
            command,
            cwd=str(working_directory),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_creation_flags(),
        )
    except Exception as exc:
        return {"success": False, "message": f"Falha ao iniciar painel nativo: {exc}"}

    return {
        "success": True,
        "message": "Painel nativo iniciado.",
        "pid": process.pid,
    }