"""Backup e restauração do banco de dados (PostgreSQL-only)."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


class BackupService:
    """Responsável por gerar/restaurar cópias do banco configurado."""

    def __init__(self, app):
        self._uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        self._backup_root = Path(app.instance_path) / "backups"
        self._backup_root.mkdir(parents=True, exist_ok=True)
        self._pg_dump_cmd = app.config.get("BACKUP_PG_DUMP", "pg_dump")
        self._psql_cmd = app.config.get("BACKUP_PSQL", "psql")
        self._subprocess_timeout_seconds = int(
            os.environ.get("GALINT_BACKUP_TIMEOUT_SECONDS")
            or os.environ.get("BACKUP_TIMEOUT_SECONDS")
            or 120
        )
        self._connect_timeout_seconds = int(
            os.environ.get("GALINT_PG_CONNECT_TIMEOUT_SECONDS")
            or os.environ.get("PGCONNECT_TIMEOUT")
            or 10
        )
        self._lock_timeout_ms = int(
            os.environ.get("GALINT_PG_LOCK_TIMEOUT_MS")
            or os.environ.get("PG_LOCK_TIMEOUT_MS")
            or 5000
        )
        self._statement_timeout_ms = int(
            os.environ.get("GALINT_PG_STATEMENT_TIMEOUT_MS")
            or os.environ.get("PG_STATEMENT_TIMEOUT_MS")
            or 60000
        )

    def _apply_pg_timeouts(self, env: dict[str, str]) -> None:
        if self._connect_timeout_seconds > 0:
            env["PGCONNECT_TIMEOUT"] = str(self._connect_timeout_seconds)

        options: list[str] = []
        if self._lock_timeout_ms > 0:
            options.append(f"-c lock_timeout={self._lock_timeout_ms}")
        if self._statement_timeout_ms > 0:
            options.append(f"-c statement_timeout={self._statement_timeout_ms}")
        if not options:
            return

        existing = env.get("PGOPTIONS", "").strip()
        extra = " ".join(options)
        env["PGOPTIONS"] = (existing + " " + extra).strip() if existing else extra

    def _windows_find_postgres_tool(self, tool: str) -> str | None:
        """Tenta localizar ferramentas do PostgreSQL no Windows.

        Procura em locais comuns como:
        - %ProgramFiles%\PostgreSQL\<versão>\bin
        - %ProgramFiles(x86)%\PostgreSQL\<versão>\bin

        Retorna o caminho completo do executável se encontrar.
        """
        if os.name != "nt":
            return None

        exe = f"{tool}.exe" if not tool.lower().endswith(".exe") else tool

        base_dirs: list[Path] = []
        pf = os.environ.get("ProgramFiles")
        if pf:
            base_dirs.append(Path(pf) / "PostgreSQL")
        pf86 = os.environ.get("ProgramFiles(x86)")
        if pf86:
            base_dirs.append(Path(pf86) / "PostgreSQL")

        for extra in ("C:/PostgreSQL", "C:/pgsql"):
            base_dirs.append(Path(extra))

        candidates: list[Path] = []
        for base in base_dirs:
            try:
                if not base.is_dir():
                    continue
                for version_dir in base.iterdir():
                    bin_dir = version_dir / "bin"
                    if bin_dir.is_dir():
                        candidates.append(bin_dir)
            except Exception:
                continue

        def _version_key(p: Path) -> tuple[int, ...]:
            m = re.findall(r"\d+", p.parent.name)
            if not m:
                return (0,)
            return tuple(int(x) for x in m[:3])

        candidates.sort(key=_version_key, reverse=True)
        for bin_dir in candidates:
            p = bin_dir / exe
            if p.is_file():
                return str(p)
        return None

    def _derive_postgres_tool_from_other(self, desired: str) -> str | None:
        """Se um binário (pg_dump/psql) estiver configurado/encontrável, deriva o outro no mesmo diretório bin."""
        if desired == "psql":
            other = self._pg_dump_cmd
        else:
            other = self._psql_cmd

        other_path = shutil.which(other)
        if other_path is None:
            try:
                p = Path(other)
                other_path = str(p) if p.is_file() else None
            except Exception:
                other_path = None
        if other_path is None:
            return None

        try:
            other_p = Path(other_path)
            exe = f"{desired}.exe" if os.name == "nt" else desired
            candidate = other_p.with_name(exe)
            if candidate.is_file():
                return str(candidate)
        except Exception:
            return None
        return None

    def _resolve_postgres_tool(self, tool: str) -> str:
        """Resolve (e fixa) o comando pg_dump/psql, com heurísticas para Windows."""
        if tool == "pg_dump":
            configured = self._pg_dump_cmd
        else:
            configured = self._psql_cmd

        found = shutil.which(configured)
        if found:
            if tool == "pg_dump":
                self._pg_dump_cmd = found
            else:
                self._psql_cmd = found
            return found

        try:
            p = Path(configured)
            if p.is_file():
                if tool == "pg_dump":
                    self._pg_dump_cmd = str(p)
                else:
                    self._psql_cmd = str(p)
                return str(p)
        except Exception:
            pass

        derived = self._derive_postgres_tool_from_other(tool)
        if derived:
            if tool == "pg_dump":
                self._pg_dump_cmd = derived
            else:
                self._psql_cmd = derived
            return derived

        win_found = self._windows_find_postgres_tool(tool)
        if win_found:
            if tool == "pg_dump":
                self._pg_dump_cmd = win_found
            else:
                self._psql_cmd = win_found
            return win_found

        return configured

    def _ensure_uri(self) -> str:
        if not self._uri:
            raise ValueError("A URL do banco de dados não está configurada para backup")
        return self._uri

    def _postgres_params(self) -> dict[str, str | int | None]:
        url = make_url(self._ensure_uri())
        if not url.drivername.startswith("postgresql"):
            raise ValueError("Backup PostgreSQL indisponível para esse driver de banco")
        if not url.database:
            raise ValueError("Banco de dados PostgreSQL não informado na URL")
        return {
            "host": url.host,
            "port": url.port,
            "username": url.username,
            "password": url.password,
            "database": url.database,
        }

    def list_backups(self) -> list[dict[str, str]]:
        entries = []
        suportados = {".sql"}
        arquivos = sorted(
            (backup for backup in self._backup_root.glob("*") if backup.suffix.lower() in suportados),
            reverse=True,
        )
        for backup in arquivos:
            stat = backup.stat()
            entries.append(
                {
                    "name": backup.name,
                    "path": str(backup),
                    "size": f"{stat.st_size // 1024} KB",
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(sep=" ", timespec="seconds"),
                }
            )
        return entries

    def create_backup(self) -> str:
        url = make_url(self._ensure_uri())
        if url.drivername.startswith("postgresql"):
            return self._create_postgres_backup()
        raise ValueError("Somente PostgreSQL é suportado pelo backup automático")

    def restore_backup(self, backup_name: str) -> str:
        source = self._backup_root / backup_name
        if not source.exists():
            raise ValueError("Backup selecionado não existe")
        url = make_url(self._ensure_uri())
        if source.suffix.lower() == ".sql":
            if not url.drivername.startswith("postgresql"):
                raise ValueError("Este backup é de PostgreSQL, mas o banco atual não é PostgreSQL")
            cutoff = self._backup_cutoff_from_name(backup_name, source)
            delta = self._capture_post_backup_delta(cutoff)
            self._restore_postgres_backup(source)
            self._reapply_post_backup_delta(delta)
            return backup_name
        raise ValueError("Formato de backup não reconhecido para restauração")

    def delete_backup(self, backup_name: str) -> str:
        target = self._safe_backup_path(backup_name)
        if not target.exists():
            raise ValueError("Backup selecionado não existe")
        if not target.is_file():
            raise ValueError("Backup inválido")
        target.unlink()
        return target.name

    def _safe_backup_path(self, backup_name: str) -> Path:
        name = (backup_name or "").strip()
        if not name:
            raise ValueError("Nome de backup inválido")

        # Evitar path traversal (somente nome de arquivo)
        if Path(name).name != name:
            raise ValueError("Nome de backup inválido")

        target = self._backup_root / name
        try:
            target.resolve().relative_to(self._backup_root.resolve())
        except Exception:
            raise ValueError("Nome de backup inválido")

        if target.suffix.lower() != ".sql":
            raise ValueError("Formato de backup inválido")

        return target

    # Helpers -----------------------------------------------------------------

    def _create_postgres_backup(self) -> str:
        params = self._postgres_params()
        self._resolve_postgres_tool("pg_dump")
        if shutil.which(self._pg_dump_cmd) is None:
            raise ValueError(
                "Comando pg_dump não encontrado. Adicione-o ao PATH ou configure BACKUP_PG_DUMP com o caminho completo."
            )
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"galint_backup_{timestamp}.sql"
        destination = self._backup_root / backup_name
        cmd: list[str] = [
            self._pg_dump_cmd,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
        ]
        if params["host"]:
            cmd += ["-h", str(params["host"])]
        if params["port"]:
            cmd += ["-p", str(params["port"])]
        if params["username"]:
            cmd += ["-U", str(params["username"])]
        cmd += ["-d", str(params["database"]), "-f", str(destination)]
        env = os.environ.copy()
        if params["password"]:
            env["PGPASSWORD"] = str(params["password"])
        self._apply_pg_timeouts(env)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                stdin=subprocess.DEVNULL,
                timeout=self._subprocess_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            if destination.exists():
                destination.unlink()
            raise ValueError(
                f"Tempo limite ao executar pg_dump ({self._subprocess_timeout_seconds}s). "
                "Verifique conexão com o PostgreSQL e credenciais."
            )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Falha desconhecida ao executar pg_dump"
            if destination.exists():
                destination.unlink()
            raise ValueError(f"Erro ao gerar backup PostgreSQL: {message}")
        return backup_name

    def _restore_postgres_backup(self, source: Path) -> None:
        params = self._postgres_params()
        self._resolve_postgres_tool("psql")
        if shutil.which(self._psql_cmd) is None:
            raise ValueError(
                "Comando psql não encontrado. Adicione-o ao PATH ou configure BACKUP_PSQL com o caminho completo."
            )
        env = os.environ.copy()
        if params["password"]:
            env["PGPASSWORD"] = str(params["password"])
        self._apply_pg_timeouts(env)
        cmd: list[str] = [
            self._psql_cmd,
            "-w",
            "-v",
            "ON_ERROR_STOP=1",
            "--single-transaction",
        ]
        if params["host"]:
            cmd += ["-h", str(params["host"])]
        if params["port"]:
            cmd += ["-p", str(params["port"])]
        if params["username"]:
            cmd += ["-U", str(params["username"])]
        cmd += ["-d", str(params["database"]), "-f", str(source)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                stdin=subprocess.DEVNULL,
                timeout=self._subprocess_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            raise ValueError(
                f"Tempo limite ao executar psql ({self._subprocess_timeout_seconds}s). "
                "Geralmente isso indica conexão lenta/travada ou bloqueio no banco."
            )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Falha desconhecida ao executar psql"
            raise ValueError(f"Erro ao restaurar backup PostgreSQL: {message}")

    def _backup_cutoff_from_name(self, backup_name: str, source: Path) -> datetime:
        match = re.search(r"(\d{8})_(\d{6})", backup_name)
        if match:
            try:
                return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
            except ValueError:
                pass
        # fallback: usar timestamp do arquivo
        return datetime.fromtimestamp(source.stat().st_mtime)

    def _capture_post_backup_delta(self, cutoff: datetime) -> dict[str, object]:
        """Captura movimentos ocorridos após o backup para reaplicar depois do restore."""
        engine = create_engine(self._ensure_uri(), future=True)
        tables = [
            {"name": "entradas", "time_col": "data_entrada", "pk": "id_entrada"},
            {"name": "saidas", "time_col": "data_saida", "pk": "id_saida"},
            {"name": "inventario_eventos", "time_col": "data_evento", "pk": "id_evento"},
            {"name": "material_inventario", "time_col": "data_registro", "pk": "id"},
        ]
        payload: dict[str, object] = {"cutoff": cutoff.isoformat(), "tables": {}}
        with engine.connect() as conn:
            for table in tables:
                stmt = text(
                    f"SELECT * FROM {table['name']} WHERE {table['time_col']} > :cutoff"
                )
                rows = conn.execute(stmt, {"cutoff": cutoff}).mappings().all()
                payload["tables"][table["name"]] = rows
        return payload

    def _reapply_post_backup_delta(self, delta: dict[str, object]) -> None:
        """Reaplica movimentos pós-backup para evitar voltar itens retirados."""
        if not delta or not isinstance(delta.get("tables"), dict):
            return
        tables: dict[str, list[dict[str, object]]] = delta.get("tables", {})  # type: ignore[assignment]
        engine = create_engine(self._ensure_uri(), future=True)

        order = ["entradas", "saidas", "inventario_eventos", "material_inventario"]
        pks = {
            "entradas": "id_entrada",
            "saidas": "id_saida",
            "inventario_eventos": "id_evento",
            "material_inventario": "id",
        }

        with engine.begin() as conn:
            for table in order:
                rows = tables.get(table) or []
                if not rows:
                    continue
                cols = list(rows[0].keys())
                columns = ", ".join(cols)
                values = ", ".join([f":{c}" for c in cols])
                pk = pks.get(table)
                on_conflict = f" ON CONFLICT ({pk}) DO NOTHING" if pk else ""
                stmt = text(
                    f"INSERT INTO {table} ({columns}) VALUES ({values}){on_conflict}"
                )
                conn.execute(stmt, rows)

            # Ajustar sequências para evitar conflitos futuros
            for table, pk in pks.items():
                seq_stmt = text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), GREATEST((SELECT COALESCE(MAX({pk}), 0) FROM {table}), 1))"
                )
                conn.execute(seq_stmt)
