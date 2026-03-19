"""ConversionEngine: análise e preparação de bases compatíveis com GALINT.

Escopo atual:
- Entrada suportada: dump SQL em texto plano (ex.: pg_dump .sql)
- Análise estrutural com score de compatibilidade
- Geração de artefato técnico (.zip) e, quando seguro, base .sql apta a restore

Observação importante:
- O deploy direto só é liberado quando o dump já está estruturalmente compatível
  com as tabelas-alvo do GALINT. Não há conversão universal entre esquemas
  arbitrários nesta primeira versão.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import shutil
import threading
import time
from typing import Any, Protocol
from uuid import uuid4
import zipfile

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .backup import BackupService
from ..extensions import db


class _AppWithContext(Protocol):
    def app_context(self): ...


@dataclass
class ConversionJobState:
    job_id: str
    user_key: str
    source_name: str
    stored_name: str
    status: str
    progress: int
    phase: str
    message: str
    error: str | None
    started_at: str
    updated_at: str
    finished_at: str | None
    metrics: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    logs: list[dict[str, str]] = field(default_factory=list)


_jobs: dict[str, ConversionJobState] = {}
_lock = threading.Lock()
_active_jobs_by_user: dict[str, str] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append_log(state: ConversionJobState, message: str) -> None:
    state.logs.append({"timestamp": _now_iso(), "message": str(message)})
    if len(state.logs) > 40:
        del state.logs[:-40]


def start_conversion_job(
    *,
    app: _AppWithContext,
    user_key: str,
    source_name: str,
    stored_name: str,
) -> str:
    with _lock:
        existing_job_id = _active_jobs_by_user.get(user_key)
        if existing_job_id:
            existing = _jobs.get(existing_job_id)
            if existing and existing.status == "running":
                return existing.job_id

        job_id = str(uuid4())
        state = ConversionJobState(
            job_id=job_id,
            user_key=user_key,
            source_name=source_name,
            stored_name=stored_name,
            status="running",
            progress=1,
            phase="queued",
            message="Job criado.",
            error=None,
            started_at=_now_iso(),
            updated_at=_now_iso(),
            finished_at=None,
        )
        _append_log(state, "Job enfileirado para análise da base externa.")
        _jobs[job_id] = state
        _active_jobs_by_user[user_key] = job_id

    def _update(
        progress: int,
        message: str,
        *,
        phase: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        with _lock:
            current = _jobs.get(job_id)
            if not current:
                return
            current.progress = max(0, min(100, int(progress)))
            current.message = str(message)
            if phase:
                current.phase = phase
            if metrics:
                current.metrics.update(metrics)
            current.updated_at = _now_iso()
            _append_log(current, message)

    def _finish_success(result: dict[str, Any]) -> None:
        with _lock:
            current = _jobs.get(job_id)
            if not current:
                return
            current.status = "success"
            current.progress = 100
            current.phase = "completed"
            current.message = "ConversionEngine concluído."
            current.result = result
            current.updated_at = _now_iso()
            current.finished_at = _now_iso()
            _append_log(current, "Artefatos de conversão gerados com sucesso.")
            if _active_jobs_by_user.get(user_key) == job_id:
                _active_jobs_by_user.pop(user_key, None)

    def _finish_error(exc: Exception) -> None:
        with _lock:
            current = _jobs.get(job_id)
            if not current:
                return
            current.status = "error"
            current.phase = "error"
            current.error = str(exc)
            current.message = "Falha ao processar a base enviada."
            current.updated_at = _now_iso()
            current.finished_at = _now_iso()
            _append_log(current, f"Erro: {exc}")
            if _active_jobs_by_user.get(user_key) == job_id:
                _active_jobs_by_user.pop(user_key, None)

    def _runner() -> None:
        try:
            with app.app_context():
                service = ConversionEngineService(app)
                result = service.run_conversion(
                    stored_name=stored_name,
                    source_name=source_name,
                    reporter=_update,
                )
            _finish_success(result)
        except Exception as exc:  # noqa: BLE001
            _finish_error(exc)

    thread = threading.Thread(target=_runner, daemon=True, name=f"galint-conversion-{job_id}")
    thread.start()
    return job_id


def get_conversion_job_state(*, job_id: str, user_key: str) -> dict[str, Any] | None:
    with _lock:
        state = _jobs.get(job_id)
        if not state or state.user_key != user_key:
            return None
        return asdict(state)


class ConversionEngineService:
    ALLOWED_SUFFIXES = {".sql", ".zip", ".sqlite", ".db"}
    SQL_SUFFIXES = {".sql"}
    SQLITE_SUFFIXES = {".sqlite", ".db"}
    TABLE_ALIAS_MAP = {
        "item": "itens",
        "items": "itens",
        "material": "itens",
        "materials": "itens",
        "product": "itens",
        "products": "itens",
        "user": "usuarios",
        "users": "usuarios",
        "employee": "usuarios",
        "employees": "usuarios",
        "entrada": "entradas",
        "entradas": "entradas",
        "entry": "entradas",
        "entries": "entradas",
        "saida": "saidas",
        "saidas": "saidas",
        "output": "saidas",
        "outputs": "saidas",
        "movement": "inventario_eventos",
        "movements": "inventario_eventos",
        "inventory_events": "inventario_eventos",
        "invoice": "notas_fiscais",
        "invoices": "notas_fiscais",
        "nf": "notas_fiscais",
        "nfs": "notas_fiscais",
        "supplier": "fornecedores",
        "suppliers": "fornecedores",
    }

    CREATE_TABLE_RE = re.compile(
        r'^CREATE TABLE(?: IF NOT EXISTS)?\s+(?:ONLY\s+)?(?:public\.)?"?([A-Za-z_][\w$]*)"?\s*\($',
        re.IGNORECASE,
    )
    COPY_RE = re.compile(
        r'^COPY\s+(?:public\.)?"?([A-Za-z_][\w$]*)"?\s*\((.*?)\)\s+FROM\s+stdin;\s*$',
        re.IGNORECASE,
    )
    INSERT_RE = re.compile(
        r'^INSERT INTO\s+(?:ONLY\s+)?(?:public\.)?"?([A-Za-z_][\w$]*)"?\s*\((.*?)\)\s+VALUES\s+',
        re.IGNORECASE,
    )
    COLUMN_RE = re.compile(r'^"?([A-Za-z_][\w$]*)"?\s+')
    STRUCTURAL_KEYWORDS = {
        "constraint",
        "primary",
        "foreign",
        "unique",
        "check",
        "exclude",
        "like",
    }

    def __init__(self, app):
        self.app = app
        self.root_dir = Path(app.instance_path) / "conversionengine"
        self.sources_dir = self.root_dir / "sources"
        self.outputs_dir = self.root_dir / "outputs"
        self.staging_dir = self.root_dir / "staging"
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.backup_service = BackupService(app)

    def dashboard_payload(self) -> dict[str, Any]:
        target_schema = self.get_target_schema()
        backups = self.backup_service.list_backups()
        recent_packages = sorted(self.outputs_dir.glob("*.zip"), reverse=True)
        core_tables = self.core_tables(target_schema)
        return {
            "target_tables": len(target_schema),
            "core_tables": len(core_tables),
            "backups_available": len(backups),
            "recent_packages": len(recent_packages[:8]),
            "supported_input": "SQL plain (.sql), ZIP com SQL/SQLite e SQLite (.sqlite/.db)",
        }

    def store_upload(self, upload: FileStorage) -> dict[str, str]:
        filename = secure_filename((upload.filename or "").strip())
        if not filename:
            raise ValueError("Selecione um arquivo de origem para análise.")

        suffix = Path(filename).suffix.lower()
        if suffix not in self.ALLOWED_SUFFIXES:
            raise ValueError(
                "Formato não suportado. Envie um .sql, um .zip com .sql/.sqlite/.db ou uma base SQLite (.sqlite/.db)."
            )

        stored_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:10]}_{filename}"
        destination = self.sources_dir / stored_name
        upload.save(destination)

        if destination.stat().st_size <= 0:
            destination.unlink(missing_ok=True)
            raise ValueError("O arquivo enviado está vazio.")

        return {
            "source_name": filename,
            "stored_name": stored_name,
        }

    def run_conversion(self, *, stored_name: str, source_name: str, reporter) -> dict[str, Any]:
        source_path = self.sources_dir / stored_name
        if not source_path.exists():
            raise ValueError("Arquivo-fonte da conversão não foi encontrado.")

        started = time.perf_counter()
        reporter(3, "Validando artefato recebido...", phase="validation")
        prepared = self.prepare_source_for_analysis(
            source_path=source_path,
            source_name=source_name,
            reporter=reporter,
        )
        reporter(12, "Perfilando origem em staging isolado...", phase="staging")
        profile = self.profile_source(prepared=prepared, reporter=reporter)
        reporter(62, "Comparando estrutura externa com o schema GALINT...", phase="matching")

        target_schema = self.get_target_schema()
        assessment = self.assess_profile(profile=profile, target_schema=target_schema)
        duration = max(0.001, time.perf_counter() - started)
        reporter(
            82,
            "Gerando pacote técnico e preparando base convertida...",
            phase="packaging",
            metrics={
                "elapsed_seconds": round(duration, 2),
                "throughput_rows_per_second": round(profile["total_rows"] / duration, 2),
            },
        )
        artifacts = self.build_artifacts(
            source_path=source_path,
            analysis_path=Path(prepared["analysis_path"]),
            source_name=source_name,
            profile=profile,
            assessment=assessment,
        )
        summary = assessment["summary"]
        reporter(
            96,
            "Finalizando o relatório operacional do mecanismo...",
            phase="finalizing",
            metrics={
                "compatibility_score": summary["compatibility_score"],
                "matched_tables": summary["matched_tables"],
                "rows_detected": profile["total_rows"],
                "estimated_minutes": summary["estimated_minutes"],
            },
        )
        return {
            "summary": summary,
            "source_profile": {
                "source_kind": profile["source_kind"],
                "source_engine": profile["source_engine"],
                "size_bytes": profile["size_bytes"],
                "size_mb": profile["size_mb"],
                "total_rows": profile["total_rows"],
                "total_tables": len(profile["tables"]),
                "detected_statements": profile["detected_statements"],
                "staging_workspace": profile["staging_workspace"],
                "analysis_source_name": profile["analysis_source_name"],
            },
            "mappings": assessment["mappings"],
            "tasks": assessment["tasks"],
            "artifacts": artifacts,
            "supported": {
                "deploy_direct": bool(artifacts.get("deploy_backup_name")),
                "download_package": True,
                "download_sql": bool(artifacts.get("converted_sql_name")),
            },
        }

    def prepare_source_for_analysis(self, *, source_path: Path, source_name: str, reporter) -> dict[str, Any]:
        source_suffix = source_path.suffix.lower()
        stage_token = f"stage_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        stage_dir = self.staging_dir / stage_token
        stage_dir.mkdir(parents=True, exist_ok=True)

        staged_original = stage_dir / source_path.name
        shutil.copy2(source_path, staged_original)

        metadata = {
            "source_name": source_name,
            "stored_name": source_path.name,
            "received_at": _now_iso(),
            "stage_token": stage_token,
        }

        if source_suffix in self.SQL_SUFFIXES:
            metadata.update(
                {
                    "source_kind": "sql_dump",
                    "analysis_path": str(staged_original),
                    "analysis_source_name": staged_original.name,
                }
            )
        elif source_suffix in self.SQLITE_SUFFIXES:
            metadata.update(
                {
                    "source_kind": "sqlite_database",
                    "analysis_path": str(staged_original),
                    "analysis_source_name": staged_original.name,
                }
            )
        elif source_suffix == ".zip":
            reporter(8, "Descompactando origem em staging isolado...", phase="staging")
            extracted_dir = stage_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(staged_original) as archive:
                members = archive.infolist()
                if not members:
                    raise ValueError("O arquivo ZIP enviado está vazio.")
                for member in members:
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError("O ZIP contém caminhos inválidos para extração segura.")
                archive.extractall(extracted_dir)

            candidates = [
                item
                for item in extracted_dir.rglob("*")
                if item.is_file() and item.suffix.lower() in (self.SQL_SUFFIXES | self.SQLITE_SUFFIXES)
            ]
            if not candidates:
                raise ValueError("Nenhum .sql, .sqlite ou .db foi encontrado dentro do ZIP enviado.")

            candidates.sort(
                key=lambda item: (
                    0 if item.suffix.lower() in self.SQL_SUFFIXES else 1,
                    -item.stat().st_size,
                    item.name.lower(),
                )
            )
            chosen = candidates[0]
            metadata.update(
                {
                    "source_kind": "zip_package",
                    "analysis_path": str(chosen),
                    "analysis_source_name": chosen.name,
                    "zip_candidates": [str(item.relative_to(extracted_dir)).replace('\\', '/') for item in candidates[:12]],
                }
            )
        else:
            raise ValueError("Formato de origem não suportado pelo motor.")

        metadata_path = stage_dir / "staging.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return metadata

    def profile_source(self, *, prepared: dict[str, Any], reporter) -> dict[str, Any]:
        analysis_path = Path(prepared["analysis_path"])
        source_kind = prepared["source_kind"]
        if source_kind == "sqlite_database" or analysis_path.suffix.lower() in self.SQLITE_SUFFIXES:
            profile = self.profile_sqlite_database(source_path=analysis_path, reporter=reporter)
        else:
            profile = self.profile_source_dump(source_path=analysis_path, reporter=reporter)

        profile["source_kind"] = source_kind
        profile["analysis_source_name"] = prepared["analysis_source_name"]
        profile["staging_workspace"] = prepared["stage_token"]
        if prepared.get("zip_candidates"):
            profile["zip_candidates"] = prepared["zip_candidates"]
        return profile

    def get_target_schema(self) -> dict[str, list[str]]:
        schema: dict[str, list[str]] = {}
        for table in db.metadata.sorted_tables:
            schema[table.name] = [column.name for column in table.columns]
        return schema

    @staticmethod
    def core_tables(target_schema: dict[str, list[str]]) -> list[str]:
        preferred = ["usuarios", "itens", "entradas", "saidas", "notas_fiscais", "inventario_eventos"]
        return [table for table in preferred if table in target_schema]

    @staticmethod
    def normalize_identifier(value: str) -> str:
        cleaned = (value or "").strip().strip('"').lower()
        cleaned = cleaned.replace("public.", "")
        return re.sub(r"[^a-z0-9_]+", "_", cleaned)

    def resolve_target_table(self, source_table: str, target_schema: dict[str, list[str]]) -> tuple[str | None, bool]:
        normalized = self.normalize_identifier(source_table)
        normalized_targets = {self.normalize_identifier(name): name for name in target_schema}
        if normalized in normalized_targets:
            return normalized_targets[normalized], False

        alias_target = self.TABLE_ALIAS_MAP.get(normalized)
        if alias_target and alias_target in target_schema:
            return alias_target, True

        if normalized.endswith("s") and normalized[:-1] in normalized_targets:
            return normalized_targets[normalized[:-1]], True
        if (normalized + "s") in normalized_targets:
            return normalized_targets[normalized + "s"], True
        return None, False

    def profile_source_dump(self, *, source_path: Path, reporter) -> dict[str, Any]:
        size_bytes = source_path.stat().st_size
        processed_bytes = 0
        tables: dict[str, dict[str, Any]] = {}
        current_create_table: str | None = None
        current_copy_table: str | None = None
        detected_statements = 0
        started = time.perf_counter()
        source_engine = "postgresql"
        engine_hints = {"postgresql": 0, "mysql": 0, "sqlite": 0}

        def ensure_table(table_name: str) -> dict[str, Any]:
            table = tables.setdefault(
                table_name,
                {"columns": set(), "rows": 0, "create_seen": False, "copy_seen": False, "insert_seen": False},
            )
            return table

        with source_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line_number, line in enumerate(handle, start=1):
                processed_bytes += len(line.encode("utf-8", errors="ignore"))
                stripped = line.strip()

                if "COPY " in line or " FROM stdin;" in line or "SET search_path" in line:
                    engine_hints["postgresql"] += 1
                if "ENGINE=" in line or "AUTO_INCREMENT" in line or "LOCK TABLES" in line:
                    engine_hints["mysql"] += 1
                if "PRAGMA " in line or "sqlite_sequence" in line or "BEGIN TRANSACTION" in line:
                    engine_hints["sqlite"] += 1

                if current_copy_table:
                    if stripped == r"\\.":
                        current_copy_table = None
                    elif stripped:
                        ensure_table(current_copy_table)["rows"] += 1
                    if line_number % 500 == 0:
                        reporter(
                            18 + int((processed_bytes / max(1, size_bytes)) * 34),
                            f"Lendo bloco COPY: {current_copy_table}...",
                            phase="profiling",
                            metrics=self._profiling_metrics(
                                tables=tables,
                                processed_bytes=processed_bytes,
                                size_bytes=size_bytes,
                                started=started,
                            ),
                        )
                    continue

                create_match = self.CREATE_TABLE_RE.match(stripped)
                if create_match:
                    current_create_table = create_match.group(1)
                    ensure_table(current_create_table)["create_seen"] = True
                    detected_statements += 1
                    continue

                if current_create_table:
                    if stripped.startswith(");") or stripped == ")":
                        current_create_table = None
                        continue
                    col_match = self.COLUMN_RE.match(stripped)
                    if col_match:
                        candidate = self.normalize_identifier(col_match.group(1))
                        if candidate and candidate not in self.STRUCTURAL_KEYWORDS:
                            ensure_table(current_create_table)["columns"].add(candidate)
                    continue

                copy_match = self.COPY_RE.match(stripped)
                if copy_match:
                    table_name = copy_match.group(1)
                    cols = [self.normalize_identifier(part.strip()) for part in copy_match.group(2).split(",") if part.strip()]
                    table = ensure_table(table_name)
                    table["copy_seen"] = True
                    table["columns"].update(cols)
                    current_copy_table = table_name
                    detected_statements += 1
                    continue

                insert_match = self.INSERT_RE.match(stripped)
                if insert_match:
                    table_name = insert_match.group(1)
                    cols = [self.normalize_identifier(part.strip()) for part in insert_match.group(2).split(",") if part.strip()]
                    table = ensure_table(table_name)
                    table["insert_seen"] = True
                    table["columns"].update(cols)
                    values_part = stripped.partition(" VALUES ")[2]
                    row_count = max(1, values_part.count("),(") + values_part.count("), (") + 1)
                    table["rows"] += row_count
                    detected_statements += 1

                if line_number % 500 == 0:
                    reporter(
                        18 + int((processed_bytes / max(1, size_bytes)) * 34),
                        "Perfilando estrutura e volume do dump recebido...",
                        phase="profiling",
                        metrics=self._profiling_metrics(
                            tables=tables,
                            processed_bytes=processed_bytes,
                            size_bytes=size_bytes,
                            started=started,
                        ),
                    )

        profiled_tables = {
            name: {
                "columns": sorted(meta["columns"]),
                "rows": int(meta["rows"]),
                "create_seen": bool(meta["create_seen"]),
                "copy_seen": bool(meta["copy_seen"]),
                "insert_seen": bool(meta["insert_seen"]),
            }
            for name, meta in sorted(tables.items())
        }
        if not profiled_tables:
            raise ValueError(
                "Nenhuma tabela foi detectada no dump enviado. Gere um .sql em texto plano e tente novamente."
            )

        source_engine = max(engine_hints.items(), key=lambda item: item[1])[0] if any(engine_hints.values()) else "postgresql"

        return {
            "tables": profiled_tables,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "total_rows": sum(table["rows"] for table in profiled_tables.values()),
            "detected_statements": detected_statements,
            "source_engine": source_engine,
        }

    def profile_sqlite_database(self, *, source_path: Path, reporter) -> dict[str, Any]:
        size_bytes = source_path.stat().st_size
        started = time.perf_counter()
        tables: dict[str, dict[str, Any]] = {}

        with sqlite3.connect(source_path) as connection:
            cursor = connection.cursor()
            names = [
                row[0]
                for row in cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            ]
            if not names:
                raise ValueError("A base SQLite enviada não contém tabelas de usuário para análise.")

            total = len(names)
            for index, table_name in enumerate(names, start=1):
                columns = [
                    self.normalize_identifier(row[1])
                    for row in cursor.execute(f'PRAGMA table_info("{table_name}")').fetchall()
                    if row[1]
                ]
                row_total = cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
                tables[table_name] = {
                    "columns": sorted(set(columns)),
                    "rows": int(row_total or 0),
                    "create_seen": True,
                    "copy_seen": False,
                    "insert_seen": True,
                }
                reporter(
                    18 + int((index / max(1, total)) * 34),
                    f"Lendo staging SQLite: {table_name}...",
                    phase="profiling",
                    metrics={
                        "tables_detected": len(tables),
                        "rows_detected": sum(int(meta["rows"]) for meta in tables.values()),
                        "scan_progress_pct": round((index / max(1, total)) * 100, 1),
                        "throughput_mb_per_second": round((size_bytes / (1024 * 1024)) / max(0.001, time.perf_counter() - started), 2),
                    },
                )

        return {
            "tables": tables,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "total_rows": sum(table["rows"] for table in tables.values()),
            "detected_statements": len(tables),
            "source_engine": "sqlite",
        }

    def _profiling_metrics(
        self,
        *,
        tables: dict[str, dict[str, Any]],
        processed_bytes: int,
        size_bytes: int,
        started: float,
    ) -> dict[str, Any]:
        elapsed = max(0.001, time.perf_counter() - started)
        rows_detected = sum(int(meta["rows"]) for meta in tables.values())
        return {
            "tables_detected": len(tables),
            "rows_detected": rows_detected,
            "scan_progress_pct": round((processed_bytes / max(1, size_bytes)) * 100, 1),
            "throughput_mb_per_second": round((processed_bytes / (1024 * 1024)) / elapsed, 2),
        }

    def assess_profile(self, *, profile: dict[str, Any], target_schema: dict[str, list[str]]) -> dict[str, Any]:
        mappings: list[dict[str, Any]] = []
        matched_tables = 0
        exact_match_tables = 0
        column_scores: list[float] = []
        unmatched_tables: list[str] = []
        alias_mapped_tables: list[str] = []
        source_engine = str(profile.get("source_engine") or "postgresql")
        source_kind = str(profile.get("source_kind") or "sql_dump")

        for source_table, source_meta in profile["tables"].items():
            target_table, mapped_by_alias = self.resolve_target_table(source_table, target_schema)
            source_cols = set(source_meta["columns"])
            target_cols = set(target_schema.get(target_table or "", []))
            overlap = sorted(source_cols & target_cols)
            column_score = round(
                (len(overlap) / max(1, max(len(source_cols), len(target_cols)))) * 100,
                1,
            ) if target_table else 0.0

            if target_table:
                matched_tables += 1
                if not mapped_by_alias:
                    exact_match_tables += 1
                else:
                    alias_mapped_tables.append(source_table)
                column_scores.append(column_score)
            else:
                unmatched_tables.append(source_table)

            mappings.append(
                {
                    "source_table": source_table,
                    "target_table": target_table,
                    "mapped_by_alias": mapped_by_alias,
                    "rows": int(source_meta["rows"]),
                    "column_score": column_score,
                    "source_columns": sorted(source_cols),
                    "matched_columns": overlap,
                    "missing_in_source": sorted(target_cols - source_cols)[:12] if target_table else [],
                    "extra_in_source": sorted(source_cols - target_cols)[:12] if target_table else sorted(source_cols)[:12],
                }
            )

        total_source_tables = max(1, len(profile["tables"]))
        table_score = round((matched_tables / total_source_tables) * 100, 1)
        column_score_avg = round(sum(column_scores) / max(1, len(column_scores)), 1)
        exactness_score = round((exact_match_tables / total_source_tables) * 100, 1)

        core_tables = self.core_tables(target_schema)
        matched_targets = {item["target_table"] for item in mappings if item["target_table"]}
        missing_core_tables = [table for table in core_tables if table not in matched_targets]
        exact_targets = {
            item["target_table"]
            for item in mappings
            if item["target_table"] and not item["mapped_by_alias"]
        }
        missing_exact_core_tables = [table for table in core_tables if table not in exact_targets]

        raw_score = (table_score * 0.45) + (column_score_avg * 0.35) + (exactness_score * 0.20)
        penalty = min(40.0, len(missing_core_tables) * 8.0)
        compatibility_score = round(max(0.0, min(100.0, raw_score - penalty)), 1)

        estimated_minutes = round(
            max(
                1.0,
                (profile["size_mb"] * 0.6) + (profile["total_rows"] / 50000.0) + (len(profile["tables"]) * 0.12),
            ),
            1,
        )

        deployable = (
            compatibility_score >= 72
            and not missing_exact_core_tables
            and matched_tables > 0
            and matched_tables == exact_match_tables
            and source_engine == "postgresql"
            and source_kind != "sqlite_database"
        )

        if compatibility_score >= 85 and deployable:
            risk_level = "baixo"
        elif compatibility_score >= 60:
            risk_level = "medio"
        else:
            risk_level = "alto"

        blockers: list[str] = []
        if source_engine != "postgresql":
            blockers.append(
                f"Origem detectada como {source_engine}; o deploy direto do GALINT continua restrito a artefatos PostgreSQL compatíveis."
            )
        if missing_exact_core_tables:
            blockers.append(
                "Tabelas críticas sem correspondência exata no dump: " + ", ".join(sorted(missing_exact_core_tables))
            )
        if alias_mapped_tables:
            blockers.append(
                "Há mapeamentos por alias; a implantação direta exige nomes exatos de tabelas no dump."
            )
        if not deployable:
            blockers.append(
                "A implantação direta foi bloqueada. O pacote técnico continua disponível para revisão e ajuste manual."
            )

        tasks = [
            {
                "kind": "critical",
                "title": "Executar backup do ambiente atual",
                "detail": "Sempre gere um backup do GALINT antes de restaurar qualquer base convertida.",
            },
            {
                "kind": "analysis",
                "title": "Validar staging isolado",
                "detail": f"A origem foi preparada no staging {profile.get('staging_workspace')} antes da comparação com o schema GALINT.",
            },
            {
                "kind": "analysis",
                "title": "Validar score e colunas faltantes",
                "detail": "Revise o score final, as tabelas não mapeadas e as colunas ausentes antes do deploy.",
            },
        ]
        if source_kind == "zip_package":
            tasks.append(
                {
                    "kind": "analysis",
                    "title": "Confirmar artefato escolhido dentro do ZIP",
                    "detail": f"O motor selecionou {profile.get('analysis_source_name')} como base principal para análise.",
                }
            )
        if source_engine == "sqlite":
            tasks.append(
                {
                    "kind": "mapping",
                    "title": "Planejar exportação SQLite para SQL PostgreSQL",
                    "detail": "A análise estrutural foi concluída, mas a implantação direta exige uma etapa posterior de conversão SQL compatível com PostgreSQL.",
                }
            )
        for table_name in unmatched_tables[:8]:
            tasks.append(
                {
                    "kind": "mapping",
                    "title": f"Mapear tabela externa {table_name}",
                    "detail": "Definir equivalência com o schema GALINT ou remover este bloco do dump antes do deploy.",
                }
            )
        for blocker in blockers:
            tasks.append({"kind": "blocker", "title": "Ajuste obrigatório", "detail": blocker})

        return {
            "summary": {
                "compatibility_score": compatibility_score,
                "table_score": table_score,
                "column_score": column_score_avg,
                "exactness_score": exactness_score,
                "matched_tables": matched_tables,
                "exact_match_tables": exact_match_tables,
                "total_source_tables": len(profile["tables"]),
                "missing_core_tables": missing_core_tables,
                "estimated_minutes": estimated_minutes,
                "risk_level": risk_level,
                "deployable": deployable,
                "deploy_blockers": blockers,
                "source_engine": source_engine,
                "source_kind": source_kind,
            },
            "mappings": sorted(mappings, key=lambda item: (-item["rows"], item["source_table"])),
            "tasks": tasks,
        }

    def build_artifacts(
        self,
        *,
        source_path: Path,
        analysis_path: Path,
        source_name: str,
        profile: dict[str, Any],
        assessment: dict[str, Any],
    ) -> dict[str, Any]:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        summary = assessment["summary"]
        base_name = f"conversionengine_{timestamp}_{uuid4().hex[:8]}"

        manifest_path = self.outputs_dir / f"{base_name}_manifest.json"
        readme_path = self.outputs_dir / f"{base_name}_README.txt"
        package_path = self.outputs_dir / f"{base_name}.zip"

        manifest_payload = {
            "generated_at": _now_iso(),
            "source_name": source_name,
            "summary": summary,
            "profile": profile,
            "mappings": assessment["mappings"],
            "tasks": assessment["tasks"],
        }
        manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        readme_path.write_text(self._artifact_readme(source_name, summary), encoding="utf-8")

        converted_sql_name = None
        deploy_backup_name = None
        if summary["deployable"]:
            converted_sql_name = f"{base_name}.sql"
            converted_sql_path = self.outputs_dir / converted_sql_name
            shutil.copy2(analysis_path, converted_sql_path)

            deploy_backup_name = f"{base_name}_deploy.sql"
            deploy_backup_path = self.backup_service._backup_root / deploy_backup_name
            shutil.copy2(analysis_path, deploy_backup_path)

        with zipfile.ZipFile(package_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(source_path, arcname=f"origem/{source_path.name}")
            if analysis_path != source_path and analysis_path.exists():
                archive.write(analysis_path, arcname=f"staging/{analysis_path.name}")
            archive.write(manifest_path, arcname="manifest.json")
            archive.write(readme_path, arcname="README_implantacao.txt")
            if converted_sql_name:
                archive.write(self.outputs_dir / converted_sql_name, arcname=f"base_convertida/{converted_sql_name}")

        return {
            "package_name": package_path.name,
            "manifest_name": manifest_path.name,
            "readme_name": readme_path.name,
            "converted_sql_name": converted_sql_name,
            "deploy_backup_name": deploy_backup_name,
        }

    @staticmethod
    def _artifact_readme(source_name: str, summary: dict[str, Any]) -> str:
        deploy_text = (
            "A base convertida foi considerada apta para implantação direta no GALINT."
            if summary["deployable"]
            else "A implantação direta foi bloqueada. Use primeiro o pacote técnico e o staging para ajuste manual da origem."
        )
        blockers = "\n".join(f"- {item}" for item in summary["deploy_blockers"]) or "- Nenhum bloqueio crítico registrado."
        return (
            "CONVERSIONENGINE - PACOTE DE IMPLANTACAO\n"
            "======================================\n\n"
            f"Arquivo de origem: {source_name}\n"
            f"Engine detectada: {summary['source_engine']}\n"
            f"Tipo de origem: {summary['source_kind']}\n"
            f"Score final de compatibilidade: {summary['compatibility_score']}%\n"
            f"Risco operacional: {summary['risk_level']}\n"
            f"Tempo estimado de execução: {summary['estimated_minutes']} minutos\n\n"
            f"Status do deploy direto: {deploy_text}\n\n"
            "PASSOS RECOMENDADOS\n"
            "1. Gere um backup do ambiente GALINT atual.\n"
            "2. Revise o manifest.json para confirmar tabelas, colunas e bloqueios.\n"
            "3. Se houver base_convertida/*.sql, essa é a base que pode ser restaurada diretamente.\n"
            "4. Se não houver base_convertida/*.sql, ajuste o dump externo antes de tentar implantar.\n"
            "5. Após restaurar, reinicie o servidor Flask se houver rotas Python recém-alteradas.\n\n"
            "BLOQUEIOS E OBSERVACOES\n"
            f"{blockers}\n"
        )