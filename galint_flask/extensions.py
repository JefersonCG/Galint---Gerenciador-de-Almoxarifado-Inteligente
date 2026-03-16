"""Extensions registry."""
from __future__ import annotations

import logging

from flask import jsonify, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_cors import CORS


# extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
cors = CORS()
# login_view must point to the actual login endpoint name
login_manager.login_view = "auth.login_form"
login_manager.login_message = None


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

    @login_manager.user_loader
    def _load_user(matricula: str):
        from .models import Usuario

        return Usuario.query.get(matricula)
