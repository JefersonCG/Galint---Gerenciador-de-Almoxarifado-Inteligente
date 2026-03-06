"""Helper para registrar ações em arquivo de auditoria.

Uso:
    from galint_flask.utils.action_logger import log_action
    log_action("Descrição do que foi feito")

Observação importante:
    Versões anteriores também inseriam entradas no README.md. Isso foi removido
    para evitar que o README (documentação) fosse poluído com logs operacionais.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

LOCK = threading.Lock()
ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "log"
LOG_FILE = LOG_DIR / "actions.log"

# garantir diretório
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def log_action(message: str) -> None:
    """Escreve uma linha no arquivo de log com timestamp (auditoria leve).

    Este logger é "best-effort": falhas aqui não devem derrubar o fluxo principal.
    """
    entry = f"[{_timestamp()}] {message}\n"
    try:
        with LOCK:
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(entry)
    except Exception:
        # não propagar falhas de logging
        pass
