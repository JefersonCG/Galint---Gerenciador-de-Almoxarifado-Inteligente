"""Launches native operational windows for GALINT."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


_WORKSPACE_SLOTS = (2, 3)


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


def _registry_path() -> Path:
    return Path(tempfile.gettempdir()) / "galint_workspace_windows.json"


def _normalize_owner_key(owner_key: object) -> str:
    normalized = str(owner_key or "").strip()
    return normalized or "global"


def _load_registry() -> dict[str, dict[str, dict[str, Any]]]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_registry(registry: dict[str, dict[str, dict[str, Any]]]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(registry, ensure_ascii=True), encoding="utf-8")
    temp_path.replace(path)


def _pid_is_running(pid: object) -> bool:
    try:
        normalized_pid = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if normalized_pid <= 0:
        return False

    try:
        os.kill(normalized_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _clean_owner_slots(owner_key: object) -> dict[str, dict[str, Any]]:
    normalized_owner = _normalize_owner_key(owner_key)
    registry = _load_registry()
    current_slots = registry.get(normalized_owner)
    if not isinstance(current_slots, dict):
        current_slots = {}

    cleaned_slots: dict[str, dict[str, Any]] = {}
    for slot in _WORKSPACE_SLOTS:
        entry = current_slots.get(str(slot))
        if not isinstance(entry, dict):
            continue
        if not _pid_is_running(entry.get("pid")):
            continue
        cleaned_slots[str(slot)] = entry

    changed = cleaned_slots != current_slots
    if cleaned_slots:
        registry[normalized_owner] = cleaned_slots
    else:
        registry.pop(normalized_owner, None)
        changed = changed or bool(current_slots)

    if changed:
        _save_registry(registry)

    return cleaned_slots


def _reserve_slot(owner_key: object, slot: int, pid: int, title: str, url: str) -> None:
    normalized_owner = _normalize_owner_key(owner_key)
    registry = _load_registry()
    current_slots = _clean_owner_slots(normalized_owner)
    current_slots[str(slot)] = {
        "pid": int(pid),
        "title": str(title or "").strip(),
        "url": str(url or "").strip(),
    }
    registry[normalized_owner] = current_slots
    _save_registry(registry)


def get_workspace_slot_state(*, owner_key: object = None) -> dict[str, Any]:
    occupied_slots = sorted(int(slot) for slot in _clean_owner_slots(owner_key).keys())
    available_slots = [slot for slot in _WORKSPACE_SLOTS if slot not in occupied_slots]
    return {
        "occupied_slots": occupied_slots,
        "available_slots": available_slots,
        "has_capacity": bool(available_slots),
    }


def is_available() -> tuple[bool, str | None]:
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except Exception as exc:
        return False, str(exc)
    return True, None


def launch_workspace_window(url: str, title: str, *, slot: int | str | None = 2, owner_key: object = None) -> dict[str, Any]:
    available, error = is_available()
    if not available:
        return {
            "success": False,
            "message": f"Janela nativa indisponivel: {error or 'PySide6 nao encontrado'}",
        }

    normalized_slot = int(_normalize_slot(slot))
    slot_state = get_workspace_slot_state(owner_key=owner_key)
    if normalized_slot in slot_state["occupied_slots"]:
        return {
            "success": False,
            "code": "slot-occupied",
            "message": f"A janela auxiliar {normalized_slot} ja esta em uso.",
            "slot": normalized_slot,
        }

    command, working_directory = _build_command(url, title, normalized_slot)
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

    _reserve_slot(owner_key, normalized_slot, process.pid, title, url)

    return {
        "success": True,
        "message": "Janela nativa iniciada.",
        "pid": process.pid,
        "slot": normalized_slot,
    }


def launch_workspace_window_auto(url: str, title: str, *, owner_key: object = None) -> dict[str, Any]:
    slot_state = get_workspace_slot_state(owner_key=owner_key)
    available_slots = slot_state["available_slots"]
    if not available_slots:
        return {
            "success": False,
            "code": "slot-limit-reached",
            "message": "As 3 janelas de trabalho ja estao em uso. Feche uma auxiliar ou continue na janela atual.",
            "occupied_slots": slot_state["occupied_slots"],
        }

    return launch_workspace_window(url, title, slot=available_slots[0], owner_key=owner_key)