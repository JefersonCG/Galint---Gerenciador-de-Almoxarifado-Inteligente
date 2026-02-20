from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


def _strip_outer_quotes(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1].strip()
    return value


def safe_part(url: str) -> str:
    return url.split("@", 1)[1] if "@" in url else url


def find_psql() -> str | None:
    # Prefer PATH
    for candidate in ("psql.exe", "psql"):
        path = shutil_which(candidate)
        if path:
            return path

    # Common install location on Windows
    root = Path(r"C:\Program Files\PostgreSQL")
    if root.exists():
        hits = sorted(root.glob("**/bin/psql.exe"), reverse=True)
        if hits:
            return str(hits[0])

    return None


def shutil_which(cmd: str) -> str | None:
    try:
        import shutil

        return shutil.which(cmd)
    except Exception:
        return None


def main() -> int:
    env_url = os.environ.get("GALINT_DATABASE_URI") or os.environ.get("DATABASE_URL")
    file_env = dotenv_values(".env") if Path(".env").exists() else {}
    file_url = (
        file_env.get("GALINT_DATABASE_URI")
        or file_env.get("DATABASE_URL")
        or file_env.get("SQLALCHEMY_DATABASE_URI")
    )

    raw_url = _strip_outer_quotes(env_url or file_url or "")
    if not raw_url:
        print("ERRO: DATABASE_URL/GALINT_DATABASE_URI não definido (env nem .env)")
        return 2

    parsed = urlparse(raw_url)
    host = parsed.hostname
    port = parsed.port or 5432
    db = (parsed.path or "").lstrip("/")
    user = parsed.username
    has_password = bool(parsed.password)

    print("URL (safe):", safe_part(raw_url))
    print("host=", host, "port=", port, "db=", db, "user=", user, "has_password=", has_password)

    # TCP reachability
    try:
        with socket.create_connection((host or "", port), timeout=3):
            print("TCP: OK")
    except Exception as exc:
        print("TCP: FALHOU:", type(exc).__name__, str(exc))
        print("Dica: firewall/porta 5432, listen_addresses, rede.")
        return 3

    # Prefer using psql for a full server-side error message
    psql = find_psql()
    if not psql:
        print("psql: não encontrado (PATH nem Program Files)")
        print("Pulando teste via psql.")
        return 0

    if not has_password:
        print("psql: senha ausente na URL (não dá para autenticar).")
        return 4

    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or ""

    cmd = [psql, "-h", host or "", "-p", str(port), "-U", user or "", "-d", db or "", "-c", "select 1;"]
    print("psql:", "executando teste...")

    completed = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if completed.returncode == 0:
        print("psql: OK")
        return 0

    stderr = (completed.stderr or "").strip()
    stdout = (completed.stdout or "").strip()

    print("psql: FALHOU (returncode=%s)" % completed.returncode)
    if stdout:
        print("psql stdout:")
        print(stdout)
    if stderr:
        print("psql stderr:")
        print(stderr)

    print("Dica: se aparecer 'no pg_hba.conf entry', ajuste pg_hba.conf no servidor.")
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
