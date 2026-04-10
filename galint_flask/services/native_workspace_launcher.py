"""Launches native operational windows for GALINT."""
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


def _normalize_slot(slot: int | str | None) -> str:
    try:
        value = int(slot or 2)
    except (TypeError, ValueError):
        value = 2
    return str(value if value in (2, 3) else 2)


def _build_command(url: str, title: str, slot: int | str | None) -> tuple[list[str], Path]:
    normalized_slot = _normalize_slot(slot)
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        return [str(executable), "native-window", "--url", url, "--title", title, "--slot", normalized_slot], executable.parent

    root = _project_root()
    return [_gui_python_executable(), str(root / "app.py"), "native-window", "--url", url, "--title", title, "--slot", normalized_slot], root


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


def launch_workspace_window(url: str, title: str, *, slot: int | str | None = 2) -> dict[str, Any]:
    available, error = is_available()
    if not available:
        return {
            "success": False,
            "message": f"Janela nativa indisponivel: {error or 'PySide6 nao encontrado'}",
        }

    command, working_directory = _build_command(url, title, slot)
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
        return {"success": False, "message": f"Falha ao iniciar janela nativa: {exc}"}

    return {
        "success": True,
        "message": "Janela nativa iniciada.",
        "pid": process.pid,
    }