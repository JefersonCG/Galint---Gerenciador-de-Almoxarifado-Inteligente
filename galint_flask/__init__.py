"""GALINT Flask application factory."""
from __future__ import annotations

from pathlib import Path
import traceback

from dotenv import load_dotenv
from flask import Flask
from flask import jsonify
from flask import render_template, request
from werkzeug.exceptions import HTTPException

from .config import load_config
from .extensions import register_extensions
from .services.document_integrity_service import install_document_integrity_guards
from .views import register_blueprints
from .cli import register_cli
import logging
import threading
import re
import os


def _background_services_disabled() -> bool:
    """Permite desabilitar efeitos colaterais (scheduler/polling/saudação) via env.

    Útil para diagnósticos e testes de formatação sem iniciar threads nem tocar
    em integrações externas.
    """

    return os.environ.get("GALINT_DISABLE_BACKGROUND_SERVICES", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _should_run_startup_side_effects() -> bool:
    """Evita executar efeitos colaterais duas vezes no modo debug com reloader.

    No Flask/Werkzeug reloader, o processo "pai" executa o import/init e depois
    spawna o processo real com WERKZEUG_RUN_MAIN=true.
    """

    flag = os.environ.get("WERKZEUG_RUN_MAIN")
    return flag is None or flag.strip().lower() in ("1", "true", "yes")


def _load_dotenv_hierarchy() -> None:
    """Carrega .env sem sobrescrever variáveis já definidas.

    Prioridade (maior -> menor):
    - diretório avô (workspace/root)
    - diretório pai
    - diretório atual

    Isso permite manter um único .env fora da pasta interna.
    """

    cwd = Path.cwd()
    candidates = [cwd.parent.parent / ".env", cwd.parent / ".env", cwd / ".env"]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=False)

    # fallback padrão do python-dotenv (procura .env automaticamente)
    load_dotenv(override=False)


_load_dotenv_hierarchy()


