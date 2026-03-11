"""Jobs de restauração de backup (assíncrono, com progresso).

Objetivo: permitir que a UI inicie a restauração e acompanhe o progresso sem
travar a requisição HTTP.

Observação: é um job in-memory (reiniciar o servidor limpa o estado).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import threading
from typing import Any, Callable, ContextManager, Protocol
from uuid import uuid4


class _AppWithContext(Protocol):
    def app_context(self) -> ContextManager[Any]: ...


@dataclass
class RestoreJobState:
    job_id: str
    user_key: str
    backup_name: str
    status: str  # running|success|error
    progress: int
    message: str
    error: str | None
    started_at: str
    updated_at: str
    finished_at: str | None


_jobs: dict[str, RestoreJobState] = {}
_lock = threading.Lock()
_active_restore_job_id: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _set_active(job_id: str | None) -> None:
    global _active_restore_job_id
    _active_restore_job_id = job_id


def start_restore_job(
    *,
    app: _AppWithContext,
    backup_name: str,
    user_key: str,
    restore_callable: Callable[[Callable[[int, str], None]], object],
) -> str:
    """Inicia (ou reutiliza) um job de restore.

    restore_callable: função que recebe um callback reporter(progress, message).
    """
    with _lock:
        if _active_restore_job_id:
            existing = _jobs.get(_active_restore_job_id)
            if existing and existing.status == "running":
                if existing.user_key == user_key:
                    return existing.job_id
                raise RuntimeError("Já existe uma restauração em andamento.")

        job_id = str(uuid4())
        state = RestoreJobState(
            job_id=job_id,
            user_key=user_key,
            backup_name=backup_name,
            status="running",
            progress=1,
            message="Job criado.",
            error=None,
            started_at=_now_iso(),
            updated_at=_now_iso(),
            finished_at=None,
        )
        _jobs[job_id] = state
        _set_active(job_id)

    def _update(progress: int, message: str) -> None:
        with _lock:
            st = _jobs.get(job_id)
            if not st:
                return
            st.progress = max(0, min(100, int(progress)))
            st.message = str(message)
            st.updated_at = _now_iso()

    def _finish_success() -> None:
        with _lock:
            st = _jobs.get(job_id)
            if st:
                st.status = "success"
                st.progress = 100
                st.message = "Concluído."
                st.updated_at = _now_iso()
                st.finished_at = _now_iso()
            if _active_restore_job_id == job_id:
                _set_active(None)

    def _finish_error(err: Exception) -> None:
        with _lock:
            st = _jobs.get(job_id)
            if st:
                st.status = "error"
                st.error = str(err)
                st.message = "Erro ao restaurar."
                st.updated_at = _now_iso()
                st.finished_at = _now_iso()
            if _active_restore_job_id == job_id:
                _set_active(None)

    def _runner() -> None:
        try:
            with app.app_context():
                restore_callable(_update)
            _finish_success()
        except Exception as exc:  # noqa: BLE001
            _finish_error(exc)

    thread = threading.Thread(target=_runner, daemon=True, name=f"galint-restore-{job_id}")
    thread.start()
    return job_id


def get_job_state(*, job_id: str, user_key: str) -> dict[str, Any] | None:
    with _lock:
        state = _jobs.get(job_id)
        if not state:
            return None
        if state.user_key != user_key:
            return None
        return asdict(state)
