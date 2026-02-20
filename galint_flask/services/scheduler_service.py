"""Serviço de agendamento de tarefas usando APScheduler."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
import tempfile
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class SchedulerService:
    """Gerenciador de tarefas agendadas."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        logger.info("APScheduler initialized")

    def schedule_telegram_alerts(self, app):
        """Agenda alertas do Telegram baseado na configuração."""
        from .telegram_service import TelegramService

        # Remover jobs anteriores se existirem
        for job in self.scheduler.get_jobs():
            if job.id in ["telegram_alert_weekday", "telegram_alert_saturday", "telegram_alert_4h"]:
                job.remove()

        with app.app_context():
            from ..models import TelegramConfig

            config = TelegramConfig.query.first()
            if not config or not config.alert_enabled:
                logger.info("Alertas Telegram desabilitados")
                return

            # ALERTA DE DEVOLUÇÃO: a cada 4h (custódia diária)
            try:
                self.scheduler.add_job(
                    func=lambda: self._run_alert_job(app),
                    trigger=IntervalTrigger(hours=4),
                    id="telegram_alert_4h",
                    name="Alerta Telegram Devolução (4h)",
                    replace_existing=True,
                    # Sem next_run_time, o APScheduler pode esperar até 4h após reinício.
                    # Rodar rapidamente após iniciar para não "perder" o ciclo.
                    next_run_time=datetime.now() + timedelta(seconds=30),
                )
                logger.info("Alerta de devolução (custódia diária) agendado a cada 4h")
            except Exception as e:
                logger.error(f"Erro ao agendar alerta 4h: {e}")



            # Agendar notificações de estoque baixo (configuráveis)
            try:
                if getattr(config, "low_stock_enabled", False):
                    # Agendar envios diários: executar `low_stock_daily_count` vezes por dia
                    daily = int(getattr(config, "low_stock_daily_count", 3) or 3)
                    # escolher horários espaçados entre 09:00 e 17:00
                    start_hour = 9
                    end_hour = 17
                    span = max(1, (end_hour - start_hour) // max(1, daily))
                    for i in range(daily):
                        hour = start_hour + i * span
                        job_id = f"low_stock_daily_{i}"
                        self.scheduler.add_job(
                            func=lambda: self._run_low_stock_job(app),
                            trigger=CronTrigger(hour=hour, minute=0),
                            id=job_id,
                            name=f"Low stock daily #{i+1}",
                            replace_existing=True,
                        )

                    # Agendar envios semanais: usar low_stock_weekly_count times per week (Mon/Wed/Fri as default)
                    weekly = int(getattr(config, "low_stock_weekly_count", 3) or 3)
                    weekdays = ["mon", "wed", "fri", "tue", "thu", "sat", "sun"]
                    selected_days = weekdays[:weekly]
                    # schedule weekly on selected days at 08:00
                    self.scheduler.add_job(
                        func=lambda: self._run_low_stock_job(app),
                        trigger=CronTrigger(day_of_week=','.join(selected_days), hour=8, minute=0),
                        id="low_stock_weekly",
                        name="Low stock weekly",
                        replace_existing=True,
                    )
                    logger.info(f"Notificações low-stock agendadas: daily={daily}, weekly={weekly}")
            except Exception as e:
                logger.error(f"Erro ao agendar low-stock notifications: {e}")

    def schedule_telegram_watchdog(self, app, minutes: int = 2):
        """Agenda um watchdog periódico para manter o Telegram operacional.

        Responsabilidades:
        - Atualizar status de saúde do Telegram (getMe)
        - Reiniciar polling background se configurado e o thread morrer
        """
        for job in self.scheduler.get_jobs():
            if job.id == "telegram_watchdog":
                job.remove()

        self.scheduler.add_job(
            func=lambda: self._run_telegram_watchdog(app),
            trigger=IntervalTrigger(minutes=int(minutes)),
            id="telegram_watchdog",
            name="Telegram watchdog",
            replace_existing=True,
        )

    def _run_telegram_watchdog(self, app) -> None:
        from .telegram_service import TelegramService

        with app.app_context():
            try:
                TelegramService.watchdog_check(app)
            except Exception as e:
                logger.error(f"Falha no watchdog do Telegram: {e}")

    def schedule_telegram_retry_failed_notifications(self, app, minutes: int = 5):
        """Agenda retry periódico de notificações Telegram que falharam."""
        for job in self.scheduler.get_jobs():
            if job.id == "telegram_retry_failed":
                job.remove()

        self.scheduler.add_job(
            func=lambda: self._run_telegram_retry_failed(app),
            trigger=IntervalTrigger(minutes=int(minutes)),
            id="telegram_retry_failed",
            name="Telegram retry failed notifications",
            replace_existing=True,
        )

    def _run_telegram_retry_failed(self, app) -> None:
        from .telegram_service import TelegramService

        with app.app_context():
            try:
                TelegramService.retry_failed_notifications()
            except Exception as e:
                logger.error(f"Falha no retry de notificações Telegram: {e}")

    def schedule_telegram_outbox_worker(self, app, seconds: int = 30):
        """Agenda worker periódico para processar a fila Outbox do Telegram."""
        for job in self.scheduler.get_jobs():
            if job.id == "telegram_outbox_worker":
                job.remove()

        self.scheduler.add_job(
            func=lambda: self._run_telegram_outbox_worker(app),
            trigger=IntervalTrigger(seconds=int(seconds)),
            id="telegram_outbox_worker",
            name="Telegram outbox worker",
            replace_existing=True,
        )

    def _run_telegram_outbox_worker(self, app) -> None:
        from .telegram_service import TelegramService

        with app.app_context():
            try:
                TelegramService.process_outbox(limit=50, drain=False)
            except Exception as e:
                logger.error(f"Falha no worker do outbox Telegram: {e}")

    def schedule_cleanup_old_history(self, app, days: int = 180):
        """Agenda rotina diária para remover históricos com mais de `days` dias.

        A rotina remove registros antigos das tabelas de histórico (entradas, saídas,
        inventário, mensagens e notificações) para controlar retenção.
        """
        # remover job anterior, se existir
        for job in self.scheduler.get_jobs():
            if job.id == "cleanup_old_history":
                job.remove()

        # agendar para rodar diariamente às 03:00
        try:
            self.scheduler.add_job(
                func=lambda: self._run_cleanup_job(app, days),
                trigger=CronTrigger(hour=3, minute=0),
                id="cleanup_old_history",
                name="Limpeza de históricos antigos",
                replace_existing=True,
            )
            logger.info(f"Job de limpeza agendada (limite dias={days})")
        except Exception as e:
            logger.error(f"Erro ao agendar limpeza de históricos: {e}")

    def schedule_report_cleanup(self, app, days: int = 7):
        """Agenda rotina diária para apagar relatórios antigos (arquivos)."""
        for job in self.scheduler.get_jobs():
            if job.id == "cleanup_old_reports":
                job.remove()

        try:
            self.scheduler.add_job(
                func=lambda: self._run_report_cleanup_job(app, days),
                trigger=CronTrigger(hour=12, minute=0),
                id="cleanup_old_reports",
                name="Limpeza de relatórios antigos",
                replace_existing=True,
            )
            logger.info(f"Job de limpeza de relatórios agendada (limite dias={days})")
        except Exception as e:
            logger.error(f"Erro ao agendar limpeza de relatórios: {e}")

    def _run_report_cleanup_job(self, app, days: int = 7):
        """Remove arquivos de relatórios com mais de `days` dias."""
        with app.app_context():
            try:
                cutoff = datetime.utcnow() - timedelta(days=days)
                reports_dir = Path(app.instance_path) / "reports"
                temp_reports_dir = Path(tempfile.gettempdir()) / "galint_reports"
                deleted = 0
                for target_dir in (reports_dir, temp_reports_dir):
                    if not target_dir.exists():
                        continue
                    for item in target_dir.iterdir():
                        if not item.is_file():
                            continue
                        if item.suffix.lower() not in (".pdf", ".xlsx", ".jpeg", ".jpg"):
                            continue
                        try:
                            mtime = datetime.utcfromtimestamp(item.stat().st_mtime)
                        except Exception:
                            continue
                        if mtime < cutoff:
                            try:
                                item.unlink()
                                deleted += 1
                            except Exception:
                                logger.warning(f"Falha ao remover relatório: {item}")

                logger.info(
                    f"Limpeza de relatórios concluída: removidos={deleted}, dias>{days}"
                )
            except Exception as e:
                logger.error(f"Erro durante limpeza de relatórios: {e}", exc_info=True)

    def _run_cleanup_job(self, app, days: int = 180):
        """Executa limpeza de registros antigos dentro do contexto da aplicação."""
        from ..extensions import db

        with app.app_context():
            try:
                cutoff = datetime.utcnow() - timedelta(days=days)
                # tabelas e colunas de data a serem limpas
                from ..models import (
                    Saida,
                    Entrada,
                    InventarioEvento,
                    ChatMessage,
                    MaterialInventario,
                    DescarteAutorizacao,
                    TelegramNotification,
                    TelegramOutbox,
                )

                # Saídas
                deleted_saida = (
                    db.session.query(Saida)
                    .filter(Saida.data_saida < cutoff)
                    .delete(synchronize_session=False)
                )
                # Entradas
                deleted_entrada = (
                    db.session.query(Entrada)
                    .filter(Entrada.data_entrada < cutoff)
                    .delete(synchronize_session=False)
                )
                # Inventário eventos
                deleted_invent = (
                    db.session.query(InventarioEvento)
                    .filter(InventarioEvento.data_evento < cutoff)
                    .delete(synchronize_session=False)
                )
                # Chat messages
                deleted_chat = (
                    db.session.query(ChatMessage)
                    .filter(ChatMessage.data_envio < cutoff)
                    .delete(synchronize_session=False)
                )
                # Material inventario
                deleted_material = (
                    db.session.query(MaterialInventario)
                    .filter(MaterialInventario.data_registro < cutoff)
                    .delete(synchronize_session=False)
                )
                # Descarte autorizações
                deleted_descarte = (
                    db.session.query(DescarteAutorizacao)
                    .filter(DescarteAutorizacao.data_autorizacao < cutoff)
                    .delete(synchronize_session=False)
                )
                # Telegram notifications
                deleted_notifs = (
                    db.session.query(TelegramNotification)
                    .filter(TelegramNotification.sent_at < cutoff)
                    .delete(synchronize_session=False)
                )

                # Outbox: apagar somente mensagens já enviadas (ou mortas) antigas.
                deleted_outbox = (
                    db.session.query(TelegramOutbox)
                    .filter(TelegramOutbox.created_at < cutoff)
                    .filter(TelegramOutbox.status.in_(["sent", "dead"]))
                    .delete(synchronize_session=False)
                )

                db.session.commit()
                logger.info(
                    "Limpeza concluída: "
                    f"saida={deleted_saida}, entrada={deleted_entrada}, inventario={deleted_invent}, "
                    f"chat={deleted_chat}, material={deleted_material}, descarte={deleted_descarte}, "
                    f"notificacoes={deleted_notifs}, outbox={deleted_outbox}"
                )
            except Exception as e:
                db.session.rollback()
                logger.error(f"Erro durante limpeza de históricos: {e}", exc_info=True)

    def run_cleanup_now(self, app, days: int = 180):
        """Executa limpeza imediatamente (útil para testes)."""
        self._run_cleanup_job(app, days)

    def _run_alert_job(self, app):
        """Executa job de alerta dentro do contexto da aplicação."""
        from .telegram_service import TelegramService

        with app.app_context():
            try:
                logger.info("Executando alerta agendado do Telegram")
                result = TelegramService.send_scheduled_alerts()
                logger.info(
                    f"Alerta enviado: {result.get('total_sent', 0)} enviados, "
                    f"{result.get('total_failed', 0)} falhas"
                )
            except Exception as e:
                logger.error(f"Erro ao executar alerta agendado: {e}", exc_info=True)

    def _run_low_stock_job(self, app):
        """Executa job de low-stock dentro do contexto da aplicação."""
        from .telegram_service import TelegramService

        with app.app_context():
            try:
                logger.info("Executando low-stock scheduled job")
                result = TelegramService.send_low_stock_notifications()
                logger.info(f"Low-stock enviado: {result.get('sent', 0)} enviados")
            except Exception as e:
                logger.error(f"Erro ao executar low-stock job: {e}", exc_info=True)

    def schedule_end_of_workday_message(self, app):
        """Agenda mensagem motivacional de fim de expediente às 17h todos os dias."""
        try:
            self.scheduler.add_job(
                func=lambda: self._run_end_of_workday_job(app),
                trigger=CronTrigger(hour=17, minute=0),
                id="end_of_workday_message",
                name="Mensagem de Fim de Expediente",
                replace_existing=True,
            )
            logger.info("Mensagem de fim de expediente agendada para 17:00")
        except Exception as e:
            logger.error(f"Erro ao agendar mensagem de fim de expediente: {e}")

    def _run_end_of_workday_job(self, app):
        """Executa job de fim de expediente dentro do contexto da aplicação."""
        from .telegram_service import TelegramService

        with app.app_context():
            try:
                logger.info("Executando mensagem de fim de expediente")
                result = TelegramService.send_end_of_workday_message()
                logger.info(
                    f"Mensagem de fim de expediente enviada: {result.get('sent', 0)} enviados, "
                    f"{result.get('failed', 0)} falhas"
                )
            except Exception as e:
                logger.error(f"Erro ao executar mensagem de fim de expediente: {e}", exc_info=True)

    def run_alert_now(self, app):
        """Executa alerta manualmente (para testes)."""
        self._run_alert_job(app)

    def get_scheduled_jobs(self) -> list[dict]:
        """Retorna lista de jobs agendados."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs

    def shutdown(self):
        """Desliga o scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("APScheduler shut down")