def create_app(config_name: str | None = None) -> Flask:
    """Application factory used by both production and tests."""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    load_config(app, config_name)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    register_extensions(app)
    install_document_integrity_guards()
    register_blueprints(app)
    register_cli(app)
    _register_error_handlers(app)

    # Nome do sistema (usado em título/branding). Pode ser sobrescrito via env.
    app.config.setdefault(
        "SYSTEM_NAME",
        os.environ.get("GALINT_SYSTEM_NAME", "Gerenciador de Almoxarifado Inteligente").strip()
        or "Gerenciador de Almoxarifado Inteligente",
    )

    @app.context_processor
    def _inject_system_name():
        return {"system_name": app.config.get("SYSTEM_NAME", "Gerenciador de Almoxarifado Inteligente")}

    # Helpers globais para templates
    app.jinja_env.globals["endpoint_exists"] = lambda endpoint: endpoint in app.view_functions
    
    # Filtro customizado para formatar datas no timezone local
    from .utils.time_service import TimeService
    from .utils.formatters import (
        format_currency_br,
        format_datetime_br,
        format_number_br,
        format_percent_br,
    )
    
    @app.template_filter('format_local')
    def format_local_filter(dt, fmt='%d/%m/%Y %H:%M'):
        """Converte datetime UTC para horário local e formata."""
        return TimeService.format_local(dt, fmt)

    @app.template_filter('number_br')
    def number_br_filter(value, decimals=0, strip_trailing_zeros=False, default='0'):
        return format_number_br(value, decimals, strip_trailing_zeros, default)

    @app.template_filter('currency_br')
    def currency_br_filter(value, default='R$ 0,00'):
        return format_currency_br(value, default)

    @app.template_filter('percent_br')
    def percent_br_filter(value, decimals=0, default='0%'):
        return format_percent_br(value, decimals, default)

    @app.template_filter('datetime_br')
    def datetime_br_filter(value, fmt='%d/%m/%Y %H:%M', default='-'):
        return format_datetime_br(value, fmt, default)
    
    # Guardas de execução antes de tocar em autenticação/DB
    _register_restore_guard(app)

    # Middleware de monitoramento de inatividade
    _register_inactivity_middleware(app)

    @app.get("/api/health")
    def api_health():
        return jsonify({"status": "ok"}), 200

    # Rotas legadas: algumas instalações antigas usavam /login e /logout.
    # Mantemos como alias para a UI atual (/auth/login).
    try:
        from flask import redirect, url_for

        @app.get("/login")
        def _legacy_login_get():
            return redirect(url_for("auth.login_form"))

        @app.post("/login")
        def _legacy_login_post():
            return redirect(url_for("auth.login_submit"))

        @app.get("/logout")
        def _legacy_logout_get():
            from .services.auth import end_session

            end_session()
            return redirect(url_for("auth.login_form"))
    except Exception:
        # não bloquear o app caso falhe import por algum motivo
        pass
    
    # Inicializar scheduler do Telegram
    if not _background_services_disabled():
        _initialize_scheduler(app)
    else:
        app.logger.info(
            "Serviços em background desabilitados via GALINT_DISABLE_BACKGROUND_SERVICES=true"
        )
    # Aplicar filtro de sanitização de logs para evitar dump de bytes binários
    class _SanitizeFilter(logging.Filter):
        def filter(self, record):
            try:
                if isinstance(record.msg, str):
                    record.msg = re.sub(r"\\x[0-9a-fA-F]{2}", "<bin>", record.msg)
            except Exception:
                pass
            return True

    sanitize = _SanitizeFilter()
    root = logging.getLogger()
    for h in root.handlers:
        h.addFilter(sanitize)
    app.logger.addFilter(sanitize)
    # Iniciar polling do Telegram automaticamente se indicado pela env
    try:
        if _background_services_disabled():
            pass
        elif os.environ.get("GALINT_TELEGRAM_POLLING", "true").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            # Em debug com reloader, o Werkzeug cria 2 processos. Para evitar dois bots
            # respondendo ao mesmo tempo, só iniciamos o polling no processo "real".
            # Se use_reloader=False, WERKZEUG_RUN_MAIN não é setado, então iniciamos normalmente.
            if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") is not None and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
                app.logger.info("Telegram polling ignorado no processo do reloader (WERKZEUG_RUN_MAIN!=true)")
            else:
                from .services.telegram_service import TelegramService
                # keep_webhook pode ser controlado por var de ambiente também
                keep = os.environ.get("GALINT_TELEGRAM_KEEP_WEBHOOK", "false").strip().lower() in ("1", "true", "yes")
                TelegramService.start_polling_background(app, keep_webhook=keep)
                app.logger.info("Telegram polling iniciado em background (GALINT_TELEGRAM_POLLING=true)")
    except Exception:
        pass

    # Saudação no startup via Telegram (não bloquear init)
    try:
        if (
            (not _background_services_disabled())
            and _should_run_startup_side_effects()
            and os.environ.get(
            "GALINT_TELEGRAM_STARTUP_GREETING", "true"
            ).strip().lower()
            in ("1", "true", "yes")
        ):
            from .services.telegram_service import TelegramService
            from .utils.action_logger import log_action

            def _startup_greeting_task() -> None:
                try:
                    with app.app_context():
                        # registra status inicial (e tenta auto-recuperar polling, se necessário)
                        try:
                            TelegramService.watchdog_check(app)
                        except Exception:
                            pass

                        log_action("Iniciando saudação de startup (thread)")
                        TelegramService.send_startup_broadcast()
                        log_action("Saudação de startup finalizada (thread)")
                except Exception as exc:
                    try:
                        log_action(f"Erro na saudação de startup: {exc}")
                    except Exception:
                        app.logger.exception("Erro ao logar falha na saudação de startup")

            threading.Thread(target=_startup_greeting_task, daemon=True).start()
    except Exception:
        app.logger.exception("Falha ao disparar thread de saudação de startup")

    return app


