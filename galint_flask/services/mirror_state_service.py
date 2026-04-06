"""Shared mirror state storage for browser and native display surfaces."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any


_VALID_MODES = {"", "saida", "entrada", "ferramenta", "fracionada"}


def _normalize_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in _VALID_MODES else ""


def _empty_payload(mode: str) -> dict[str, Any]:
    return {
        "kind": mode,
        "kind_label": mode.capitalize() if mode else "Operacao",
        "status": "idle",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_label": "servidor",
    }


class MirrorStateService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._latest_state: dict[str, Any] | None = None
        self._state_by_mode: dict[str, dict[str, Any]] = {}

    def publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = deepcopy(dict(payload or {}))
        mode = _normalize_mode(state.get("kind"))
        if mode:
            state["kind"] = mode
        state.setdefault("status", "preview" if mode else "idle")
        state.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        with self._lock:
            self._latest_state = state
            if mode:
                self._state_by_mode[mode] = state
        return deepcopy(state)

    def get_state(self, mode: str | None = None) -> dict[str, Any]:
        normalized_mode = _normalize_mode(mode)
        with self._lock:
            if normalized_mode:
                state = self._state_by_mode.get(normalized_mode)
            else:
                state = self._latest_state
        if state:
            return deepcopy(state)
        return _empty_payload(normalized_mode)


mirror_state_service = MirrorStateService()