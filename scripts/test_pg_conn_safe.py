from __future__ import annotations

import os
import sys
import traceback

import psycopg2
from sqlalchemy.engine import make_url

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from galint_flask.config import _resolve_database_uri


def safe_part(url: str) -> str:
    return url.split("@", 1)[1] if "@" in url else url


dsn = _resolve_database_uri()
print("Connecting to:", safe_part(dsn))

try:
    url = make_url(dsn)
    conn = psycopg2.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=5,
    )
    conn.close()
    print("OK")
except Exception as exc:
    print("ERROR_TYPE:", type(exc).__name__)
    print("ERROR_ARGS:", getattr(exc, "args", None))
    print("ERROR_REPR:", repr(exc))
    print("ERROR_STR:", str(exc))
    print("PGERROR:", getattr(exc, "pgerror", None))
    diag = getattr(exc, "diag", None)
    print("DIAG_PRIMARY:", getattr(diag, "message_primary", None))
    print("TRACEBACK:")
    traceback.print_exc()