def _register_inactivity_middleware(app: Flask) -> None:
    """Registra middleware para monitorar inatividade e invalidar sessões expiradas."""
    from datetime import datetime
    from flask import session, request
    from flask_login import current_user
    
    @app.before_request
    def check_session_inactivity():
        """Verifica se a sessão expirou por inatividade conforme a configuração global."""
        # Ignora verificação para rotas públicas e API mobile (que tem seu próprio controle)
        if request.endpoint in ('auth.login_form', 'auth.login_submit', 'static', 'api_health'):
            return
        if request.path.startswith('/api/mobile/'):
            return
            
        if current_user.is_authenticated:
            login_at = session.get('login_at')
            last_activity = session.get('last_activity')
            now = datetime.utcnow()
            timeout_seconds = int(app.permanent_session_lifetime.total_seconds())

            if not login_at:
                login_at = now.isoformat()
                session['login_at'] = login_at

            login_time = datetime.fromisoformat(login_at)
            session_age_seconds = (now - login_time).total_seconds()
            if session_age_seconds > timeout_seconds:
                from flask_login import logout_user
                from flask import redirect, url_for, flash

                user_label = (
                    getattr(current_user, "nome", None)
                    or getattr(current_user, "matricula", None)
                    or getattr(current_user, "id", None)
                    or "usuario"
                )
                app.logger.info(
                    f"Sessão expirada por tempo máximo ({session_age_seconds:.0f}s): {user_label}"
                )
                logout_user()
                session.clear()
                flash('Sua sessão expirou após 1 hora. Por favor, faça login novamente.', 'warning')
                return redirect(url_for('auth.login_form'))
            
            if last_activity:
                last_activity_time = datetime.fromisoformat(last_activity)
                inactive_seconds = (now - last_activity_time).total_seconds()
                
                if inactive_seconds > timeout_seconds:
                    from flask_login import logout_user
                    from flask import redirect, url_for, flash

                    user_label = (
                        getattr(current_user, "nome", None)
                        or getattr(current_user, "matricula", None)
                        or getattr(current_user, "id", None)
                        or "usuario"
                    )
                    app.logger.info(
                        f"Sessão expirada por inatividade ({inactive_seconds:.0f}s): {user_label}"
                    )
                    logout_user()
                    session.clear()
                    flash('Sua sessão expirou por inatividade. Por favor, faça login novamente.', 'warning')
                    return redirect(url_for('auth.login_form'))
            
            # Atualiza timestamp da última atividade
            session['last_activity'] = now.isoformat()
            session.permanent = True


def _register_restore_guard(app: Flask) -> None:
    """Bloqueia novas requisições durante restore para reduzir contenção no banco."""
    from .services.backup_restore_jobs import is_restore_running

    allowed_prefixes = (
        "/static/",
        "/auth/login",
        "/api/health",
        "/configuracoes/restaurar/status/",
    )

    @app.before_request
    def block_requests_during_restore():
        if not is_restore_running():
            return None

        path = request.path or ""
        if path.startswith(allowed_prefixes):
            return None

        if _request_expects_json():
            return jsonify({
                "success": False,
                "error": "RestoreInProgress",
                "message": "Restauração em andamento. Aguarde a conclusão para acessar o GALINT.",
                "status_code": 503,
            }), 503

        return (
            "<html><head><title>GALINT em restauração</title></head>"
            "<body style='font-family:Segoe UI,Arial,sans-serif;background:#08111f;color:#e5eefc;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;'>"
            "<div style='max-width:640px;padding:32px;border-radius:20px;background:#0f1b2f;border:1px solid rgba(125,211,252,.18);box-shadow:0 24px 56px rgba(2,8,23,.45)'>"
            "<h1 style='margin-top:0'>Restauração em andamento</h1>"
            "<p>O GALINT está implantando uma base e bloqueou novos acessos temporariamente para evitar corrupção e timeouts de lock.</p>"
            "<p>Atualize a página em instantes após a conclusão do processo.</p>"
            "</div></body></html>",
            503,
            {"Retry-After": "15"},
        )


