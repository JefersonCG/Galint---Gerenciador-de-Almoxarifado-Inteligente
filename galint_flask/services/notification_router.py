from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time
from typing import Any

from ..extensions import db
from ..models import (
    GalintNotifyRecipient,
    InventarioEvento,
    Item,
    NotificationRouterConfig,
    Saida,
    TelegramConfig,
    TelegramUser,
)
from .galint_notify_service import GalintNotifyService
from .telegram_service import TelegramService


logger = logging.getLogger(__name__)


class NotificationRouterService:
    @staticmethod
    def get_config() -> NotificationRouterConfig:
        config = NotificationRouterConfig.query.first()
        if config is None:
            config = NotificationRouterConfig()
            db.session.add(config)
            db.session.commit()
        return config

    @staticmethod
    def telegram_circuit_open(config: NotificationRouterConfig | None = None) -> bool:
        config = config or NotificationRouterService.get_config()
        if config.telegram_unhealthy_until is None:
            return False
        return config.telegram_unhealthy_until > datetime.utcnow()

    @staticmethod
    def telegram_available(config: NotificationRouterConfig | None = None) -> bool:
        config = config or NotificationRouterService.get_config()
        telegram_config = TelegramConfig.query.first()
        telegram_bot_enabled = bool(telegram_config.enabled) if telegram_config else False
        return bool(config.telegram_enabled and telegram_bot_enabled and not NotificationRouterService.telegram_circuit_open(config))

    @staticmethod
    def notify_available(config: NotificationRouterConfig | None = None) -> bool:
        config = config or NotificationRouterService.get_config()
        return bool(config.notify_enabled)

    @staticmethod
    def record_telegram_success(config: NotificationRouterConfig | None = None) -> None:
        config = config or NotificationRouterService.get_config()
        config.telegram_fail_count = 0
        config.telegram_last_error = None
        config.telegram_last_success_at = datetime.utcnow()
        config.telegram_unhealthy_until = None
        db.session.commit()

    @staticmethod
    def record_telegram_failure(error: str, elapsed_seconds: float, config: NotificationRouterConfig | None = None) -> None:
        config = config or NotificationRouterService.get_config()
        config.telegram_fail_count = int(config.telegram_fail_count or 0) + 1
        config.telegram_last_error = error[:1000]
        config.telegram_last_failure_at = datetime.utcnow()

        threshold = max(1, int(config.circuit_fail_threshold or 2))
        timeout_limit = max(1, int(config.circuit_timeout_seconds or 10))
        should_open = config.telegram_fail_count >= threshold or elapsed_seconds >= timeout_limit
        if should_open:
            cooldown = max(60, int(config.circuit_cooldown_seconds or 120))
            config.telegram_unhealthy_until = datetime.utcnow() + timedelta(seconds=cooldown)
        db.session.commit()

    @staticmethod
    def route_event(*, event_name: str, telegram_callable, notify_payload: dict[str, Any]) -> dict[str, Any]:
        config = NotificationRouterService.get_config()
        default_channel = (config.default_channel or "telegram").strip().lower()
        attempted: list[str] = []

        if default_channel == "notify":
            channel_order = ["notify", "telegram"]
        else:
            channel_order = ["telegram", "notify"]

        for channel in channel_order:
            if channel == "telegram":
                if not NotificationRouterService.telegram_available(config):
                    continue
                attempted.append("telegram")
                started = time.perf_counter()
                try:
                    result = telegram_callable()
                    elapsed = time.perf_counter() - started
                    if result is False or (isinstance(result, dict) and result.get("success") is False):
                        error = str((result or {}).get("error") or f"Falha no evento {event_name} via Telegram")
                        NotificationRouterService.record_telegram_failure(error, elapsed, config)
                        continue
                    NotificationRouterService.record_telegram_success(config)
                    return {"success": True, "channel": "telegram", "result": result, "attempted": attempted}
                except Exception as exc:  # noqa: BLE001
                    elapsed = time.perf_counter() - started
                    NotificationRouterService.record_telegram_failure(str(exc), elapsed, config)
                    logger.warning("Router Telegram falhou em %s: %s", event_name, exc)
                    continue

            if channel == "notify":
                if not NotificationRouterService.notify_available(config):
                    continue
                attempted.append("notify")
                result = GalintNotifyService.deliver_message(**notify_payload)
                if result.get("success"):
                    return {"success": True, "channel": "notify", "result": result, "attempted": attempted}

        return {
            "success": False,
            "channel": None,
            "attempted": attempted,
            "error": f"Nenhum canal disponível para {event_name}.",
        }

    @staticmethod
    def route_withdrawal(
        saida_id: int,
        *,
        force_single: bool = False,
        balance_before: float | None = None,
        balance_after: float | None = None,
        balance_unit: str | None = None,
    ) -> dict[str, Any]:
        saida = Saida.query.get(saida_id)
        if saida is None:
            return {"success": False, "error": "Saída não encontrada."}
        item_desc = saida.item.descricao if saida.item else saida.codigo_item or "Item"
        user_name = saida.usuario.nome if saida.usuario else saida.matricula or "Usuário"
        payload = {
            "recipient_ids": NotificationRouterService._resolve_saida_recipients(saida),
            "title": "Nova retirada registrada",
            "body": f"{user_name} retirou {saida.quantidade:g} de {item_desc}.",
            "category": "withdrawal",
            "message_type": "withdrawal",
            "payload": {
                "kind": "withdrawal",
                "saidaId": saida.id_saida,
                "codigo": saida.codigo_item,
                "matricula": saida.matricula,
                "tipoCustodia": saida.tipo_custodia,
                "balanceBefore": balance_before,
                "balanceAfter": balance_after,
                "balanceUnit": balance_unit,
            },
        }
        return NotificationRouterService.route_event(
            event_name="withdrawal",
            telegram_callable=lambda: TelegramService.notify_withdrawal(
                saida_id,
                force_single=force_single,
                balance_before=balance_before,
                balance_after=balance_after,
                balance_unit=balance_unit,
            ),
            notify_payload=payload,
        )

    @staticmethod
    def route_multiple_withdrawal(saida_ids: list[int]) -> dict[str, Any]:
        saidas = Saida.query.filter(Saida.id_saida.in_(saida_ids)).all() if saida_ids else []
        recipients: set[str] = set()
        for saida in saidas:
            recipients.update(NotificationRouterService._resolve_saida_recipients(saida))
        payload = {
            "recipient_ids": sorted(recipients),
            "title": "Retiradas agrupadas concluídas",
            "body": f"{len(saidas)} retiradas foram registradas e agrupadas para notificação.",
            "category": "withdrawal",
            "message_type": "withdrawal_batch",
            "payload": {"kind": "withdrawal_batch", "saidaIds": saida_ids},
        }
        return NotificationRouterService.route_event(
            event_name="withdrawal_batch",
            telegram_callable=lambda: TelegramService.notify_multiple_withdrawal(saida_ids),
            notify_payload=payload,
        )

    @staticmethod
    def route_inventory_event(event_id: int) -> dict[str, Any]:
        event = InventarioEvento.query.get(event_id)
        if event is None:
            return {"success": False, "error": "Evento não encontrado."}
        item = Item.query.get(event.codigo_item) if event.codigo_item else None
        payload = {
            "recipient_ids": NotificationRouterService._resolve_inventory_recipients(event),
            "title": "Movimento de inventário registrado",
            "body": f"Evento {event.tipo} para {item.descricao if item else (event.codigo_item or 'item')} com quantidade {event.quantidade:g}.",
            "category": "inventory",
            "message_type": "inventory_event",
            "payload": {
                "kind": "inventory_event",
                "eventId": event.id_evento,
                "codigo": event.codigo_item,
                "matricula": event.matricula,
                "tipo": event.tipo,
            },
        }
        return NotificationRouterService.route_event(
            event_name="inventory_event",
            telegram_callable=lambda: TelegramService.notify_inventory_event(event_id),
            notify_payload=payload,
        )

    @staticmethod
    def route_item_created(codigo: str, *, entrada_inicial: dict[str, Any] | None = None) -> dict[str, Any]:
        item = Item.query.get(codigo)
        recipients = NotificationRouterService._resolve_item_recipients(item)
        payload = {
            "recipient_ids": recipients,
            "title": "Novo item cadastrado",
            "body": f"Item {codigo} - {item.descricao if item else 'Sem descrição'} foi criado no GALINT.",
            "category": "item",
            "message_type": "item_created",
            "payload": {
                "kind": "item_created",
                "codigo": codigo,
                "entradaInicial": entrada_inicial or {},
            },
        }
        return NotificationRouterService.route_event(
            event_name="item_created",
            telegram_callable=lambda: TelegramService.notify_item_created(codigo, entrada_inicial=entrada_inicial),
            notify_payload=payload,
        )

    @staticmethod
    def route_permanent_custody(saida_id: int) -> dict[str, Any]:
        saida = Saida.query.get(saida_id)
        payload = {
            "recipient_ids": NotificationRouterService._resolve_saida_recipients(saida) if saida else [],
            "title": "Custódia permanente registrada",
            "body": f"Saída {saida_id} foi registrada como custódia permanente.",
            "category": "custody",
            "message_type": "permanent_custody",
            "payload": {"kind": "permanent_custody", "saidaId": saida_id},
        }
        return NotificationRouterService.route_event(
            event_name="permanent_custody",
            telegram_callable=lambda: TelegramService.notify_permanent_custody(saida_id),
            notify_payload=payload,
        )

    @staticmethod
    def _resolve_saida_recipients(saida: Saida | None) -> list[str]:
        recipients: set[str] = set()
        if saida and saida.matricula:
            recipients.add(saida.matricula)
        recipients.update(NotificationRouterService._telegram_user_matriculas())
        return sorted(recipients)

    @staticmethod
    def _resolve_inventory_recipients(event: InventarioEvento) -> list[str]:
        recipients: set[str] = set()
        if event.matricula:
            recipients.add(event.matricula)
        recipients.update(NotificationRouterService._telegram_user_matriculas())
        return sorted(recipients)

    @staticmethod
    def _resolve_item_recipients(item: Item | None) -> list[str]:
        recipients = set(NotificationRouterService._telegram_user_matriculas())
        if item and item.entradas:
            for entrada in item.entradas[-3:]:
                if entrada.matricula:
                    recipients.add(entrada.matricula)
        return sorted(recipients)

    @staticmethod
    def _telegram_user_matriculas() -> list[str]:
        return [row.matricula for row in TelegramUser.query.filter_by(enabled=True).all() if row.matricula]

    @staticmethod
    def status_payload() -> dict[str, Any]:
        config = NotificationRouterService.get_config()
        metrics = GalintNotifyService.metrics()
        recent_unreads = (
            GalintNotifyRecipient.query.filter_by(status="unread")
            .order_by(GalintNotifyRecipient.created_at.desc())
            .limit(5)
            .all()
        )
        return {
            "default_channel": config.default_channel,
            "telegram_enabled": config.telegram_enabled,
            "notify_enabled": config.notify_enabled,
            "push_provider": config.push_provider,
            "push_enabled": config.push_enabled,
            "telegram_circuit_open": NotificationRouterService.telegram_circuit_open(config),
            "telegram_unhealthy_until": config.telegram_unhealthy_until.isoformat() if config.telegram_unhealthy_until else None,
            "telegram_fail_count": config.telegram_fail_count,
            "telegram_last_error": config.telegram_last_error,
            "telegram_last_success_at": config.telegram_last_success_at.isoformat() if config.telegram_last_success_at else None,
            "telegram_last_failure_at": config.telegram_last_failure_at.isoformat() if config.telegram_last_failure_at else None,
            "notify_metrics": metrics,
            "recent_unreads": [
                {
                    "matricula": row.matricula,
                    "title": row.message.title,
                    "created_at": row.message.created_at.isoformat() if row.message.created_at else None,
                }
                for row in recent_unreads
            ],
        }