"""GALINT Flask application factory."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask import jsonify

from .config import load_config
from .extensions import register_extensions
from .views import register_blueprints
from .cli import register_cli
import logging
import threading
import re
import os


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
    register_extensions(app)
    register_blueprints(app)
    register_cli(app)

    # Helpers globais para templates
    app.jinja_env.globals["endpoint_exists"] = lambda endpoint: endpoint in app.view_functions
    
    # Filtro customizado para formatar datas no timezone local
    from .utils.time_service import TimeService
    
    @app.template_filter('format_local')
    def format_local_filter(dt, fmt='%d/%m/%Y %H:%M'):
        """Converte datetime UTC para horário local e formata."""
        return TimeService.format_local(dt, fmt)
    
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
    _initialize_scheduler(app)
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
        if os.environ.get("GALINT_TELEGRAM_POLLING", "true").strip().lower() in ("1", "true", "yes"):
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
        if _should_run_startup_side_effects() and os.environ.get(
            "GALINT_TELEGRAM_STARTUP_GREETING", "true"
        ).strip().lower() in ("1", "true", "yes"):
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
    from datetime import datetime, timedelta
    from flask import session, request
    from flask_login import current_user
    
    @app.before_request
    def check_session_inactivity():
        """Verifica se a sessão expirou por inatividade (25 minutos)."""
        # Ignora verificação para rotas públicas e API mobile (que tem seu próprio controle)
        if request.endpoint in ('auth.login_form', 'auth.login_submit', 'static', 'api_health'):
            return
        if request.path.startswith('/api/mobile/'):
            return
            
        if current_user.is_authenticated:
            last_activity = session.get('last_activity')
            now = datetime.utcnow()
            
            if last_activity:
                last_activity_time = datetime.fromisoformat(last_activity)
                inactive_seconds = (now - last_activity_time).total_seconds()
                
                # Timeout: 25 minutos = 1500 segundos
                if inactive_seconds > 1500:
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


def _initialize_scheduler(app: Flask) -> None:
    """Inicializa o agendador de tarefas do Telegram."""
    try:
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