def _request_expects_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    if request.is_json:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        best = request.accept_mimetypes.best_match(["application/json", "text/html"])
        return best == "application/json"
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def _build_error_context(exc: Exception, status_code: int) -> dict[str, object]:
    trace_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    return {
        "status_code": status_code,
        "error_title": "Erro de programação" if status_code >= 500 else "Falha na requisição",
        "error_message": str(exc) or "Ocorreu uma falha inesperada durante o processamento.",
        "exception_type": type(exc).__name__,
        "request_path": request.path,
        "request_method": request.method,
        "traceback_text": "".join(trace_lines).strip(),
        "show_traceback": status_code >= 500,
    }


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException):
        status_code = exc.code or 500
        if _request_expects_json():
            return jsonify({
                "success": False,
                "error": exc.name,
                "message": exc.description,
                "status_code": status_code,
            }), status_code
        return render_template("errors/exception.html", **_build_error_context(exc, status_code)), status_code

    @app.errorhandler(Exception)
    def _handle_unexpected_exception(exc: Exception):
        app.logger.exception("Unhandled application exception")
        if _request_expects_json():
            return jsonify({
                "success": False,
                "error": type(exc).__name__,
                "message": str(exc) or "Erro interno do servidor.",
                "status_code": 500,
            }), 500
        return render_template("errors/exception.html", **_build_error_context(exc, 500)), 500


def _initialize_scheduler(app: Flask) -> None:
    """Inicializa o agendador de tarefas do Telegram."""
    try:
        if _background_services_disabled():
            return

        # Evitar duplicidade no reloader do Flask (debug)
        # Se use_reloader=False, WERKZEUG_RUN_MAIN não é setado, então iniciamos normalmente.
        try:
            if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") is not None and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
                app.logger.info(
                    "Scheduler ignorado no processo do reloader (WERKZEUG_RUN_MAIN!=true)"
                )
                return
        except Exception:
            pass

        from .services.scheduler_service import SchedulerService
        
        scheduler = SchedulerService()
        scheduler.schedule_telegram_alerts(app)
        # watchdog para manter Telegram operacional (status + reinício de polling)
        try:
            scheduler.schedule_telegram_watchdog(app)
        except Exception:
            pass
        # Worker de contingência (Outbox) para garantir entrega eventual.
        try:
            scheduler.schedule_telegram_outbox_worker(app)
        except Exception:
            pass

        # Compatibilidade: retry antigo (tabela telegram_notifications) só quando Outbox estiver desabilitado.
        try:
            outbox_enabled = os.environ.get("GALINT_TELEGRAM_OUTBOX_ENABLED", "true").strip().lower() in ("1", "true", "yes")
            if not outbox_enabled:
                scheduler.schedule_telegram_retry_failed_notifications(app)
        except Exception:
            pass
        # Agendar limpeza diária de históricos (6 meses)
        try:
            scheduler.schedule_cleanup_old_history(app, days=180)
        except Exception:
            pass

        # Agendar limpeza de relatórios antigos (7 dias) às 12:00
        try:
            scheduler.schedule_report_cleanup(app, days=7)
        except Exception:
            pass
        
        # Agendar mensagem de fim de expediente às 17h
        try:
            scheduler.schedule_end_of_workday_message(app)
        except Exception:
            pass
        
        # Salvar no app context para shutdown posterior
        app.extensions = getattr(app, "extensions", {})
        app.extensions["scheduler"] = scheduler
        
        # Registrar shutdown handler
        import atexit
        atexit.register(lambda: scheduler.shutdown())
    except Exception as e:
        import logging
        logging.warning(f"Falha ao inicializar scheduler: {e}")

