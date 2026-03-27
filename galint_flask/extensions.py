"""Extensions registry."""
from __future__ import annotations

import logging

from flask import jsonify, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_cors import CORS
from sqlalchemy import inspect, text


# extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
cors = CORS()
# login_view must point to the actual login endpoint name
login_manager.login_view = "auth.login_form"
login_manager.login_message = None


def _ensure_document_item_processing_columns() -> None:
    inspector = inspect(db.engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("entrada_documento_itens")}
    except Exception:
        return

    required_columns = {
        "status_processamento",
        "processado_em",
        "erro_processamento",
        "stock_movement_id",
        "operation_log_id",
    }
    if required_columns.issubset(columns):
        return

    logging.getLogger(__name__).warning(
        "Schema legado detectado em entrada_documento_itens; aplicando compatibilidade automatica"
    )

    with db.engine.begin() as connection:
        connection.execute(
            text(
                """
                ALTER TABLE entrada_documento_itens
                ADD COLUMN IF NOT EXISTS status_processamento varchar(30) NOT NULL DEFAULT 'pendente',
                ADD COLUMN IF NOT EXISTS processado_em timestamp NULL,
                ADD COLUMN IF NOT EXISTS erro_processamento text NULL,
                ADD COLUMN IF NOT EXISTS stock_movement_id integer NULL REFERENCES stock_movements(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS operation_log_id integer NULL REFERENCES operation_logs(id) ON DELETE SET NULL
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_entrada_documento_itens_status_processamento ON entrada_documento_itens(status_processamento)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_entrada_documento_itens_stock_movement_id ON entrada_documento_itens(stock_movement_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_entrada_documento_itens_operation_log_id ON entrada_documento_itens(operation_log_id)"
            )
        )
        connection.execute(
            text(
                """
                UPDATE entrada_documento_itens
                   SET status_processamento = 'processado',
                       processado_em = COALESCE(processado_em, criado_em, now()),
                       erro_processamento = NULL
                 WHERE entrada_id IS NOT NULL
                """
            )
        )


def _ensure_stock_document_columns() -> None:
    inspector = inspect(db.engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("entrada_documentos")}
    except Exception:
        return

    if "movimenta_estoque" in columns:
        return

    logging.getLogger(__name__).warning(
        "Schema legado detectado em entrada_documentos; aplicando compatibilidade automatica"
    )

    with db.engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE entrada_documentos ADD COLUMN IF NOT EXISTS movimenta_estoque boolean NOT NULL DEFAULT true"
            )
        )


def register_extensions(app) -> None:
    """Attach extensions to the app instance."""
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    @login_manager.unauthorized_handler
    def _unauthorized():
        # If a fetch/XHR expects JSON, avoid redirecting to an HTML login page.
        accept = request.headers.get("Accept", "")
        if "application/json" in accept:
            return jsonify({"success": False, "message": "Nao autenticado"}), 401
        return redirect(url_for(login_manager.login_view, next=request.url))
    # Habilitar CORS para permitir requisições do app mobile
    cors.init_app(app, resources={
        r"/api/mobile/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })

    with app.app_context():
        logging.getLogger(__name__).info("Garantindo estrutura do banco de dados")
        db.create_all()
        _ensure_stock_document_columns()
        _ensure_document_item_processing_columns()

    @login_manager.user_loader
    def _load_user(matricula: str):
        from .models import Usuario

        return Usuario.query.get(matricula)
