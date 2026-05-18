"""Runtime schema compatibility safeguards for additive migrations."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class SchemaCompatRule:
    table_name: str
    required_columns: tuple[str, ...]
    ddl_statements: tuple[str, ...]
    post_statements: tuple[str, ...] = ()

    def is_satisfied_by(self, existing_columns: set[str]) -> bool:
        return set(self.required_columns).issubset(existing_columns)


RUNTIME_SCHEMA_COMPAT_RULES: tuple[SchemaCompatRule, ...] = (
    SchemaCompatRule(
        table_name="entrada_documentos",
        required_columns=("movimenta_estoque",),
        ddl_statements=(
            "ALTER TABLE entrada_documentos ADD COLUMN IF NOT EXISTS movimenta_estoque boolean NOT NULL DEFAULT true",
        ),
    ),
    SchemaCompatRule(
        table_name="entrada_documento_itens",
        required_columns=(
            "status_processamento",
            "processado_em",
            "erro_processamento",
            "stock_movement_id",
            "operation_log_id",
        ),
        ddl_statements=(
            """
            ALTER TABLE entrada_documento_itens
            ADD COLUMN IF NOT EXISTS status_processamento varchar(30) NOT NULL DEFAULT 'pendente',
            ADD COLUMN IF NOT EXISTS processado_em timestamp NULL,
            ADD COLUMN IF NOT EXISTS erro_processamento text NULL,
            ADD COLUMN IF NOT EXISTS stock_movement_id integer NULL REFERENCES stock_movements(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS operation_log_id integer NULL REFERENCES operation_logs(id) ON DELETE SET NULL
            """,
            "CREATE INDEX IF NOT EXISTS ix_entrada_documento_itens_status_processamento ON entrada_documento_itens(status_processamento)",
            "CREATE INDEX IF NOT EXISTS ix_entrada_documento_itens_stock_movement_id ON entrada_documento_itens(stock_movement_id)",
            "CREATE INDEX IF NOT EXISTS ix_entrada_documento_itens_operation_log_id ON entrada_documento_itens(operation_log_id)",
        ),
        post_statements=(
            """
            UPDATE entrada_documento_itens
               SET status_processamento = 'processado',
                   processado_em = COALESCE(processado_em, criado_em, now()),
                   erro_processamento = NULL
             WHERE entrada_id IS NOT NULL
            """,
        ),
    ),
    SchemaCompatRule(
        table_name="saidas",
        required_columns=(
            "tipo_custodia",
            "atividade_operacional",
            "ordem_servico",
            "centro_custo",
        ),
        ddl_statements=(
            "ALTER TABLE saidas ADD COLUMN IF NOT EXISTS tipo_custodia varchar(20) NOT NULL DEFAULT 'temporaria'",
            "ALTER TABLE saidas ADD COLUMN IF NOT EXISTS atividade_operacional varchar(64)",
            "ALTER TABLE saidas ADD COLUMN IF NOT EXISTS ordem_servico varchar(120)",
            "ALTER TABLE saidas ADD COLUMN IF NOT EXISTS centro_custo varchar(120)",
        ),
        post_statements=(
            "UPDATE saidas SET tipo_custodia = 'temporaria' WHERE tipo_custodia IS NULL OR btrim(tipo_custodia) = ''",
            "ALTER TABLE saidas ALTER COLUMN tipo_custodia SET DEFAULT 'temporaria'",
            "ALTER TABLE saidas ALTER COLUMN tipo_custodia SET NOT NULL",
        ),
    ),
    SchemaCompatRule(
        table_name="telegram_config",
        required_columns=(
            "low_stock_enabled",
            "low_stock_weekly_count",
            "low_stock_daily_count",
        ),
        ddl_statements=(
            "ALTER TABLE telegram_config ADD COLUMN IF NOT EXISTS low_stock_enabled boolean NOT NULL DEFAULT false",
            "ALTER TABLE telegram_config ADD COLUMN IF NOT EXISTS low_stock_weekly_count integer NOT NULL DEFAULT 3",
            "ALTER TABLE telegram_config ADD COLUMN IF NOT EXISTS low_stock_daily_count integer NOT NULL DEFAULT 3",
        ),
        post_statements=(
            "UPDATE telegram_config SET low_stock_enabled = COALESCE(low_stock_enabled, false), low_stock_weekly_count = COALESCE(low_stock_weekly_count, 3), low_stock_daily_count = COALESCE(low_stock_daily_count, 3)",
        ),
    ),
    SchemaCompatRule(
        table_name="condominium_owners",
        required_columns=(
            "registry_data_json",
            "attachment_checklist_json",
        ),
        ddl_statements=(
            "ALTER TABLE condominium_owners ADD COLUMN IF NOT EXISTS registry_data_json JSONB",
            "ALTER TABLE condominium_owners ADD COLUMN IF NOT EXISTS attachment_checklist_json JSONB",
        ),
    ),
)


def _get_columns(engine: Engine, table_name: str) -> set[str] | None:
    try:
        inspector = inspect(engine)
        return {column["name"] for column in inspector.get_columns(table_name)}
    except Exception:
        return None


def ensure_runtime_schema_compatibility(engine: Engine, logger: logging.Logger | None = None) -> None:
    active_logger = logger or logging.getLogger(__name__)

    for rule in RUNTIME_SCHEMA_COMPAT_RULES:
        existing_columns = _get_columns(engine, rule.table_name)
        if existing_columns is None or rule.is_satisfied_by(existing_columns):
            continue

        active_logger.warning(
            "Schema legado detectado em %s; aplicando compatibilidade automatica",
            rule.table_name,
        )

        with engine.begin() as connection:
            for statement in rule.ddl_statements:
                connection.execute(text(statement))
            for statement in rule.post_statements:
                connection.execute(text(statement))