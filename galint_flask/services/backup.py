"""Backup e restauração do banco de dados (PostgreSQL-only)."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Any
import zipfile

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from ..paths import get_version


class BackupService:
    """Responsável por gerar/restaurar cópias do banco configurado."""

    MANIFEST_SCHEMA_VERSION = "1.0"
    COMPLETE_BACKUP_KIND = "complete"
    DATABASE_BACKUP_KIND = "database"
    UPDATE_BACKUP_MAX_AGE_MINUTES = 30

    def __init__(self, app):
        self._app = app
        self._uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        self._backup_root = Path(app.instance_path) / "backups"
        self._backup_root.mkdir(parents=True, exist_ok=True)
        self._pg_dump_cmd = app.config.get("BACKUP_PG_DUMP", "pg_dump")
        self._psql_cmd = app.config.get("BACKUP_PSQL", "psql")
        self._subprocess_timeout_seconds = int(
            os.environ.get("GALINT_BACKUP_TIMEOUT_SECONDS")
            or os.environ.get("BACKUP_TIMEOUT_SECONDS")
            or 3600
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
        self._restore_connection_drain_seconds = int(
            os.environ.get("GALINT_RESTORE_CONNECTION_DRAIN_SECONDS")
            or os.environ.get("RESTORE_CONNECTION_DRAIN_SECONDS")
            or 20
        )
        self._restore_maintenance_database = (
            os.environ.get("GALINT_RESTORE_MAINTENANCE_DB")
            or os.environ.get("RESTORE_MAINTENANCE_DB")
            or "postgres"
        )
        self._retention_days = int(
            app.config.get("BACKUP_RETENTION_DAYS")
            or os.environ.get("GALINT_BACKUP_RETENTION_DAYS")
            or os.environ.get("BACKUP_RETENTION_DAYS")
            or 0
        )
        self._retention_count = int(
            app.config.get("BACKUP_RETENTION_COUNT")
            or os.environ.get("GALINT_BACKUP_RETENTION_COUNT")
            or os.environ.get("BACKUP_RETENTION_COUNT")
            or 0
        )
        self._project_root = Path(app.root_path).parent
        self._full_backup_directories = [
            {
                "source": Path(app.root_path) / "static" / "uploads",
                "archive_prefix": "assets/static/uploads",
                "criticality": "important",
                "group": "item_photos",
                "description": "Fotos e anexos salvos em uploads.",
            },
            {
                "source": Path(app.root_path) / "static" / "logo",
                "archive_prefix": "assets/static/logo",
                "criticality": "important",
                "group": "branding",
                "description": "Logo e arquivos visuais institucionais.",
            },
            {
                "source": Path(app.instance_path) / "barcodes",
                "archive_prefix": "assets/instance/barcodes",
                "criticality": "important",
                "group": "barcodes",
                "description": "Codigos de barras gerados localmente.",
            },
            {
                "source": Path(app.instance_path) / "reports",
                "archive_prefix": "assets/instance/reports",
                "criticality": "important",
                "group": "reports",
                "description": "Relatorios e PDFs persistidos em disco.",
            },
        ]
        self._full_backup_files = [
            {
                "source": Path(app.instance_path) / "network_settings.json",
                "archive_path": "assets/instance/network_settings.json",
                "criticality": "important",
                "group": "runtime_config",
                "description": "Configuracao de rede do ambiente.",
            },
            {
                "source": Path(app.instance_path) / "secret_key.txt",
                "archive_path": "assets/instance/secret_key.txt",
                "criticality": "critical",
                "group": "runtime_config",
                "description": "Chave secreta local do ambiente.",
            },
        ]

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

    def _apply_restore_pg_timeouts(self, env: dict[str, str]) -> None:
        if self._connect_timeout_seconds > 0:
            env["PGCONNECT_TIMEOUT"] = str(self._connect_timeout_seconds)

        options = ["-c lock_timeout=0", "-c statement_timeout=0"]
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
        entries: list[dict[str, str]] = []
        suportados = {".sql", ".zip"}
        arquivos = sorted(
            (backup for backup in self._backup_root.glob("*") if backup.suffix.lower() in suportados),
            reverse=True,
        )
        for backup in arquivos:
            stat = backup.stat()
            metadata = self._read_backup_metadata(backup)
            entries.append(
                {
                    "name": backup.name,
                    "path": str(backup),
                    "size": f"{stat.st_size // 1024} KB",
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(sep=" ", timespec="seconds"),
                    "kind": str(metadata.get("kind") or "database"),
                    "label": str(metadata.get("label") or "Banco SQL"),
                    "restore_hint": str(metadata.get("restore_hint") or "Restaure com o fluxo oficial."),
                    "manifest_version": str(metadata.get("manifest_version") or "-"),
                }
            )
        return entries

    def diagnostic_report(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add_check(name: str, ok: bool, detail: str, *, required: bool = True) -> None:
            checks.append(
                {
                    "name": name,
                    "ok": bool(ok),
                    "detail": detail,
                    "required": required,
                }
            )

        try:
            uri = self._ensure_uri()
            add_check("Banco configurado", True, "SQLALCHEMY_DATABASE_URI presente.")
        except Exception as exc:
            uri = ""
            add_check("Banco configurado", False, str(exc))

        pg_dump_cmd = self._resolve_postgres_tool("pg_dump")
        pg_dump_found = bool(shutil.which(pg_dump_cmd) or Path(pg_dump_cmd).is_file())
        add_check(
            "pg_dump disponível",
            pg_dump_found,
            pg_dump_cmd if pg_dump_found else "Não localizado no PATH nem por configuração.",
        )

        psql_cmd = self._resolve_postgres_tool("psql")
        psql_found = bool(shutil.which(psql_cmd) or Path(psql_cmd).is_file())
        add_check(
            "psql disponível",
            psql_found,
            psql_cmd if psql_found else "Não localizado no PATH nem por configuração.",
        )

        backup_root_ok = False
        backup_root_detail = str(self._backup_root)
        try:
            self._backup_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self._backup_root, delete=True):
                pass
            backup_root_ok = True
            backup_root_detail = f"Gravação validada em {self._backup_root}"
        except Exception as exc:
            backup_root_detail = str(exc)
        add_check("Pasta de backups gravável", backup_root_ok, backup_root_detail)

        database_ok = False
        database_detail = "Não validada."
        if uri:
            engine = create_engine(uri, future=True)
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                database_ok = True
                database_detail = "Conexão de validação respondeu com sucesso."
            except Exception as exc:
                database_detail = str(exc)
            finally:
                try:
                    engine.dispose()
                except Exception:
                    pass
        add_check("Conexão com PostgreSQL", database_ok, database_detail)

        disk_ok = False
        disk_detail = "Não foi possível obter uso de disco."
        try:
            disk_usage = shutil.disk_usage(self._backup_root)
            disk_ok = True
            disk_detail = f"Livre: {disk_usage.free // (1024 * 1024)} MB"
        except Exception as exc:
            disk_detail = str(exc)
        add_check("Espaço em disco", disk_ok, disk_detail, required=False)

        retention_enabled = self._retention_days > 0 or self._retention_count > 0
        add_check(
            "Retenção configurada",
            retention_enabled,
            (
                f"Dias={self._retention_days}, limite={self._retention_count}"
                if retention_enabled
                else "Retenção automática desativada."
            ),
            required=False,
        )

        ready = all(check["ok"] for check in checks if check["required"])
        return {
            "ready": ready,
            "checks": checks,
            "backup_root": str(self._backup_root),
            "retention": {
                "days": self._retention_days,
                "count": self._retention_count,
                "enabled": retention_enabled,
            },
        }

    def create_backup(self, backup_kind: str = DATABASE_BACKUP_KIND) -> str:
        url = make_url(self._ensure_uri())
        if not url.drivername.startswith("postgresql"):
            raise ValueError("Somente PostgreSQL é suportado pelo backup automático")

        normalized_kind = (backup_kind or self.DATABASE_BACKUP_KIND).strip().lower()
        if normalized_kind == self.DATABASE_BACKUP_KIND:
            created_backup = self._create_postgres_backup()
        elif normalized_kind == self.COMPLETE_BACKUP_KIND:
            created_backup = self._create_complete_backup_package()
        else:
            raise ValueError("Tipo de backup inválido")

        self._apply_retention_policy()
        return created_backup

    def restore_backup(self, backup_name: str) -> str:
        return self.restore_backup_with_progress(backup_name)

    def restore_complete_package(self, package_path: Path, reporter: Callable[[int, str], None] | None = None) -> str:
        def _report(progress: int, message: str) -> None:
            if reporter is None:
                return
            try:
                reporter(int(progress), str(message))
            except Exception:
                return

        _report(5, "Validando pacote completo...")
        if not package_path.exists() or not package_path.is_file():
            raise ValueError("Pacote completo não encontrado para restauração.")
        if package_path.suffix.lower() != ".zip":
            raise ValueError("A restauração completa exige um pacote .zip válido.")

        with tempfile.TemporaryDirectory(prefix="galint_restore_full_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            extracted_dir = temp_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(package_path) as archive:
                members = archive.infolist()
                if not members:
                    raise ValueError("O pacote ZIP está vazio.")
                for member in members:
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError("O pacote ZIP contém caminhos inválidos para restauração segura.")
                archive.extractall(extracted_dir)

            manifest_path = extracted_dir / "manifest.json"
            if not manifest_path.exists():
                raise ValueError("O pacote completo não contém manifest.json.")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if str(manifest.get("backup_kind") or "") != self.COMPLETE_BACKUP_KIND:
                raise ValueError("O pacote informado não é um backup completo do GALINT.")

            dump_info = manifest.get("database_dump") or {}
            dump_archive_path = str(dump_info.get("archive_path") or "").strip()
            if not dump_archive_path:
                raise ValueError("O manifesto do pacote não informa o dump SQL interno.")

            sql_path = extracted_dir / Path(dump_archive_path)
            if not sql_path.exists() or not sql_path.is_file():
                raise ValueError("O dump SQL interno do pacote não foi encontrado.")

            _report(25, "Restaurando dump SQL interno do pacote...")
            self._restore_postgres_backup(sql_path, reporter=_report)

            asset_entries = manifest.get("asset_entries") or []
            restorable_assets = [entry for entry in asset_entries if entry.get("exists")]
            if restorable_assets:
                _report(82, "Restaurando arquivos externos do pacote...")
                self._restore_complete_package_assets(extracted_dir=extracted_dir, asset_entries=restorable_assets, reporter=_report)

        _report(100, "Restauração completa do pacote concluída.")
        return package_path.name

    def get_backup_path(self, backup_name: str) -> Path:
        return self._safe_backup_path(backup_name)

    def ensure_backup_for_update(self, *, max_age_minutes: int | None = None, prefer_complete: bool = True) -> dict[str, Any]:
        age_limit = max_age_minutes if max_age_minutes is not None else self.UPDATE_BACKUP_MAX_AGE_MINUTES
        backups = self.list_backups()
        candidates = backups
        if prefer_complete:
            complete_backups = [item for item in backups if item.get("kind") == self.COMPLETE_BACKUP_KIND]
            candidates = complete_backups or backups

        latest = candidates[0] if candidates else None
        if latest:
            candidate = self.get_backup_path(str(latest["name"]))
            age_minutes = max(0.0, (time.time() - candidate.stat().st_mtime) / 60.0)
            if age_minutes <= age_limit:
                return {
                    "backup_name": str(latest["name"]),
                    "kind": str(latest.get("kind") or self.DATABASE_BACKUP_KIND),
                    "created_now": False,
                    "age_minutes": round(age_minutes, 1),
                }

        backup_kind = self.COMPLETE_BACKUP_KIND if prefer_complete else self.DATABASE_BACKUP_KIND
        backup_name = self.create_backup(backup_kind=backup_kind)
        return {
            "backup_name": backup_name,
            "kind": backup_kind,
            "created_now": True,
            "age_minutes": 0.0,
        }

    def restore_backup_with_progress(
        self,
        backup_name: str,
        reporter: Callable[[int, str], None] | None = None,
        *,
        capture_delta: bool = True,
    ) -> str:
        def _report(progress: int, message: str) -> None:
            if reporter is None:
                return
            try:
                reporter(int(progress), str(message))
            except Exception:
                # Progresso nunca deve quebrar o restore.
                return

        _report(5, "Validando backup...")
        source = self._backup_root / backup_name
        if not source.exists():
            raise ValueError("Backup selecionado não existe")
        url = make_url(self._ensure_uri())
        if source.suffix.lower() == ".sql":
            if not url.drivername.startswith("postgresql"):
                raise ValueError("Este backup é de PostgreSQL, mas o banco atual não é PostgreSQL")

            delta: dict[str, object] = {"tables": {}}
            if capture_delta:
                _report(15, "Capturando movimentos pós-backup...")
                cutoff = self._backup_cutoff_from_name(backup_name, source)
                delta = self._capture_post_backup_delta(cutoff, reporter=_report)

            _report(60, "Restaurando backup no PostgreSQL...")
            self._restore_postgres_backup(source, reporter=_report)

            if capture_delta:
                _report(85, "Reaplicando movimentos pós-backup...")
                self._reapply_post_backup_delta(delta, reporter=_report)

            _report(100, "Restauração concluída.")
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

        if target.suffix.lower() not in {".sql", ".zip"}:
            raise ValueError("Formato de backup inválido")

        return target

    # Helpers -----------------------------------------------------------------

    def _read_backup_metadata(self, backup: Path) -> dict[str, str]:
        if backup.suffix.lower() == ".sql":
            return {
                "kind": self.DATABASE_BACKUP_KIND,
                "label": "Banco SQL",
                "restore_hint": "Pode ser restaurado localmente ou enviado ao ConversionEngine.",
                "manifest_version": "-",
            }

        metadata = {
            "kind": self.COMPLETE_BACKUP_KIND,
            "label": "Pacote completo",
            "restore_hint": "Use o arquivo ZIP no ConversionEngine para validacao e staging.",
            "manifest_version": "-",
        }
        try:
            with zipfile.ZipFile(backup) as archive:
                if "manifest.json" not in archive.namelist():
                    return metadata
                payload = json.loads(archive.read("manifest.json").decode("utf-8"))
                metadata["kind"] = str(payload.get("backup_kind") or metadata["kind"])
                metadata["manifest_version"] = str(payload.get("manifest_schema_version") or "-")
                compatibility = payload.get("compatibility") or {}
                minimum_version = str(compatibility.get("minimum_app_version") or "").strip()
                if minimum_version:
                    metadata["restore_hint"] = (
                        f"Use no ConversionEngine. Compatibilidade minima declarada: {minimum_version}."
                    )
        except Exception:
            return metadata
        return metadata

    def _create_complete_backup_package(self) -> str:
        sql_name = self._create_postgres_backup()
        sql_path = self._backup_root / sql_name
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        package_name = f"galint_backup_full_{timestamp}.zip"
        package_path = self._backup_root / package_name

        asset_entries = self._collect_complete_backup_assets()
        manifest = self._build_complete_backup_manifest(
            sql_name=sql_name,
            sql_path=sql_path,
            package_name=package_name,
            asset_entries=asset_entries,
        )
        readme_content = self._build_complete_backup_readme(manifest)

        try:
            with zipfile.ZipFile(package_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(sql_path, arcname=f"database/{sql_name}")
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                archive.writestr("README_backup_completo.txt", readme_content)
                for entry in asset_entries:
                    source = Path(entry["source_path"])
                    if not source.exists() or not source.is_file():
                        continue
                    archive.write(source, arcname=str(entry["archive_path"]))
        except Exception as exc:
            package_path.unlink(missing_ok=True)
            raise ValueError(f"Erro ao gerar pacote completo: {exc}") from exc
        finally:
            sql_path.unlink(missing_ok=True)

        return package_name

    def _restore_complete_package_assets(
        self,
        *,
        extracted_dir: Path,
        asset_entries: list[dict[str, Any]],
        reporter: Callable[[int, str], None] | None = None,
    ) -> None:
        total = max(1, len(asset_entries))
        for index, entry in enumerate(asset_entries, start=1):
            archive_path = str(entry.get("archive_path") or "").strip().replace("\\", "/")
            if not archive_path:
                continue
            source = extracted_dir / Path(archive_path)
            if not source.exists() or not source.is_file():
                continue

            destination = self._resolve_asset_restore_path(archive_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

            if reporter is not None:
                try:
                    progress = 82 + int((index / total) * 16)
                    reporter(progress, f"Restaurando ativo: {archive_path}")
                except Exception:
                    pass

    def _resolve_asset_restore_path(self, archive_path: str) -> Path:
        normalized = archive_path.strip().replace("\\", "/")
        if normalized.startswith("assets/static/"):
            relative = normalized.removeprefix("assets/static/")
            target = Path(self._app.root_path) / "static" / Path(relative)
        elif normalized.startswith("assets/instance/"):
            relative = normalized.removeprefix("assets/instance/")
            target = Path(self._app.instance_path) / Path(relative)
        else:
            raise ValueError(f"Caminho de ativo não suportado para restore: {archive_path}")

        target_resolved = target.resolve()
        allowed_roots = [
            (Path(self._app.root_path) / "static").resolve(),
            Path(self._app.instance_path).resolve(),
        ]
        if not any(str(target_resolved).startswith(str(root)) for root in allowed_roots):
            raise ValueError(f"Destino inseguro detectado no restore do ativo: {archive_path}")
        return target_resolved

    def _collect_complete_backup_assets(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []

        for directory in self._full_backup_directories:
            source = Path(directory["source"])
            if not source.exists() or not source.is_dir():
                entries.append(
                    {
                        "source_path": str(source),
                        "archive_path": str(directory["archive_prefix"]),
                        "criticality": str(directory["criticality"]),
                        "group": str(directory["group"]),
                        "description": str(directory["description"]),
                        "exists": False,
                        "size_bytes": 0,
                        "sha256": None,
                    }
                )
                continue

            for file_path in sorted(path for path in source.rglob("*") if path.is_file()):
                relative = file_path.relative_to(source).as_posix()
                archive_path = f"{directory['archive_prefix']}/{relative}"
                entries.append(
                    {
                        "source_path": str(file_path),
                        "archive_path": archive_path,
                        "criticality": str(directory["criticality"]),
                        "group": str(directory["group"]),
                        "description": str(directory["description"]),
                        "exists": True,
                        "size_bytes": file_path.stat().st_size,
                        "sha256": self._hash_file(file_path),
                    }
                )

        for file_entry in self._full_backup_files:
            source = Path(file_entry["source"])
            exists = source.exists() and source.is_file()
            entries.append(
                {
                    "source_path": str(source),
                    "archive_path": str(file_entry["archive_path"]),
                    "criticality": str(file_entry["criticality"]),
                    "group": str(file_entry["group"]),
                    "description": str(file_entry["description"]),
                    "exists": exists,
                    "size_bytes": source.stat().st_size if exists else 0,
                    "sha256": self._hash_file(source) if exists else None,
                }
            )

        return entries

    def _build_complete_backup_manifest(
        self,
        *,
        sql_name: str,
        sql_path: Path,
        package_name: str,
        asset_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        existing_assets = [entry for entry in asset_entries if entry.get("exists")]
        missing_assets = [entry for entry in asset_entries if not entry.get("exists")]
        created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        current_version = get_version()

        return {
            "manifest_schema_version": self.MANIFEST_SCHEMA_VERSION,
            "backup_kind": self.COMPLETE_BACKUP_KIND,
            "created_at": created_at,
            "package_name": package_name,
            "app_version": current_version,
            "compatibility": {
                "minimum_app_version": current_version,
                "source_app_version": current_version,
                "recommended_restore_path": "ConversionEngine",
                "direct_restore_supported": False,
            },
            "origin": {
                "hostname": socket.gethostname(),
                "instance_path": str(Path(self._app.instance_path)),
                "project_root": str(self._project_root),
            },
            "database_dump": {
                "name": sql_name,
                "archive_path": f"database/{sql_name}",
                "size_bytes": sql_path.stat().st_size,
                "sha256": self._hash_file(sql_path),
                "criticality": "critical",
            },
            "asset_summary": {
                "files_included": len(existing_assets),
                "files_missing": len(missing_assets),
                "groups": sorted({str(entry.get("group") or "") for entry in asset_entries if entry.get("group")}),
            },
            "asset_entries": asset_entries,
        }

    def _build_complete_backup_readme(self, manifest: dict[str, Any]) -> str:
        database_dump = manifest.get("database_dump") or {}
        compatibility = manifest.get("compatibility") or {}
        summary = manifest.get("asset_summary") or {}
        return (
            "GALINT - BACKUP COMPLETO DO SISTEMA\n"
            "=================================\n\n"
            f"Pacote: {manifest.get('package_name')}\n"
            f"Criado em: {manifest.get('created_at')}\n"
            f"Versao do GALINT: {manifest.get('app_version')}\n"
            f"Backup SQL interno: {database_dump.get('name')}\n"
            f"Arquivos incluidos: {summary.get('files_included', 0)}\n"
            f"Arquivos ausentes no inventario: {summary.get('files_missing', 0)}\n\n"
            "COMO USAR COM O CONVERSIONENGINE\n"
            "1. Abra Configuracoes > ConversionEngine.\n"
            "2. Envie este arquivo .zip como origem.\n"
            "3. O motor vai extrair o pacote, localizar o dump SQL e validar o staging.\n"
            "4. Revise o manifest.json, a compatibilidade e os avisos antes de qualquer implantacao.\n"
            "5. Use restore direto apenas pelo pipeline oficial.\n\n"
            "OBSERVACOES\n"
            f"- Compatibilidade minima declarada: {compatibility.get('minimum_app_version')}.\n"
            "- Este pacote inclui dump SQL e artefatos de disco selecionados do ambiente GALINT.\n"
            "- A restauracao local direta do .zip nao e suportada por este servico; use o ConversionEngine.\n"
        )

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

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

    def _apply_retention_policy(self) -> list[str]:
        if self._retention_days <= 0 and self._retention_count <= 0:
            return []

        supported_suffixes = {".sql", ".zip"}
        backups = sorted(
            [backup for backup in self._backup_root.glob("*") if backup.suffix.lower() in supported_suffixes],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        keep_names: set[str] = set()

        if self._retention_count > 0:
            keep_names.update(backup.name for backup in backups[: self._retention_count])

        if self._retention_days > 0:
            cutoff = time.time() - (self._retention_days * 86400)
            for backup in backups:
                if backup.stat().st_mtime >= cutoff:
                    keep_names.add(backup.name)

        removed: list[str] = []
        for backup in backups:
            if backup.name in keep_names:
                continue
            try:
                backup.unlink()
                removed.append(backup.name)
            except Exception:
                continue

        return removed

    def _restore_postgres_backup(
        self,
        source: Path,
        reporter: Callable[[int, str], None] | None = None,
    ) -> None:
        def _report(progress: int, message: str) -> None:
            if reporter is None:
                return
            try:
                reporter(int(progress), str(message))
            except Exception:
                return

        params = self._postgres_params()
        self._resolve_postgres_tool("psql")
        if shutil.which(self._psql_cmd) is None:
            raise ValueError(
                "Comando psql não encontrado. Adicione-o ao PATH ou configure BACKUP_PSQL com o caminho completo."
            )
        env = os.environ.copy()
        if params["password"]:
            env["PGPASSWORD"] = str(params["password"])
        self._apply_restore_pg_timeouts(env)
        _report(58, "Colocando o banco em modo de restauração...")
        self._dispose_sqlalchemy_connections()
        self._terminate_other_postgres_sessions(params)
        reset_schema_sql = (
            "DROP SCHEMA IF EXISTS public CASCADE; "
            "CREATE SCHEMA public; "
            "GRANT ALL ON SCHEMA public TO PUBLIC;"
        )
        normalized_source, cleanup_source = self._prepare_restore_source(source)
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
        cmd += [
            "-d",
            str(params["database"]),
            "-c",
            reset_schema_sql,
            "-f",
            str(normalized_source),
        ]
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
        finally:
            if cleanup_source is not None:
                try:
                    cleanup_source.unlink(missing_ok=True)
                except Exception:
                    pass
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Falha desconhecida ao executar psql"
            raise ValueError(f"Erro ao restaurar backup PostgreSQL: {message}")

        self._dispose_sqlalchemy_connections()
        _report(78, "Aplicando compatibilidade de schema pós-restauração...")
        self._apply_post_restore_schema_fixes()

    def _prepare_restore_source(self, source: Path) -> tuple[Path, Path | None]:
        temp_path: Path | None = None
        removed_meta_commands = False
        pattern = re.compile(r"^\\(?:un)?restrict\b")

        with source.open("r", encoding="utf-8", errors="replace", newline="") as original:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                suffix=source.suffix or ".sql",
                prefix="restore_clean_",
                dir=source.parent,
                delete=False,
            ) as temp:
                temp_path = Path(temp.name)
                for line in original:
                    if pattern.match(line.strip()):
                        removed_meta_commands = True
                        continue
                    temp.write(line)

        if not removed_meta_commands:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            return source, None

        return temp_path, temp_path

    def _backup_cutoff_from_name(self, backup_name: str, source: Path) -> datetime:
        match = re.search(r"(\d{8})_(\d{6})", backup_name)
        if match:
            try:
                return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
            except ValueError:
                pass
        # fallback: usar timestamp do arquivo
        return datetime.fromtimestamp(source.stat().st_mtime)

    def _dispose_sqlalchemy_connections(self) -> None:
        try:
            from ..extensions import db

            with self._app.app_context():
                db.session.remove()
                try:
                    db.engine.dispose()
                except Exception:
                    pass
        except Exception:
            return

    def _maintenance_uri(self) -> str:
        url = make_url(self._ensure_uri())
        maintenance_db = (self._restore_maintenance_database or "postgres").strip() or "postgres"
        return url.set(database=maintenance_db).render_as_string(hide_password=False)

    def _terminate_other_postgres_sessions(self, params: dict[str, str | int | None]) -> None:
        maintenance_engine = create_engine(self._maintenance_uri(), future=True)
        target_db = str(params["database"])
        deadline = time.monotonic() + max(1, self._restore_connection_drain_seconds)
        terminate_stmt = text(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = :database
              AND pid <> pg_backend_pid()
            """
        )
        count_stmt = text(
            """
            SELECT COUNT(*)
            FROM pg_stat_activity
            WHERE datname = :database
              AND pid <> pg_backend_pid()
            """
        )

        try:
            while True:
                with maintenance_engine.begin() as conn:
                    conn.execute(terminate_stmt, {"database": target_db})
                    remaining = int(conn.execute(count_stmt, {"database": target_db}).scalar() or 0)
                if remaining <= 0:
                    break
                if time.monotonic() >= deadline:
                    raise ValueError(
                        "Ainda existem conexões ativas usando o banco após a drenagem de sessões. "
                        "Feche acessos concorrentes e tente novamente."
                    )
                time.sleep(0.5)
        finally:
            try:
                maintenance_engine.dispose()
            except Exception:
                pass

    def _apply_post_restore_schema_fixes(self) -> None:
        ddl = text(
            """
            DO $$
            BEGIN
                            IF EXISTS (
                                SELECT 1 FROM information_schema.tables
                                WHERE table_schema = 'public' AND table_name = 'stock_balances'
                            ) THEN
                                IF EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_balances' AND column_name = 'codigo_item'
                                ) AND NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_balances' AND column_name = 'product_id'
                                ) THEN
                                    ALTER TABLE stock_balances RENAME COLUMN codigo_item TO product_id;
                                END IF;
                            END IF;

                            IF EXISTS (
                                SELECT 1 FROM information_schema.tables
                                WHERE table_schema = 'public' AND table_name = 'stock_movements'
                            ) THEN
                                IF EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_movements' AND column_name = 'codigo_item'
                                ) AND NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_movements' AND column_name = 'product_id'
                                ) THEN
                                    ALTER TABLE stock_movements RENAME COLUMN codigo_item TO product_id;
                                END IF;

                                IF EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_movements' AND column_name = 'motion_type'
                                ) AND NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_movements' AND column_name = 'movement_type'
                                ) THEN
                                    ALTER TABLE stock_movements RENAME COLUMN motion_type TO movement_type;
                                END IF;

                                IF EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_movements' AND column_name = 'amount_base'
                                ) AND NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_movements' AND column_name = 'quantity_base'
                                ) THEN
                                    ALTER TABLE stock_movements RENAME COLUMN amount_base TO quantity_base;
                                END IF;

                                IF EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_movements' AND column_name = 'unit_type'
                                ) AND NOT EXISTS (
                                    SELECT 1 FROM information_schema.columns
                                    WHERE table_schema = 'public' AND table_name = 'stock_movements' AND column_name = 'unit_base'
                                ) THEN
                                    ALTER TABLE stock_movements RENAME COLUMN unit_type TO unit_base;
                                END IF;
                            END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'entrada_documentos'
              ) THEN
                IF NOT EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public' AND table_name = 'entrada_documentos' AND column_name = 'chave_acesso'
                ) THEN
                  ALTER TABLE entrada_documentos ADD COLUMN chave_acesso varchar(64);
                END IF;

                IF NOT EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public' AND table_name = 'entrada_documentos' AND column_name = 'status_integracao'
                ) THEN
                  ALTER TABLE entrada_documentos ADD COLUMN status_integracao varchar(40) NOT NULL DEFAULT 'manual';
                END IF;

                IF NOT EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public' AND table_name = 'entrada_documentos' AND column_name = 'mensagem_integracao'
                ) THEN
                  ALTER TABLE entrada_documentos ADD COLUMN mensagem_integracao text;
                END IF;
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'itens'
              ) THEN
                IF NOT EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public' AND table_name = 'itens' AND column_name = 'preco_compra_chave_acesso'
                ) THEN
                  ALTER TABLE itens ADD COLUMN preco_compra_chave_acesso varchar(64);
                END IF;
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'finance_lancamentos'
              ) THEN
                IF NOT EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public' AND table_name = 'finance_lancamentos' AND column_name = 'chave_acesso'
                ) THEN
                  ALTER TABLE finance_lancamentos ADD COLUMN chave_acesso varchar(64);
                END IF;
              END IF;
            END $$;
            """
        )
        engine = create_engine(self._ensure_uri(), future=True)
        try:
            with engine.begin() as conn:
                conn.execute(ddl)
        finally:
            try:
                engine.dispose()
            except Exception:
                pass

    def _capture_post_backup_delta(
        self,
        cutoff: datetime,
        reporter: Callable[[int, str], None] | None = None,
    ) -> dict[str, object]:
        """Captura movimentos ocorridos após o backup para reaplicar depois do restore.

        Implementação em lotes para evitar travar o servidor durante operações grandes
        (e para permitir "heartbeats" no progresso).
        """
        engine = create_engine(self._ensure_uri(), future=True)
        tables = [
            {"name": "entradas", "time_col": "data_entrada", "pk": "id_entrada"},
            {"name": "saidas", "time_col": "data_saida", "pk": "id_saida"},
            {"name": "inventario_eventos", "time_col": "data_evento", "pk": "id_evento"},
            {"name": "material_inventario", "time_col": "data_registro", "pk": "id"},
        ]
        payload: dict[str, object] = {"cutoff": cutoff.isoformat(), "tables": {}}
        last_hb = time.monotonic()
        batch_size = int(os.environ.get("GALINT_RESTORE_CAPTURE_BATCH_SIZE") or 1000)
        hb_interval_s = float(os.environ.get("GALINT_RESTORE_HEARTBEAT_SECONDS") or 1.5)

        def _hb(progress: int, message: str) -> None:
            nonlocal last_hb
            if reporter is None:
                return
            now = time.monotonic()
            if (now - last_hb) < hb_interval_s:
                return
            try:
                reporter(int(progress), str(message))
            finally:
                last_hb = now

        try:
            with engine.connect() as conn:
                # stream_results ajuda a não carregar tudo de uma vez quando o driver suporta.
                conn = conn.execution_options(stream_results=True)
                total_tables = max(1, len(tables))
                for index, table in enumerate(tables):
                    base_progress = 15 + int((index * 40) / total_tables)  # 15..55
                    table_name = str(table["name"])
                    _hb(base_progress, f"Capturando movimentos: {table_name}...")

                    stmt = text(f"SELECT * FROM {table_name} WHERE {table['time_col']} > :cutoff")
                    result = conn.execute(stmt, {"cutoff": cutoff})
                    mappings = result.mappings()

                    rows: list[dict[str, object]] = []
                    captured = 0
                    while True:
                        batch = mappings.fetchmany(batch_size)
                        if not batch:
                            break
                        rows.extend(batch)
                        captured += len(batch)

                        _hb(base_progress, f"Capturando movimentos: {table_name}... ({captured} linhas)")

                        # Ceder execução para evitar starvation de outras threads/requests.
                        if captured % (batch_size * 5) == 0:
                            time.sleep(0)

                    payload["tables"][table_name] = rows
        finally:
            try:
                engine.dispose()
            except Exception:
                pass
        return payload

    def _reapply_post_backup_delta(
        self,
        delta: dict[str, object],
        reporter: Callable[[int, str], None] | None = None,
    ) -> None:
        """Reaplica movimentos pós-backup para evitar voltar itens retirados."""
        if not delta or not isinstance(delta.get("tables"), dict):
            return
        tables: dict[str, list[dict[str, object]]] = delta.get("tables", {})  # type: ignore[assignment]
        engine = create_engine(self._ensure_uri(), future=True)

        last_hb = time.monotonic()
        batch_size = int(os.environ.get("GALINT_RESTORE_REAPPLY_BATCH_SIZE") or 1000)
        hb_interval_s = float(os.environ.get("GALINT_RESTORE_HEARTBEAT_SECONDS") or 1.5)

        def _hb(progress: int, message: str) -> None:
            nonlocal last_hb
            if reporter is None:
                return
            now = time.monotonic()
            if (now - last_hb) < hb_interval_s:
                return
            try:
                reporter(int(progress), str(message))
            finally:
                last_hb = now

        order = ["entradas", "saidas", "inventario_eventos", "material_inventario"]
        pks = {
            "entradas": "id_entrada",
            "saidas": "id_saida",
            "inventario_eventos": "id_evento",
            "material_inventario": "id",
        }

        try:
            with engine.begin() as conn:
                total_tables = len([t for t in order if tables.get(t)])
                processed = 0
                for table in order:
                    rows = tables.get(table) or []
                    if not rows:
                        continue

                    base_progress = 85 + int((processed * 12) / max(1, total_tables))  # 85..97
                    _hb(base_progress, f"Reaplicando movimentos: {table}... ({len(rows)} linhas)")

                    cols = list(rows[0].keys())
                    columns = ", ".join(cols)
                    values = ", ".join([f":{c}" for c in cols])
                    pk = pks.get(table)
                    on_conflict = f" ON CONFLICT ({pk}) DO NOTHING" if pk else ""
                    stmt = text(f"INSERT INTO {table} ({columns}) VALUES ({values}){on_conflict}")

                    for start in range(0, len(rows), batch_size):
                        chunk = rows[start : start + batch_size]
                        conn.execute(stmt, chunk)
                        applied = min(start + len(chunk), len(rows))
                        _hb(base_progress, f"Reaplicando movimentos: {table}... ({applied}/{len(rows)})")
                        if applied % (batch_size * 5) == 0:
                            time.sleep(0)

                    processed += 1

                _hb(98, "Ajustando sequências...")
                for table, pk in pks.items():
                    seq_stmt = text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), GREATEST((SELECT COALESCE(MAX({pk}), 0) FROM {table}), 1))"
                    )
                    conn.execute(seq_stmt)
        finally:
            try:
                engine.dispose()
            except Exception:
                pass
