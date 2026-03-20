from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any

import requests
from flask import current_app

from ..extensions import db
from ..models import DevicePushToken, GalintNotifyMessage, GalintNotifyRecipient, Usuario


logger = logging.getLogger(__name__)


class GalintNotifyService:
    EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

    @staticmethod
    def register_push_token(*, matricula: str, device_uuid: str, provider: str, token: str) -> DevicePushToken:
        entry = DevicePushToken.query.filter_by(device_uuid=device_uuid, provider=provider).first()
        if entry is None:
            entry = DevicePushToken(
                matricula=matricula,
                device_uuid=device_uuid,
                provider=provider,
                token=token,
                ativo=True,
            )
            db.session.add(entry)
        else:
            entry.matricula = matricula
            entry.token = token
            entry.ativo = True
            entry.last_error = None
        db.session.commit()
        return entry

    @staticmethod
    def deliver_message(
        *,
        recipient_ids: list[str],
        title: str,
        body: str,
        category: str,
        message_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        unique_ids = sorted({(item or "").strip() for item in recipient_ids if (item or "").strip()})
        if not unique_ids:
            return {"success": False, "error": "Nenhum destinatário válido informado.", "message_id": None}

        message = GalintNotifyMessage(
            category=category,
            message_type=message_type,
            title=title,
            body=body,
            payload=payload or {},
        )
        db.session.add(message)
        db.session.flush()

        recipients: list[GalintNotifyRecipient] = []
        for matricula in unique_ids:
            recipients.append(
                GalintNotifyRecipient(
                    message_id=message.id,
                    matricula=matricula,
                    status="unread",
                )
            )
        db.session.add_all(recipients)
        db.session.commit()

        push_result = GalintNotifyService._send_push(message=message, recipient_ids=unique_ids)
        return {
            "success": True,
            "message_id": message.id,
            "push": push_result,
        }

    @staticmethod
    def list_inbox(*, matricula: str, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        page = max(1, int(page or 1))
        per_page = min(100, max(1, int(per_page or 20)))
        pagination = (
            GalintNotifyRecipient.query.filter_by(matricula=matricula)
            .join(GalintNotifyMessage, GalintNotifyMessage.id == GalintNotifyRecipient.message_id)
            .order_by(GalintNotifyMessage.created_at.desc(), GalintNotifyRecipient.id.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

        items = []
        for row in pagination.items:
            message = row.message
            items.append(
                {
                    "id": message.id,
                    "recipient_id": row.id,
                    "status": row.status,
                    "read_at": row.read_at.isoformat() if row.read_at else None,
                    "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
                    "title": message.title,
                    "body": message.body,
                    "category": message.category,
                    "message_type": message.message_type,
                    "payload": message.payload or {},
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                }
            )

        unread_count = GalintNotifyRecipient.query.filter_by(matricula=matricula, status="unread").count()
        return {
            "items": items,
            "page": page,
            "per_page": per_page,
            "pages": pagination.pages,
            "total": pagination.total,
            "unread_count": unread_count,
        }

    @staticmethod
    def mark_read(*, matricula: str, message_id: int) -> GalintNotifyRecipient | None:
        recipient = GalintNotifyRecipient.query.filter_by(matricula=matricula, message_id=message_id).first()
        if recipient is None:
            return None
        recipient.status = "read"
        recipient.read_at = datetime.utcnow()
        db.session.commit()
        return recipient

    @staticmethod
    def list_reports() -> list[dict[str, Any]]:
        return [
            {
                "id": "daily",
                "label": "Relatório diário de saídas",
                "formats": ["pdf", "xlsx"],
                "params": {"scope": ["all", "materials", "tools"]},
            },
            {
                "id": "monthly",
                "label": "Relatório mensal de saídas",
                "formats": ["pdf", "xlsx"],
                "params": {
                    "scope": ["all", "materials", "tools"],
                    "year": "int",
                    "month": "int",
                },
            },
        ]

    @staticmethod
    def _send_push(*, message: GalintNotifyMessage, recipient_ids: list[str]) -> dict[str, Any]:
        from .notification_router import NotificationRouterService

        config = NotificationRouterService.get_config()
        if not config.push_enabled:
            return {"success": False, "sent": 0, "error": "Push desabilitado no router."}

        tokens = (
            DevicePushToken.query.filter(DevicePushToken.matricula.in_(recipient_ids), DevicePushToken.ativo.is_(True))
            .all()
        )
        expo_tokens = [item for item in tokens if (item.provider or "expo") == "expo" and (item.token or "").startswith("ExponentPushToken[")]
        if not expo_tokens:
            return {"success": False, "sent": 0, "error": "Nenhum token Expo ativo encontrado."}

        payload = []
        for token in expo_tokens:
            body = {
                "to": token.token,
                "title": message.title,
                "body": message.body[:300],
                "sound": "default",
                "data": {
                    "messageId": message.id,
                    "category": message.category,
                    **(message.payload or {}),
                },
            }
            payload.append(body)

        sent = 0
        last_error = None
        try:
            response = requests.post(
                GalintNotifyService.EXPO_PUSH_URL,
                json=payload,
                headers={"Accept": "application/json", "Accept-encoding": "gzip, deflate", "Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json() if response.content else {}
            results = data.get("data") if isinstance(data, dict) else []
            for index, token in enumerate(expo_tokens):
                result = results[index] if index < len(results) else {}
                if result.get("status") == "ok":
                    token.last_push_at = datetime.utcnow()
                    token.last_error = None
                    sent += 1
                else:
                    token.last_error = str(result.get("message") or result.get("details") or "Falha ao enviar push")
                    last_error = token.last_error
            db.session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao enviar Expo Push: %s", exc)
            for token in expo_tokens:
                token.last_error = str(exc)
            db.session.commit()
            last_error = str(exc)

        if sent:
            GalintNotifyRecipient.query.filter(
                GalintNotifyRecipient.message_id == message.id,
                GalintNotifyRecipient.matricula.in_(recipient_ids),
            ).update({"delivered_at": datetime.utcnow()}, synchronize_session=False)
            db.session.commit()

        return {"success": sent > 0, "sent": sent, "error": last_error}

    @staticmethod
    def metrics() -> dict[str, Any]:
        return {
            "devices": DevicePushToken.query.filter_by(ativo=True).count(),
            "users_with_tokens": db.session.query(DevicePushToken.matricula).filter_by(ativo=True).distinct().count(),
            "unread": GalintNotifyRecipient.query.filter_by(status="unread").count(),
            "messages": GalintNotifyMessage.query.count(),
        }

    @staticmethod
    def resolve_user(matricula: str) -> Usuario | None:
        return Usuario.query.get(matricula)