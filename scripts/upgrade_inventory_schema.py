"""Utility to ensure inventory-related schema upgrades are applied."""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from galint_flask.config import _resolve_database_uri


def _ensure_itens_columns(connection, inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns("itens")}
    if "categoria" not in columns:
        connection.execute(
            text("ALTER TABLE itens ADD COLUMN categoria VARCHAR NOT NULL DEFAULT 'Material Eletrico'")
        )


def _ensure_saidas_columns(connection, inspector) -> None:
    columns = {column["name"]: column for column in inspector.get_columns("saidas")}

    column_definitions = {
        "tipo_produto": "ALTER TABLE saidas ADD COLUMN tipo_produto VARCHAR",
        "densidade_aplicada": "ALTER TABLE saidas ADD COLUMN densidade_aplicada DOUBLE PRECISION",
        "fracao_numerador": "ALTER TABLE saidas ADD COLUMN fracao_numerador INTEGER",
        "fracao_denominador": "ALTER TABLE saidas ADD COLUMN fracao_denominador INTEGER",
        "quantidade_total_embalagem": "ALTER TABLE saidas ADD COLUMN quantidade_total_embalagem DOUBLE PRECISION",
        "quantidade_retirada_em_litros": "ALTER TABLE saidas ADD COLUMN quantidade_retirada_em_litros DOUBLE PRECISION",
        "quantidade_retirada_em_quilos": "ALTER TABLE saidas ADD COLUMN quantidade_retirada_em_quilos DOUBLE PRECISION",
        "quantidade_restante": "ALTER TABLE saidas ADD COLUMN quantidade_restante DOUBLE PRECISION",
        "usou_fracao": "ALTER TABLE saidas ADD COLUMN usou_fracao BOOLEAN NOT NULL DEFAULT FALSE",
    }

    for name, ddl in column_definitions.items():
        if name not in columns:
            connection.execute(text(ddl))

    quantidade_type = columns.get("quantidade", {}).get("type")
    if quantidade_type is not None and "double" not in str(quantidade_type).lower():
        connection.execute(
            text("ALTER TABLE saidas ALTER COLUMN quantidade TYPE DOUBLE PRECISION USING quantidade::double precision")
        )


def _ensure_entradas_columns(connection, inspector) -> None:
    columns = {column["name"]: column for column in inspector.get_columns("entradas")}
    quantidade_type = columns.get("quantidade", {}).get("type")
    if quantidade_type is not None and "double" not in str(quantidade_type).lower():
        connection.execute(
            text("ALTER TABLE entradas ALTER COLUMN quantidade TYPE DOUBLE PRECISION USING quantidade::double precision")
        )


def _ensure_inventario_eventos_columns(connection, inspector) -> None:
    columns = {column["name"]: column for column in inspector.get_columns("inventario_eventos")}
    quantidade_type = columns.get("quantidade", {}).get("type")
    if quantidade_type is not None and "double" not in str(quantidade_type).lower():
        connection.execute(
            text(
                "ALTER TABLE inventario_eventos ALTER COLUMN quantidade TYPE DOUBLE PRECISION USING quantidade::double precision"
            )
        )


def ensure_columns() -> None:
    engine = create_engine(_resolve_database_uri())
    inspector = inspect(engine)
    with engine.begin() as connection:
        _ensure_itens_columns(connection, inspector)
        inspector = inspect(engine)
        _ensure_saidas_columns(connection, inspector)
        inspector = inspect(engine)
        _ensure_entradas_columns(connection, inspector)
        inspector = inspect(engine)
        _ensure_inventario_eventos_columns(connection, inspector)


def main() -> None:
    ensure_columns()


if __name__ == "__main__":
    main()
