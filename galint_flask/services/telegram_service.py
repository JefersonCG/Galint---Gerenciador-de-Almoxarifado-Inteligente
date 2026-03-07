"""Serviço para envio de mensagens via Telegram Bot API."""

from __future__ import annotations



import logging

import html

import re

import hashlib

from collections import defaultdict

from datetime import datetime, timedelta, timezone

from typing import Any

import json

import os



import requests



from ..extensions import db

from sqlalchemy import exc as sa_exc, func, or_

from ..models import (

    Item,

    Saida,

    Entrada,

    InventarioEvento,

    TelegramConfig,

    TelegramConversation,

    TelegramGroup,

    TelegramNotification,

    TelegramNotificationPreferences,

    TelegramOutbox,

    TelegramUser,

    Usuario,

)

import threading

import time

from pathlib import Path

from typing import Optional

from ..utils.action_logger import log_action

from ..utils.time_service import TimeService



logger = logging.getLogger(__name__)





class TelegramService:

    """Serviço para gerenciamento de notificações Telegram."""



    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    _outbox_lock = threading.Lock()

    _recent_callback_ids: dict[str, datetime] = {}

    ITEM_CATEGORIES = [

        "Material Elétrico",

        "Material Hidráulico",

        "Material Piscina",

        "Mat. Pintura e Drywall",

        "Materiais de Limpeza",

        "Material Construção",

        "Ferramentas",

        "Equipamento",

        "Material de EP",

        "Material/Uso geral",

    ]

    ITEM_UNITS = [

        "Unidade",

        "Lata",

        "Litro",

        "Quilo",

        "Caixa",

        "Pacote",

        "Rolo",

        "Balde",

        "Par",

        "Peça",

    ]



    @staticmethod

    def _env_int(name: str, default: int) -> int:

        try:

            return int(os.environ.get(name, str(default)).strip())

        except Exception:

            return int(default)



    @staticmethod

    def _outbox_enabled() -> bool:

        return os.environ.get("GALINT_TELEGRAM_OUTBOX_ENABLED", "true").strip().lower() in (

            "1",

            "true",

            "yes",

        )



    @staticmethod

    def _outbox_max_attempts() -> int:

        # 0 = ilimitado

        return TelegramService._env_int("GALINT_TELEGRAM_OUTBOX_MAX_ATTEMPTS", 0)



    @staticmethod

    def _outbox_base_delay_seconds() -> int:

        return max(1, TelegramService._env_int("GALINT_TELEGRAM_OUTBOX_BASE_DELAY_SECONDS", 30))



    @staticmethod

    def _outbox_max_delay_seconds() -> int:

        return max(5, TelegramService._env_int("GALINT_TELEGRAM_OUTBOX_MAX_DELAY_SECONDS", 21600))


    @staticmethod

    def _outbox_dedupe_window_seconds() -> int:

        return max(10, TelegramService._env_int("GALINT_TELEGRAM_OUTBOX_DEDUPE_WINDOW_SECONDS", 120))



    @staticmethod

    def _outbox_accelerate_recovery_enabled() -> bool:

        return os.environ.get("GALINT_TELEGRAM_OUTBOX_ACCELERATE_ON_RECOVERY", "true").strip().lower() in (

            "1",

            "true",

            "yes",

        )



    @staticmethod

    def _is_duplicate_callback(callback_id: str, ttl_seconds: int = 120) -> bool:

        """Evita processar o mesmo callback duas vezes."""

        now = datetime.utcnow()

        # Limpeza simples do cache

        cutoff = now - timedelta(seconds=int(ttl_seconds))

        for key, ts in list(TelegramService._recent_callback_ids.items()):

            if ts < cutoff:

                TelegramService._recent_callback_ids.pop(key, None)



        if callback_id in TelegramService._recent_callback_ids:

            return True

        TelegramService._recent_callback_ids[callback_id] = now

        return False



    @staticmethod

    def _is_privileged_user(user: Usuario | None) -> bool:

        if not user:

            return False

        if getattr(user, "is_admin", 0) == 1:

            return True

        setor = (getattr(user, "setor", "") or "").strip().upper()

        cargo = (getattr(user, "cargo", "") or "").strip().upper()

        return any(keyword in setor for keyword in ("ZELADOR", "SUPERVISOR")) or any(

            keyword in cargo for keyword in ("ZELADOR", "SUPERVISOR")

        )



    @staticmethod

    def _privileged_users_query():

        return (

            db.session.query(TelegramUser)

            .join(Usuario, TelegramUser.matricula == Usuario.matricula)

            .filter(TelegramUser.enabled.is_(True))

            .filter(

                or_(

                    Usuario.is_admin == 1,

                    Usuario.setor.ilike("%ZELADOR%"),

                    Usuario.setor.ilike("%SUPERVISOR%"),

                    Usuario.cargo.ilike("%ZELADOR%"),

                    Usuario.cargo.ilike("%SUPERVISOR%"),

                )

            )

        )

    

    @staticmethod

    def _should_notify_user(telegram_user: TelegramUser, item_categoria: str, is_return: bool = False) -> bool:

        """Verifica se o usuário deve receber notificação baseado em suas preferências.

        

        Args:

            telegram_user: Usuário do Telegram

            item_categoria: Categoria do item (ex: "Material Elétrico", "Ferramenta")

            is_return: True se for devolução, False se for retirada

            

        Returns:

            True se deve notificar, False caso contrário

        """

        # Se não tem preferências configuradas, notifica tudo (comportamento padrão)

        if not telegram_user.notification_preferences:

            # Criar preferências padrão automaticamente

            prefs = TelegramNotificationPreferences(telegram_user_id=telegram_user.id)

            db.session.add(prefs)

            try:

                db.session.commit()

            except Exception as e:

                logger.warning(f"Erro ao criar preferências padrão para {telegram_user.id}: {e}")

                db.session.rollback()

            return True



    @staticmethod

    def _compute_backoff_seconds(attempt_count: int) -> int:

        base = TelegramService._outbox_base_delay_seconds()

        max_delay = TelegramService._outbox_max_delay_seconds()

        # backoff exponencial (1->base, 2->2*base, ...), com teto.

        try:

            delay = int(base * (2 ** max(0, attempt_count - 1)))

        except Exception:

            delay = base

        return int(min(max_delay, max(base, delay)))



    @staticmethod

    def release_outbox_backlog(*, limit: int | None = None) -> dict[str, Any]:

        """Antecipa mensagens pendentes/falhas com available_at no futuro.

        Usado para recuperar rapidamente após retorno de internet.
        """

        now = datetime.utcnow()

        try:

            query = (

                db.session.query(TelegramOutbox)

                .filter(TelegramOutbox.status.in_(["pending", "failed"]))

                .filter(TelegramOutbox.available_at > now)

                .order_by(TelegramOutbox.available_at.asc(), TelegramOutbox.id.asc())

            )



            if limit is not None:

                rows = query.limit(int(limit)).all()

                released = 0

                for row in rows:

                    row.available_at = now

                    released += 1

            else:

                released = query.update({TelegramOutbox.available_at: now}, synchronize_session=False)



            db.session.commit()

            return {"success": True, "released": int(released or 0)}

        except Exception as exc:

            db.session.rollback()

            return {"success": False, "released": 0, "error": str(exc)}



    @staticmethod

    def enqueue_outbox_message(

        *,

        chat_id: str,

        recipient_name: str | None,

        message_type: str,

        message_text: str,

        idempotency_key: str,

        parse_mode: str | None = "HTML",

        reply_markup: dict[str, Any] | None = None,

        saida_id: int | None = None,

        entrada_id: int | None = None,

        inventario_evento_id: int | None = None,

        commit: bool = True,

    ) -> dict[str, Any]:

        """Registra uma mensagem na fila (Outbox) e retorna ids.



        Regra principal: nunca depender do envio imediato para não perder mensagens.

        """



        if not TelegramService._outbox_enabled():

            return {"success": False, "error": "Outbox desabilitado por configuração"}


        # Dedupe curto para evitar mensagens identicas em sequencia no mesmo chat.

        try:

            dedupe_window = TelegramService._outbox_dedupe_window_seconds()

            cutoff = datetime.utcnow() - timedelta(seconds=int(dedupe_window))

            recent_same = (

                db.session.query(TelegramNotification)

                .filter(TelegramNotification.chat_id == str(chat_id))

                .filter(TelegramNotification.message_type == message_type)

                .filter(TelegramNotification.message_text == message_text)

                .filter(TelegramNotification.sent_at >= cutoff)

                .first()

            )

            if recent_same:
                logger.info(f"[DEDUPE] Ignorando mensagem já enviada: {chat_id}")
                return {
                    "success": True,
                    "queued": False,
                    "deduped": True,
                    "reason": "recent_same_message",
                    "notification_id": recent_same.id,
                }
            
            # Verificação também na tabela TelegramOutbox (fila de pendentes)
            recent_pending = (
                db.session.query(TelegramOutbox)
                .filter(TelegramOutbox.chat_id == str(chat_id))
                .filter(TelegramOutbox.message_type == message_type)
                .filter(TelegramOutbox.message_text == message_text)
                .filter(TelegramOutbox.created_at >= cutoff)
                .filter(TelegramOutbox.status.in_(["pending", "processing"]))
                .first()
            )

            if recent_pending:
                logger.info(f"[DEDUPE] Ignorando mensagem pendente na fila: {chat_id}")
                return {
                    "success": True,
                    "queued": False,
                    "deduped": True,
                    "reason": "recent_pending_message",
                    "outbox_id": recent_pending.id,
                }

        except Exception:

            pass



        # Adi anti-duplicidade adicional: verificar se já existe mensagem ENVIADA com mesmo saida_id/chat_id
        if saida_id:
            existing_sent = db.session.query(TelegramNotification).filter_by(
                chat_id=str(chat_id),
                saida_id=saida_id,
                status="sent"
            ).first()
            if existing_sent:
                logger.debug(f"Mensagem já enviada para chat_id={chat_id} saida_id={saida_id}, pulando")
                return {
                    "success": True,
                    "queued": False,
                    "deduped": True,
                    "reason": "already_sent",
                    "notification_id": existing_sent.id
                }

        # Idempotência: se já existe, não duplicar.

        existing = db.session.query(TelegramOutbox).filter_by(idempotency_key=idempotency_key).first()

        if existing is not None:

            return {

                "success": True,

                "queued": True,

                "outbox_id": getattr(existing, "id", None),

                "notification_id": getattr(existing, "notification_id", None),

                "deduped": True,

                "status": getattr(existing, "status", None),

            }



        # Criar (1) registro de histórico/visibilidade e (2) outbox.

        notif = TelegramNotification(

            chat_id=str(chat_id),

            recipient_name=recipient_name,

            message_type=message_type,

            message_text=message_text,

            status="pending",

            error_message=None,

            saida_id=saida_id,

        )

        db.session.add(notif)

        db.session.flush()  # garante notif.id



        out = TelegramOutbox(

            idempotency_key=idempotency_key,

            status="pending",

            chat_id=str(chat_id),

            recipient_name=recipient_name,

            message_type=message_type,

            message_text=message_text,

            parse_mode=parse_mode,

            reply_markup_json=json.dumps(reply_markup, ensure_ascii=False) if reply_markup else None,

            available_at=datetime.utcnow(),

            attempt_count=0,

            max_attempts=TelegramService._outbox_max_attempts(),

            last_error=None,

            provider_message_id=None,

            saida_id=saida_id,

            entrada_id=entrada_id,

            inventario_evento_id=inventario_evento_id,

            notification_id=getattr(notif, "id", None),

        )

        db.session.add(out)



        try:

            if commit:

                db.session.commit()

            else:

                db.session.flush()

        except sa_exc.IntegrityError:

            db.session.rollback()

            # corrida (2 processos/threads): buscar existente.

            existing = db.session.query(TelegramOutbox).filter_by(idempotency_key=idempotency_key).first()

            return {

                "success": True,

                "queued": True,

                "outbox_id": getattr(existing, "id", None) if existing else None,

                "notification_id": getattr(existing, "notification_id", None) if existing else None,

                "deduped": True,

                "status": getattr(existing, "status", None) if existing else None,

            }

        except Exception as exc:

            db.session.rollback()

            return {"success": False, "error": str(exc)}



        return {

            "success": True,

            "queued": True,

            "outbox_id": getattr(out, "id", None),

            "notification_id": getattr(notif, "id", None),

            "deduped": False,

            "status": getattr(out, "status", None),

        }



    @staticmethod

    def process_outbox(*, limit: int = 50, drain: bool = False) -> dict[str, Any]:

        """Processa a fila de mensagens Telegram (pending/failed) com retry/backoff."""



        if not TelegramService._outbox_enabled():

            return {"success": True, "skipped": True, "reason": "outbox disabled"}



        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não está habilitado"}



        acquired = TelegramService._outbox_lock.acquire(blocking=False)

        if not acquired:

            return {"success": True, "skipped": True, "reason": "outbox worker already running"}



        try:

            now = datetime.utcnow()

            totals = {"attempted": 0, "sent": 0, "failed": 0, "dead": 0}



            while True:

                rows = (

                    db.session.query(TelegramOutbox)

                    .filter(TelegramOutbox.status.in_(["pending", "failed"]))

                    .filter(TelegramOutbox.available_at <= now)

                    .order_by(TelegramOutbox.available_at.asc(), TelegramOutbox.id.asc())

                    .limit(int(limit))

                    .all()

                )



                if not rows:

                    if TelegramService._outbox_accelerate_recovery_enabled():

                        try:

                            future_failed = (

                                db.session.query(TelegramOutbox)

                                .filter(TelegramOutbox.status.in_(["pending", "failed"]))

                                .filter(TelegramOutbox.available_at > now)

                                .count()

                            )

                        except Exception:

                            future_failed = 0



                        if future_failed > 0:

                            conn = TelegramService.test_connection()

                            if conn.get("success"):

                                released = TelegramService.release_outbox_backlog(limit=max(int(limit), 50))

                                if released.get("success") and int(released.get("released", 0) or 0) > 0:

                                    now = datetime.utcnow()

                                    continue

                    break



                for msg in rows:
                    # Verifica se a mensagem ainda precisa ser processada (evita race condition)
                    try:

                        db.session.refresh(msg)

                    except Exception:

                        db.session.rollback()

                        continue

                    if msg.status not in ["pending", "failed"]:
                        logger.debug(f"[process_outbox] Pulando mensagem id={msg.id} status={msg.status} (já processada)")
                        continue

                    totals["attempted"] += 1



                    max_attempts = int(getattr(msg, "max_attempts", 0) or 0)

                    attempt_count = int(getattr(msg, "attempt_count", 0) or 0)

                    if max_attempts > 0 and attempt_count >= max_attempts:

                        msg.status = "dead"

                        msg.last_error = msg.last_error or "max_attempts_exceeded"

                        # refletir no histórico

                        try:

                            if msg.notification is not None:

                                msg.notification.status = "failed"

                                msg.notification.error_message = msg.last_error

                                msg.notification.sent_at = datetime.utcnow()

                        except Exception:

                            pass

                        totals["dead"] += 1

                        continue



                    reply_markup = None

                    try:

                        if getattr(msg, "reply_markup_json", None):

                            reply_markup = json.loads(msg.reply_markup_json)

                    except Exception:

                        reply_markup = None



                    res = TelegramService.send_message(

                        msg.chat_id,

                        msg.message_text,

                        parse_mode=getattr(msg, "parse_mode", None),

                        reply_markup=reply_markup,

                    )



                    msg.last_attempt_at = datetime.utcnow()

                    msg.attempt_count = attempt_count + 1



                    if res.get("success"):

                        msg.status = "sent"

                        msg.last_error = None

                        msg.provider_message_id = res.get("message_id")

                        msg.available_at = datetime.utcnow()

                        totals["sent"] += 1
                        logger.info(f"[process_outbox] Mensagem enviada com sucesso: outbox_id={msg.id}, chat_id={msg.chat_id}, saida_id={getattr(msg, 'saida_id', None)}, message_type={msg.message_type}")

                        try:

                            if msg.notification is not None:

                                msg.notification.status = "sent"

                                msg.notification.error_message = None

                                msg.notification.sent_at = datetime.utcnow()

                        except Exception:

                            pass

                    else:

                        msg.status = "failed"

                        msg.last_error = res.get("error")

                        backoff = TelegramService._compute_backoff_seconds(msg.attempt_count)

                        msg.available_at = datetime.utcnow() + timedelta(seconds=int(backoff))

                        totals["failed"] += 1

                        try:

                            if msg.notification is not None:

                                msg.notification.status = "failed"

                                msg.notification.error_message = msg.last_error

                                msg.notification.sent_at = datetime.utcnow()

                        except Exception:

                            pass



                try:

                    db.session.commit()

                except Exception:

                    db.session.rollback()

                    # Não abortar todo o worker; tentar continuar em execução futura.

                    return {"success": False, "error": "Falha ao persistir processamento do outbox"}



                if not drain:

                    break



                now = datetime.utcnow()



            return {"success": True, **totals}

        finally:

            try:

                TelegramService._outbox_lock.release()

            except Exception:

                pass



    @staticmethod

    def _instance_dir() -> Path:

        p = Path("instance")

        p.mkdir(parents=True, exist_ok=True)

        return p



    @staticmethod

    def _status_file() -> Path:

        return TelegramService._instance_dir() / "telegram_runtime_status.json"



    @staticmethod

    def _retry_attempts_file() -> Path:

        return TelegramService._instance_dir() / "telegram_retry_attempts.json"



    @staticmethod

    def _load_retry_attempts() -> dict[str, int]:

        try:

            p = TelegramService._retry_attempts_file()

            if not p.exists():

                return {}

            data = json.loads(p.read_text(encoding="utf-8"))

            if isinstance(data, dict):

                out: dict[str, int] = {}

                for k, v in data.items():

                    try:

                        out[str(k)] = int(v)

                    except Exception:

                        out[str(k)] = 0

                return out

            return {}

        except Exception:

            return {}



    @staticmethod

    def _save_retry_attempts(attempts: dict[str, int]) -> None:

        try:

            TelegramService._retry_attempts_file().write_text(

                json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8"

            )

        except Exception:

            pass



    @staticmethod

    def read_runtime_status() -> dict[str, Any] | None:

        try:

            p = TelegramService._status_file()

            if not p.exists():

                return None

            return json.loads(p.read_text(encoding="utf-8"))

        except Exception:

            return None



    @staticmethod

    def _write_runtime_status(payload: dict[str, Any]) -> None:

        try:

            TelegramService._status_file().write_text(

                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"

            )

        except Exception:

            pass



    @staticmethod

    def _daypart_prefix(now_local: datetime) -> str:

        hour = int(now_local.hour)

        if 5 <= hour < 12:

            return "Bom dia"

        if 12 <= hour < 18:

            return "Boa tarde"

        return "Boa noite"



    @staticmethod

    def _allowed_boa_noite_window(now_local: datetime) -> bool:

        """Permite envio de mensagens com 'Boa noite' apenas entre 07:50 e 18:00."""

        hour = int(now_local.hour)

        minute = int(now_local.minute)

        if hour < 7 or (hour == 7 and minute < 50):

            return False

        if hour > 18 or (hour == 18 and minute > 0):

            return False

        return True



    @staticmethod

    def _first_name(full_name: str | None) -> str:

        if not full_name:

            return "amigo"

        parts = [p for p in str(full_name).strip().split() if p]

        if not parts:

            return "amigo"

        return parts[0].strip().title()



    @staticmethod

    def _startup_greeting_text(nome: str | None) -> str:

        now_local = TimeService.now_local()

        prefix = TelegramService._daypart_prefix(now_local)

        first = TelegramService._first_name(nome).upper()

        # Texto solicitado (mensagem "abençoada" + almoxarifado aberto)

        return f"{prefix}, {first}! Que seu dia seja uma benção. O almoxarifado está aberto!"



    @staticmethod

    def _notify_admins(text: str) -> None:

        """Envia uma mensagem para administradores com Telegram vinculado."""

        try:

            admins = TelegramService._privileged_users_query().all()

        except Exception:

            return



        for adm in admins:

            try:

                TelegramService.send_message(adm.chat_id, text)

            except Exception:

                pass



    @staticmethod

    def watchdog_check(app) -> dict[str, Any]:

        """Checa saúde do Telegram e tenta manter o polling ativo.



        - Atualiza um status persistido em instance/telegram_runtime_status.json

        - Se polling estiver configurado e o thread morrer, tenta reiniciar.

        """



        checked_at = TimeService.now_local().isoformat()



        # Detectar transições (down -> up / up -> down)

        previous = TelegramService.read_runtime_status() or {}

        previous_ok = previous.get("ok")



        # Se não está habilitado, apenas registrar estado e sair.

        if not TelegramService.is_enabled():

            payload = {

                "ok": False,

                "mode": "disabled",

                "checked_at": checked_at,

                "error": "Telegram não habilitado/configurado",

            }

            TelegramService._write_runtime_status(payload)

            return payload



        conn = TelegramService.test_connection()

        ok = bool(conn.get("success"))

        payload: dict[str, Any] = {

            "ok": ok,

            "mode": "enabled",

            "checked_at": checked_at,

        }

        if ok:

            payload["bot_username"] = conn.get("bot_username")

            payload["bot_name"] = conn.get("bot_name")

            payload["bot_id"] = conn.get("bot_id")

        else:

            payload["error"] = conn.get("error") or "Falha ao conectar no Telegram"



        # Notificar admins quando houver transição de estado

        try:

            if previous_ok is True and ok is False:

                TelegramService._notify_admins(

                    f"⚠️ Telegram fora do ar: {payload.get('error') or 'motivo não informado'}."

                )

            elif previous_ok is False and ok is True:

                # Ao normalizar, drenar a fila do Outbox e reportar resumo.

                release_summary: dict[str, Any] = {"success": True, "released": 0}

                if TelegramService._outbox_accelerate_recovery_enabled():

                    try:

                        release_summary = TelegramService.release_outbox_backlog()

                    except Exception as exc:

                        release_summary = {"success": False, "released": 0, "error": str(exc)}

                drain_summary: dict[str, Any] = {}

                try:

                    drain_summary = TelegramService.process_outbox(drain=True, limit=200)

                except Exception as exc:

                    drain_summary = {"success": False, "error": str(exc)}



                if drain_summary.get("success"):

                    if drain_summary.get("skipped"):

                        TelegramService._notify_admins(

                            "✅ Telegram normalizado e operacional. (Outbox/contingência desativada)"

                        )

                    else:

                        sent = int(drain_summary.get("sent", 0) or 0)

                        failed = int(drain_summary.get("failed", 0) or 0)

                        dead = int(drain_summary.get("dead", 0) or 0)

                        attempted = int(drain_summary.get("attempted", 0) or 0)

                        released = int(release_summary.get("released", 0) or 0)

                        TelegramService._notify_admins(

                            "✅ Telegram normalizado e operacional. "

                            f"Outbox: liberadas={released}, tentadas={attempted}, enviadas={sent}, falhas={failed}, mortas={dead}."

                        )

                else:

                    TelegramService._notify_admins(

                        "✅ Telegram normalizado e operacional. "

                        f"Drenagem do outbox falhou: {drain_summary.get('error') or 'motivo não informado'}."

                    )

        except Exception:

            pass



        # Watchdog do polling (somente se for desejado pela env)

        try:

            want_polling = os.environ.get("GALINT_TELEGRAM_POLLING", "true").strip().lower() in (

                "1",

                "true",

                "yes",

            )

            if want_polling:

                alive = bool(TelegramService._polling_thread and TelegramService._polling_thread.is_alive())

                payload["polling_alive"] = alive

                if ok and not alive:

                    try:

                        keep = os.environ.get("GALINT_TELEGRAM_KEEP_WEBHOOK", "false").strip().lower() in (

                            "1",

                            "true",

                            "yes",

                        )

                        TelegramService.start_polling_background(app, keep_webhook=keep)

                        payload["polling_restarted_at"] = TimeService.now_local().isoformat()

                    except Exception as exc:

                        payload["polling_restart_error"] = str(exc)

        except Exception:

            pass



        TelegramService._write_runtime_status(payload)

        return payload



    @staticmethod

    def retry_failed_notifications(

        limit: int = 50,

        within_hours: int = 168,

        max_attempts: int = 10,

    ) -> dict[str, Any]:

        """Reenvia mensagens que falharam, para não perder alertas durante instabilidade.



        Persistimos contagem de tentativas em arquivo (sem migração de banco).

        """

        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não habilitado"}



        # só tenta se conexão estiver OK

        conn = TelegramService.test_connection()

        if not conn.get("success"):

            return {"success": False, "error": conn.get("error") or "Falha ao conectar"}



        # feature flag

        # Objetivo: manter notificações resilientes (contingência) e reenviar ao normalizar.

        # Pode ser desativado explicitamente se necessário.

        if os.environ.get("GALINT_TELEGRAM_RETRY_FAILED", "true").strip().lower() not in (

            "1",

            "true",

            "yes",

        ):

            return {"success": True, "skipped": True, "reason": "retry disabled"}



        try:

            within_hours = int(os.environ.get("GALINT_TELEGRAM_RETRY_WITHIN_HOURS", str(within_hours)))

        except Exception:

            within_hours = within_hours

        try:

            max_attempts = int(os.environ.get("GALINT_TELEGRAM_RETRY_MAX_ATTEMPTS", str(max_attempts)))

        except Exception:

            max_attempts = max_attempts



        cutoff = datetime.utcnow() - timedelta(hours=int(within_hours))



        attempts = TelegramService._load_retry_attempts()



        try:

            failed = (

                db.session.query(TelegramNotification)

                .filter(TelegramNotification.status == "failed", TelegramNotification.sent_at >= cutoff)

                .order_by(TelegramNotification.sent_at.asc())

                .limit(int(limit))

                .all()

            )

        except Exception as exc:

            return {"success": False, "error": str(exc)}



        resent = 0

        still_failed: list[dict[str, Any]] = []

        skipped_max = 0

        skipped_duplicates = 0



        for n in failed:

            key = str(getattr(n, "id", ""))

            try:

                cur = int(attempts.get(key, 0))

            except Exception:

                cur = 0



            if cur >= int(max_attempts):

                skipped_max += 1

                continue



            # Proteção anti-duplicidade:

            # - Se já existe um envio "sent" do mesmo evento (saida_id) para o mesmo chat,

            #   não faz sentido reenviar.

            # - Para notificações sem saida_id, tenta deduplicar por texto em janela curta.

            try:

                dup = None

                if getattr(n, "saida_id", None):

                    dup = (

                        db.session.query(TelegramNotification)

                        .filter(

                            TelegramNotification.chat_id == n.chat_id,

                            TelegramNotification.message_type == n.message_type,

                            TelegramNotification.saida_id == n.saida_id,

                            TelegramNotification.status == "sent",

                        )

                        .first()

                    )

                else:

                    recent_cutoff = datetime.utcnow() - timedelta(minutes=15)

                    dup = (

                        db.session.query(TelegramNotification)

                        .filter(

                            TelegramNotification.chat_id == n.chat_id,

                            TelegramNotification.message_type == n.message_type,

                            TelegramNotification.status == "sent",

                            TelegramNotification.sent_at >= recent_cutoff,

                            TelegramNotification.message_text == n.message_text,

                        )

                        .first()

                    )



                if dup is not None:

                    skipped_duplicates += 1

                    n.status = "sent"

                    n.error_message = "auto-marked-sent: duplicate detected"

                    # limpar contagem para esse id

                    if key in attempts:

                        attempts.pop(key, None)

                    continue

            except Exception:

                # se falhar dedupe por algum motivo, seguimos com retry normal

                pass



            res = TelegramService.send_message(n.chat_id, n.message_text)

            if res.get("success"):

                n.status = "sent"

                n.error_message = None

                n.sent_at = datetime.utcnow()

                resent += 1

                # limpar contagem para esse id

                if key in attempts:

                    attempts.pop(key, None)

            else:

                attempts[key] = cur + 1

                n.error_message = res.get("error")

                still_failed.append({"id": getattr(n, "id", None), "error": res.get("error")})



        try:

            db.session.commit()

        except Exception:

            db.session.rollback()



        TelegramService._save_retry_attempts(attempts)

        return {

            "success": True,

            "resent": resent,

            "failed": len(still_failed),

            "skipped_max_attempts": skipped_max,

            "skipped_duplicates": skipped_duplicates,

        }



    @staticmethod

    def get_config() -> TelegramConfig | None:

        """Retorna configuração atual do Telegram."""

        try:

            return db.session.query(TelegramConfig).first()

        except sa_exc.ProgrammingError:

            # Esquema do banco não contém colunas novas (migração pendente)

            db.session.rollback()

            logger.warning("TelegramConfig: coluna ausente no DB — migração pendente")

            return None



    @staticmethod

    def is_enabled() -> bool:

        """Verifica se Telegram está habilitado."""

        config = TelegramService.get_config()

        return config is not None and config.enabled and bool(config.bot_token)



    @staticmethod

    def test_connection() -> dict[str, Any]:

        """Testa conexão com o bot do Telegram."""

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Token do bot não configurado"}



        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="getMe")

            response = requests.get(url, timeout=10)

            data = response.json()



            if data.get("ok"):

                bot_info = data.get("result", {})

                return {

                    "success": True,

                    "bot_username": bot_info.get("username"),

                    "bot_name": bot_info.get("first_name"),

                    "bot_id": bot_info.get("id"),

                }

            return {"success": False, "error": data.get("description", "Erro desconhecido")}

        except requests.RequestException as e:

            logger.error(f"Erro ao testar conexão Telegram: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def set_webhook(webhook_url: str) -> dict[str, Any]:

        """Configura webhook do Telegram."""

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Token do bot não configurado"}



        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="setWebhook")

            payload = {"url": webhook_url}

            

            response = requests.post(url, json=payload, timeout=10)

            data = response.json()



            if data.get("ok"):

                return {"success": True, "description": data.get("description", "Webhook configurado")}

            return {"success": False, "error": data.get("description", "Erro ao configurar webhook")}

        except requests.RequestException as e:

            logger.error(f"Erro ao configurar webhook: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def delete_webhook() -> dict[str, Any]:

        """Remove webhook do Telegram."""

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Token do bot não configurado"}



        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="deleteWebhook")

            response = requests.post(url, timeout=10)

            data = response.json()



            if data.get("ok"):

                return {"success": True, "description": "Webhook removido"}

            return {"success": False, "error": data.get("description", "Erro ao remover webhook")}

        except requests.RequestException as e:

            logger.error(f"Erro ao remover webhook: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def get_updates(

        offset: int | None = None,

        timeout: int = 30,

        allowed_updates: list[str] | None = None,

    ) -> dict[str, Any]:

        """Busca atualizações do Telegram (polling/webhook suporte).



        Importante: Se o webhook estiver ativo, o Telegram pode retornar "Conflict"

        para getUpdates.

        """

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Token do bot não configurado"}



        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="getUpdates")

            params: dict[str, Any] = {"timeout": timeout}

            if offset is not None:

                params["offset"] = offset

            if allowed_updates is not None:

                params["allowed_updates"] = allowed_updates

            

            response = requests.get(url, params=params, timeout=timeout + 5)

            data = response.json()



            if data.get("ok"):

                return {"success": True, "updates": data.get("result", [])}

            return {"success": False, "error": data.get("description", "Erro ao buscar updates")}

        except requests.RequestException as e:

            logger.error(f"Erro ao buscar updates: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def send_message(

        chat_id: str,

        text: str,

        parse_mode: str | None = "HTML",

        reply_markup: dict[str, Any] | None = None,

    ) -> dict[str, Any]:

        """Envia mensagem para um chat específico.



        Suporta `reply_markup` para ReplyKeyboardMarkup/InlineKeyboardMarkup.

        """

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Bot não configurado"}



        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="sendMessage")

            payload: dict[str, Any] = {"chat_id": chat_id, "text": text}

            if parse_mode is not None:

                payload["parse_mode"] = parse_mode

            if reply_markup is not None:

                payload["reply_markup"] = reply_markup



            response = requests.post(url, json=payload, timeout=10)

            data = response.json()



            if data.get("ok"):

                return {"success": True, "message_id": data.get("result", {}).get("message_id")}

            return {"success": False, "error": data.get("description", "Erro ao enviar mensagem")}

        except requests.RequestException as e:

            logger.error(f"Erro ao enviar mensagem Telegram: {e}")

            return {"success": False, "error": str(e)}

    @staticmethod
    def send_alert_to_user(nome_usuario: str, mensagem: str) -> bool:
        """Envia alerta para um usuário específico do Telegram pelo nome.
        
        Args:
            nome_usuario: Nome do usuário no banco (ex: "Jeferson dos Santos")
            mensagem: Texto da mensagem a enviar (HTML)
            
        Returns:
            bool: True se enviado com sucesso
        """
        try:
            # Buscar usuário por nome
            usuario = db.session.query(Usuario).filter(
                func.upper(Usuario.nome) == nome_usuario.upper()
            ).first()
            
            if not usuario:
                logger.warning(f"Usuário não encontrado: {nome_usuario}")
                return False
            
            # Buscar configuração Telegram do usuário
            telegram_user = db.session.query(TelegramUser).filter_by(
                matricula=usuario.matricula,
                enabled=True
            ).first()
            
            if not telegram_user:
                logger.warning(f"Usuário {nome_usuario} não tem Telegram configurado")
                return False
            
            # Enviar mensagem
            result = TelegramService.send_message(
                chat_id=telegram_user.chat_id,
                text=mensagem,
                parse_mode="HTML"
            )
            
            return result.get("success", False)
            
        except Exception as e:
            logger.error(f"Erro ao enviar alerta para {nome_usuario}: {e}")
            return False


    @staticmethod

    def send_document(chat_id: str, file_path: str, caption: str | None = None) -> dict[str, Any]:

        """Envia um arquivo (document) para um chat via Telegram Bot API."""

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Bot não configurado"}



        try:

            url = f"https://api.telegram.org/bot{config.bot_token}/sendDocument"

            with open(file_path, "rb") as fh:

                files = {"document": fh}

                data = {"chat_id": chat_id}

                if caption:

                    data["caption"] = caption

                response = requests.post(url, data=data, files=files, timeout=30)

            res = response.json()

            if res.get("ok"):

                return {"success": True, "message_id": res.get("result", {}).get("message_id")}

            return {"success": False, "error": res.get("description", "Erro ao enviar documento")}

        except requests.RequestException as e:

            logger.error(f"Erro ao enviar documento Telegram: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def _format_saida_quantidade(saida: Saida, item: Item) -> str:

        """Formata quantidade da saída considerando unidade original informada pelo modal."""

        def _fmt_number_pt(value: float, *, decimals: int = 3) -> str:
            try:
                value_f = float(value)
            except Exception:
                return "0"
            if abs(value_f - round(value_f)) < 1e-9:
                return str(int(round(value_f)))
            txt = f"{value_f:.{decimals}f}".rstrip("0").rstrip(".")
            return txt.replace(".", ",")

        try:
            observacao = (saida.observacao or "").upper()
        except Exception:
            observacao = ""

        # Se a saída foi registrada como fracionada em KG, priorizar exibição em KG
        try:
            qtd_quilos = getattr(saida, "quantidade_retirada_em_quilos", None)
            if qtd_quilos is not None and float(qtd_quilos) > 0:
                return f"{_fmt_number_pt(float(qtd_quilos), decimals=3)} KG"
        except Exception:
            pass

        unidade_map = {

            "METROS": "metros",

            "CM": "cm",

            "LITROS": "litros",

            "KG": "KG",

            "UNIDADES": "unidades",

        }



        if "UNIDADE=" in observacao:

            unidade = None

            qtd_original = None

            try:

                for part in observacao.split(";"):

                    if part.startswith("UNIDADE="):

                        unidade = part.split("=")[-1].strip()

                    elif part.startswith("QTD_ORIGINAL="):

                        qtd_original = part.split("=")[-1].strip()

            except Exception:

                unidade = None

                qtd_original = None



            if unidade:

                unidade_fmt = unidade_map.get(unidade, unidade.lower())

                if qtd_original:

                    qtd_fmt = qtd_original.replace(".", ",") if "," not in qtd_original else qtd_original

                    return f"{qtd_fmt} {unidade_fmt}"

                return f"{saida.quantidade:g} {unidade_fmt}"



        try:
            # Tentar usar formatação inteligente com embalagens
            from ..services.embalagem_service import EmbalagemService
            quantidade_fmt = EmbalagemService.formatar_quantidade(saida.quantidade, item)
            return quantidade_fmt
        except Exception:
            pass



        return f"{saida.quantidade:g} {item.unidade or 'un'}"



    @staticmethod

    def _format_balance_totals(item: Item, prefix: str = "   ", saldo_override: float = None) -> str:

        """Gera linhas de saldo total em Kg/Litros/Metros e detalhes de caixa/pacote.
        
        Args:
            item: Item do estoque
            prefix: Prefixo para cada linha
            saldo_override: Se fornecido, usa este saldo ao invés de ler do banco (útil em notificações)
        """

        lines: list[str] = []

        def _fmt_amount(value: float, decimals: int = 2) -> str:
            try:
                value_f = float(value)
            except Exception:
                return "0"
            if abs(value_f - round(value_f)) < 1e-9:
                return str(int(round(value_f)))
            return f"{value_f:.{decimals}f}".rstrip("0").rstrip(".")



        try:

            from galint_flask.services.embalagem_service import EmbalagemService

        except Exception:

            EmbalagemService = None



        embalagens = None

        soltas = None

        saldo_total_units = None



        try:

            # Se saldo_override foi fornecido, usar ele ao invés de ler do banco

            if saldo_override is not None:

                saldo_total_units = float(saldo_override)

                # Para itens com embalagens, calcular quantas embalagens + soltas baseado no saldo

                if EmbalagemService and EmbalagemService.tem_embalagem(item):

                    unidades_por = item.unidades_por_embalagem or 1

                    embalagens = int(saldo_total_units // unidades_por)

                    soltas = saldo_total_units % unidades_por

            elif EmbalagemService and EmbalagemService.tem_embalagem(item):

                embalagens = item.estoque_embalagens or 0

                soltas = item.estoque_unidades_soltas or 0

                saldo_total_units = EmbalagemService.calcular_estoque_total(item)

            else:

                saldo_total_units = float(item.get_saldo_atual() or 0)

        except Exception:

            saldo_total_units = None



        tipo_emb = (item.tipo_embalagem_novo or "").strip().lower()

        unidade_raw = (item.unidade or "").strip().lower()



        if EmbalagemService and EmbalagemService.tem_embalagem(item) and tipo_emb in ("caixa", "pacote"):

            unidades_por = item.unidades_por_embalagem or 0

            total_internas = (embalagens or 0) * unidades_por

            nome = "Caixas" if tipo_emb == "caixa" else "Pacotes"

            lines.append(f"{prefix}📦 {nome}: {embalagens:g} (internas: {total_internas:g} un)")

            if soltas:

                lines.append(f"{prefix}+ Unidades soltas: {soltas:g} un")



        total_litros = None

        litros_por_emb = getattr(item, "litros_por_embalagem", None)

        if litros_por_emb:

            if EmbalagemService and EmbalagemService.tem_embalagem(item):

                # Em itens de volume com embalagem (lata/balde/litro), unidades soltas são litros.
                total_litros = (embalagens or 0) * litros_por_emb + (soltas or 0)

            else:

                total_litros = (saldo_total_units or 0) * litros_por_emb

        elif unidade_raw in ("litro", "litros", "l", "lt", "lts"):

            total_litros = saldo_total_units



        total_kg = None

        # Se o item é de litros (litros_por_embalagem definido), não exibir KG mesmo que exista valor legado em grandeza_referencia.
        if not litros_por_emb:

            kg_por_emb = getattr(item, "grandeza_referencia", None)

            if kg_por_emb:

                if EmbalagemService and EmbalagemService.tem_embalagem(item):

                    # Em itens de peso com embalagem, unidades soltas são kg.
                    total_kg = (embalagens or 0) * kg_por_emb + (soltas or 0)

                else:

                    total_kg = (saldo_total_units or 0) * kg_por_emb

            elif unidade_raw in ("kg", "quilo", "quilos"):

                total_kg = saldo_total_units



        total_metros = None

        if EmbalagemService and EmbalagemService.tem_rolo_legacy(item):

            total_metros = (saldo_total_units or 0) * (item.grandeza_referencia or 0)

        elif EmbalagemService and EmbalagemService.tem_embalagem(item) and tipo_emb == "rolo":

            total_metros = (embalagens or 0) * (item.unidades_por_embalagem or 0) + (soltas or 0)

        elif unidade_raw in ("rolo", "rolos") and item.unidades_por_embalagem:

            # Para ROLO usando campo unidade (legacy) com unidades_por_embalagem configurado

            total_metros = (saldo_total_units or 0) * (item.unidades_por_embalagem or 0)

        elif unidade_raw in ("metro", "metros", "m"):

            total_metros = saldo_total_units



        # Calcular totais internos para PACOTE e CAIXA

        total_interno_unidades = None

        if tipo_emb in ("pacote", "caixa") and item.unidades_por_embalagem:

            total_interno_unidades = (embalagens or 0) * (item.unidades_por_embalagem or 0) + (soltas or 0)

        elif unidade_raw in ("pacote", "pacotes", "caixa", "caixas") and item.unidades_por_embalagem:

            # Para PACOTE/CAIXA usando campo unidade (legacy) com unidades_por_embalagem configurado

            total_interno_unidades = (saldo_total_units or 0) * (item.unidades_por_embalagem or 0)



        if total_kg is not None:

            lines.append(f"{prefix}⚖️ Saldo total em KG: {_fmt_amount(total_kg)}Kg")

        if total_litros is not None:

            lines.append(f"{prefix}💧 Saldo total em Litros: {_fmt_amount(total_litros)}L")

        if total_metros is not None:

            lines.append(f"{prefix}📏 Saldo total em Metros: {_fmt_amount(total_metros)}m")

        if total_interno_unidades is not None:

            nome_tipo = "Caixas" if tipo_emb == "caixa" or unidade_raw in ("caixa", "caixas") else "Pacotes"

            lines.append(f"{prefix}📦 Saldo interno total ({nome_tipo}): {total_interno_unidades:.2f} unidades")



        return "\n".join(lines)



    @staticmethod
    def format_withdrawal_message_user(
        saida: Saida,
        usuario: Usuario,
        item: Item,
        *,
        balance_before: float | None = None,
        balance_after: float | None = None,
        balance_unit: str | None = None,
    ) -> str:
        """Formata mensagem de retirada para o funcionário - Modelo 3: Ficha Técnica."""
        categoria = (item.categoria or "Geral").strip() or "Geral"
        local = (saida.local_servico or "NÃO INFORMADO").strip() or "NÃO INFORMADO"
        data_fmt = TimeService.format_local(saida.data_saida)
        quantidade_fmt = TelegramService._format_saida_quantidade(saida, item)

        emoji_map = {
            "ferramentas": "🔧",
            "material elétrico": "⚡",
            "material eletrico": "⚡",
            "material hidráulico": "🚰",
            "material hidraulico": "🚰",
            "material piscina": "🏊",
            "equipamento": "⚙️",
            "liquido": "💧",
            "líquido": "💧",
        }
        emoji = emoji_map.get(categoria.lower(), "📦")
        
        # Determinar se é ferramenta ou material
        is_ferramenta = "ferrament" in categoria.lower()
        tipo_item = "🔧 FERRAMENTA" if is_ferramenta else "📦 MATERIAL"

        msg = f"📤 <b>NOVA RETIRADA REGISTRADA</b>\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{tipo_item}\n"
        msg += f"{emoji} <b>{item.descricao}</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"👤 <b>VOCÊ RETIROU</b>\n"
        msg += f"   • Data/Hora: {data_fmt}\n\n"
        msg += f"📋 <b>INFORMAÇÕES</b>\n"
        msg += f"   • Categoria: {categoria}\n"
        msg += f"   • Quantidade retirada: {quantidade_fmt}\n"
        if hasattr(item, "lote") and item.lote:
            msg += f"   • Lote: {item.lote}\n"
        msg += f"   • Destino: {local}\n"
        msg += f"\n📊 <b>IMPACTO NO ESTOQUE</b>\n"

        try:
            def _fmt_amount(value: float, decimals: int = 6) -> str:
                try:
                    value_f = float(value)
                except Exception:
                    return "0"
                if abs(value_f - round(value_f)) < 1e-9:
                    return str(int(round(value_f)))
                return f"{value_f:.{decimals}f}".rstrip("0").rstrip(".")

            unidade = (balance_unit or item.unidade or "unidades")

            try:
                from ..services.embalagem_service import EmbalagemService

                has_packaging = bool(EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item))
            except Exception:
                has_packaging = False

            if balance_after is not None:
                saldo_atual = float(balance_after)
            else:
                if has_packaging:
                    saldo_atual = float(EmbalagemService.calcular_estoque_total(item) or 0)  # type: ignore[name-defined]
                else:
                    saldo_atual = float(item.get_saldo_atual() or 0)

            def _fmt_number_pt(value: float, *, decimals: int = 3) -> str:
                try:
                    value_f = float(value)
                except Exception:
                    return "0"
                if abs(value_f - round(value_f)) < 1e-9:
                    return str(int(round(value_f)))
                txt = f"{value_f:.{decimals}f}".rstrip("0").rstrip(".")
                return txt.replace(".", ",")

            def _lata_ou_balde(item: Item) -> bool:
                try:
                    if (item.tipo_embalagem_novo or "").strip().lower() in {"lata", "balde"}:
                        return True
                except Exception:
                    pass
                try:
                    if (item.unidade or "").strip().lower() in {"lata", "balde"}:
                        return True
                except Exception:
                    pass
                return False

            def _unidade_por_embalagem(saida: Saida, item: Item) -> tuple[float, str] | None:
                """Retorna (valor_por_embalagem, 'KG' ou 'L')."""
                # Prioridade 1: litros_por_embalagem do item
                try:
                    litros_value = getattr(item, "litros_por_embalagem", None)
                    if litros_value is not None and float(litros_value) > 0:
                        return (float(litros_value), "L")
                except Exception:
                    pass
                
                # Prioridade 2: quantidade_total_embalagem da saída (KG)
                for attr in ("quantidade_total_embalagem",):
                    try:
                        value = getattr(saida, attr, None)
                        if value is not None and float(value) > 0:
                            return (float(value), "KG")
                    except Exception:
                        continue
                
                # Prioridade 3: grandeza_referencia do item (KG)
                for attr in ("grandeza_referencia", "unidades_por_embalagem"):
                    try:
                        value = getattr(item, attr, None)
                        if value is not None and float(value) > 0:
                            return (float(value), "KG")
                    except Exception:
                        continue
                
                return None

            def _format_latas_mais_unidade(total_value: float, value_per_emb: float, item: Item, unit_type: str) -> str:
                if value_per_emb <= 0:
                    return f"{_fmt_number_pt(total_value, decimals=3)} {unit_type}"
                latas_int = int(total_value // value_per_emb)
                resto = float(total_value) - (latas_int * float(value_per_emb))
                if abs(resto) < 1e-9:
                    resto = 0.0

                nome_singular = item.get_nome_embalagem() if hasattr(item, "get_nome_embalagem") else "lata"
                nome_plural = item.get_nome_embalagem_plural() if hasattr(item, "get_nome_embalagem_plural") else "latas"

                if latas_int <= 0:
                    return f"{_fmt_number_pt(resto, decimals=3)} {unit_type}"
                nome_emb = nome_singular if latas_int == 1 else nome_plural
                if resto > 0:
                    return f"{latas_int} {nome_emb} + {_fmt_number_pt(resto, decimals=3)} {unit_type}"
                return f"{latas_int} {nome_emb}"

            try:
                obs_upper = (saida.observacao or "").upper()
            except Exception:
                obs_upper = ""

            unidade_lower = (unidade or "").strip().lower()
            unidade_info = _unidade_por_embalagem(saida, item)
            usa_view_fracionada = bool(
                unidade_info
                and unidade_info[0] > 0
                and _lata_ou_balde(item)
                and (
                    bool(getattr(saida, "quantidade_retirada_em_quilos", None))
                    or bool(getattr(saida, "usou_fracao", False))
                    or "UNIDADE=KG" in obs_upper
                    or "UNIDADE=L" in obs_upper
                    or unidade_lower in {"kg", "quilo", "quilos", "l", "litro", "litros"}
                )
            )

            if usa_view_fracionada and balance_before is not None and unidade_info:
                value_per_emb, unit_type = unidade_info
                
                def _to_unit(value: float) -> float:
                    if unidade_lower in {"kg", "quilo", "quilos"} and unit_type == "KG":
                        return float(value)
                    if unidade_lower in {"l", "litro", "litros"} and unit_type == "L":
                        return float(value)
                    return float(value) * float(value_per_emb)

                saldo_anterior_convertido = _to_unit(float(balance_before))
                saldo_atual_convertido = _to_unit(float(saldo_atual))

                msg += f"   • Saldo anterior: {_fmt_number_pt(saldo_anterior_convertido, decimals=3)} {unit_type}\n"
                msg += f"   • Nova disponibilidade: <b>{_format_latas_mais_unidade(saldo_atual_convertido, float(value_per_emb), item, unit_type)}</b>\n"
                if saldo_atual_convertido <= 0:
                    msg += "   • ⚠️ <b>STATUS: ESTOQUE ZERADO</b>\n"
            else:
                # Formato padrão: respeita a unidade registrada SEM conversão
                if balance_before is not None:
                    saldo_anterior = float(balance_before)
                    msg += f"   • Saldo anterior: {_fmt_amount(saldo_anterior)} {unidade}\n"
                elif not has_packaging:
                    saldo_anterior = saldo_atual + float(saida.quantidade or 0)
                    msg += f"   • Saldo anterior: {_fmt_amount(saldo_anterior)} {unidade}\n"

                msg += f"   • Nova disponibilidade: <b>{_fmt_amount(saldo_atual)} {unidade}</b>\n"
                if saldo_atual <= 0:
                    msg += "   • ⚠️ <b>STATUS: ESTOQUE ZERADO</b>\n"
                elif saldo_atual < 3:
                    msg += "   • ⚠️ STATUS: Estoque baixo\n"
        except Exception:
            pass

        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if "ferrament" in categoria.lower():
            msg += "⚠️ <i>Lembre-se de devolver ao final do expediente!</i>\n"
        msg += f"⏰ Registro em {data_fmt}\n"
        return msg


    @staticmethod
    def format_withdrawal_message_supervisor(
        saida: Saida,
        usuario: Usuario,
        item: Item,
        *,
        balance_before: float | None = None,
        balance_after: float | None = None,
        balance_unit: str | None = None,
    ) -> str:
        """Formata mensagem de retirada para supervisão - Modelo 3: Ficha Técnica."""
        categoria = (item.categoria or "Geral").strip() or "Geral"
        local = (saida.local_servico or "NÃO INFORMADO").strip() or "NÃO INFORMADO"
        data_fmt = TimeService.format_local(saida.data_saida)
        quantidade_fmt = TelegramService._format_saida_quantidade(saida, item)

        emoji_map = {
            "ferramentas": "🔧",
            "material elétrico": "⚡",
            "material eletrico": "⚡",
            "material hidráulico": "🚰",
            "material hidraulico": "🚰",
            "material piscina": "🏊",
            "equipamento": "⚙️",
            "liquido": "💧",
            "líquido": "💧",
        }
        emoji = emoji_map.get(categoria.lower(), "📦")
        
        # Determinar se é ferramenta ou material
        is_ferramenta = "ferrament" in categoria.lower()
        tipo_item = "🔧 FERRAMENTA" if is_ferramenta else "📦 MATERIAL"

        msg = f"📤 <b>NOVA RETIRADA REGISTRADA</b>\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{tipo_item}\n"
        msg += f"{emoji} <b>{item.descricao}</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += "👤 <b>RESPONSÁVEL PELA RETIRADA</b>\n"
        msg += f"   • Nome: {usuario.nome}\n"
        msg += f"   • Matrícula: {usuario.matricula}\n"
        msg += f"   • Data/Hora: {data_fmt}\n\n"
        msg += "📋 <b>INFORMAÇÕES</b>\n"
        msg += f"   • Categoria: {categoria}\n"
        msg += f"   • Quantidade retirada: {quantidade_fmt}\n"
        if hasattr(item, "lote") and item.lote:
            msg += f"   • Lote: {item.lote}\n"
        msg += f"   • Destino: {local}\n"
        msg += "\n📊 <b>IMPACTO NO ESTOQUE</b>\n"

        try:
            def _fmt_amount(value: float, decimals: int = 6) -> str:
                try:
                    value_f = float(value)
                except Exception:
                    return "0"
                if abs(value_f - round(value_f)) < 1e-9:
                    return str(int(round(value_f)))
                return f"{value_f:.{decimals}f}".rstrip("0").rstrip(".")

            unidade = (balance_unit or item.unidade or "unidades")

            try:
                from ..services.embalagem_service import EmbalagemService

                has_packaging = bool(EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item))
            except Exception:
                has_packaging = False

            if balance_after is not None:
                saldo_atual = float(balance_after)
            else:
                if has_packaging:
                    saldo_atual = float(EmbalagemService.calcular_estoque_total(item) or 0)  # type: ignore[name-defined]
                else:
                    saldo_atual = float(item.get_saldo_atual() or 0)

            def _fmt_number_pt(value: float, *, decimals: int = 3) -> str:
                try:
                    value_f = float(value)
                except Exception:
                    return "0"
                if abs(value_f - round(value_f)) < 1e-9:
                    return str(int(round(value_f)))
                txt = f"{value_f:.{decimals}f}".rstrip("0").rstrip(".")
                return txt.replace(".", ",")

            def _lata_ou_balde(item: Item) -> bool:
                try:
                    if (item.tipo_embalagem_novo or "").strip().lower() in {"lata", "balde"}:
                        return True
                except Exception:
                    pass
                try:
                    if (item.unidade or "").strip().lower() in {"lata", "balde"}:
                        return True
                except Exception:
                    pass
                return False

            def _unidade_por_embalagem(saida: Saida, item: Item) -> tuple[float, str] | None:
                """Retorna (valor_por_embalagem, 'KG' ou 'L')."""
                # Prioridade 1: litros_por_embalagem do item
                try:
                    litros_value = getattr(item, "litros_por_embalagem", None)
                    if litros_value is not None and float(litros_value) > 0:
                        return (float(litros_value), "L")
                except Exception:
                    pass
                
                # Prioridade 2: quantidade_total_embalagem da saída (KG)
                for attr in ("quantidade_total_embalagem",):
                    try:
                        value = getattr(saida, attr, None)
                        if value is not None and float(value) > 0:
                            return (float(value), "KG")
                    except Exception:
                        continue
                
                # Prioridade 3: grandeza_referencia do item (KG)
                for attr in ("grandeza_referencia", "unidades_por_embalagem"):
                    try:
                        value = getattr(item, attr, None)
                        if value is not None and float(value) > 0:
                            return (float(value), "KG")
                    except Exception:
                        continue
                
                return None

            def _format_latas_mais_unidade(total_value: float, value_per_emb: float, item: Item, unit_type: str) -> str:
                if value_per_emb <= 0:
                    return f"{_fmt_number_pt(total_value, decimals=3)} {unit_type}"
                latas_int = int(total_value // value_per_emb)
                resto = float(total_value) - (latas_int * float(value_per_emb))
                if abs(resto) < 1e-9:
                    resto = 0.0

                nome_singular = item.get_nome_embalagem() if hasattr(item, "get_nome_embalagem") else "lata"
                nome_plural = item.get_nome_embalagem_plural() if hasattr(item, "get_nome_embalagem_plural") else "latas"

                if latas_int <= 0:
                    return f"{_fmt_number_pt(resto, decimals=3)} {unit_type}"
                nome_emb = nome_singular if latas_int == 1 else nome_plural
                if resto > 0:
                    return f"{latas_int} {nome_emb} + {_fmt_number_pt(resto, decimals=3)} {unit_type}"
                return f"{latas_int} {nome_emb}"

            try:
                obs_upper = (saida.observacao or "").upper()
            except Exception:
                obs_upper = ""

            unidade_lower = (unidade or "").strip().lower()
            unidade_info = _unidade_por_embalagem(saida, item)
            usa_view_fracionada = bool(
                unidade_info
                and unidade_info[0] > 0
                and _lata_ou_balde(item)
                and (
                    bool(getattr(saida, "quantidade_retirada_em_quilos", None))
                    or bool(getattr(saida, "usou_fracao", False))
                    or "UNIDADE=KG" in obs_upper
                    or "UNIDADE=L" in obs_upper
                    or unidade_lower in {"kg", "quilo", "quilos", "l", "litro", "litros"}
                )
            )

            if usa_view_fracionada and balance_before is not None and unidade_info:
                value_per_emb, unit_type = unidade_info
                
                def _to_unit(value: float) -> float:
                    if unidade_lower in {"kg", "quilo", "quilos"} and unit_type == "KG":
                        return float(value)
                    if unidade_lower in {"l", "litro", "litros"} and unit_type == "L":
                        return float(value)
                    return float(value) * float(value_per_emb)

                saldo_anterior_convertido = _to_unit(float(balance_before))
                saldo_atual_convertido = _to_unit(float(saldo_atual))

                msg += f"   • Saldo anterior: {_fmt_number_pt(saldo_anterior_convertido, decimals=3)} {unit_type}\n"
                msg += f"   • Nova disponibilidade: <b>{_format_latas_mais_unidade(saldo_atual_convertido, float(value_per_emb), item, unit_type)}</b>\n"
                if saldo_atual_convertido <= 0:
                    msg += "   • ⚠️ <b>STATUS: ESTOQUE ZERADO</b>\n"
            else:
                # Formato padrão: respeita a unidade registrada SEM conversão
                if balance_before is not None:
                    saldo_anterior = float(balance_before)
                    msg += f"   • Saldo anterior: {_fmt_amount(saldo_anterior)} {unidade}\n"
                elif not has_packaging:
                    saldo_anterior = saldo_atual + float(saida.quantidade or 0)
                    msg += f"   • Saldo anterior: {_fmt_amount(saldo_anterior)} {unidade}\n"

                msg += f"   • Nova disponibilidade: <b>{_fmt_amount(saldo_atual)} {unidade}</b>\n"
                if saldo_atual <= 0:
                    msg += "   • ⚠️ <b>STATUS: ESTOQUE ZERADO</b>\n"
                elif saldo_atual < 3:
                    msg += "   • ⚠️ STATUS: Estoque baixo\n"
        except Exception:
            pass

        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"⏰ Registro em {data_fmt}\n"
        return msg

    @staticmethod
    def format_permanent_custody_message_user(saida: Saida, usuario: Usuario, item: Item) -> str:
        """Formata mensagem de custódia permanente para o funcionário."""
        categoria = (item.categoria or "Geral").strip() or "Geral"
        data_fmt = TimeService.format_local(saida.data_saida)
        quantidade_fmt = TelegramService._format_saida_quantidade(saida, item)

        emoji_map = {
            "ferramentas": "🔧",
            "material elétrico": "⚡",
            "material eletrico": "⚡",
            "material hidráulico": "🚰",
            "material hidraulico": "🚰",
            "material piscina": "🏊",
            "equipamento": "⚙️",
            "liquido": "💧",
            "líquido": "💧",
        }
        emoji = emoji_map.get(categoria.lower(), "📦")
        
        # Determinar se é ferramenta ou material
        is_ferramenta = "ferrament" in categoria.lower()
        tipo_item = "🔧 FERRAMENTA" if is_ferramenta else "📦 MATERIAL"

        msg = f"🔐 <b>CUSTÓDIA PERMANENTE ATRIBUÍDA</b>\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{tipo_item}\n"
        msg += f"{emoji} <b>{item.descricao}</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"👤 <b>VOCÊ ESTÁ RESPONSÁVEL POR:</b>\n"
        msg += f"   • Material: <b>{item.descricao}</b>\n"
        msg += f"   • Categoria: {categoria}\n"
        msg += f"   • Quantidade: {quantidade_fmt}\n"
        if hasattr(item, "lote") and item.lote:
            msg += f"   • Lote: {item.lote}\n"
        msg += f"   • Data de atribuição: {data_fmt}\n\n"
        msg += f"📌 <b>TIPO DE CUSTÓDIA</b>\n"
        msg += f"   • <b>PERMANENTE</b> - Este material está sob sua\n"
        msg += f"     responsabilidade por tempo indefinido.\n\n"
        msg += f"⚠️ <b>IMPORTANTE</b>\n"
        msg += f"   • Você é responsável pela conservação\n"
        msg += f"   • Mantenha em local seguro\n"
        msg += f"   • Comunique qualquer problema ou dano\n"
        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"⏰ Registro em {data_fmt}\n"
        return msg

    @staticmethod
    def format_permanent_custody_message_supervisor(saida: Saida, usuario: Usuario, item: Item) -> str:
        """Formata mensagem de custódia permanente para supervisão."""
        categoria = (item.categoria or "Geral").strip() or "Geral"
        data_fmt = TimeService.format_local(saida.data_saida)
        quantidade_fmt = TelegramService._format_saida_quantidade(saida, item)

        emoji_map = {
            "ferramentas": "🔧",
            "material elétrico": "⚡",
            "material eletrico": "⚡",
            "material hidráulico": "🚰",
            "material hidraulico": "🚰",
            "material piscina": "🏊",
            "equipamento": "⚙️",
            "liquido": "💧",
            "líquido": "💧",
        }
        emoji = emoji_map.get(categoria.lower(), "📦")
        
        # Determinar se é ferramenta ou material
        is_ferramenta = "ferrament" in categoria.lower()
        tipo_item = "🔧 FERRAMENTA" if is_ferramenta else "📦 MATERIAL"

        msg = f"🔐 <b>CUSTÓDIA PERMANENTE ATRIBUÍDA</b>\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{tipo_item}\n"
        msg += f"{emoji} <b>{item.descricao}</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += "👤 <b>RESPONSÁVEL PELA CUSTÓDIA</b>\n"
        msg += f"   • Nome: {usuario.nome}\n"
        msg += f"   • Matrícula: {usuario.matricula}\n"
        msg += f"   • Data de atribuição: {data_fmt}\n\n"
        msg += "📋 <b>INFORMAÇÕES DO MATERIAL</b>\n"
        msg += f"   • Categoria: {categoria}\n"
        msg += f"   • Quantidade: {quantidade_fmt}\n"
        if hasattr(item, "lote") and item.lote:
            msg += f"   • Lote: {item.lote}\n"
        msg += "\n"
        msg += "📌 <b>TIPO DE CUSTÓDIA</b>\n"
        msg += f"   • <b>PERMANENTE</b> - Material atribuído por tempo\n"
        msg += f"     indefinido ao funcionário.\n"
        msg += "\n📊 <b>IMPACTO NO ESTOQUE</b>\n"

        try:
            def _fmt_amount(value: float, decimals: int = 6) -> str:
                try:
                    value_f = float(value)
                except Exception:
                    return "0"
                if abs(value_f - round(value_f)) < 1e-9:
                    return str(int(round(value_f)))
                return f"{value_f:.{decimals}f}".rstrip("0").rstrip(".")
            
            def _fmt_number_pt(value: float, *, decimals: int = 3) -> str:
                try:
                    value_f = float(value)
                except Exception:
                    return "0"
                if abs(value_f - round(value_f)) < 1e-9:
                    return str(int(round(value_f)))
                txt = f"{value_f:.{decimals}f}".rstrip("0").rstrip(".")
                return txt.replace(".", ",")
            
            def _lata_ou_balde(item: Item) -> bool:
                try:
                    if (item.tipo_embalagem_novo or "").strip().lower() in {"lata", "balde"}:
                        return True
                except Exception:
                    pass
                try:
                    if (item.unidade or "").strip().lower() in {"lata", "balde"}:
                        return True
                except Exception:
                    pass
                return False
            
            def _kg_por_embalagem(item: Item) -> float | None:
                for attr in ("grandeza_referencia", "unidades_por_embalagem"):
                    try:
                        value = getattr(item, attr, None)
                        if value is not None and float(value) > 0:
                            return float(value)
                    except Exception:
                        continue
                return None
            
            def _format_latas_mais_kg(total_kg: float, kg_por_emb: float, item: Item) -> str:
                if kg_por_emb <= 0:
                    return f"{_fmt_number_pt(total_kg, decimals=3)} KG"
                latas_int = int(total_kg // kg_por_emb)
                resto_kg = float(total_kg) - (latas_int * float(kg_por_emb))
                if abs(resto_kg) < 1e-9:
                    resto_kg = 0.0

                nome_singular = item.get_nome_embalagem() if hasattr(item, "get_nome_embalagem") else "lata"
                nome_plural = item.get_nome_embalagem_plural() if hasattr(item, "get_nome_embalagem_plural") else "latas"

                if latas_int <= 0:
                    return f"{_fmt_number_pt(resto_kg, decimals=3)} KG"
                nome_emb = nome_singular if latas_int == 1 else nome_plural
                if resto_kg > 0:
                    return f"{latas_int} {nome_emb} + {_fmt_number_pt(resto_kg, decimals=3)} KG"
                return f"{latas_int} {nome_emb}"

            saldo_atual = float(item.get_saldo_atual() or 0)
            saldo_anterior = saldo_atual + float(saida.quantidade or 0)
            unidade = (item.unidade or "unidades").strip()

            msg += f"   • Saldo anterior: {_fmt_amount(saldo_anterior)} {unidade}\n"
            msg += f"   • Nova disponibilidade: <b>{_fmt_amount(saldo_atual)} {unidade}</b>\n"
            if saldo_atual <= 0:
                msg += "   • ⚠️ <b>STATUS: ESTOQUE ZERADO</b>\n"
            elif saldo_atual < 3:
                msg += "   • ⚠️ STATUS: Estoque baixo\n"
        except Exception:
            pass

        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"⏰ Registro em {data_fmt}\n"
        return msg

    @staticmethod

    def _format_fraction_info(saida: Saida, item: Item) -> str:

        """Formata bloco de detalhes de fracionamento (quando aplicável)."""

        if not bool(getattr(saida, "usou_fracao", False)):

            return ""



        numerador = getattr(saida, "fracao_numerador", None)

        denominador = getattr(saida, "fracao_denominador", None)

        total_embalagem = getattr(saida, "quantidade_total_embalagem", None)

        retirada_litros = getattr(saida, "quantidade_retirada_em_litros", None)

        retirada_quilos = getattr(saida, "quantidade_retirada_em_quilos", None)

        restante = getattr(saida, "quantidade_restante", None)



        unidade_display = item.unidade or "un"

        linhas: list[str] = []



        linhas.append("🧪 <b>Fracionado</b>")

        if numerador and denominador:

            linhas.append(f"🔢 <b>Fração:</b> {numerador}/{denominador}")

        if total_embalagem is not None:

            linhas.append(f"🧴 <b>Embalagem:</b> {float(total_embalagem):.2f} {unidade_display}")



        partes_retirada: list[str] = []

        if retirada_litros is not None:

            partes_retirada.append(f"{float(retirada_litros):.2f} L")

        if retirada_quilos is not None:

            partes_retirada.append(f"{float(retirada_quilos):.2f} kg")

        if partes_retirada:

            linhas.append(f"📌 <b>Retirada (calc):</b> {' / '.join(partes_retirada)}")



        if restante is not None:

            linhas.append(f"📉 <b>Restante estimado:</b> {float(restante):.2f} {unidade_display}")



        return "\n" + "\n".join(linhas) + "\n"



    @staticmethod

    def notify_multiple_withdrawal(saida_ids: list[int]) -> None:

        """Notifica retirada múltipla com todos os itens agrupados em uma única mensagem."""

        if not saida_ids:

            return



        try:

            config = TelegramConfig.query.first()

            if not config or not config.enabled or not config.notify_on_withdrawal:

                return



            saidas = Saida.query.filter(Saida.id_saida.in_(saida_ids)).all()

            if not saidas:

                return



            # Agrupar por usuário (caso seja sempre o mesmo)

            primeiro = saidas[0]

            usuario = Usuario.query.filter_by(matricula=primeiro.matricula).first()

            if not usuario:

                return



            # Montar mensagem agrupada

            message = TelegramService._format_multiple_withdrawal_message(usuario, saidas)

            if not message:

                return



            notified_chat_ids: set[str] = set()



            # 1) Notificar funcionário (se tiver Telegram vinculado)

            telegram_user = (

                db.session.query(TelegramUser)

                .filter_by(matricula=usuario.matricula, enabled=True)

                .first()

            )

            if telegram_user:

                chat_id_str = str(telegram_user.chat_id)

                key = f"withdrawal-multi:{'-'.join(str(s) for s in sorted(saida_ids))}:user:{chat_id_str}"

                TelegramService.enqueue_outbox_message(

                    chat_id=chat_id_str,

                    recipient_name=usuario.nome,

                    message_type="withdrawal",

                    message_text=message,

                    idempotency_key=key,

                    saida_id=saidas[0].id_saida if saidas else None,

                    commit=True,

                )

                notified_chat_ids.add(chat_id_str)



            # 2) Notificar supervisores/grupos (ou usuários privilegiados)

            if config.notify_supervisors or TelegramService._privileged_users_query().count() > 0:

                groups = db.session.query(TelegramGroup).filter_by(

                    enabled=True, receive_withdrawals=True

                ).all()



                if groups:

                    for group in groups:

                        chat_id_str = str(group.chat_id)

                        if chat_id_str in notified_chat_ids:

                            continue

                        key = f"withdrawal-multi:{'-'.join(str(s) for s in sorted(saida_ids))}:group:{chat_id_str}"

                        TelegramService.enqueue_outbox_message(

                            chat_id=chat_id_str,

                            recipient_name=f"Grupo: {group.name}",

                            message_type="withdrawal",

                            message_text=message,

                            idempotency_key=key,

                            saida_id=saidas[0].id_saida if saidas else None,

                            commit=True,

                        )

                        notified_chat_ids.add(chat_id_str)

                else:

                    # Fallback: administradores com Telegram habilitado

                    admins = TelegramService._privileged_users_query().all()

                    for adm in admins:

                        chat_id_str = str(adm.chat_id)

                        if chat_id_str in notified_chat_ids:

                            continue

                        key = f"withdrawal-multi:{'-'.join(str(s) for s in sorted(saida_ids))}:admin:{chat_id_str}"

                        TelegramService.enqueue_outbox_message(

                            chat_id=chat_id_str,

                            recipient_name=f"Admin: {getattr(adm.usuario, 'nome', adm.matricula)}",

                            message_type="withdrawal",

                            message_text=message,

                            idempotency_key=key,

                            saida_id=saidas[0].id_saida if saidas else None,

                            commit=True,

                        )

                        notified_chat_ids.add(chat_id_str)



        except Exception as e:

            logger.exception(f"Erro ao notificar retirada múltipla: {e}")



    @staticmethod

    def _format_multiple_withdrawal_message(usuario: Usuario, saidas: list[Saida]) -> str:

        """Formata mensagem de retirada múltipla com todos os itens agrupados."""

        if not saidas:

            return ""



        from ..models import Item



        # Cabeçalho

        data_fmt = TimeService.format_local(saidas[0].data_saida)

        local = (saidas[0].local_servico or "NÃO INFORMADO").strip() or "NÃO INFORMADO"

        

        msg = f"⚠️ <b>RETIRADA MÚLTIPLA DE MATERIAL</b>\n\n"

        msg += f"👤 <b>Funcionário:</b> {usuario.nome} (Mat. {usuario.matricula})\n"

        msg += f"📦 <b>Total de itens:</b> {len(saidas)}\n"

        msg += f"📍 <b>Local/Uso:</b> {local}\n"

        msg += f"⏰ <b>Horário:</b> {data_fmt}\n\n"

        msg += f"━━━━━━━━━━━━━━━━━\n\n"

        def _fmt_amount(value: float, decimals: int = 6) -> str:
            try:
                value_f = float(value)
            except Exception:
                return "0"
            if abs(value_f - round(value_f)) < 1e-9:
                return str(int(round(value_f)))
            return f"{value_f:.{decimals}f}".rstrip("0").rstrip(".")



        # Listar cada item de forma compacta

        for idx, saida in enumerate(saidas, 1):

            item = Item.query.filter_by(codigo_item=saida.codigo_item).first()

            if not item:

                continue



            categoria = (item.categoria or "Geral").strip() or "Geral"

            

            # Emoji baseado na categoria

            emoji_map = {

                "ferramentas": "🔧",

                "material elétrico": "⚡",

                "material eletrico": "âš¡",

                "material hidráulico": "🚰",

                "material hidraulico": "🚰",

                "material piscina": "🏊",

                "liquido": "💧",

                "líquido": "💧",

            }

            emoji = emoji_map.get(categoria.lower(), "📦")



            msg += f"<b>{idx}.</b> {emoji} <b>{item.descricao}</b>\n"

            msg += f"   🏷️ {categoria}\n"

            msg += f"   📊 Qtd: <b>{TelegramService._format_saida_quantidade(saida, item)}</b>\n"

            

            # Saldo restante

            try:

                from galint_flask.services.embalagem_service import EmbalagemService

                if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):

                    estoque_str = EmbalagemService.formatar_estoque(item)

                    msg += f"   💼 Saldo: {estoque_str}\n"

                else:

                    saldo_atual = float(item.get_saldo_atual() or 0)

                    msg += f"   💼 Saldo: {_fmt_amount(saldo_atual)} {item.unidade or 'un'}\n"

            except Exception:

                try:

                    saldo_atual = float(item.get_saldo_atual() or 0)

                    msg += f"   💼 Saldo: {_fmt_amount(saldo_atual)} {item.unidade or 'un'}\n"

                except Exception:

                    pass



            totals = TelegramService._format_balance_totals(item)

            if totals:

                msg += totals + "\n"



            if idx < len(saidas):

                msg += "\n"



        return msg



    @staticmethod

    def notify_multiple_entry(entrada_ids: list[int], is_devolucao: bool = False) -> None:

        """Notifica entrada múltipla com todos os itens agrupados em uma única mensagem."""

        if not entrada_ids:

            return



        try:

            if not TelegramService.is_enabled():

                return



            entradas = Entrada.query.filter(Entrada.id_entrada.in_(entrada_ids)).all()

            if not entradas:

                return



            # Montar mensagem agrupada

            message = TelegramService._format_multiple_entry_message(entradas, is_devolucao)

            if not message:

                return



            # Notificar apenas administradores

            try:

                admins = TelegramService._privileged_users_query().all()

            except Exception:

                admins = []



            for admin in admins:

                try:

                    tipo = "devolucao" if is_devolucao else "entrada"

                    key = f"{tipo}-multi:{'-'.join(str(e) for e in sorted(entrada_ids))}:admin:{admin.chat_id}"

                    TelegramService.enqueue_outbox_message(

                        chat_id=str(admin.chat_id),

                        recipient_name=admin.usuario.nome if getattr(admin, 'usuario', None) else None,

                        message_type=tipo,

                        message_text=message,

                        idempotency_key=key,

                        entrada_id=entradas[0].id_entrada if entradas else None,

                        commit=True,

                    )

                except Exception:

                    pass



        except Exception as e:

            logger.exception(f"Erro ao notificar entrada múltipla: {e}")



    @staticmethod

    def _format_multiple_entry_message(entradas: list[Entrada], is_devolucao: bool = False, retirado_por_map: dict[int, Usuario] = None) -> str:

        """Formata mensagem de entrada/devolução múltipla com todos os itens agrupados."""

        if not entradas:

            return ""



        from ..models import Item



        # Cabeçalho

        data_fmt = TimeService.format_local(entradas[0].data_entrada)

        devolvedor = entradas[0].usuario

        

        if is_devolucao:

            msg = f"✅ <b>DEVOLUÇÃO MÚLTIPLA DE MATERIAL</b>\n\n"

            # Tentar pegar quem retirou (assumindo que todas as entradas são do mesmo contexto)

            if retirado_por_map:

                primeiro_retirado = next(iter(retirado_por_map.values()), None)

                if primeiro_retirado:

                    msg += f"📤 <b>Retirado por:</b> {primeiro_retirado.nome} (Mat. {primeiro_retirado.matricula})\n"

            if devolvedor:

                msg += f"📥 <b>Devolvido por:</b> {devolvedor.nome} (Mat. {devolvedor.matricula})\n"

        else:

            msg = f"📥 <b>ENTRADA MÚLTIPLA DE MATERIAL</b>\n\n"

        

        msg += f"📦 <b>Total de itens:</b> {len(entradas)}\n"

        msg += f"⏰ <b>Horário:</b> {data_fmt}\n\n"

        msg += f"━━━━━━━━━━━━━━━━━\n\n"



        # Listar cada item

        for idx, entrada in enumerate(entradas, 1):

            item = Item.query.filter_by(codigo_item=entrada.codigo_item).first()

            if not item:

                continue



            categoria = (item.categoria or "Geral").strip() or "Geral"

            

            # Emoji baseado na categoria

            emoji_map = {

                "ferramentas": "🔧",

                "material elétrico": "⚡",

                "material eletrico": "âš¡",

                "material hidráulico": "🚰",

                "material hidraulico": "🚰",

                "material piscina": "🏊",

                "liquido": "💧",

                "líquido": "💧",

            }

            emoji = emoji_map.get(categoria.lower(), "📦")



            msg += f"<b>{idx}.</b> {emoji} <b>{item.descricao}</b>\n"

            msg += f"   🏷️ {categoria}\n"

            

            # Para devolução múltipla, não usar o símbolo + (acréscimo)

            if is_devolucao:

                msg += f"   📊 Qtd Devolvida: <b>{entrada.quantidade}</b> {item.unidade or 'un'}\n"

            else:

                msg += f"   📊 Qtd: <b>+{entrada.quantidade}</b> {item.unidade or 'un'}\n"

            

            # Saldo após entrada/devolução

            try:

                from galint_flask.services.embalagem_service import EmbalagemService

                if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):

                    estoque_str = EmbalagemService.formatar_estoque(item)

                    if is_devolucao:

                        msg += f"   ✅ Estoque atualizado: {estoque_str}\n"

                    else:

                        msg += f"   💼 Novo Saldo: {estoque_str}\n"

                else:

                    saldo_atual = int(item.get_saldo_atual() or 0)

                    if is_devolucao:

                        msg += f"   ✅ Estoque atualizado: {saldo_atual} {item.unidade or 'un'}\n"

                    else:

                        msg += f"   💼 Novo Saldo: {saldo_atual} {item.unidade or 'un'}\n"

            except Exception:

                try:

                    saldo_atual = int(item.get_saldo_atual() or 0)

                    if is_devolucao:

                        msg += f"   ✅ Estoque atualizado: {saldo_atual} {item.unidade or 'un'}\n"

                    else:

                        msg += f"   💼 Novo Saldo: {saldo_atual} {item.unidade or 'un'}\n"

                except Exception:

                    pass



            totals = TelegramService._format_balance_totals(item)

            if totals:

                msg += totals + "\n"



            if idx < len(entradas):

                msg += "\n"



        return msg



    @staticmethod

    def notify_multiple_inventory_event(event_ids: list[int]) -> None:

        """Notifica múltiplos ajustes de inventário agrupados em uma única mensagem."""

        if not event_ids:

            return



        try:

            if not TelegramService.is_enabled():

                return



            eventos = InventarioEvento.query.filter(InventarioEvento.id_evento.in_(event_ids)).all()

            if not eventos:

                return



            # Montar mensagem agrupada

            message = TelegramService._format_multiple_inventory_event_message(eventos)

            if not message:

                return



            # Notificar apenas administradores

            try:

                admins = TelegramService._privileged_users_query().all()

            except Exception:

                admins = []



            for admin in admins:

                try:

                    key = f"inv-event-multi:{'-'.join(str(e) for e in sorted(event_ids))}:admin:{admin.chat_id}"

                    TelegramService.enqueue_outbox_message(

                        chat_id=str(admin.chat_id),

                        recipient_name=admin.usuario.nome if getattr(admin, 'usuario', None) else None,

                        message_type="inventory_adjustment",

                        message_text=message,

                        idempotency_key=key,

                        inventario_evento_id=eventos[0].id_evento if eventos else None,

                        commit=True,

                    )

                except Exception:

                    pass



        except Exception as e:

            logger.exception(f"Erro ao notificar ajuste de inventário múltiplo: {e}")



    @staticmethod

    def _format_multiple_inventory_event_message(eventos: list[InventarioEvento]) -> str:

        """Formata mensagem de ajustes de inventário múltiplos agrupados."""

        if not eventos:

            return ""



        from ..models import Item



        # Cabeçalho

        data_fmt = TimeService.format_local(eventos[0].data_evento)

        

        msg = f"🔄 <b>AJUSTE MÚLTIPLO DE INVENTÁRIO</b>\n\n"

        msg += f"📦 <b>Total de ajustes:</b> {len(eventos)}\n"

        msg += f"⏰ <b>Horário:</b> {data_fmt}\n\n"

        msg += f"━━━━━━━━━━━━━━━━━\n\n"



        # Listar cada ajuste

        for idx, evento in enumerate(eventos, 1):

            item = Item.query.filter_by(codigo_item=evento.codigo_item).first() if evento.codigo_item else None

            

            if item:

                categoria = (item.categoria or "Geral").strip() or "Geral"

                descricao = item.descricao

                unidade = item.unidade or 'un'

            else:

                categoria = "Geral"

                descricao = evento.codigo_item or "Item desconhecido"

                unidade = 'un'

            

            # Emoji baseado na categoria

            emoji_map = {

                "ferramentas": "🔧",

                "material elétrico": "⚡",

                "material eletrico": "âš¡",

                "material hidráulico": "🚰",

                "material hidraulico": "🚰",

                "material piscina": "🏊",

                "liquido": "💧",

                "líquido": "💧",

            }

            emoji = emoji_map.get(categoria.lower(), "📦")



            quantidade = evento.quantidade

            sinal = "+" if quantidade > 0 else ""



            msg += f"<b>{idx}.</b> {emoji} <b>{descricao}</b>\n"

            msg += f"   🏷️ {categoria}\n"

            msg += f"   📊 Ajuste: <b>{sinal}{quantidade}</b> {unidade}\n"

            msg += f"   📝 Tipo: {evento.tipo or 'Ajuste'}\n"

            

            if evento.descricao:

                msg += f"   💬 Obs: {evento.descricao[:50]}\n"

            

            # Saldo após ajuste

            if item:

                try:

                    from galint_flask.services.embalagem_service import EmbalagemService

                    if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):

                        estoque_str = EmbalagemService.formatar_estoque(item)

                        msg += f"   💼 Novo Saldo: {estoque_str}\n"

                    else:

                        saldo_atual = int(item.get_saldo_atual() or 0)

                        msg += f"   💼 Novo Saldo: {saldo_atual} {unidade}\n"

                except Exception:

                    try:

                        saldo_atual = int(item.get_saldo_atual() or 0)

                        msg += f"   💼 Novo Saldo: {saldo_atual} {unidade}\n"

                    except Exception:

                        pass



                totals = TelegramService._format_balance_totals(item)

                if totals:

                    msg += totals + "\n"



            if idx < len(eventos):

                msg += "\n"



        return msg



    @staticmethod

    def format_alert_message(usuario: Usuario, ferramentas: list[dict[str, Any]]) -> str:

        """Formata mensagem de alerta agendado."""

        if not ferramentas:

            return ""



        msg = f"🔔 <b>Lembrete - Devolução de Ferramentas</b>\n\n"

        msg += f"Olá <b>{usuario.nome}</b>, você possui {len(ferramentas)} ferramenta(s) não devolvida(s):\n\n"



        for idx, ferramenta in enumerate(ferramentas, 1):

            codigo = ferramenta.get("codigo", "N/A")

            descricao = ferramenta.get("descricao", "N/A")

            quantidade = ferramenta.get("quantidade", 0)

            unidade = ferramenta.get("unidade", "un")

            local = ferramenta.get("local_servico", "Não informado")

            data_retirada = ferramenta.get("data_saida")

            data_fmt = TimeService.format_local(data_retirada) if data_retirada else "N/A"



            msg += f"📌 <b>{codigo}</b> ({descricao}) - {quantidade} {unidade}\n"

            msg += f"   Serviço: {local}\n"

            msg += f"   Retirado em: {data_fmt}\n\n"



        msg += "⚠️ <i>Lembre-se de devolver ao final do expediente!</i>"

        return msg





    # ---- Polling background runner utilities ----

    _polling_thread: Optional[threading.Thread] = None

    _polling_stop_event: Optional[threading.Event] = None



    @staticmethod

    def _load_last_update_id_from_file(offset_file: Path) -> int:

        try:

            if not offset_file.exists():

                return 0

            content = offset_file.read_text(encoding="utf-8").strip()

            return int(content) if content else 0

        except Exception:

            return 0



    @staticmethod

    def _save_last_update_id_to_file(offset_file: Path, last_update_id: int) -> None:

        try:

            offset_file.parent.mkdir(parents=True, exist_ok=True)

            offset_file.write_text(str(int(last_update_id)), encoding="utf-8")

        except Exception:

            pass



    @staticmethod

    def start_polling_background(

        app,

        keep_webhook: bool = False,

        offset_file: str | Path | None = None,

        poll_timeout: int = 25,

    ) -> None:

        """Inicia um thread em background que faz long-polling do Telegram.



        - `keep_webhook`: se False tenta remover webhook ao iniciar.

        - `offset_file`: caminho para persistir last_update_id.

        """

        if TelegramService._polling_thread and TelegramService._polling_thread.is_alive():

            return



        stop_event = threading.Event()

        TelegramService._polling_stop_event = stop_event



        offset_path = Path(offset_file) if offset_file else Path("instance") / "telegram_polling_offset.txt"



        def _worker():

            # Import process_message lazily to avoid circular imports on module load

            try:

                from scripts.telegram_polling import process_message

            except Exception:

                process_message = None



            with app.app_context():

                if not keep_webhook:

                    try:

                        TelegramService.delete_webhook()

                    except Exception:

                        pass



                last_update_id = TelegramService._load_last_update_id_from_file(offset_path)



                backoff = 2

                while not stop_event.is_set():

                    try:

                        result = TelegramService.get_updates(offset=last_update_id + 1, timeout=poll_timeout)

                        if not result.get("success"):

                            err = result.get("error") or "Erro desconhecido"

                            # detect conflict and continue

                            if "Conflict" in str(err):

                                # webhook ativo em outro lugar

                                time.sleep(5)

                                continue

                            time.sleep(backoff)

                            backoff = min(backoff * 2, 30)

                            continue



                        updates = result.get("updates") or []

                        if updates:

                            for update in updates:

                                update_id = update.get("update_id") or 0

                                

                                # Handle Message

                                message = update.get("message")

                                if message:

                                    if process_message:

                                        try:

                                            process_message(message)

                                        except Exception:

                                            pass

                                

                                # Handle Callback Query (fixes buttons not working)

                                callback = update.get("callback_query")

                                if callback:

                                    try:

                                        TelegramService.handle_callback_query(callback)

                                    except Exception:

                                        pass



                                last_update_id = max(last_update_id, update_id)

                                TelegramService._save_last_update_id_to_file(offset_path, last_update_id)

                            backoff = 2

                        else:

                            backoff = 2

                            time.sleep(1)



                    except Exception:

                        time.sleep(5)



        t = threading.Thread(target=_worker, daemon=True, name="galint-telegram-polling")

        TelegramService._polling_thread = t

        t.start()



    @staticmethod

    def stop_polling_background() -> None:

        """Sinaliza o thread de polling para encerrar."""

        if TelegramService._polling_stop_event:

            TelegramService._polling_stop_event.set()

        if TelegramService._polling_thread:

            try:

                TelegramService._polling_thread.join(timeout=5)

            except Exception:

                pass



    # Controle de agrupamento de saídas para notificação múltipla

    _pending_withdrawals: dict[str, list[int]] = {}

    _last_withdrawal_time: dict[str, datetime] = {}

    

    @staticmethod

    def _get_session_key() -> str:

        """Gera chave única para sessão baseada no usuário atual."""

        from flask import session

        from flask_login import current_user

        

        # Usar ID da sessão Flask + matrícula do usuário

        user_id = getattr(current_user, 'matricula', None) or getattr(current_user, 'id', 'anonymous')

        session_id = session.get('_id', id(session))

        return f"{user_id}:{session_id}"

    

    @staticmethod

    def _should_group_withdrawals(session_key: str) -> bool:

        """Verifica se deve agrupar saídas (se houve saída recente na mesma sessão)."""

        from datetime import timedelta

        

        last_time = TelegramService._last_withdrawal_time.get(session_key)

        if not last_time:

            return False

        

        # Agrupar se última saída foi há menos de 60 segundos

        time_window = timedelta(seconds=60)

        return (datetime.utcnow() - last_time) < time_window

    

    @staticmethod

    def _add_pending_withdrawal(session_key: str, saida_id: int) -> None:

        """Adiciona saída à lista de pendentes para agrupamento."""

        if session_key not in TelegramService._pending_withdrawals:

            TelegramService._pending_withdrawals[session_key] = []

        TelegramService._pending_withdrawals[session_key].append(saida_id)

        TelegramService._last_withdrawal_time[session_key] = datetime.utcnow()

    

    @staticmethod

    def _get_and_clear_pending(session_key: str) -> list[int]:

        """Obtém e limpa lista de saídas pendentes."""

        saidas = TelegramService._pending_withdrawals.get(session_key, [])

        if session_key in TelegramService._pending_withdrawals:

            del TelegramService._pending_withdrawals[session_key]

        if session_key in TelegramService._last_withdrawal_time:

            del TelegramService._last_withdrawal_time[session_key]

        return saidas

    

    @staticmethod

    def notify_withdrawal(
        saida_id: int,
        force_single: bool = False,
        *,
        balance_before: float | None = None,
        balance_after: float | None = None,
        balance_unit: str | None = None,
    ) -> dict[str, Any]:

        """Envia notificações para retirada de ferramenta.

        

        Args:

            saida_id: ID da saída registrada

            force_single: Se True, força notificação individual (ignora agrupamento)

        """
        logger.debug(f"[notify_withdrawal] Chamada recebida para saida_id={saida_id}, force_single={force_single}")
        
        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não está habilitado"}



        config = TelegramService.get_config()

        if not config or not config.notify_on_withdrawal:

            return {"success": False, "error": "Notificações de retirada desabilitadas"}



        # Buscar dados da saída

        saida = db.session.get(Saida, saida_id)

        if not saida or not saida.item or not saida.usuario:

            return {"success": False, "error": "Saída não encontrada ou incompleta"}

        

        # AGRUPAMENTO: Detectar múltiplas saídas em sequência

        if not force_single:

            try:

                session_key = TelegramService._get_session_key()

                

                # Verificar se deve agrupar (já houve saída recente)

                if TelegramService._should_group_withdrawals(session_key):

                    # Adicionar à lista de pendentes e NÃO notificar ainda

                    TelegramService._add_pending_withdrawal(session_key, saida_id)

                    return {

                        "success": True,

                        "grouped": True,

                        "pending_count": len(TelegramService._pending_withdrawals.get(session_key, [])),

                        "message": "Saída adicionada ao grupo pendente"

                    }

                else:

                    # Primeira saída da sequência - adicionar aos pendentes

                    TelegramService._add_pending_withdrawal(session_key, saida_id)

                    return {

                        "success": True,

                        "grouped": False,

                        "message": "Primeira saída registrada - aguardando possíveis adições"

                    }

            except Exception as e:

                # Se falhar agrupamento, continuar com notificação individual

                logger.warning(f"Falha no agrupamento de saídas: {e}")

                pass



        # Notificar QUALQUER categoria de material (via Outbox)

        results = {"queued": [], "failed": [], "skipped": []}



        # 1. Notificar funcionário (se tiver Telegram vinculado E preferências permitirem)

        telegram_user = db.session.query(TelegramUser).filter_by(

            matricula=saida.matricula, enabled=True

        ).first()



        if telegram_user:

            # Verificar preferências de notificação

            if TelegramService._should_notify_user(telegram_user, saida.item.categoria, is_return=False):

                message_text = TelegramService.format_withdrawal_message_user(

                    saida,
                    saida.usuario,
                    saida.item,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    balance_unit=balance_unit,

                )

                key = f"withdrawal:{saida_id}:user:{telegram_user.chat_id}"
                logger.debug(f"[notify_withdrawal] Enfileirando para usuário: key={key}")
                q = TelegramService.enqueue_outbox_message(

                    chat_id=str(telegram_user.chat_id),

                    recipient_name=saida.usuario.nome,

                    message_type="withdrawal",

                    message_text=message_text,

                    idempotency_key=key,

                    saida_id=saida_id,

                    commit=True,

                )

                if q.get("success"):
                    if q.get("deduped"):
                        logger.info(f"[notify_withdrawal] Mensagem dedupliacada para user chat_id={telegram_user.chat_id}, saida_id={saida_id}")
                        results["skipped"].append(f"Funcionário {saida.usuario.nome} (já enviado)")
                    else:
                        results["queued"].append(f"Funcionário: {saida.usuario.nome}")

                else:

                    results["failed"].append(f"Funcionário: {q.get('error')}")

            else:

                results["skipped"].append(f"Funcionário {saida.usuario.nome} (preferências)")



        # 2. Notificar grupos de supervisão (ou fallback para usuários privilegiados)

        if config.notify_supervisors or TelegramService._privileged_users_query().count() > 0:

            groups = db.session.query(TelegramGroup).filter_by(

                enabled=True, receive_withdrawals=True

            ).all()



            message_text = TelegramService.format_withdrawal_message_supervisor(

                saida,
                saida.usuario,
                saida.item,
                balance_before=balance_before,
                balance_after=balance_after,
                balance_unit=balance_unit,

            )



            notified_chat_ids: set[str] = set()

            if telegram_user:

                notified_chat_ids.add(str(telegram_user.chat_id))



            if groups:

                for group in groups:

                    key = f"withdrawal:{saida_id}:group:{group.chat_id}"
                    logger.debug(f"[notify_withdrawal] Enfileirando para grupo: key={key}")

                    q = TelegramService.enqueue_outbox_message(

                        chat_id=str(group.chat_id),

                        recipient_name=f"Grupo: {group.name}",

                        message_type="withdrawal",

                        message_text=message_text,

                        idempotency_key=key,

                        saida_id=saida_id,

                        commit=True,

                    )

                    if q.get("success"):
                        if q.get("deduped"):
                            logger.info(f"[notify_withdrawal] Mensagem deduplicada para grupo {group.name}, saida_id={saida_id}")
                            results["skipped"].append(f"Grupo {group.name} (já enviado)")
                        else:
                            results["queued"].append(f"Grupo: {group.name}")

                        notified_chat_ids.add(str(group.chat_id))

                    else:

                        results["failed"].append(f"Grupo {group.name}: {q.get('error')}")

            else:

                # Fallback: se não houver grupo configurado, notificar administradores vinculados.

                admins = TelegramService._privileged_users_query().all()



                for adm in admins:

                    if str(adm.chat_id) in notified_chat_ids:

                        continue

                    key = f"withdrawal:{saida_id}:admin:{adm.chat_id}"
                    logger.debug(f"[notify_withdrawal] Enfileirando para admin: key={key}")

                    q = TelegramService.enqueue_outbox_message(

                        chat_id=str(adm.chat_id),

                        recipient_name=f"Admin: {getattr(adm.usuario, 'nome', adm.matricula)}",

                        message_type="withdrawal",

                        message_text=message_text,

                        idempotency_key=key,

                        saida_id=saida_id,

                        commit=True,

                    )

                    if q.get("success"):
                        if q.get("deduped"):
                            logger.info(f"[notify_withdrawal] Mensagem deduplicada para admin {adm.matricula}, saida_id={saida_id}")
                            results["skipped"].append(f"Admin {adm.matricula} (já enviado)")
                        else:
                            results["queued"].append("Admin")

                        notified_chat_ids.add(str(adm.chat_id))

                    else:

                        results["failed"].append(f"Admin {adm.matricula}: {q.get('error')}")



        return {

            "success": True,

            "sent": results["queued"],

            "failed": results["failed"],

            "total_sent": len(results["queued"]),

            "total_failed": len(results["failed"]),

            "queued": results["queued"],

        }



    @staticmethod
    def notify_permanent_custody(saida_id: int) -> dict[str, Any]:
        """Envia notificações para custódia permanente de ferramenta.
        
        Args:
            saida_id: ID da saída registrada com tipo_custodia='permanente'
        """
        logger.debug(f"[notify_permanent_custody] Chamada recebida para saida_id={saida_id}")
        
        if not TelegramService.is_enabled():
            return {"success": False, "error": "Telegram não está habilitado"}

        # Buscar dados da saída
        saida = db.session.get(Saida, saida_id)
        if not saida or not saida.item or not saida.usuario:
            return {"success": False, "error": "Saída não encontrada ou incompleta"}

        results = {"queued": [], "failed": [], "skipped": []}

        # 1. Notificar funcionário (se tiver Telegram vinculado)
        telegram_user = db.session.query(TelegramUser).filter_by(
            matricula=saida.matricula, enabled=True
        ).first()

        if telegram_user:
            # Verificar preferências de notificação
            if TelegramService._should_notify_user(telegram_user, saida.item.categoria, is_return=False):
                message_text = TelegramService.format_permanent_custody_message_user(
                    saida, saida.usuario, saida.item
                )
                key = f"permanent_custody:{saida_id}:user:{telegram_user.chat_id}"
                logger.debug(f"[notify_permanent_custody] Enfileirando para usuário: key={key}")
                q = TelegramService.enqueue_outbox_message(
                    chat_id=str(telegram_user.chat_id),
                    recipient_name=saida.usuario.nome,
                    message_type="permanent_custody",
                    message_text=message_text,
                    idempotency_key=key,
                    saida_id=saida_id,
                    commit=True,
                )
                if q.get("success"):
                    if q.get("deduped"):
                        logger.info(f"[notify_permanent_custody] Mensagem deduplicada para user chat_id={telegram_user.chat_id}, saida_id={saida_id}")
                        results["skipped"].append(f"Funcionário {saida.usuario.nome} (já enviado)")
                    else:
                        results["queued"].append(f"Funcionário: {saida.usuario.nome}")
                else:
                    results["failed"].append(f"Funcionário: {q.get('error')}")
            else:
                results["skipped"].append(f"Funcionário {saida.usuario.nome} (preferências)")

        # 2. Notificar grupos de supervisão (ou fallback para usuários privilegiados)
        config = TelegramService.get_config()
        if config and (config.notify_supervisors or TelegramService._privileged_users_query().count() > 0):
            groups = db.session.query(TelegramGroup).filter_by(
                enabled=True, receive_withdrawals=True
            ).all()

            message_text = TelegramService.format_permanent_custody_message_supervisor(
                saida, saida.usuario, saida.item
            )

            notified_chat_ids: set[str] = set()
            if telegram_user:
                notified_chat_ids.add(str(telegram_user.chat_id))

            if groups:
                for group in groups:
                    key = f"permanent_custody:{saida_id}:group:{group.chat_id}"
                    logger.debug(f"[notify_permanent_custody] Enfileirando para grupo: key={key}")
                    q = TelegramService.enqueue_outbox_message(
                        chat_id=str(group.chat_id),
                        recipient_name=f"Grupo: {group.name}",
                        message_type="permanent_custody",
                        message_text=message_text,
                        idempotency_key=key,
                        saida_id=saida_id,
                        commit=True,
                    )
                    if q.get("success"):
                        if q.get("deduped"):
                            logger.info(f"[notify_permanent_custody] Mensagem deduplicada para grupo {group.name}, saida_id={saida_id}")
                            results["skipped"].append(f"Grupo {group.name} (já enviado)")
                        else:
                            results["queued"].append(f"Grupo: {group.name}")
                        notified_chat_ids.add(str(group.chat_id))
                    else:
                        results["failed"].append(f"Grupo {group.name}: {q.get('error')}")
            else:
                # Fallback: se não houver grupo configurado, notificar administradores vinculados
                admins = TelegramService._privileged_users_query().all()
                for adm in admins:
                    if str(adm.chat_id) in notified_chat_ids:
                        continue
                    key = f"permanent_custody:{saida_id}:admin:{adm.chat_id}"
                    logger.debug(f"[notify_permanent_custody] Enfileirando para admin: key={key}")
                    q = TelegramService.enqueue_outbox_message(
                        chat_id=str(adm.chat_id),
                        recipient_name=f"Admin: {getattr(adm.usuario, 'nome', adm.matricula)}",
                        message_type="permanent_custody",
                        message_text=message_text,
                        idempotency_key=key,
                        saida_id=saida_id,
                        commit=True,
                    )
                    if q.get("success"):
                        if q.get("deduped"):
                            logger.info(f"[notify_permanent_custody] Mensagem deduplicada para admin {adm.matricula}, saida_id={saida_id}")
                            results["skipped"].append(f"Admin {adm.matricula} (já enviado)")
                        else:
                            results["queued"].append("Admin")
                        notified_chat_ids.add(str(adm.chat_id))
                    else:
                        results["failed"].append(f"Admin {adm.matricula}: {q.get('error')}")

        return {
            "success": True,
            "sent": results["queued"],
            "failed": results["failed"],
            "total_sent": len(results["queued"]),
            "total_failed": len(results["failed"]),
            "queued": results["queued"],
        }



    @staticmethod

    def flush_pending_withdrawals(session_key: str | None = None) -> dict[str, Any]:

        """Finaliza e envia notificações para saídas agrupadas pendentes.

        

        Args:

            session_key: Chave da sessão (se None, usa sessão atual)

        

        Returns:

            dict com resultado da operação

        """

        if session_key is None:

            try:

                session_key = TelegramService._get_session_key()

            except Exception:

                return {"success": False, "error": "Não foi possível obter chave da sessão"}

        

        # Obter e limpar pendentes

        pending_ids = TelegramService._get_and_clear_pending(session_key)

        

        if not pending_ids:

            return {"success": True, "message": "Nenhuma saída pendente"}

        

        # Se houver apenas 1 saída, enviar notificação individual

        if len(pending_ids) == 1:

            return TelegramService.notify_withdrawal(pending_ids[0], force_single=True)

        

        # Se houver 2 ou mais, enviar notificação múltipla

        TelegramService.notify_multiple_withdrawal(pending_ids)

        return {

            "success": True,

            "sent_as_multiple": True,

            "count": len(pending_ids),

            "saida_ids": pending_ids

        }

    

    @staticmethod

    def format_new_entry_message(entrada, is_devolucao: bool = False, retirado_por: Usuario | None = None) -> str:

        """Formata mensagem de nova entrada para administradores."""

        item = entrada.item

        devolvedor = entrada.usuario

        descricao = item.descricao if item else "Item desconhecido"

        categoria = (item.categoria or "Geral").strip() if item else "Geral"

        quantidade = entrada.quantidade

        unidade = item.unidade or 'un' if item else 'un'

        data_fmt = TimeService.format_local(getattr(entrada, "data_entrada", None))



        # Emoji baseado na categoria

        emoji_map = {

            "ferramentas": "🔧",

            "material elétrico": "⚡",

            "material eletrico": "âš¡",

            "material hidráulico": "🚰",

            "material hidraulico": "🚰",

            "material piscina": "🏊",

            "liquido": "💧",

            "líquido": "💧",

        }

        emoji = emoji_map.get(categoria.lower(), "📦")



        if is_devolucao:

            # Título dinâmico baseado na categoria

            categoria_titulo = categoria.upper()

            if "FERRAMENTA" in categoria_titulo:

                categoria_titulo = "FERRAMENTA"

            titulo = f"DEVOLUÇÃO DE {categoria_titulo}"

            

            msg = f"✅ <b>{titulo}</b>\n\n"

            # Mostrar quem retirou e quem devolveu

            if retirado_por:

                msg += f"📤 <b>Retirado por:</b> {retirado_por.nome} (Mat. {retirado_por.matricula})\n"

            if devolvedor:

                msg += f"📥 <b>Devolvido por:</b> {devolvedor.nome} (Mat. {devolvedor.matricula})\n"

        else:

            # Título dinâmico para entrada

            categoria_titulo = categoria.upper()

            if "FERRAMENTA" in categoria_titulo:

                categoria_titulo = "FERRAMENTA"

            titulo = f"ENTRADA DE {categoria_titulo}"

            msg = f"📥 <b>{titulo}</b>\n\n"

        

        msg += f"📦 <b>Total de itens:</b> 1\n"

        msg += f"⏰ <b>Horário:</b> {data_fmt}\n\n"

        msg += f"━━━━━━━━━━━━━━━━━\n\n"

        msg += f"<b>1.</b> {emoji} <b>{descricao}</b>\n"

        msg += f"   🏷️ {categoria}\n"

        # Para devolução, não usar o símbolo + (acréscimo)

        if is_devolucao:

            msg += f"   📊 Qtd Devolvida: <b>{quantidade}</b> {unidade}\n"

        else:

            msg += f"   📊 Qtd: <b>+{quantidade}</b> {unidade}\n"

        

        # Saldo após entrada/devolução

        if item:

            try:

                from galint_flask.services.embalagem_service import EmbalagemService

                if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):

                    estoque_str = EmbalagemService.formatar_estoque(item)

                    if is_devolucao:

                        msg += f"   ✅ Estoque atualizado: {estoque_str}"

                    else:

                        msg += f"   💼 Novo Saldo: {estoque_str}"

                else:

                    saldo_atual = int(item.get_saldo_atual() or 0)

                    if is_devolucao:

                        msg += f"   ✅ Estoque atualizado: {saldo_atual} {unidade}"

                    else:

                        msg += f"   💼 Novo Saldo: {saldo_atual} {unidade}"

            except Exception:

                try:

                    saldo_atual = int(item.get_saldo_atual() or 0)

                    if is_devolucao:

                        msg += f"   ✅ Estoque atualizado: {saldo_atual} {unidade}"

                    else:

                        msg += f"   💼 Novo Saldo: {saldo_atual} {unidade}"

                except Exception:

                    pass



            totals = TelegramService._format_balance_totals(item)

            if totals:

                msg += "\n" + totals

        

        return msg



    @staticmethod
    def format_devolucao_message(evento, item) -> str:
        """Formata mensagem personalizada para devolução de material - Modelo 3: Tabela Descritiva."""
        from ..models import Saida

        codigo = evento.codigo_item or "N/A"
        descricao = item.descricao if item else "N/D"
        categoria = getattr(item, "categoria", None) or "Material"
        marca = getattr(item, "marca", None)
        quantidade = abs(float(getattr(evento, "quantidade", 0) or 0))
        data_devolucao = getattr(evento, "data_evento", None)
        data_devolucao_fmt = TimeService.format_local(data_devolucao)

        descricao_evento = getattr(evento, "descricao", "") or ""
        devolvido_por = ""
        if "por" in descricao_evento:
            try:
                devolvido_por = descricao_evento.split("por")[-1].split(":")[0].strip()
            except Exception:
                pass

        retirado_por = None
        retirado_matricula = None
        data_retirada = None
        local_uso = None
        tempo_posse_str = ""

        if item:
            try:
                ultima_saida = (
                    Saida.query
                    .filter(Saida.codigo_item == codigo)
                    .order_by(Saida.data_saida.desc())
                    .first()
                )
                if ultima_saida:
                    data_retirada = ultima_saida.data_saida
                    local_uso = ultima_saida.local_servico
                    if ultima_saida.usuario:
                        retirado_por = ultima_saida.usuario.nome
                        retirado_matricula = ultima_saida.usuario.matricula
                    if data_retirada and data_devolucao:
                        delta = data_devolucao - data_retirada
                        dias = delta.days
                        horas = delta.seconds // 3600
                        minutos = (delta.seconds % 3600) // 60
                        partes = []
                        if dias > 0:
                            partes.append(f"{dias} dia{'s' if dias != 1 else ''}")
                        if horas > 0:
                            partes.append(f"{horas} hora{'s' if horas != 1 else ''}")
                        if minutos > 0 or not partes:
                            partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
                        tempo_posse_str = ", ".join(partes)
            except Exception:
                pass

        categoria_titulo = categoria.upper() if isinstance(categoria, str) else "MATERIAL"
        if "FERRAMENTA" in categoria_titulo:
            categoria_titulo = "FERRAMENTA"

        emoji_map = {
            "ferramentas": "🔧",
            "material elétrico": "⚡",
            "material eletrico": "⚡",
            "material hidráulico": "🚰",
            "material hidraulico": "🚰",
            "material piscina": "🏊",
            "material de limpeza": "🧹",
            "equipamentos de epi": "🦺",
            "liquido": "💧",
            "líquido": "💧",
        }
        categoria_lower = categoria.lower() if isinstance(categoria, str) else ""
        emoji = emoji_map.get(categoria_lower, "📦")

        msg = f"🔄 <b>DEVOLUÇÃO DE {categoria_titulo}</b>\n\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{emoji} <b>{descricao}</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += "📋 <b>DADOS DO ITEM</b>\n"
        msg += f"   • Código: <code>{codigo}</code>\n"
        msg += f"   • Categoria: {categoria}\n"
        if marca:
            msg += f"   • Marca: {marca}\n"
        lote = getattr(item, "lote", None) if item else None
        if lote:
            msg += f"   • Lote: {lote}\n"

        if retirado_por:
            msg += "\n📤 <b>RETIRADA ORIGINAL</b>\n"
            msg += f"   • Por: {retirado_por}"
            if retirado_matricula:
                msg += f" (Mat. {retirado_matricula})"
            msg += "\n"
            if data_retirada:
                msg += f"   • Quando: {TimeService.format_local(data_retirada)}\n"
            if local_uso:
                msg += f"   • Local: {local_uso}\n"

        msg += "\n📥 <b>DEVOLUÇÃO REGISTRADA</b>\n"
        if devolvido_por:
            msg += f"   • Por: {devolvido_por}\n"
        msg += f"   • Quando: {data_devolucao_fmt}\n"
        msg += f"   • Qtd: {quantidade:g} unidade{'s' if quantidade != 1 else ''}\n"

        if tempo_posse_str:
            msg += "\n⏱️ <b>TEMPO DE POSSE</b>\n"
            msg += f"   └─ {tempo_posse_str}\n"

        msg += "\n✅ <b>Status:</b> Devolvida e disponível\n"
        if item:
            try:
                from galint_flask.services.embalagem_service import EmbalagemService
                if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):
                    msg += f"📊 <b>Estoque atualizado:</b> {EmbalagemService.formatar_estoque(item)}\n"
                else:
                    saldo_atual = int(item.get_saldo_atual() or 0)
                    msg += f"📊 <b>Estoque atualizado:</b> {saldo_atual} {item.unidade or 'unidades'}\n"
            except Exception:
                pass

            totals = TelegramService._format_balance_totals(item, prefix="")
            if totals:
                msg += totals + "\n"

        return msg


    @staticmethod
    def _format_possession_duration(start, end) -> str:
        """Gera texto legível para o tempo de posse da ferramenta."""
        if not start or not end:
            return ""

        try:
            delta = end - start
        except Exception:
            return ""

        if delta.total_seconds() < 0:
            return ""

        dias = delta.days
        horas = (delta.seconds // 3600)
        minutos = (delta.seconds % 3600) // 60
        partes = []

        if dias > 0:
            partes.append(f"{dias} dia{'s' if dias != 1 else ''}")
        if horas > 0:
            partes.append(f"{horas} hora{'s' if horas != 1 else ''}")
        if minutos > 0 or not partes:
            partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")

        return ", ".join(partes)


    @staticmethod
    def format_tool_damage_message(evento, item, usuario=None, saida=None) -> str:
        """Mensagem rica para incidentes de quebra."""
        descricao = item.descricao if item else "Ferramenta"
        codigo = evento.codigo_item or "N/D"
        categoria = getattr(item, "categoria", None) or "Ferramentas"
        marca = getattr(item, "marca", None)
        quantidade = abs(float(getattr(evento, "quantidade", 0) or 0))
        data_registro_fmt = TimeService.format_local(getattr(evento, "data_evento", None))
        obs = (getattr(evento, "descricao", "") or "").strip()
        local_servico = getattr(saida, "local_servico", None)
        data_saida = getattr(saida, "data_saida", None)
        tempo_posse = TelegramService._format_possession_duration(data_saida, getattr(evento, "data_evento", None))

        msg = "🚨 <b>FERRAMENTA QUEBRADA</b>\n\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🔧 <b>{descricao}</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += "📋 <b>DADOS DO ITEM</b>\n"
        msg += f"   • Código: <code>{codigo}</code>\n"
        msg += f"   • Categoria: {categoria}\n"
        if marca:
            msg += f"   • Marca: {marca}\n"
        msg += f"   • Quantidade: {quantidade:g} unidade{'s' if quantidade != 1 else ''}\n"

        if usuario:
            msg += "\n👷 <b>DEVOLVIDO POR</b>\n"
            msg += f"   • {usuario.nome} (Mat. {usuario.matricula})\n"
        elif getattr(evento, "matricula", None):
            msg += "\n👷 <b>DEVOLVIDO POR</b>\n"
            msg += f"   • Matrícula {evento.matricula}\n"

        if local_servico:
            msg += f"   • Local informado: {local_servico}\n"

        if data_saida:
            msg += f"   • Retirada em: {TimeService.format_local(data_saida)}\n"

        if data_registro_fmt:
            msg += f"\n⏰ <b>Registro:</b> {data_registro_fmt}\n"

        if tempo_posse:
            msg += f"⏱️ <b>Tempo de posse:</b> {tempo_posse}\n"

        if obs:
            msg += "\n⚠️ <b>Relato do colaborador</b>\n"
            msg += f"   └─ {obs}\n"

        msg += "\n📦 <b>Status:</b> Item devolvido quebrado - retirar de circulação\n"
        return msg


    @staticmethod
    def format_tool_repair_message(evento, item, usuario=None, saida=None) -> str:
        """Mensagem detalhada para envio de ferramenta ao reparo."""
        descricao = item.descricao if item else "Ferramenta"
        codigo = evento.codigo_item or "N/D"
        categoria = getattr(item, "categoria", None) or "Ferramentas"
        marca = getattr(item, "marca", None)
        quantidade = abs(float(getattr(evento, "quantidade", 0) or 0))
        data_registro_fmt = TimeService.format_local(getattr(evento, "data_evento", None))
        obs = (getattr(evento, "descricao", "") or "").strip()
        local_servico = getattr(saida, "local_servico", None)
        data_saida = getattr(saida, "data_saida", None)
        tempo_posse = TelegramService._format_possession_duration(data_saida, getattr(evento, "data_evento", None))

        msg = "🛠️ <b>Equipamento para Reparo</b>\n\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🔧 <b>{descricao}</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += "📋 <b>DADOS DO ITEM</b>\n"
        msg += f"   • Código: <code>{codigo}</code>\n"
        msg += f"   • Categoria: {categoria}\n"
        if marca:
            msg += f"   • Marca: {marca}\n"
        msg += f"   • Quantidade: {quantidade:g} unidade{'s' if quantidade != 1 else ''}\n"

        if usuario:
            msg += "\n👷 <b>ENTREGUE POR</b>\n"
            msg += f"   • {usuario.nome} (Mat. {usuario.matricula})\n"
        elif getattr(evento, "matricula", None):
            msg += "\n👷 <b>ENTREGUE POR</b>\n"
            msg += f"   • Matrícula {evento.matricula}\n"

        if local_servico:
            msg += f"   • Local original: {local_servico}\n"

        if data_saida:
            msg += f"   • Retirada em: {TimeService.format_local(data_saida)}\n"

        if data_registro_fmt:
            msg += f"\n⏰ <b>Registro:</b> {data_registro_fmt}\n"

        if tempo_posse:
            msg += f"⏱️ <b>Tempo em posse:</b> {tempo_posse}\n"

        if obs:
            msg += "\n📝 <b>Motivo do reparo</b>\n"
            msg += f"   └─ {obs}\n"

        msg += "\n📦 <b>Status:</b> Em manutenção - aguardando retorno ao estoque\n"
        return msg



    @staticmethod

    def notify_new_entry(entrada_id: int, is_devolucao: bool = False) -> dict[str, Any]:

        """Notifica somente administradores com Telegram sobre nova entrada (Entrada)."""

        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não está habilitado"}



        # buscar entrada

        entrada = db.session.get(Entrada, entrada_id)

        if not entrada or not entrada.item:

            return {"success": False, "error": "Entrada inválida"}



        # Se for devolução, buscar quem retirou originalmente (última saída deste item)

        retirado_por = None

        if is_devolucao and entrada.item:

            ultima_saida = (

                Saida.query

                .filter(Saida.codigo_item == entrada.codigo_item)

                .order_by(Saida.data_saida.desc())

                .first()

            )

            if ultima_saida and ultima_saida.usuario:

                retirado_por = ultima_saida.usuario



        # montar mensagem

        message_text = TelegramService.format_new_entry_message(entrada, is_devolucao=is_devolucao, retirado_por=retirado_por)



        results = {"queued": [], "failed": [], "skipped": []}



        # buscar administradores com Telegram vinculado

        try:

            admins = TelegramService._privileged_users_query().all()

        except Exception:

            admins = []



        for admin in admins:

            try:

                # Verificar preferências se for devolução

                if is_devolucao:

                    if not TelegramService._should_notify_user(admin, entrada.item.categoria, is_return=True):

                        results["skipped"].append(f"{admin.usuario.nome if admin.usuario else admin.chat_id} (preferências)")

                        continue

                

                # Usar message_type e key apropriados para devolução

                if is_devolucao:

                    msg_type = "devolucao_material"

                    key = f"devolucao:{entrada_id}:admin:{admin.chat_id}"

                else:

                    msg_type = "new_entry"

                    key = f"new_entry:{entrada_id}:admin:{admin.chat_id}"

                

                q = TelegramService.enqueue_outbox_message(

                    chat_id=str(admin.chat_id),

                    recipient_name=admin.usuario.nome if getattr(admin, 'usuario', None) else None,

                    message_type=msg_type,

                    message_text=message_text,

                    idempotency_key=key,

                    entrada_id=entrada_id,

                    commit=False,

                )

                if q.get("success"):

                    results["queued"].append(str(admin.chat_id))

                else:

                    results["failed"].append(f"{admin.chat_id}: {q.get('error')}")

            except Exception as e:

                results["failed"].append(f"{admin.chat_id}: {e}")



        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            return {"success": False, "error": "Falha ao persistir enfileiramento de new_entry"}



        return {"success": True, "sent": results["queued"], "queued": results["queued"], "failed": results["failed"]}


    @staticmethod
    def notify_tool_damage(event_id: int) -> dict[str, Any]:
        """Notifica incidentes de quebra/dano."""
        return TelegramService._notify_tool_incident(event_id, incident_type="damage")


    @staticmethod
    def notify_tool_repair(event_id: int) -> dict[str, Any]:
        """Notifica envios de ferramenta para reparo."""
        return TelegramService._notify_tool_incident(event_id, incident_type="repair")


    @staticmethod
    def _notify_tool_incident(event_id: int, incident_type: str) -> dict[str, Any]:
        if not TelegramService.is_enabled():
            return {"success": False, "error": "Telegram não está habilitado"}

        evento = db.session.get(InventarioEvento, event_id)
        if not evento:
            return {"success": False, "error": "Evento não encontrado"}

        tipo_evento = (getattr(evento, "tipo", "") or "").lower()
        if incident_type == "damage":
            expected_types = {"quebra_ferramenta", "quebra_material"}
        else:
            expected_types = {"reparo_ferramenta"}

        if expected_types and tipo_evento not in expected_types:
            return {"success": False, "error": "Evento incompatível com incidente solicitado"}

        item = db.session.get(Item, evento.codigo_item) if evento.codigo_item else None
        usuario = db.session.get(Usuario, evento.matricula) if evento.matricula else None

        saida = None
        if evento.codigo_item and evento.matricula:
            saida = (
                Saida.query
                .filter(
                    Saida.codigo_item == evento.codigo_item,
                    Saida.matricula == evento.matricula,
                )
                .order_by(Saida.data_saida.desc())
                .first()
            )

        if incident_type == "damage":
            message_text = TelegramService.format_tool_damage_message(evento, item, usuario=usuario, saida=saida)
            message_type = "quebra_ferramenta"
            key_label = "damage"
        else:
            message_text = TelegramService.format_tool_repair_message(evento, item, usuario=usuario, saida=saida)
            message_type = "reparo_ferramenta"
            key_label = "repair"

        results = {"queued": [], "failed": []}
        admins = TelegramService._privileged_users_query().all()

        for admin in admins:
            try:
                key = f"tool_incident:{event_id}:{key_label}:admin:{admin.chat_id}"
                q = TelegramService.enqueue_outbox_message(
                    chat_id=str(admin.chat_id),
                    recipient_name=admin.usuario.nome if getattr(admin, 'usuario', None) else None,
                    message_type=message_type,
                    message_text=message_text,
                    idempotency_key=key,
                    inventario_evento_id=event_id,
                    commit=False,
                )
                if q.get("success"):
                    results["queued"].append(str(admin.chat_id))
                else:
                    results["failed"].append(f"{admin.chat_id}: {q.get('error')}")
            except Exception as e:
                results["failed"].append(f"{admin.chat_id}: {e}")

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return {"success": False, "error": "Falha ao persistir enfileiramento de incidente"}

        return {"success": True, "sent": results["queued"], "queued": results["queued"], "failed": results["failed"]}



    @staticmethod

    def notify_inventory_event(event_id: int) -> dict[str, Any]:

        """Notifica administradores sobre eventos de inventário (InventarioEvento)."""

        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não está habilitado"}



        # Ajustes de estoque (delta > 0) são usados como "entrada/devolução" em algumas rotas.
        # Para garantir que a entrada não passe despercebida, o padrão agora é NOTIFICAR.

        if os.environ.get("GALINT_TELEGRAM_NOTIFY_INVENTORY_ADJUSTMENTS", "true").strip().lower() not in (

            "1",

            "true",

            "yes",

        ):

            return {"success": True, "skipped": True, "reason": "inventory adjustments notifications disabled"}



        evento = db.session.get(InventarioEvento, event_id)

        if not evento:

            return {"success": False, "error": "Evento não encontrado"}



        # Somente notificar se for aumento de estoque
        quantidade = float(getattr(evento, "quantidade", 0) or 0)
        if quantidade <= 0:
            return {"success": False, "error": "Evento não é entrada"}



        item = None

        if evento.codigo_item:

            item = db.session.get(Item, evento.codigo_item)



        # Detectar se é devolução e usar mensagem personalizada

        tipo_evento = getattr(evento, "tipo", "") or ""

        descricao_evento = getattr(evento, "descricao", "") or ""

        is_devolucao = (

            "devolu" in tipo_evento.lower()

            or "devolu" in descricao_evento.lower()

        )

        

        if is_devolucao:

            # Usar mensagem personalizada de devolução

            message_text = TelegramService.format_devolucao_message(evento, item)

            message_type = "devolucao_material"

        else:

            # Mensagem detalhada de ajuste manual de estoque

            data_fmt = TimeService.format_local(getattr(evento, "data_evento", None))

            

            # Extrair informações do ajuste da descrição

            descricao = getattr(evento, "descricao", "") or ""

            saldo_anterior = None

            saldo_novo = None

            

            # Parsear "de X para Y" da descrição (suporta float)
            import re
            match = re.search(r'de\s+([0-9]+(?:\.[0-9]+)?)\s+para\s+([0-9]+(?:\.[0-9]+)?)', descricao)
            if match:
                try:
                    saldo_anterior = float(match.group(1))
                    saldo_novo = float(match.group(2))
                except Exception:
                    saldo_anterior = None
                    saldo_novo = None

            

            # Calcular saldo atual se não foi parseado
            if saldo_novo is None and item:
                try:
                    # Para itens com embalagem, a fonte da verdade é o estoque físico (embalagens + soltas)
                    from galint_flask.services.embalagem_service import EmbalagemService
                    if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):
                        saldo_novo = float(EmbalagemService.calcular_estoque_total(item))
                    else:
                        saldo_novo = float(item.get_saldo_atual() or 0)
                except Exception:
                    saldo_novo = float(item.get_saldo_atual() or 0)
                try:
                    saldo_anterior = float(saldo_novo) - float(quantidade)
                except Exception:
                    saldo_anterior = None

            

            # Obter informações do responsável

            from ..models import Usuario

            responsavel = None

            if evento.matricula:

                responsavel = db.session.query(Usuario).filter_by(matricula=evento.matricula).first()

            

            # Emojis baseados na categoria

            emoji_map = {

                "ferramentas": "🔧",

                "material elétrico": "⚡",

                "material eletrico": "âš¡",

                "material hidráulico": "🚰",

                "material hidraulico": "🚰",

                "material piscina": "🏊",

                "liquido": "💧",

                "líquido": "💧",

            }

            categoria = (item.categoria or "Geral").strip() if item else "Geral"

            emoji = emoji_map.get(categoria.lower(), "📦")

            

            # Determinar tipo de ajuste
            if quantidade > 0:
                tipo_ajuste = "ENTRADA MANUAL"
                icone_tipo = "📥"
                variacao_icon = "📈"
            else:
                tipo_ajuste = "RETIRADA MANUAL"
                icone_tipo = "📤"
                variacao_icon = "📉"

            

            # Montar mensagem rica

            message_text = f"{icone_tipo} <b>AJUSTE DE ESTOQUE - {tipo_ajuste}</b>\n\n"

            message_text += f"{emoji} <b>{item.descricao if item else 'Item desconhecido'}</b>\n"

            message_text += f"🏷️ Código: <code>{evento.codigo_item or 'N/D'}</code>\n"

            message_text += f"📂 Categoria: {categoria}\n"

            if item and item.marca:

                message_text += f"🏭 Marca: {item.marca}\n"

            message_text += f"\n━━━━━━━━━━━━━━━━━\n\n"

            

            if saldo_anterior is not None and saldo_novo is not None:
                message_text += f"📊 <b>MOVIMENTAÇÃO</b>\n"

                try:
                    from galint_flask.services.embalagem_service import EmbalagemService
                    tem_emb = item and (EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item))
                except Exception:
                    EmbalagemService = None
                    tem_emb = False

                # Caso especial: ajuste via edição do item em "saldo em embalagens" — os números do texto são embalagens.
                ajuste_em_embalagens = "saldo em embalagens" in (descricao or "").lower()
                if tem_emb and ajuste_em_embalagens and EmbalagemService:
                    nome_emb_sing = item.get_nome_embalagem() if hasattr(item, "get_nome_embalagem") else (item.tipo_embalagem_novo or "embalagem")
                    nome_emb_pl = item.get_nome_embalagem_plural() if hasattr(item, "get_nome_embalagem_plural") else (nome_emb_sing + "s")
                    def _nome(q: float) -> str:
                        return nome_emb_sing if abs(float(q) - 1.0) < 1e-9 else nome_emb_pl

                    variacao_emb = float(saldo_novo) - float(saldo_anterior)
                    message_text += f"├─ Saldo anterior: <b>{saldo_anterior:g}</b> {_nome(saldo_anterior)}\n"
                    message_text += f"├─ Variação: <b>{variacao_emb:+g}</b> {_nome(variacao_emb)} {variacao_icon}\n"
                    message_text += f"└─ Saldo atual: <b>{saldo_novo:g}</b> {_nome(saldo_novo)}\n"

                    try:
                        estoque_fisico = EmbalagemService.formatar_estoque(item)
                        message_text += f"\n📦 <b>Estoque físico:</b> {estoque_fisico}\n"
                        totals = TelegramService._format_balance_totals(item, prefix="", saldo_override=float(EmbalagemService.calcular_estoque_total(item)))
                        if totals:
                            message_text += totals + "\n"
                        message_text += "\n"
                    except Exception:
                        message_text += "\n"

                else:
                    unidade_mov = (item.unidade or "un") if item else "un"
                    message_text += f"├─ Saldo anterior: <b>{saldo_anterior:g}</b> {unidade_mov}\n"
                    message_text += f"├─ Variação: <b>{quantidade:+g}</b> {unidade_mov} {variacao_icon}\n"

                    if tem_emb and EmbalagemService and item:
                        try:
                            estoque_fisico = EmbalagemService.formatar_estoque(item)
                            message_text += f"└─ Saldo atual: <b>{estoque_fisico}</b>\n\n"
                            totals = TelegramService._format_balance_totals(item, prefix="")
                            if totals:
                                message_text += totals + "\n\n"
                        except Exception:
                            message_text += f"└─ Saldo atual: <b>{saldo_novo:g}</b> {unidade_mov}\n\n"
                    else:
                        message_text += f"└─ Saldo atual: <b>{saldo_novo:g}</b> {unidade_mov}\n\n"



                if item:

                    totals = TelegramService._format_balance_totals(item, prefix="", saldo_override=saldo_novo)

                    if totals:

                        message_text += totals + "\n\n"

            else:

                message_text += f"📊 <b>Variação:</b> {quantidade:+g} {item.unidade or 'un'}\n\n"

            

            if responsavel:

                message_text += f"👤 <b>Responsável:</b> {responsavel.nome} (Mat. {responsavel.matricula})\n"

            elif evento.matricula:

                message_text += f"👤 <b>Matrícula:</b> {evento.matricula}\n"

            

            # Extrair motivo da descrição

            motivo = descricao.split(':')[0] if ':' in descricao else "Ajuste manual"

            message_text += f"📝 <b>Motivo:</b> {motivo}\n"

            message_text += f"⏰ <b>Data/Hora:</b> {data_fmt}"

            

            message_type = "inventory_adjustment"



        results = {"queued": [], "failed": []}



        admins = TelegramService._privileged_users_query().all()



        for admin in admins:

            try:

                key_suffix = "devolucao" if is_devolucao else "adjustment"

                key = f"inventory_event:{event_id}:{key_suffix}:admin:{admin.chat_id}"

                q = TelegramService.enqueue_outbox_message(

                    chat_id=str(admin.chat_id),

                    recipient_name=admin.usuario.nome if getattr(admin, 'usuario', None) else None,

                    message_type=message_type,

                    message_text=message_text,

                    idempotency_key=key,

                    inventario_evento_id=event_id,

                    commit=False,

                )

                if q.get("success"):

                    results["queued"].append(str(admin.chat_id))

                else:

                    results["failed"].append(f"{admin.chat_id}: {q.get('error')}")

            except Exception as e:

                results["failed"].append(f"{admin.chat_id}: {e}")



        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            return {"success": False, "error": "Falha ao persistir enfileiramento de inventory_event"}



        return {"success": True, "sent": results["queued"], "queued": results["queued"], "failed": results["failed"]}



    @staticmethod

    def notify_item_now(codigo: str) -> dict[str, Any]:

        """Notifica administradores sobre um item específico (manual 'Notificar agora')."""

        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não está habilitado"}



        item = db.session.get(Item, codigo)

        if not item:

            return {"success": False, "error": "Item não encontrado"}



        # Formatar saldo com embalagens se aplicável

        try:

            from galint_flask.services.embalagem_service import EmbalagemService

            if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):

                saldo = EmbalagemService.formatar_estoque(item)

            else:

                saldo = item.get_saldo_atual()

        except Exception:

            saldo = item.get_saldo_atual()

            

        data_fmt = TimeService.now_local().strftime("%d/%m/%Y %H:%M")

        message_text = (

            f"📣 <b>NOTIFICAÇÃO MANUAL DE ITEM</b>\n\n"

            f"🏷️ <b>Código:</b> {item.codigo_item}\n"

            f"📦 <b>Descrição:</b> {item.descricao}\n"

            f"🏷️ <b>Marca:</b> {item.marca or 'N/D'}\n"

            f"🔖 <b>Categoria:</b> {item.categoria or 'N/D'}\n"

            f"📊 <b>Quantidade atual:</b> {saldo}\n"

            f"⏰ <b>Data:</b> {data_fmt}"

        )



        totals = TelegramService._format_balance_totals(item, prefix="")

        if totals:

            message_text += "\n" + totals



        results = {"sent": [], "failed": []}

        admins = TelegramService._privileged_users_query().all()



        for admin in admins:

            try:

                res = TelegramService.send_message(admin.chat_id, message_text)

                notification = TelegramNotification(

                    chat_id=admin.chat_id,

                    recipient_name=admin.usuario.nome if getattr(admin, 'usuario', None) else None,

                    message_type="manual_item",

                    message_text=message_text,

                    status="sent" if res.get("success") else "failed",

                    error_message=res.get("error"),

                )

                db.session.add(notification)

                if res.get("success"):

                    admin.last_notification = datetime.utcnow()

                    results["sent"].append(admin.chat_id)

                else:

                    results["failed"].append(f"{admin.chat_id}: {res.get('error')}")

            except Exception as e:

                results["failed"].append(f"{admin.chat_id}: {e}")



        db.session.commit()

        return {"success": True, "sent": results["sent"], "failed": results["failed"]}



    @staticmethod

    def notify_item_created(codigo: str, entrada_inicial: Any = None) -> dict[str, Any]:

        """Notifica administradores que um novo item foi cadastrado.

        

        Esta notificação é UNIFICADA e substitui as notificações separadas de:

        - item_created (criação do item)

        - new_entry (entrada inicial de estoque)

        

        Formato: Model 1 - Compact and Direct

        """

        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não habilitado"}



        item = db.session.get(Item, codigo)

        if not item:

            return {"success": False, "error": "Item não encontrado"}



        # Obter informações sobre a entrada inicial (se houver)

        saldo_inicial = 0

        usuario_cadastro = None

        data_cadastro = None

        

        try:

            saldo_inicial = int(item.get_saldo_atual() or 0)

        except Exception:

            pass

        

        if entrada_inicial:

            if hasattr(entrada_inicial, 'usuario') and entrada_inicial.usuario:

                usuario_cadastro = entrada_inicial.usuario.nome

            if hasattr(entrada_inicial, 'data_entrada'):

                data_cadastro = TimeService.format_local(entrada_inicial.data_entrada)

        

        # Se não temos a entrada mas o item existe, buscar última entrada

        if not data_cadastro:

            try:

                from galint_flask.models import Entrada

                ultima_entrada = (

                    Entrada.query

                    .filter(Entrada.codigo_item == codigo)

                    .order_by(Entrada.data_entrada.desc())

                    .first()

                )

                if ultima_entrada:

                    if not usuario_cadastro and ultima_entrada.usuario:

                        usuario_cadastro = ultima_entrada.usuario.nome

                    if not data_cadastro:

                        data_cadastro = TimeService.format_local(ultima_entrada.data_entrada)

            except Exception:

                pass

        

        # Fallback para data atual se não conseguiu obter

        if not data_cadastro:

            from datetime import datetime

            data_cadastro = TimeService.format_local(datetime.now())

        

        # Emoji baseado na categoria

        emoji_map = {

            "ferramentas": "🔧",

            "material elétrico": "⚡",

            "material eletrico": "âš¡",

            "material hidráulico": "🚰",

            "material hidraulico": "🚰",

            "material piscina": "🏊",

            "liquido": "💧",

            "líquido": "💧",

            "equipamento": "⚙️",

        }

        categoria_lower = (item.categoria or "geral").lower()

        # emoji = emoji_map.get(categoria_lower, "📦")

        

        # Formatar estoque inicial

        estoque_str = ""

        unidade = item.unidade or 'un'

        

        try:

            from galint_flask.services.embalagem_service import EmbalagemService

            if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):

                estoque_str = EmbalagemService.formatar_estoque(item)

            else:

                estoque_str = f"{saldo_inicial} {unidade}"

        except Exception:

            estoque_str = f"{saldo_inicial} {unidade}"

        

        # FORMATO MODEL 1: Compact and Direct

        text = f"🆕 <b>NOVO ITEM CADASTRADO</b>\n\n"

        text += f"📦 <b>{item.descricao}</b>\n"

        text += f"🏷️ {item.categoria or 'Geral'}\n"

        text += f"📊 Estoque inicial: <b>{estoque_str}</b>"

        

        # Adicionar informações específicas de equipamento

        if item.categoria == "Equipamento":

            text += "\n\n⚙️ <b>INFORMAÇÕES DO EQUIPAMENTO:</b>"

            if item.modelo:

                text += f"\n├─ Modelo: {item.modelo}"

            if item.numero_serie:

                text += f"\n├─ Serial: {item.numero_serie}"

            if item.voltagem:

                text += f"\n├─ Voltagem: {item.voltagem}"

            if item.amperagem:

                text += f"\n├─ Amperagem: {item.amperagem}"

            if item.local_instalacao:

                text += f"\n└─ Local: {item.local_instalacao}"

        

        text += "\n"

        if usuario_cadastro:

            text += f"\n👤 Cadastrado por: {usuario_cadastro}"

        text += f"\n📅 {data_cadastro}"

        text += f"\n\nCódigo: <code>{item.codigo_item}</code>"



        # Adicionar totais se houver múltiplos lotes

        totals = TelegramService._format_balance_totals(item, prefix="")

        if totals:

            text += "\n\n" + totals



        results = {"queued": [], "failed": []}

        admins = TelegramService._privileged_users_query().all()



        for adm in admins:

            try:

                key = f"item_created:{codigo}:admin:{adm.chat_id}"

                q = TelegramService.enqueue_outbox_message(

                    chat_id=str(adm.chat_id),

                    recipient_name=getattr(getattr(adm, "usuario", None), "nome", None),

                    message_type="item_created",

                    message_text=text,

                    idempotency_key=key,

                    commit=False,

                )

                if q.get("success"):

                    results["queued"].append(str(adm.chat_id))

                    log_action(f"notify_item_created(outbox): enfileirado para {adm.chat_id} (item={codigo})")

                else:

                    results["failed"].append({"chat_id": adm.chat_id, "error": q.get("error")})

                    log_action(f"notify_item_created(outbox): falha para {adm.chat_id} - {q.get('error')}")

            except Exception as e:

                results["failed"].append({"chat_id": adm.chat_id, "error": str(e)})

                logger.exception("Erro ao notificar admin sobre novo item")



        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            return {"success": False, "error": "Falha ao persistir enfileiramento item_created"}



        return {"success": True, "sent": results["queued"], "queued": results["queued"], "failed": results["failed"]}



    @staticmethod

    def notify_item_updated(codigo: str, prev: dict[str, Any] | None = None, prev_balance: int | None = None) -> dict[str, Any]:

        """Notifica administradores sobre atualização de item.



        `prev` pode conter campos anteriores (descricao, marca, categoria).

        `prev_balance` contém saldo anterior se aplicável.

        """

        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não habilitado"}



        item = db.session.get(Item, codigo)

        if not item:

            return {"success": False, "error": "Item não encontrado"}



        try:

            new_balance = int(item.get_saldo_atual() or 0)

        except Exception:

            new_balance = 0



        # Detectar tipo de alteração

        houve_alteracao_saldo = prev_balance is not None and prev_balance != new_balance

        houve_alteracao_dados = False

        

        if prev:

            if prev.get("descricao") and prev.get("descricao") != item.descricao:

                houve_alteracao_dados = True

            if prev.get("marca") and prev.get("marca") != (item.marca or ""):

                houve_alteracao_dados = True

            if prev.get("categoria") and prev.get("categoria") != (item.categoria or ""):

                houve_alteracao_dados = True



        # Determinar tipo de ajuste

        if houve_alteracao_saldo:

            delta = new_balance - prev_balance

            if delta > 0:

                tipo_ajuste = "ENTRADA MANUAL"

                icone_tipo = "📥"

                variacao_icon = "📈"

            else:

                tipo_ajuste = "RETIRADA MANUAL"

                icone_tipo = "📤"

                variacao_icon = "📉"

        else:

            tipo_ajuste = "ALTERAÇÃO DE CADASTRO"

            icone_tipo = "✏️"

            variacao_icon = ""



        # Emojis baseados na categoria

        categoria = (item.categoria or "Geral").strip()

        emoji_map = {

            "ferramentas": "🔧",

            "material elétrico": "⚡",

            "material eletrico": "âš¡",

            "material hidráulico": "🚰",

            "material hidraulico": "🚰",

            "material piscina": "🏊",

            "material de limpeza": "🧹",

            "equipamentos de epi": "🦺",

            "equipamento": "⚙️",

            "liquido": "💧",

            "líquido": "💧",

        }

        emoji = emoji_map.get(categoria.lower(), "📦")



        # Montar mensagem rica

        data_fmt = TimeService.now_local().strftime("%d/%m/%Y %H:%M")

        

        text = f"{icone_tipo} <b>AJUSTE DE ESTOQUE - {tipo_ajuste}</b>\n\n"

        text += f"{emoji} <b>{item.descricao}</b>\n"

        text += f"🏷️ Código: <code>{item.codigo_item}</code>\n"

        text += f"📂 Categoria: {categoria}\n"

        if item.marca:

            text += f"🏭 Marca: {item.marca}\n"

        text += "\n━━━━━━━━━━━━━━━━━\n\n"

        

        # Adicionar informações específicas de equipamento

        if item.categoria == "Equipamento":

            text += "⚙️ <b>INFORMAÇÕES DO EQUIPAMENTO</b>\n"

            if item.modelo:

                text += f"├─ Modelo: <b>{item.modelo}</b>\n"

            if item.numero_serie:

                text += f"├─ Serial Number: <b>{item.numero_serie}</b>\n"

            if item.voltagem:

                text += f"├─ Voltagem: <b>{item.voltagem}</b>\n"

            if item.amperagem:

                text += f"├─ Amperagem: <b>{item.amperagem}</b>\n"

            if item.local_instalacao:

                text += f"└─ Local: <b>{item.local_instalacao}</b>\n"

            text += "\n━━━━━━━━━━━━━━━━━\n\n"



        # Alterações de saldo

        if houve_alteracao_saldo:

            delta = new_balance - prev_balance

            text += f"📊 <b>MOVIMENTAÇÃO</b>\n"

            text += f"├─ Saldo anterior: <b>{prev_balance}</b> {item.unidade or 'un'}\n"

            text += f"├─ Variação: <b>{delta:+g}</b> {item.unidade or 'un'} {variacao_icon}\n"

            text += f"└─ Saldo atual: <b>{new_balance}</b> {item.unidade or 'un'}\n"

            

            # Adicionar saldo em medidas para itens com embalagens

            from galint_flask.services.embalagem_service import EmbalagemService

            if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):

                estoque_detalhado = EmbalagemService.formatar_estoque(item)

                text += f"📦 <b>Saldo em medidas:</b> {estoque_detalhado}\n"

            totals = TelegramService._format_balance_totals(item, prefix="")

            if totals:

                text += totals + "\n"

            text += "\n"

        else:

            text += f"💼 <b>Saldo atual:</b> {new_balance} {item.unidade or 'un'}"

            

            # Adicionar saldo em medidas para itens com embalagens

            from galint_flask.services.embalagem_service import EmbalagemService

            if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):

                estoque_detalhado = EmbalagemService.formatar_estoque(item)

                text += f"\n📦 <b>Saldo em medidas:</b> {estoque_detalhado}"

            totals = TelegramService._format_balance_totals(item, prefix="")

            if totals:

                text += "\n" + totals

            text += "\n\n"



        # Alterações de dados cadastrais

        if houve_alteracao_dados:

            text += "📝 <b>ALTERAÇÕES:</b>\n"

            if prev and prev.get("descricao") and prev.get("descricao") != item.descricao:

                text += f"├─ Nome: {prev.get('descricao')} → {item.descricao}\n"

            if prev and prev.get("marca") and prev.get("marca") != (item.marca or ""):

                text += f"├─ Marca: {prev.get('marca')} → {item.marca or '-'}\n"

            if prev and prev.get("categoria") and prev.get("categoria") != (item.categoria or ""):

                text += f"├─ Categoria: {prev.get('categoria')} → {item.categoria or '-'}\n"

            text += "\n"



        text += f"⏰ <b>Data/Hora:</b> {data_fmt}"



        results = {"queued": [], "failed": []}

        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

        admins = TelegramService._privileged_users_query().all()



        for adm in admins:

            try:

                key = f"item_updated:{codigo}:h:{h}:admin:{adm.chat_id}"

                q = TelegramService.enqueue_outbox_message(

                    chat_id=str(adm.chat_id),

                    recipient_name=getattr(getattr(adm, "usuario", None), "nome", None),

                    message_type="item_updated",

                    message_text=text,

                    idempotency_key=key,

                    commit=False,

                )

                if q.get("success"):

                    results["queued"].append(str(adm.chat_id))

                    log_action(f"notify_item_updated(outbox): enfileirado para {adm.chat_id} (item={codigo})")

                else:

                    results["failed"].append({"chat_id": adm.chat_id, "error": q.get("error")})

                    log_action(f"notify_item_updated(outbox): falha para {adm.chat_id} - {q.get('error')}")

            except Exception:

                logger.exception("Erro ao notificar admin sobre item atualizado")



        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            return {"success": False, "error": "Falha ao persistir enfileiramento item_updated"}



        return {"success": True, "sent": results["queued"], "queued": results["queued"], "failed": results["failed"]}



    @staticmethod

    def send_low_stock_notifications() -> dict[str, Any]:

        """Envia mensagem sobre itens com estoque baixo para administradores."""

        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não habilitado"}



        config = TelegramService.get_config()

        if not config or not config.low_stock_enabled:

            return {"success": False, "error": "Low stock notifications disabled"}



        # listar itens com saldo <= minimo

        items = db.session.query(Item).all()

        low = []

        for it in items:

            try:

                saldo = it.get_saldo_atual()

            except Exception:

                saldo = 0

            if saldo <= (it.estoque_minimo or 0):

                low.append((it.codigo_item, it.descricao, saldo, it.estoque_minimo))



        if not low:

            return {"success": True, "sent": 0, "message": "Nenhum item em falta"}



        # montar mensagem resumida

        lines = [f"{c} — {d} — Saldo: {s} (Min: {m})" for c, d, s, m in low[:50]]

        text = "📉 ALERTA: Itens com estoque baixo:\n" + "\n".join(lines)



        results = {"queued": [], "failed": []}

        today_str = TimeService.now_local().date().isoformat()

        admins = TelegramService._privileged_users_query().all()

        for adm in admins:

            try:

                key = f"low_stock:{today_str}:admin:{adm.chat_id}"

                q = TelegramService.enqueue_outbox_message(

                    chat_id=str(adm.chat_id),

                    recipient_name=adm.usuario.nome if getattr(adm, 'usuario', None) else None,

                    message_type="low_stock",

                    message_text=text,

                    idempotency_key=key,

                    commit=False,

                )

                if q.get("success"):

                    results["queued"].append(str(adm.chat_id))

                else:

                    results["failed"].append({"chat_id": adm.chat_id, "error": q.get("error")})

            except Exception:

                logger.exception("Erro ao enviar low stock notification")



        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            return {"success": False, "error": "Falha ao persistir enfileiramento low_stock"}



        log_action(f"Low stock notification (outbox): enfileirados={len(results['queued'])}, falhas={len(results['failed'])}")

        return {"success": True, "sent": len(results["queued"]), "queued": len(results["queued"]), "failed": results["failed"]}



    @staticmethod

    def send_scheduled_alerts() -> dict[str, Any]:

        """Envia alerta de devolução (custódia diária) para TODOS no Telegram.

        Observações:
        - "Custódia diária" no sistema equivale às ferramentas classificadas como temporárias.
        - O agendamento é a cada 4h; aqui aplicamos idempotência por janela de 4h por chat.
        """

        if not TelegramService.is_enabled():
            return {"success": False, "error": "Telegram não está habilitado"}

        config = TelegramService.get_config()
        if not config or not config.alert_enabled:
            return {"success": False, "error": "Alertas agendados desabilitados"}

        from datetime import timedelta

        from .tool_custody_service import ToolCustodyService

        def _split_into_parts(text: str, max_chars: int = 3500) -> list[str]:
            if len(text) <= max_chars:
                return [text]
            lines = text.split("\n")
            parts: list[str] = []
            buf: list[str] = []
            size = 0
            for line in lines:
                extra = len(line) + 1
                if buf and size + extra > max_chars:
                    parts.append("\n".join(buf).strip())
                    buf = [line]
                    size = len(line) + 1
                else:
                    buf.append(line)
                    size += extra
            if buf:
                parts.append("\n".join(buf).strip())
            return [p for p in parts if p]

        now = TimeService.now_local()
        window_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=(now.hour % 4))
        window_key = window_start.strftime("%Y%m%dT%H")

        # Montar pendências (somente custódia diária/temporária)
        employees = ToolCustodyService.get_all_employees_with_tools()
        pendencias: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for emp in employees:
            tools = [t for t in (emp.get("tools") or []) if (t.get("tipo_custodia") or "").strip().lower() == "temporaria"]
            if tools:
                pendencias.append((emp, tools))

        if not pendencias:
            return {
                "success": True,
                "sent": [],
                "queued": [],
                "failed": [],
                "skipped": ["Sem pendências de custódia diária"],
                "total_sent": 0,
                "total_failed": 0,
            }

        # Calcular totais
        total_items = sum(len(tools) for _, tools in pendencias)
        total_funcionarios = len(pendencias)

        header = (
            "🚨 <b>ALERTA DE CUSTÓDIA TEMPORÁRIA</b>\n"
            f"Data/Hora: <b>{html.escape(TimeService.format_local(now, '%d/%m/%Y %H:%M'))}</b>\n\n"
            f"Ferramentas não devolvidas: <b>{total_items} itens</b> | <b>{total_funcionarios} funcionários</b>\n"
        )

        body_lines: list[str] = []
        for emp, tools in pendencias:
            nome = html.escape(str(emp.get("nome") or "N/D"))
            matricula = html.escape(str(emp.get("matricula") or ""))
            setor = html.escape(str(emp.get("setor") or "N/D"))
            
            # Card estruturado para cada funcionário
            body_lines.append("\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
            body_lines.append(f"┃ <b>{nome}</b>")
            body_lines.append("┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫")
            body_lines.append(f"┃ Mat: <code>{matricula}</code>")
            body_lines.append(f"┃ Setor: {setor}")
            body_lines.append("┃")
            
            for t in tools:
                codigo = html.escape(str(t.get("codigo_item") or "-"))
                desc = html.escape(str(t.get("descricao") or "Sem descrição"))
                local = html.escape(str(t.get("local_servico") or "Não informado"))
                days = int(t.get("days_in_use") or 0)
                
                body_lines.append(f"┃ 🔧 Item: <code>{codigo}</code>")
                body_lines.append(f"┃    {desc}")
                body_lines.append(f"┃    📍 {local} | ⏳ {days} dias")
                if t != tools[-1]:  # Adiciona linha em branco entre itens, exceto no último
                    body_lines.append("┃")
            
            body_lines.append("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")

        message_text = (header + "\n".join(body_lines)).strip()
        parts = _split_into_parts(message_text, max_chars=3500)

        # Enviar para todos Telegram users habilitados
        telegram_users = db.session.query(TelegramUser).filter_by(enabled=True).all()
        results = {"queued": [], "failed": [], "skipped": []}

        if not telegram_users:
            return {"success": False, "error": "Nenhum usuário Telegram habilitado"}

        for tu in telegram_users:
            recipient_name = None
            try:
                recipient_name = tu.usuario.nome if getattr(tu, "usuario", None) else None
            except Exception:
                recipient_name = None

            for idx, part in enumerate(parts, start=1):
                key = f"return_alert_4h:{window_key}:chat:{tu.chat_id}:part:{idx}"
                q = TelegramService.enqueue_outbox_message(
                    chat_id=str(tu.chat_id),
                    recipient_name=recipient_name,
                    message_type="return_alert_4h",
                    message_text=part,
                    idempotency_key=key,
                    commit=False,
                )
                if q.get("success"):
                    results["queued"].append(str(tu.chat_id))
                else:
                    results["failed"].append({"chat_id": str(tu.chat_id), "error": q.get("error")})

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return {"success": False, "error": "Falha ao persistir enfileiramento de alertas"}

        return {
            "success": True,
            "sent": results["queued"],
            "queued": results["queued"],
            "failed": results["failed"],
            "skipped": results["skipped"],
            "total_sent": len(results["queued"]),
            "total_failed": len(results["failed"]),
        }



    @staticmethod

    def send_end_of_workday_message() -> dict[str, Any]:

        """Envia mensagem motivacional de fim de expediente às 17h para todos os usuários Telegram ativos."""

        if not TelegramService.is_enabled():

            return {"success": False, "error": "Telegram não está habilitado"}



        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Token não configurado"}



        # Mensagens estimulantes variadas (sorteia uma)

        import random

        mensagens = [

            "🎉 <b>Fim de Expediente!</b> 🎉\n\n"

            "Parabéns por mais um dia de trabalho! 💪\n"

            "Descanse bem, você merece! 🌟\n\n"

            "Até amanhã! 👋",

            

            "⏰ <b>17h - Hora de Descansar!</b> ⏰\n\n"

            "Missão cumprida! 🏆\n"

            "Aproveite seu merecido descanso. 😊\n\n"

            "Nos vemos amanhã com energia renovada! 🚀",

            

            "✨ <b>Expediente Encerrado!</b> ✨\n\n"

            "Mais um dia de sucesso! 🎯\n"

            "Hora de recarregar as energias! âš¡\n\n"

            "Tenha uma excelente noite! 🌙",

            

            "🌟 <b>Fim do Dia de Trabalho!</b> 🌟\n\n"

            "Você fez a diferença hoje! 💼\n"

            "Descanse, relaxe e volte com tudo amanhã! 💚\n\n"

            "Até logo! 👋",

            

            "🎊 <b>17h00 - Hora de Ir!</b> 🎊\n\n"

            "Excelente trabalho hoje! 👏\n"

            "Seu esforço é reconhecido e valorizado! 🏅\n\n"

            "Aproveite seu tempo livre! 🎈",

        ]

        

        message_text = random.choice(mensagens)

        

        # Buscar todos os usuários Telegram ativos

        telegram_users = db.session.query(TelegramUser).filter_by(enabled=True).all()

        

        if not telegram_users:

            return {"success": True, "sent": 0, "message": "Nenhum usuário Telegram ativo"}

        

        results = {"sent": [], "failed": []}

        today_str = TimeService.now_local().date().isoformat()

        

        for telegram_user in telegram_users:

            try:

                usuario = db.session.get(Usuario, telegram_user.matricula)

                recipient_name = usuario.nome if usuario else telegram_user.matricula

                

                key = f"end_of_workday:{today_str}:chat:{telegram_user.chat_id}"

                q = TelegramService.enqueue_outbox_message(

                    chat_id=str(telegram_user.chat_id),

                    recipient_name=recipient_name,

                    message_type="end_of_workday",

                    message_text=message_text,

                    idempotency_key=key,

                    commit=False,

                )

                

                if q.get("success"):

                    results["sent"].append(recipient_name)

                else:

                    results["failed"].append(f"{recipient_name}: {q.get('error')}")

            except Exception as e:

                results["failed"].append(f"chat_id {telegram_user.chat_id}: {str(e)}")

        

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            return {"success": False, "error": "Falha ao persistir mensagens"}

        

        return {

            "success": True,

            "sent": len(results["sent"]),

            "failed": len(results["failed"]),

            "total": len(telegram_users),

        }



    @staticmethod

    def send_startup_broadcast() -> dict[str, Any]:

        """Envia saudação para todos os usuários Telegram cadastrados quando o sistema inicia.



        Texto (conforme solicitado):

        - "Bom dia/Boa tarde/Boa noite, NOME! Que seu dia seja uma benção. O almoxarifado está aberto!"



        Observação:

        - Para evitar spam, pode ser controlado por env `GALINT_TELEGRAM_STARTUP_BROADCAST_MODE`:

            - "always" (padrão): envia em todo startup real do servidor

            - "daily": envia no máximo 1x por dia

        """

        if not TelegramService.is_enabled():

            log_action("Startup broadcast: Telegram não habilitado, pulando envio.")

            return {"success": False, "error": "Telegram não habilitado"}



        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Token não configurado"}



        mode = os.environ.get("GALINT_TELEGRAM_STARTUP_BROADCAST_MODE", "always").strip().lower()



        # Regra: mensagens com "Boa noite" só podem ser enviadas até 18:00 e após 07:50.

        now_local = TimeService.now_local()

        if not TelegramService._allowed_boa_noite_window(now_local):

            log_action("Startup broadcast: janela de envio (07:50-18:00) fechada, pulando.")

            return {"success": True, "skipped": True, "reason": "outside_window"}



        # Modo "daily": evitar reenvio múltiplo no mesmo dia.

        # Persistimos a data (timezone local configurada) do último broadcast em instance/last_startup_broadcast.txt

        try:

            instance_dir = TelegramService._instance_dir()

            marker_file = instance_dir / "last_startup_broadcast.txt"

            today_str = TimeService.now_local().date().isoformat()



            if mode in ("daily", "once", "once-per-day", "1x") and marker_file.exists():

                try:

                    last = marker_file.read_text(encoding="utf-8").strip()

                    if last == today_str:

                        log_action(f"Startup broadcast: já enviado hoje (marker={last}), pulando.")

                        return {"success": True, "skipped": True, "mode": mode}

                except Exception:

                    pass

        except Exception:

            # se algo falhar na verificação, prosseguir com envio (não bloquear)

            logger.exception("Erro ao verificar marker de broadcast; prosseguindo com envio")



        results = {"queued": [], "failed": []}



        today_str = now_local.date().isoformat()

        run_scope = today_str

        if mode not in ("daily", "once", "once-per-day", "1x"):

            # Em modo "always", permitir múltiplos envios por dia (mas ainda idempotente por execução).

            run_scope = datetime.utcnow().isoformat().replace(":", "").replace(".", "")



        try:

            users = db.session.query(TelegramUser).filter_by(enabled=True).all()

        except Exception as e:

            logger.exception("Erro ao buscar TelegramUser para broadcast")

            log_action(f"Startup broadcast: falha ao buscar usuários - {e}")

            return {"success": False, "error": str(e)}



        for tu in users:

            chat_id = tu.chat_id

            try:

                # tentar obter nome do usuário vinculado

                nome = None

                try:

                    if getattr(tu, "usuario", None):

                        nome = getattr(tu.usuario, "nome", None)

                except Exception:

                    nome = None



                # fallback: pegar usuário pelo matricula se existir

                if not nome and getattr(tu, "matricula", None):

                    try:

                        u = db.session.get(Usuario, tu.matricula)

                        nome = getattr(u, "nome", None) if u else None

                    except Exception:

                        nome = None



                if not nome:

                    nome = "amigo"



                text = TelegramService._startup_greeting_text(nome)

                key = f"startup_broadcast:{run_scope}:chat:{chat_id}"

                q = TelegramService.enqueue_outbox_message(

                    chat_id=str(chat_id),

                    recipient_name=nome,

                    message_type="startup_broadcast",

                    message_text=text,

                    idempotency_key=key,

                    commit=False,

                )

                if q.get("success"):

                    results["queued"].append(chat_id)

                    log_action(f"Startup broadcast (outbox): enfileirada para {nome} (chat_id={chat_id})")

                else:

                    results["failed"].append({"chat_id": chat_id, "error": q.get("error")})

                    log_action(f"Startup broadcast (outbox): falha ao enfileirar para {chat_id} - {q.get('error')}")

            except Exception as e:

                logger.exception(f"Falha ao enviar startup message para {chat_id}")

                results["failed"].append({"chat_id": chat_id, "error": str(e)})



        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            return {"success": False, "error": "Falha ao persistir enfileiramento do startup broadcast"}



        # gravar marker (data) de envio se estiver em modo daily; caso contrário, gravar timestamp para auditoria.

        try:

            if mode in ("daily", "once", "once-per-day", "1x"):

                marker_file.write_text(today_str, encoding="utf-8")

            else:

                marker_file.write_text(TimeService.now_local().isoformat(), encoding="utf-8")

        except Exception:

            logger.exception("Falha ao gravar marker de último broadcast")



        logger.info(f"Startup broadcast (outbox): enfileirados={len(results['queued'])}, falhas={len(results['failed'])}")

        log_action(f"Startup broadcast finalizado (outbox): enfileirados={len(results['queued'])}, falhas={len(results['failed'])}")

        return {

            "success": True,

            "mode": mode,

            "sent": len(results["queued"]),

            "queued": len(results["queued"]),

            "failed": results["failed"],

        }



    # ---- Menu and report helpers ----

    @staticmethod

    def _build_reply_keyboard(button_rows: list[list[str]]) -> dict[str, Any]:

        """Retorna estrutura de reply_markup para teclado simples (ReplyKeyboardMarkup)."""

        return {"keyboard": button_rows, "resize_keyboard": True, "one_time_keyboard": False}



    @staticmethod

    def _normalize_menu_text(text: str) -> str:

        """Normaliza texto de botões/menus (remove emojis iniciais e padroniza espaços)."""

        s = (text or "").strip()

        # Remove possíveis emojis/ícones no começo (ex.: "📊 Relatórios...")

        while s and not (s[0].isalnum() or s[0] in ("/",)):

            s = s[1:].lstrip()

        s = re.sub(r"\s+", " ", s)

        return s.strip().lower()



    @staticmethod

    def _get_user_by_chat_id(chat_id: str) -> Usuario | None:

        try:

            tuser = db.session.query(TelegramUser).filter_by(chat_id=str(chat_id)).first()

            if not tuser:

                return None

            return tuser.usuario

        except Exception:

            return None



    @staticmethod

    def send_reports_menu(chat_id: str) -> dict[str, Any]:

        """Envia submenu de relatórios/retiradas."""

        # Layout alinhado aos prints do Telegram (submenu com opções claras)

        options = [

            ["🛠️ Relatório de Ferramentas (1–6 meses)"],

            ["📦 Relatório de Materiais (1–6 meses)"],

            ["📊 Relatório Geral (por categoria)"],

            ["📄 Saídas do Dia (PDF)"],

            ["📄 Estoque Baixo (XLSX/PDF)"],

            ["⬅️ Voltar ao Menu", "❌ Cancelar"],

        ]

        payload = TelegramService._build_reply_keyboard(options)

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Bot não configurado"}

        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="sendMessage")

            text = (

                "📊 <b>Relatórios & Retiradas</b>\n"

                "━━━━━━━━━━━━━━━━━━━━\n\n"

                "Escolha uma opção:\n\n"

                "• <b>Ferramentas</b>: filtro automático + categoria\n"

                "• <b>Materiais</b>: filtro automático + categoria\n"

                "• <b>Geral</b>: todas as categorias\n"

                "• <b>Saídas do Dia</b>: PDF com retiradas de hoje\n"

                "• <b>Estoque Baixo</b>: planilha + PDF para download\n\n"

                "<i>Dica:</i> toque em um botão abaixo."

            )

            data = {

                "chat_id": chat_id,

                "text": text,

                "parse_mode": "HTML",

                "reply_markup": payload,

            }

            resp = requests.post(url, json=data, timeout=10)

            return resp.json()

        except Exception as e:

            logger.error(f"Erro ao enviar menu de relatórios: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def send_items_menu(chat_id: str) -> dict[str, Any]:

        """Envia submenu de itens/estoque."""

        options = [

            ["📦 Itens Cadastrados"],

            ["🔎 Buscar Item (/estoque)", "📉 Baixar Planilha Estoque Baixo"],

            ["⬅️ Menu", "❌ Cancelar"],

        ]

        payload = TelegramService._build_reply_keyboard(options)

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Bot não configurado"}

        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="sendMessage")

            data = {

                "chat_id": chat_id,

                "text": (

                    "📦 <b>Itens & Estoque</b>\n"

                    "━━━━━━━━━━━━━━━━━━━━\n\n"

                    "Escolha uma opção:\n\n"

                    "• <b>Itens Cadastrados</b>: navegar por categorias\n"

                    "• <b>Buscar Item</b>: use /estoque + termo\n"

                    "• <b>Estoque Baixo</b>: baixar XLSX/PDF\n"

                ),

                "parse_mode": "HTML",

                "reply_markup": payload,

            }

            resp = requests.post(url, json=data, timeout=10)

            return resp.json()

        except Exception as e:

            logger.error(f"Erro ao enviar menu de itens: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def send_admin_menu(chat_id: str) -> dict[str, Any]:

        """Envia menu principal para administradores."""

        can_create_item = False

        try:

            tu = db.session.query(TelegramUser).filter_by(chat_id=str(chat_id)).first()

            if tu:

                can_create_item = getattr(tu, "can_create_item_via_telegram", False)

        except Exception:

            pass

        options = [

            ["📊 Relatórios & Retiradas", "📦 Itens & Estoque"],

            ["📸 Escanear Código"],

            (["🆕 Cadastrar Item"] if can_create_item else []),

            ["📉 Baixar Planilha Estoque Baixo"],

            ["/ajuda", "/meuid", "❌ Cancelar"],

        ]

        options = [row for row in options if row]

        payload = TelegramService._build_reply_keyboard(options)

        # sendMessage with reply_markup

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Bot não configurado"}

        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="sendMessage")

            data = {

                "chat_id": chat_id,

                "text": (

                    "🛡️ <b>Menu do Administrador</b>\n"

                    "━━━━━━━━━━━━━━━━━━━━\n\n"

                    "Escolha uma opção abaixo:" 

                ),

                "parse_mode": "HTML",

                "reply_markup": payload,

            }

            resp = requests.post(url, json=data, timeout=10)

            return resp.json()

        except Exception as e:

            logger.error(f"Erro ao enviar menu admin: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def send_sector_menu(chat_id: str, setor: str | None = None) -> dict[str, Any]:

        """Envia menu específico de setor (Zeladores, Supervisores, Encarregados)."""

        can_create_item = False

        try:

            tu = db.session.query(TelegramUser).filter_by(chat_id=str(chat_id)).first()

            if tu:

                can_create_item = getattr(tu, "can_create_item_via_telegram", False)

        except Exception:

            pass

        options = [

            ["Todas as ferramentas retiradas", "Devolvidas"],

            ["Pendentes", "Onde foram usadas"],

            ["📸 Escanear Código"],

            (["🆕 Cadastrar Item"] if can_create_item else []),

            ["/ajuda"],

        ]

        options = [row for row in options if row]

        payload = TelegramService._build_reply_keyboard(options)

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Bot não configurado"}

        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="sendMessage")

            data = {

                "chat_id": chat_id,

                "text": (

                    f"👷 <b>Menu — {html.escape(setor or 'Setor')}</b>\n"

                    "━━━━━━━━━━━━━━━━━━━━\n\n"

                    "Escolha uma opção abaixo:"

                ),

                "parse_mode": "HTML",

                "reply_markup": payload,

            }

            resp = requests.post(url, json=data, timeout=10)

            return resp.json()

        except Exception as e:

            logger.error(f"Erro ao enviar menu setor: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def send_user_menu(chat_id: str) -> dict[str, Any]:

        """Envia menu básico para usuários padrão."""

        can_create_item = False

        try:

            tu = db.session.query(TelegramUser).filter_by(chat_id=str(chat_id)).first()

            if tu:

                can_create_item = getattr(tu, "can_create_item_via_telegram", False)

        except Exception:

            pass

        options = [

            ["📸 Escanear Código"],

            ["🔎 Buscar Item (/estoque)"],

            (["🆕 Cadastrar Item"] if can_create_item else []),

            ["/ajuda", "/meuid", "❌ Cancelar"],

        ]

        options = [row for row in options if row]

        payload = TelegramService._build_reply_keyboard(options)

        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return {"success": False, "error": "Bot não configurado"}

        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="sendMessage")

            data = {

                "chat_id": chat_id,

                "text": (

                    "👤 <b>Menu</b>\n"

                    "━━━━━━━━━━━━━━━━━━━━\n\n"

                    "Escolha uma opção abaixo:"

                ),

                "parse_mode": "HTML",

                "reply_markup": payload,

            }

            resp = requests.post(url, json=data, timeout=10)

            return resp.json()

        except Exception as e:

            logger.error(f"Erro ao enviar menu usuário: {e}")

            return {"success": False, "error": str(e)}



    @staticmethod

    def generate_estoque_baixo_xlsx(target_path: str) -> str:

        """Gera planilha XLSX de itens com estoque abaixo do mínimo. Retorna caminho salvo."""

        try:

            from openpyxl import Workbook

            from openpyxl.styles import Alignment, Font, PatternFill

        except Exception:

            raise



        wb = Workbook()

        ws = wb.active

        ws.title = "Estoque Baixo"

        headers = ["Código", "Descrição", "Categoria", "Marca", "Saldo", "Mínimo", "Localização", "Última Movimentação"]

        ws.append(headers)

        header_font = Font(bold=True, color="FFFFFF")

        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")

        header_alignment = Alignment(horizontal="center", vertical="center")

        for cell in ws[1]:

            cell.font = header_font

            cell.fill = header_fill

            cell.alignment = header_alignment



        items = db.session.query(Item).all()

        for it in items:

            try:

                saldo = it.get_saldo_atual()

            except Exception:

                saldo = 0

            if saldo <= (it.estoque_minimo or 0):

                # última movimentação simples: maior data entre entradas/saídas

                last_mov = None

                last_e = db.session.query(Entrada).filter_by(codigo_item=it.codigo_item).order_by(Entrada.data_entrada.desc()).first()

                last_s = db.session.query(Saida).filter_by(codigo_item=it.codigo_item).order_by(Saida.data_saida.desc()).first()

                if last_e and (not last_mov or last_e.data_entrada > last_mov):

                    last_mov = last_e.data_entrada

                if last_s and (not last_mov or last_s.data_saida > last_mov):

                    last_mov = last_s.data_saida

                last_mov_str = TimeService.format_local(last_mov) if last_mov else "-"

                codigo_display = it.codigo_item[-4:] if it.codigo_item and len(it.codigo_item) >= 4 else (it.codigo_item or "N/D")

                ws.append([codigo_display, it.descricao, it.categoria, it.marca or "-", saldo, it.estoque_minimo, it.localizacao or "-", last_mov_str])



        # Ajustar largura das colunas

        ws.column_dimensions["A"].width = 8

        ws.column_dimensions["B"].width = 40

        ws.column_dimensions["C"].width = 22

        ws.column_dimensions["D"].width = 18

        ws.column_dimensions["E"].width = 10

        ws.column_dimensions["F"].width = 10

        ws.column_dimensions["G"].width = 24

        ws.column_dimensions["H"].width = 22



        Path(target_path).parent.mkdir(parents=True, exist_ok=True)

        wb.save(target_path)

        return target_path



    @staticmethod

    def generate_estoque_baixo_pdf(target_path: str) -> str:

        """Gera PDF de itens com estoque abaixo do mínimo. Retorna caminho salvo."""

        try:

            from reportlab.lib import colors

            from reportlab.lib.pagesizes import A4, landscape

            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

            from reportlab.lib.units import cm

            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        except Exception as e:

            logger.error(f"reportlab não instalado/indisponível: {e}")

            raise



        items = db.session.query(Item).all()

        low_stock_rows: list[list[str]] = []



        for it in items:

            try:

                saldo = it.get_saldo_atual()

            except Exception:

                saldo = 0

            if saldo <= (it.estoque_minimo or 0):

                last_mov = None

                last_e = (

                    db.session.query(Entrada)

                    .filter_by(codigo_item=it.codigo_item)

                    .order_by(Entrada.data_entrada.desc())

                    .first()

                )

                last_s = (

                    db.session.query(Saida)

                    .filter_by(codigo_item=it.codigo_item)

                    .order_by(Saida.data_saida.desc())

                    .first()

                )

                if last_e and (not last_mov or last_e.data_entrada > last_mov):

                    last_mov = last_e.data_entrada

                if last_s and (not last_mov or last_s.data_saida > last_mov):

                    last_mov = last_s.data_saida

                last_mov_str = TimeService.format_local(last_mov) if last_mov else "-"



                low_stock_rows.append(

                    [

                        str(it.codigo_item or "-"),

                        (it.descricao or "-")[:40],

                        (it.categoria or "-")[:20],

                        (it.marca or "-")[:14],

                        str(saldo),

                        str(it.estoque_minimo or 0),

                        (it.localizacao or "-")[:18],

                        (last_mov_str or "-")[:16],

                    ]

                )



        Path(target_path).parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(target_path, pagesize=landscape(A4))

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(

            "TitleGalint",

            parent=styles["Heading1"],

            fontSize=16,

            textColor=colors.HexColor("#111827"),

            alignment=1,

            spaceAfter=6,

        )

        subtitle_style = ParagraphStyle(

            "SubtitleGalint",

            parent=styles["Normal"],

            fontSize=9,

            textColor=colors.HexColor("#374151"),

            alignment=1,

            leading=12,

            spaceAfter=10,

        )



        elements: list[Any] = []

        elements.append(Paragraph("RELATÓRIO DIÁRIO DE RETIRADAS DE MATERIAIS", title_style))

        from ..utils.report_branding import get_company_header_html

        elements.append(Paragraph(get_company_header_html(), subtitle_style))

        elements.append(Spacer(1, 0.3 * cm))



        data = [["Código", "Descrição", "Categoria", "Marca", "Saldo", "Mín", "Local", "Última Mov."]] + low_stock_rows

        table = Table(

            data,

            colWidths=[3.2 * cm, 7.0 * cm, 3.8 * cm, 2.8 * cm, 1.7 * cm, 1.5 * cm, 3.2 * cm, 3.2 * cm],

        )

        table.setStyle(

            TableStyle(

                [

                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#366092")),

                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),

                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

                    ("FONTSIZE", (0, 0), (-1, 0), 10),

                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),

                    ("GRID", (0, 0), (-1, -1), 0.6, colors.black),

                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),

                    ("FONTSIZE", (0, 1), (-1, -1), 8),

                ]

            )

        )

        elements.append(table)

        doc.build(elements)

        return target_path



    @staticmethod

    def generate_saidas_dia_pdf(target_path: str, scope: str = "all") -> str:

        """Gera PDF com as saídas do dia (retiradas de hoje)."""

        try:

            from reportlab.lib import colors

            from reportlab.lib.pagesizes import A4, landscape

            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

            from reportlab.lib.units import cm

            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

        except Exception as e:

            logger.error(f"reportlab não instalado/indisponível: {e}")

            raise



        def _format_data_hora(dt) -> str:

            if not dt:

                return "-"

            local_dt = TimeService.to_local(dt)

            return f"{local_dt.day}/{local_dt.month}/{local_dt.strftime('%y')} - {local_dt.hour}h{local_dt.strftime('%M')}m"



        now_local = TimeService.now_local()

        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        end_local = start_local + timedelta(days=1)

        start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)

        end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)



        q = db.session.query(Saida).filter(Saida.data_saida >= start_utc, Saida.data_saida < end_utc)

        if scope == "tools":

            q = q.join(Item, Saida.codigo_item == Item.codigo_item).filter(Item.categoria.ilike("%ferramenta%"))

        elif scope == "materials":

            q = q.join(Item, Saida.codigo_item == Item.codigo_item).filter(~Item.categoria.ilike("%ferramenta%"))

        saidas = q.order_by(Saida.data_saida.asc()).all()



        from sqlalchemy import func

        tipos_retorno = ["devolucao_ferramenta", "devolucao_material"]

        if scope == "tools":

            tipos_retorno = ["devolucao_ferramenta"]

        elif scope == "materials":

            tipos_retorno = ["devolucao_material"]



        devolucoes = (

            db.session.query(InventarioEvento.codigo_item, func.coalesce(func.sum(InventarioEvento.quantidade), 0))

            .filter(InventarioEvento.data_evento >= start_utc, InventarioEvento.data_evento < end_utc)

            .filter(InventarioEvento.tipo.in_(tipos_retorno))

            .group_by(InventarioEvento.codigo_item)

            .all()

        )

        devolucoes_map = {codigo: float(qtd or 0) for codigo, qtd in devolucoes if codigo}



        # Ordenar por ordem cronológica (data crescente)

        saidas = sorted(

            saidas,

            key=lambda s: s.data_saida or datetime.min,

        )



        Path(target_path).parent.mkdir(parents=True, exist_ok=True)



        doc = SimpleDocTemplate(

            target_path,

            pagesize=landscape(A4),

            leftMargin=0.8 * cm,

            rightMargin=0.8 * cm,

            topMargin=0.8 * cm,

            bottomMargin=0.8 * cm,

            title="Saídas do dia",

            author="GALINT",

        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(

            "TitleGalint",

            parent=styles["Heading1"],

            fontSize=16,

            textColor=colors.HexColor("#111827"),

            alignment=1,

            spaceAfter=6,

        )

        subtitle_style = ParagraphStyle(

            "SubtitleGalint",

            parent=styles["Normal"],

            fontSize=9,

            textColor=colors.HexColor("#374151"),

            alignment=1,

            leading=12,

            spaceAfter=10,

        )



        title = Paragraph("RELATÓRIO DIÁRIO DE RETIRADAS DE MATERIAIS", title_style)

        from ..utils.report_branding import get_company_header_html

        subtitle = Paragraph(get_company_header_html(), subtitle_style)

        footer_dt = TimeService.now_local()

        footer_text = f"{footer_dt.day}/{footer_dt.month}/{footer_dt.strftime('%y')} - {footer_dt.hour}h{footer_dt.strftime('%M')}m"



        def _draw_footer(canvas, _doc):

            canvas.saveState()

            canvas.setFont("Helvetica", 8)

            canvas.setFillColor(colors.HexColor("#374151"))

            canvas.drawCentredString(A4[1] / 2, 0.6 * cm, footer_text)

            canvas.restoreState()



        if not saidas:

            doc.build(

                [title, subtitle, Spacer(1, 0.4 * cm), Paragraph("Nenhuma saída registrada hoje.", styles["Italic"])],

                onFirstPage=_draw_footer,

                onLaterPages=_draw_footer,

            )

            return target_path



        elements: list[Any] = [title, subtitle, Spacer(1, 0.4 * cm)]

        body_style = styles["Normal"]

        body_style.fontSize = 8



        header_row = ["Código", "Descrição", "Qtd", "Usuário", "Data", "Obs"]

        rows_per_page = 25



        def _build_table(page_rows: list[list[Any]]) -> Table:

            table = Table(page_rows, colWidths=[1.6 * cm, 9.0 * cm, 1.4 * cm, 3.4 * cm, 3.6 * cm, 4.0 * cm])

            table.setStyle(

                TableStyle(

                    [

                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),

                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),

                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

                        ("FONTSIZE", (0, 0), (-1, 0), 9),

                        ("FONTSIZE", (0, 1), (-1, -1), 8),

                        ("ALIGN", (2, 1), (2, -1), "RIGHT"),

                        ("ALIGN", (4, 1), (4, -1), "LEFT"),

                        ("VALIGN", (0, 0), (-1, -1), "TOP"),

                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),

                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),

                        ("LEFTPADDING", (0, 0), (-1, -1), 3),

                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),

                        ("TOPPADDING", (0, 0), (-1, -1), 2),

                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),

                    ]

                )

            )

            return table



        current_rows: list[list[Any]] = [header_row]

        current_count = 0



        for s in saidas:

            if current_count >= rows_per_page:

                elements.append(_build_table(current_rows))

                elements.append(PageBreak())

                current_rows = [header_row]

                current_count = 0



            codigo = s.codigo_item or "-"

            codigo = str(codigo)[-5:]

            descricao = (s.item.descricao if s.item else "Item removido") or "-"

            

            # Formatar observação: sempre incluir local se existir

            obs_parts = []

            

            # Se for fracionado, extrair apenas valor retirado e local

            if getattr(s, "usou_fracao", False):

                retirada_litros = getattr(s, "quantidade_retirada_em_litros", None)

                retirada_quilos = getattr(s, "quantidade_retirada_em_quilos", None)

                local = (s.local_servico or "").strip()

                

                fracao_info = []

                if retirada_litros:

                    fracao_info.append(f"{float(retirada_litros):.2f}L")

                if retirada_quilos:

                    fracao_info.append(f"{float(retirada_quilos):.2f}kg")

                

                if fracao_info:

                    obs_parts.append(" / ".join(fracao_info).lower())

                if local:

                    obs_parts.append(f"local: {local.lower()}")

            else:

                # Não fracionado: mostrar local + observação original

                local = (s.local_servico or "").strip()

                obs_original = (s.observacao or "").strip()

                

                if local:

                    obs_parts.append(f"Local: {local}")

                if obs_original and obs_original.upper() != local.upper():

                    obs_parts.append(obs_original)

            

            # Adicionar informação de devolução se houver

            devolvido_qtd = devolucoes_map.get(s.codigo_item)

            if devolvido_qtd and devolvido_qtd > 0:

                obs_parts.append(f"DEVOLUÇÃO: {devolvido_qtd:g}")

            

            observacao = " | ".join(obs_parts) if obs_parts else "-"

            

            data_fmt = _format_data_hora(s.data_saida)

            usuario = (s.usuario.nome if s.usuario else "-") or "-"

            current_rows.append([

                codigo,

                Paragraph(str(descricao), body_style),

                str(s.quantidade),

                Paragraph(str(usuario), body_style),

                data_fmt,

                Paragraph(str(observacao), body_style),

            ])

            current_count += 1



        if len(current_rows) > 1:

            elements.append(_build_table(current_rows))



        doc.build(elements, onFirstPage=_draw_footer, onLaterPages=_draw_footer)

        return target_path



    @staticmethod

    def _get_category_emoji(categoria: str) -> str:

        cat_lower = (categoria or "").lower()

        emoji_map = {

            "ferrament": "🔧",

            "elétric": "⚡",

            "eletric": "âš¡",

            "hidrául": "💧",

            "hidraul": "💧",

            "pintur": "🎨",

            "constru": "🏗️",

            "seguran": "🦺",

            "limpez": "🧹",

            "piscin": "🏊",

            "jardin": "🌱",

        }

        for key, emoji in emoji_map.items():

            if key in cat_lower:

                return emoji

        return "📦"



    @staticmethod

    def _send_category_menu(chat_id: str) -> None:

        """Envia menu interativo de categorias via inline keyboard."""

        items = db.session.query(Item).order_by(Item.categoria, Item.descricao).all()

        if not items:

            TelegramService.send_message(chat_id, "Nenhum item cadastrado.", parse_mode=None)

            return



        grouped: dict[str, list[Item]] = defaultdict(list)

        for it in items:

            categoria = (it.categoria or "Sem categoria").strip() or "Sem categoria"

            grouped[categoria].append(it)



        config = TelegramService.get_config()

        if not config or not config.bot_token:

            return



        keyboard: list[list[dict[str, str]]] = []

        for categoria in sorted(grouped.keys(), key=lambda s: s.lower()):

            count = len(grouped[categoria])

            emoji = TelegramService._get_category_emoji(categoria)

            # callback_data não pode ser enorme; manter categoria como está e confiar em tamanho razoável.

            keyboard.append([

                {"text": f"{emoji} {categoria} ({count})", "callback_data": f"cat:{categoria}"}

            ])

        keyboard.append([

            {"text": "⬅️ Itens & Estoque", "callback_data": "menu:items"},

            {"text": "❌ Cancelar", "callback_data": "menu:admin"},

        ])



        msg = (

            "🏷️ <b>Itens por Categoria</b>\n"

            "━━━━━━━━━━━━━━━━━━━━\n\n"

            f"Total: <b>{len(items)}</b> itens\n"

            f"Categorias: <b>{len(grouped)}</b>\n\n"

            "Toque em uma categoria para ver os itens."

        )



        try:

            url = TelegramService.BASE_URL.format(token=config.bot_token, method="sendMessage")

            payload = {

                "chat_id": chat_id,

                "text": msg,

                "parse_mode": "HTML",

                "reply_markup": {"inline_keyboard": keyboard},

            }

            requests.post(url, json=payload, timeout=10)

        except Exception as e:

            logger.error(f"Erro ao enviar menu de categorias: {e}")



    @staticmethod

    def _send_category_items(chat_id: str, categoria: str) -> None:

        """Envia itens de uma categoria com layout organizado."""

        categoria_clean = (categoria or "Sem categoria").strip() or "Sem categoria"

        q = db.session.query(Item)

        if categoria_clean == "Sem categoria":

            q = q.filter((Item.categoria == None) | (Item.categoria == "") | (Item.categoria.ilike("%sem categoria%")))

        else:

            q = q.filter(Item.categoria == categoria_clean)



        items = q.order_by(Item.descricao).all()

        if not items:

            TelegramService.send_message(chat_id, f"Nenhum item encontrado na categoria: {categoria_clean}", parse_mode=None)

            return



        emoji = TelegramService._get_category_emoji(categoria_clean)

        safe_cat = html.escape(categoria_clean)



        header = [

            f"{emoji} <b>{safe_cat}</b>",

            "━━━━━━━━━━━━━━━━━━━━",

            f"<i>{len(items)} itens</i>",

            "",

        ]



        blocks: list[str] = []

        for idx, it in enumerate(items[:30], 1):

            try:

                saldo = it.get_saldo_atual()

            except Exception:

                saldo = "?"

            unidade = html.escape((it.unidade or "un").strip())

            descricao = html.escape((it.descricao or "Sem descrição")[:60])

            marca = html.escape(it.marca) if it.marca else ""

            localizacao = html.escape(it.localizacao) if it.localizacao else ""

            status_emoji = "✅" if (isinstance(saldo, (int, float)) and saldo > (it.estoque_minimo or 0)) else "⚠️"



            lines = [

                f"<b>{idx}.</b> {status_emoji} <code>{html.escape(str(it.codigo_item or '-'))}</code>",

                f"    📝 {descricao}" + (f" | <i>{marca}</i>" if marca else ""),

                f"    📊 Saldo: <b>{html.escape(str(saldo))}</b> {unidade} (Mín: {html.escape(str(it.estoque_minimo or 0))})",

            ]

            if localizacao:

                lines.append(f"    📍 {localizacao}")

            blocks.append("\n".join(lines))



        if len(items) > 30:

            blocks.append(f"\n… +{len(items) - 30} itens (consulte o painel web para lista completa)")



        message = "\n".join(header) + "\n\n".join(blocks)

        if len(message) > 3900:

            message = message[:3850] + "\n\n… (mensagem truncada)"



        config = TelegramService.get_config()

        if config and config.bot_token:

            try:

                url = TelegramService.BASE_URL.format(token=config.bot_token, method="sendMessage")

                nav = [

                    {"text": "⬅️ Categorias", "callback_data": "menu:categories"},

                    {"text": "📦 Itens & Estoque", "callback_data": "menu:items"},

                ]

                payload = {

                    "chat_id": chat_id,

                    "text": message,

                    "parse_mode": "HTML",

                    "reply_markup": {"inline_keyboard": [nav, [{"text": "❌ Cancelar", "callback_data": "menu:admin"}]]},

                }

                requests.post(url, json=payload, timeout=10)

                return

            except Exception as e:

                logger.error(f"Erro ao enviar itens da categoria: {e}")



        TelegramService.send_message(chat_id, message, parse_mode="HTML")



    @staticmethod

    def handle_callback_query(callback_query: dict[str, Any]) -> None:

        """Processa cliques de inline keyboard (categorias e navegação)."""

        try:

            data = (callback_query.get("data") or "").strip()

            message = callback_query.get("message") or {}

            chat_id = str((message.get("chat") or {}).get("id") or "")

            callback_id = callback_query.get("id")

            if not chat_id:

                return



            if callback_id and TelegramService._is_duplicate_callback(str(callback_id)):

                return



            config = TelegramService.get_config()

            if config and config.bot_token and callback_id:

                try:

                    url = TelegramService.BASE_URL.format(token=config.bot_token, method="answerCallbackQuery")

                    requests.post(url, json={"callback_query_id": callback_id}, timeout=5)

                except Exception:

                    pass



            if data.startswith("cat:"):

                categoria = data[4:]

                TelegramService._send_category_items(chat_id, categoria)

                return

            if data == "menu:categories":

                TelegramService._send_category_menu(chat_id)

                return

            if data == "menu:items":

                TelegramService.send_items_menu(chat_id)

                return

            if data == "menu:reports":

                TelegramService.send_reports_menu(chat_id)

                return

            if data == "menu:admin":

                TelegramService.send_admin_menu(chat_id)

                return



            if data == "cancel":

                TelegramService.send_message(chat_id, "❌ Operação cancelada.", parse_mode=None)

                return



            if data.startswith("details:"):

                codigo_item = data.split(":", 1)[1].strip()

                TelegramService._send_item_details(chat_id, codigo_item)

                return



            if data.startswith("withdraw:"):

                codigo_item = data.split(":", 1)[1].strip()

                TelegramService._handle_withdrawal_by_barcode(chat_id, codigo_item)

                return



            if data.startswith("create_item:"):

                # Iniciar fluxo de cadastro com código pré-preenchido

                codigo_barras = data.split(":", 1)[1].strip()

                allowed, _ = TelegramService._can_user_create_item_via_telegram(chat_id)

                if not allowed:

                    TelegramService.send_message(

                        chat_id,

                        "❌ Você não tem permissão para cadastrar itens via Telegram.",

                        parse_mode=None

                    )

                    return

                

                # Limpar conversa anterior

                try:

                    TelegramConversation.query.filter_by(chat_id=str(chat_id)).delete()

                    db.session.commit()

                except Exception:

                    db.session.rollback()

                

                # Iniciar fluxo com código de barras já preenchido

                meta = {"codigo": codigo_barras}

                TelegramService._item_create_update(chat_id, "item_create:descricao", meta)

                

                TelegramService.send_message(

                    chat_id,

                    (

                        "🆕 <b>Cadastro de Item</b>\n"

                        "━━━━━━━━━━━━━━━━━━━━\n\n"

                        f"✅ <b>Código de barras:</b> <code>{html.escape(codigo_barras)}</code>\n\n"

                        "Informe os próximos dados:\n"

                        "Use <b>/pular</b> para campos opcionais e <b>/cancelar</b> para sair.\n\n"

                        "<b>2) Descrição do item:</b>"

                    ),

                    parse_mode="HTML"

                )

                return



            if data.startswith("edit_item:"):

                # Iniciar fluxo de edição de item existente

                codigo_item = data.split(":", 1)[1].strip()

                return TelegramService._start_item_edit_flow(chat_id, codigo_item)

                return



            if data.startswith("return:"):

                TelegramService.send_message(

                    chat_id,

                    "⚠️ Devoluções estão bloqueadas no Telegram. Use o APK ou o painel Web.",

                    parse_mode=None,

                )

                return



            # Fluxo avançado de relatórios (período/categoria/formato)

            # Import local para evitar import circular (telegram_conversation -> telegram_service)

            try:

                from .telegram_conversation import TelegramConversationManager



                if TelegramConversationManager.handle_callback(data, chat_id):

                    return

            except Exception:

                # Não interromper outros callbacks caso falhe

                pass



        except Exception as e:

            logger.exception(f"Erro ao processar callback query: {e}")



    @staticmethod

    def handle_menu_text(chat_id: str, text: str) -> bool:

        """Interpreta texto vindo do teclado/menu e executa ação, retornando True se tratou."""

        t = text.strip()

        norm = TelegramService._normalize_menu_text(t)

        user = TelegramService._get_user_by_chat_id(chat_id)

        try:

            # Fluxo de cadastro de item (prioritário)

            if TelegramService._handle_item_create_text(chat_id, t):

                return True



            # Fluxo de edição de item (prioritário)

            if TelegramService._handle_item_edit_text(chat_id, t):

                return True



            # Wrap handler logic to ensure exceptions are logged and an error

            # message is sent back to the user, avoiding silent failures.



            # Atalhos de navegação (submenus)

            if norm in ("relatórios & retiradas", "relatorios & retiradas", "relatórios e retiradas", "relatorios e retiradas"):

                # apenas admin (para evitar acesso amplo a dados)

                if TelegramService._is_privileged_user(user):

                    TelegramService.send_reports_menu(chat_id)

                else:

                    TelegramService.send_message(chat_id, "❌ Opção disponível apenas para administradores.", parse_mode=None)

                return True



            if norm in ("escanear codigo", "escanear código", "scanear", "scanner") or t.strip().lower().startswith("/scanear"):

                TelegramService.handle_command_scanear(chat_id)

                return True



            if norm in ("cadastrar item", "novo item", "cadastro item") or t.strip().lower().startswith("/cadastrar_item"):

                return TelegramService._start_item_create_flow(chat_id)



            if norm in ("itens & estoque", "itens e estoque", "itens e estoques", "itens/estoque"):

                if TelegramService._is_privileged_user(user):

                    TelegramService.send_items_menu(chat_id)

                else:

                    TelegramService.send_message(chat_id, "❌ Opção disponível apenas para administradores.", parse_mode=None)

                return True



            if norm in ("menu", "voltar", "voltar ao menu", "inicio") or t in ("⬅️ Menu", "🔙 Menu"):

                if TelegramService._is_privileged_user(user):

                    TelegramService.send_admin_menu(chat_id)

                elif user and getattr(user, "setor", None) and str(user.setor).upper() in ("ZELADORES", "SUPERVISORES", "ENCARREGADOS"):

                    TelegramService.send_sector_menu(chat_id, setor=user.setor)

                else:

                    TelegramService.send_message(chat_id, "Envie /start para ver o menu.", parse_mode=None)

                return True



            if norm in ("cancelar",) or t in ("❌ Cancelar",):

                # Em reply keyboard, "Cancelar" volta ao menu principal

                if TelegramService._is_privileged_user(user):

                    TelegramService.send_admin_menu(chat_id)

                elif user and getattr(user, "setor", None) and str(user.setor).upper() in ("ZELADORES", "SUPERVISORES", "ENCARREGADOS"):

                    TelegramService.send_sector_menu(chat_id, setor=user.setor)

                else:

                    TelegramService.send_message(chat_id, "Envie /start para ver o menu.", parse_mode=None)

                return True



            # Submenu: Relatórios & Retiradas (igual aos prints)

            if norm.startswith("relatório de ferramentas") or norm.startswith("relatorio de ferramentas"):

                if TelegramService._is_privileged_user(user):

                    from .telegram_conversation import TelegramConversationManager



                    TelegramConversationManager.start_withdrawals_report_flow(chat_id, scope="tools")

                else:

                    TelegramService.send_message(chat_id, "❌ Opção disponível apenas para administradores.", parse_mode=None)

                return True



            if norm.startswith("relatório de materiais") or norm.startswith("relatorio de materiais"):

                if TelegramService._is_privileged_user(user):

                    from .telegram_conversation import TelegramConversationManager



                    TelegramConversationManager.start_withdrawals_report_flow(chat_id, scope="materials")

                else:

                    TelegramService.send_message(chat_id, "❌ Opção disponível apenas para administradores.", parse_mode=None)

                return True



            if norm.startswith("relatório geral") or norm.startswith("relatorio geral"):

                if TelegramService._is_privileged_user(user):

                    from .telegram_conversation import TelegramConversationManager



                    TelegramConversationManager.start_withdrawals_report_flow(chat_id, scope="all")

                else:

                    TelegramService.send_message(chat_id, "❌ Opção disponível apenas para administradores.", parse_mode=None)

                return True



            if norm.startswith("estoque baixo"):

                # Atalho do submenu para enviar XLSX+PDF

                if TelegramService._is_privileged_user(user):

                    # Reaproveita o fluxo existente

                    reports_dir = Path("instance") / "reports"

                    reports_dir.mkdir(parents=True, exist_ok=True)

                    timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')

                    target_xlsx = str(reports_dir / f"estoque_baixo_{timestamp}.xlsx")

                    target_pdf = str(reports_dir / f"estoque_baixo_{timestamp}.pdf")

                    try:

                        TelegramService.send_message(chat_id, "📊 Gerando relatórios... Aguarde.", parse_mode=None)

                        TelegramService.generate_estoque_baixo_xlsx(target_xlsx)

                        TelegramService.send_document(chat_id, target_xlsx, caption="📗 Estoque Baixo (XLSX)")

                        try:

                            TelegramService.generate_estoque_baixo_pdf(target_pdf)

                            TelegramService.send_document(chat_id, target_pdf, caption="📕 Estoque Baixo (PDF)")

                        except Exception as pdf_err:

                            logger.error(f"Erro ao gerar PDF: {pdf_err}")

                            TelegramService.send_message(chat_id, "⚠️ PDF indisponível no momento. XLSX enviado.", parse_mode=None)

                    except Exception as e:

                        logger.exception("Erro ao gerar/enviar planilha estoque baixo")

                        TelegramService.send_message(chat_id, f"Erro ao gerar relatórios: {e}", parse_mode=None)

                else:

                    TelegramService.send_message(chat_id, "❌ Opção disponível apenas para administradores.", parse_mode=None)

                return True



            if norm.startswith("saídas do dia") or norm.startswith("saidas do dia"):

                if TelegramService._is_privileged_user(user):

                    reports_dir = Path("instance") / "reports"

                    reports_dir.mkdir(parents=True, exist_ok=True)

                    timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')

                    target_pdf = str(reports_dir / f"saidas_dia_{timestamp}.pdf")

                    try:

                        TelegramService.send_message(chat_id, "📄 Gerando PDF das saídas de hoje...", parse_mode=None)

                        TelegramService.generate_saidas_dia_pdf(target_pdf)

                        TelegramService.send_document(chat_id, target_pdf, caption="📄 Saídas do Dia (PDF)")

                    except Exception as e:

                        logger.exception("Erro ao gerar/enviar PDF de saídas do dia")

                        TelegramService.send_message(chat_id, f"Erro ao gerar PDF: {e}", parse_mode=None)

                else:

                    TelegramService.send_message(chat_id, "❌ Opção disponível apenas para administradores.", parse_mode=None)

                return True



            if norm in ("voltar ao menu",) or t in ("⬅️ Voltar ao Menu",):

                if TelegramService._is_privileged_user(user):

                    TelegramService.send_admin_menu(chat_id)

                else:

                    TelegramService.send_message(chat_id, "Envie /start para ver o menu.", parse_mode=None)

                return True



            # Admin options (aceitar versões com emoji)

            if norm == "retiradas de ferramentas" or norm == "retiradas de ferramenta":

                # enviar resumo das retiradas de ferramentas (hoje e últimos 6 meses)

                res = TelegramService._send_withdrawals_summary(chat_id, category_like="%ferramentas%")

                return True

            if norm == "retiradas de materiais" or norm == "retiradas de material":

                res = TelegramService._send_withdrawals_summary(chat_id, exclude_category_like="%ferramentas%")

                return True

            if norm == "itens cadastrados":

                TelegramService._send_category_menu(chat_id)

                return True

            if norm in ("baixar planilha estoque baixo", "baixar planilha de baixo estoque", "estoque baixo"):

                reports_dir = Path("instance") / "reports"

                reports_dir.mkdir(parents=True, exist_ok=True)

                timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')

                target_xlsx = str(reports_dir / f"estoque_baixo_{timestamp}.xlsx")

                target_pdf = str(reports_dir / f"estoque_baixo_{timestamp}.pdf")

                try:

                    TelegramService.send_message(chat_id, "📊 Gerando relatórios... Aguarde.", parse_mode=None)

                    TelegramService.generate_estoque_baixo_xlsx(target_xlsx)

                    TelegramService.send_document(chat_id, target_xlsx, caption="📗 Estoque Baixo (XLSX)")

                    try:

                        TelegramService.generate_estoque_baixo_pdf(target_pdf)

                        TelegramService.send_document(chat_id, target_pdf, caption="📕 Estoque Baixo (PDF)")

                    except Exception as pdf_err:

                        logger.error(f"Erro ao gerar PDF: {pdf_err}")

                        TelegramService.send_message(chat_id, "⚠️ PDF indisponível no momento. XLSX enviado.", parse_mode=None)

                except Exception as e:

                    logger.exception("Erro ao gerar/enviar planilha estoque baixo")

                    TelegramService.send_message(chat_id, f"Erro ao gerar relatórios: {e}", parse_mode=None)

                return True



            # Sector options

            if norm == "todas as ferramentas retiradas":

                TelegramService._send_withdrawals_list(chat_id, category_like="%ferramentas%")

                return True

            if norm == "devolvidas":

                TelegramService._send_returned_list(chat_id)

                return True

            if norm == "pendentes":

                TelegramService._send_pending_list(chat_id)

                return True

            if norm == "onde foram usadas":

                TelegramService._send_where_used(chat_id)

                return True



            return False

        except Exception as e:

            # Log exception and notify user

            logger.exception(f"Erro ao processar opção do menu: {text}")

            try:

                TelegramService.send_message(chat_id, "❌ Ocorreu um erro ao processar sua solicitação. Tente novamente mais tarde.")

            except Exception:

                logger.exception("Falha ao enviar mensagem de erro ao usuário")

            return False



    @staticmethod

    def _send_withdrawals_summary(chat_id: str, category_like: str | None = None, exclude_category_like: str | None = None) -> None:

        """Envia resumo de retiradas agrupadas por item nos últimos 6 meses e hoje."""

        from sqlalchemy import func

        six_months = datetime.utcnow() - timedelta(days=180)

        # total hoje

        today = datetime.utcnow().date()



        q = db.session.query(Saida.codigo_item, func.sum(Saida.quantidade).label('total')).group_by(Saida.codigo_item)

        q = q.filter(Saida.data_saida >= six_months)

        joins = []

        if category_like:

            q = q.join(Item, Saida.codigo_item == Item.codigo_item).filter(Item.categoria.ilike(category_like))

        if exclude_category_like:

            q = q.join(Item, Saida.codigo_item == Item.codigo_item).filter(~Item.categoria.ilike(exclude_category_like))



        results = q.order_by(func.sum(Saida.quantidade).desc()).limit(50).all()

        if not results:

            TelegramService.send_message(chat_id, "Nenhuma retirada encontrada no período solicitado.")

            return

        lines = [f"{r.codigo_item} — Qtd total (6m): {r.total}" for r in results]

        TelegramService.send_message(chat_id, "Resumo de retiradas (últimos 6 meses):\n" + "\n".join(lines[:50]))



    @staticmethod

    def _send_withdrawals_list(chat_id: str, category_like: str | None = None) -> None:

        """Envia lista detalhada das retiradas (últimos 6 meses)."""

        from sqlalchemy import func

        cutoff = datetime.utcnow() - timedelta(days=180)

        q = db.session.query(Saida).filter(Saida.data_saida >= cutoff)

        if category_like:

            q = q.join(Item, Saida.codigo_item == Item.codigo_item).filter(Item.categoria.ilike(category_like))

        items = q.order_by(Saida.data_saida.desc()).limit(200).all()

        if not items:

            TelegramService.send_message(chat_id, "Nenhuma retirada encontrada.")

            return

        lines = []

        for s in items[:200]:

            usuario = s.usuario.nome if s.usuario else (s.matricula or 'N/D')

            codigo = s.codigo_item or 'N/D'

            descricao = s.item.descricao if s.item else 'N/D'

            data = TimeService.format_local(s.data_saida) if s.data_saida else 'N/D'

            lines.append(f"{data} — {codigo} — {descricao} — {s.quantidade} — {usuario}")

        TelegramService.send_message(chat_id, "Lista de retiradas (até 200):\n" + "\n".join(lines))



    @staticmethod

    def _send_returned_list(chat_id: str) -> None:

        """Envia lista de devoluções (entradas vinculadas a saídas) nos últimos 6 meses."""

        cutoff = datetime.utcnow() - timedelta(days=180)

        entries = db.session.query(Entrada).filter(Entrada.data_entrada >= cutoff).order_by(Entrada.data_entrada.desc()).limit(200).all()

        if not entries:

            TelegramService.send_message(chat_id, "Nenhuma devolução encontrada.")

            return

        lines = [f"{TimeService.format_local(e.data_entrada)} — {e.codigo_item} — {e.quantidade}" for e in entries]

        TelegramService.send_message(chat_id, "Devoluções (últimos 6 meses):\n" + "\n".join(lines))



    @staticmethod

    def _send_pending_list(chat_id: str) -> None:

        """Envia lista de itens com diferenças entre saídas e entradas (pendentes)."""

        from sqlalchemy import func

        # total saídas e entradas por item

        sa = db.session.query(Saida.codigo_item, func.coalesce(func.sum(Saida.quantidade), 0).label('total_saida')).group_by(Saida.codigo_item).subquery()

        en = db.session.query(Entrada.codigo_item, func.coalesce(func.sum(Entrada.quantidade), 0).label('total_entrada')).group_by(Entrada.codigo_item).subquery()

        q = (

            db.session.query(Item.codigo_item, Item.descricao, (func.coalesce(sa.c.total_saida,0) - func.coalesce(en.c.total_entrada,0)).label('pendente'))

            .outerjoin(sa, Item.codigo_item == sa.c.codigo_item)

            .outerjoin(en, Item.codigo_item == en.c.codigo_item)

            .filter((func.coalesce(sa.c.total_saida,0) - func.coalesce(en.c.total_entrada,0)) > 0)

            .order_by(func.coalesce(sa.c.total_saida,0) - func.coalesce(en.c.total_entrada,0).desc())

        )

        results = q.limit(100).all()

        if not results:

            TelegramService.send_message(chat_id, "Nenhum item pendente encontrado.")

            return

        lines = [f"{r.codigo_item} — {r.descricao} — Pendente: {int(r.pendente)}" for r in results]

        TelegramService.send_message(chat_id, "Itens pendentes:\n" + "\n".join(lines))



    @staticmethod

    def _send_where_used(chat_id: str) -> None:

        """Envia resumo de locais de uso das saídas recentes."""

        recent = db.session.query(Saida).order_by(Saida.data_saida.desc()).limit(100).all()

        if not recent:

            TelegramService.send_message(chat_id, "Nenhuma saída recente encontrada.")

            return

        lines = []

        for s in recent:

            data = TimeService.format_local(s.data_saida, '%d/%m/%Y %H:%M') if s.data_saida else 'N/D'

            lines.append(f"{data} — {s.codigo_item or 'N/D'} — {s.local_servico or s.observacao or '-'}")

        TelegramService.send_message(chat_id, "Locais de uso (saídas recentes):\n" + "\n".join(lines))



    # ---- Barcode scanning and withdrawal via Telegram ----

    

    @staticmethod

    def _can_user_withdraw_via_telegram(chat_id: str) -> tuple[bool, TelegramUser | None]:

        """

        Verifica se o usuário tem permissão para fazer retiradas via Telegram.

        

        Returns:

            Tupla (tem_permissão, telegram_user)

        """

        try:

            telegram_user = db.session.query(TelegramUser).filter_by(

                chat_id=str(chat_id), 

                enabled=True

            ).first()

            

            if not telegram_user:

                return False, None

            

            # Verificar se tem permissão de retirada

            if not getattr(telegram_user, 'can_withdraw_via_telegram', False):

                return False, telegram_user

            

            return True, telegram_user

            

        except Exception as e:

            logger.exception(f"Erro ao verificar permissão de retirada: {e}")

            return False, None



    @staticmethod

    def _can_user_create_item_via_telegram(chat_id: str) -> tuple[bool, TelegramUser | None]:

        """Verifica se o usuário tem permissão para cadastrar itens via Telegram."""

        try:

            telegram_user = db.session.query(TelegramUser).filter_by(

                chat_id=str(chat_id),

                enabled=True,

            ).first()

            if not telegram_user:

                return False, None

            if not getattr(telegram_user, "can_create_item_via_telegram", False):

                return False, telegram_user

            return True, telegram_user

        except Exception as e:

            logger.exception(f"Erro ao verificar permissão de cadastro: {e}")

            return False, None

    

    @staticmethod

    def handle_command_scanear(chat_id: str) -> dict[str, Any]:

        """

        Handler para comando /scanear - Instruções para escanear código de barras.

        

        Args:

            chat_id: ID do chat do Telegram

            

        Returns:

            Resultado do envio da mensagem

        """

        try:

            # Verificar permissão

            can_withdraw, telegram_user = TelegramService._can_user_withdraw_via_telegram(chat_id)

            

            if not telegram_user:

                return TelegramService.send_message(

                    chat_id,

                    "❌ <b>Acesso Negado</b>\n\n"

                    "Você não está cadastrado no sistema Telegram.\n"

                    "Entre em contato com o administrador para vincular sua conta.",

                    parse_mode="HTML"

                )

            

            if not can_withdraw:

                return TelegramService.send_message(

                    chat_id,

                    "❌ <b>Permissão Negada</b>\n\n"

                    "Você não tem permissão para fazer retiradas via Telegram.\n\n"

                    "📞 <i>Entre em contato com o administrador para solicitar acesso.</i>",

                    parse_mode="HTML"

                )

            

            # Verificar se bibliotecas estão disponíveis

            try:

                from ..utils.barcode_photo_processor import BarcodePhotoProcessor

                

                if not BarcodePhotoProcessor.is_available():

                    missing = BarcodePhotoProcessor.get_missing_libraries()

                    return TelegramService.send_message(

                        chat_id,

                        f"⚠️ <b>Scanner Indisponível</b>\n\n"

                        f"Bibliotecas necessárias não estão instaladas:\n"

                        f"• {', '.join(missing)}\n\n"

                        f"<i>Contate o administrador do sistema.</i>",

                        parse_mode="HTML"

                    )

            except ImportError:

                return TelegramService.send_message(

                    chat_id,

                    "⚠️ <b>Scanner Indisponível</b>\n\n"

                    "Módulo de processamento de código de barras não está configurado.\n\n"

                    "<i>Contate o administrador do sistema.</i>",

                    parse_mode="HTML"

                )

            

            # Enviar instruções

            message = (

                "📸 <b>SCANNER DE CÓDIGO DE BARRAS</b>\n"

                "━━━━━━━━━━━━━━━━━━━━\n\n"

                "🎯 <b>Como usar:</b>\n\n"

                "1️⃣ Tire uma <b>foto clara</b> do código de barras\n"

                "2️⃣ Envie a foto aqui no chat\n"

                "3️⃣ Aguarde o processamento automático\n"

                "4️⃣ Confirme a retirada do item\n\n"

                "💡 <b>Dicas para melhor leitura:</b>\n"

                "• ✅ Foto bem iluminada\n"

                "• ✅ Código de barras em foco\n"

                "• ✅ Sem reflexos ou sombras\n"

                "• ✅ Código de barras inteiro visível\n\n"

                "📱 <i>Basta tirar a foto e enviar!</i>"

            )

            

            return TelegramService.send_message(chat_id, message, parse_mode="HTML")

            

        except Exception as e:

            logger.exception(f"Erro no comando /scanear: {e}")

            return {

                "success": False,

                "error": str(e)

            }



    @staticmethod

    def handle_barcode_text(chat_id: str, text: str) -> dict[str, Any]:

        """

        Handler para processar código de barras digitado manualmente.

        """

        try:

            can_withdraw, telegram_user = TelegramService._can_user_withdraw_via_telegram(chat_id)

            

            if not telegram_user:

                return TelegramService.send_message(

                    chat_id,

                    "❌ Você não está cadastrado no sistema.",

                    parse_mode=None

                )

            

            # Se permitir digitar, não precisa validar se can_withdraw para CONSULTA, 

            # mas _show_item_from_barcode vai mostrar os botões de retirada.

            # Se quisermos bloquear retirada mas permitir consulta, ok.

            

            return TelegramService._show_item_from_barcode(chat_id, text, telegram_user)



        except Exception as e:

            logger.exception(f"Erro ao processar código manual: {e}")

            return TelegramService.send_message(chat_id, f"❌ Erro: {e}")

    

    @staticmethod

    def handle_photo(chat_id: str, photo_sizes: list[dict]) -> dict[str, Any]:

        """

        Handler para processar fotos enviadas ao bot.

        

        Args:

            chat_id: ID do chat

            photo_sizes: Lista de tamanhos da foto (Telegram envia múltiplos tamanhos)

            

        Returns:

            Resultado do processamento

        """

        try:

            # Verificar permissão

            can_withdraw, telegram_user = TelegramService._can_user_withdraw_via_telegram(chat_id)

            

            if not telegram_user:

                return TelegramService.send_message(

                    chat_id,

                    "❌ Você não está cadastrado no sistema.",

                    parse_mode=None

                )

            

            if not can_withdraw:

                return TelegramService.send_message(

                    chat_id,

                    "❌ Você não tem permissão para fazer retiradas via Telegram.\n"

                    "Use /scanear para mais informações.",

                    parse_mode=None

                )

            

            # Importar processador

            try:

                from ..utils.barcode_photo_processor import BarcodePhotoProcessor

            except ImportError:

                return TelegramService.send_message(

                    chat_id,

                    "❌ Scanner de código de barras não está configurado.",

                    parse_mode=None

                )

            

            if not BarcodePhotoProcessor.is_available():

                return TelegramService.send_message(

                    chat_id,

                    "❌ Scanner de código de barras indisponível.",

                    parse_mode=None

                )

            

            # Obter token do bot

            config = TelegramService.get_config()

            if not config or not config.bot_token:

                return TelegramService.send_message(

                    chat_id,

                    "❌ Configuração do bot não encontrada.",

                    parse_mode=None

                )

            

            # Escolher a melhor resolução (última é a maior)

            if not photo_sizes:

                return TelegramService.send_message(

                    chat_id,

                    "❌ Foto não recebida corretamente.",

                    parse_mode=None

                )

            

            best_photo = photo_sizes[-1]  # Maior resolução

            file_id = best_photo.get("file_id")

            

            if not file_id:

                return TelegramService.send_message(

                    chat_id,

                    "❌ Erro ao processar foto.",

                    parse_mode=None

                )

            

            # Enviar mensagem de processamento

            TelegramService.send_message(

                chat_id,

                "🔍 <b>Processando imagem...</b>\n\n⏳ Aguarde um momento...",

                parse_mode="HTML"

            )

            

            # Processar foto

            result = BarcodePhotoProcessor.process_telegram_photo(config.bot_token, file_id)

            

            if not result.get("success"):

                error_msg = result.get("error", "Erro desconhecido")

                return TelegramService.send_message(

                    chat_id,

                    f"❌ <b>Código de Barras Não Encontrado</b>\n\n"

                    f"Não foi possível detectar um código de barras na imagem.\n\n"

                    f"💡 <b>Dicas:</b>\n"

                    f"• Certifique-se de que o código está em foco\n"

                    f"• Melhore a iluminação\n"

                    f"• Evite reflexos e sombras\n"

                    f"• Use /scanear para ver instruções\n\n"

                    f"<i>Detalhes: {error_msg}</i>",

                    parse_mode="HTML"

                )

            

            # Códigos de barras encontrados

            barcodes = result.get("barcodes", [])

            

            if len(barcodes) > 1:

                # Múltiplos códigos encontrados - pedir escolha

                return TelegramService._handle_multiple_barcodes(chat_id, barcodes)

            

            # Um código encontrado - buscar item

            barcode_data = barcodes[0]["data"]

            return TelegramService._show_item_from_barcode(chat_id, barcode_data, telegram_user)

            

        except Exception as e:

            logger.exception(f"Erro ao processar foto: {e}")

            return TelegramService.send_message(

                chat_id,

                f"❌ Erro ao processar foto: {str(e)}",

                parse_mode=None

            )

    

    @staticmethod

    def _handle_multiple_barcodes(chat_id: str, barcodes: list[dict]) -> dict[str, Any]:

        """

        Handler para quando múltiplos códigos de barras são detectados.

        

        Args:

            chat_id: ID do chat

            barcodes: Lista de códigos detectados

            

        Returns:

            Resultado do envio

        """

        message = (

            "⚠️ <b>Múltiplos Códigos Detectados</b>\n"

            "━━━━━━━━━━━━━━━━━━━━\n\n"

            f"Foram encontrados <b>{len(barcodes)}</b> códigos de barras na imagem:\n\n"

        )

        

        for idx, barcode in enumerate(barcodes[:5], 1):  # Limitar a 5

            message += f"{idx}. <code>{barcode['data']}</code> ({barcode['type']})\n"

        

        if len(barcodes) > 5:

            message += f"\n... e mais {len(barcodes) - 5} códigos.\n"

        

        message += (

            "\n💡 <b>Tire uma nova foto</b> focando em apenas um código de barras."

        )

        

        return TelegramService.send_message(chat_id, message, parse_mode="HTML")

    

    @staticmethod

    def _show_item_from_barcode(chat_id: str, barcode_data: str, telegram_user: TelegramUser) -> dict[str, Any]:

        """

        Busca item pelo código de barras e exibe informações.

        

        Args:

            chat_id: ID do chat

            barcode_data: Código de barras lido

            telegram_user: Usuário do Telegram

            

        Returns:

            Resultado do envio

        """

        try:

            # Buscar item pelo código

            item = db.session.query(Item).filter_by(codigo_item=barcode_data).first()

            

            if not item:

                # Tentar busca parcial (caso o código de barras seja parte do código)

                items = db.session.query(Item).filter(

                    Item.codigo_item.ilike(f"%{barcode_data}%")

                ).limit(5).all()

                

                if not items:

                    # Verificar se o usuário pode cadastrar itens

                    allowed, _ = TelegramService._can_user_create_item_via_telegram(chat_id)

                    

                    # Criar botão inline para cadastrar com código pré-preenchido

                    inline_keyboard = None

                    if allowed:

                        inline_keyboard = {

                            "inline_keyboard": [[

                                {"text": "🆕 Cadastrar este item", "callback_data": f"create_item:{barcode_data}"}

                            ], [

                                {"text": "🔍 Buscar manualmente", "callback_data": "menu:items"}

                            ]]

                        }

                    

                    return TelegramService.send_message(

                        chat_id,

                        f"❌ <b>Item Não Encontrado</b>\n\n"

                        f"Código: <code>{html.escape(barcode_data)}</code>\n\n"

                        f"O item não está cadastrado no sistema.\n\n"

                        f"💡 {'Use o botão abaixo para cadastrar ou' if allowed else 'Use /estoque para'} buscar manualmente.",

                        parse_mode="HTML",

                        reply_markup=inline_keyboard

                    )

                

                if len(items) == 1:

                    item = items[0]

                else:

                    # Múltiplos itens encontrados

                    message = (

                        f"🔍 <b>Busca Parcial</b>\n"

                        f"━━━━━━━━━━━━━━━━━━━━\n\n"

                        f"Código escaneado: <code>{html.escape(barcode_data)}</code>\n\n"

                        f"Foram encontrados <b>{len(items)}</b> itens similares:\n\n"

                    )

                    for idx, it in enumerate(items, 1):

                        message += f"{idx}. <code>{it.codigo_item}</code> - {it.descricao[:40]}\n"

                    message += "\n💡 Use /estoque <código> para ver detalhes de um item específico."

                    return TelegramService.send_message(chat_id, message, parse_mode="HTML")

            

            # Item encontrado - mostrar informações

            return TelegramService._show_item_details_with_withdrawal_option(chat_id, item, telegram_user)

            

        except Exception as e:

            logger.exception(f"Erro ao buscar item por código de barras: {e}")

            return TelegramService.send_message(

                chat_id,

                f"❌ Erro ao buscar item: {str(e)}",

                parse_mode=None

            )

    

    @staticmethod

    def _show_item_details_with_withdrawal_option(

        chat_id: str, 

        item: Item, 

        telegram_user: TelegramUser

    ) -> dict[str, Any]:

        """

        Exibe detalhes do item com opção de fazer retirada.

        

        Args:

            chat_id: ID do chat

            item: Item encontrado

            telegram_user: Usuário do Telegram

            

        Returns:

            Resultado do envio

        """

        try:

            # Alterações de saldo

            if houve_alteracao_saldo:
                delta = new_balance - prev_balance

                text += f"📊 <b>MOVIMENTAÇÃO</b>\n"

                from galint_flask.services.embalagem_service import EmbalagemService
                tem_emb = EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item)

                # Para itens com embalagem, o saldo numérico é em unidade interna (L/Kg/m/un). Evitar rotular como "Lata".
                unidade_mov = item.unidade or 'un'
                if tem_emb:
                    tipo_emb = (item.tipo_embalagem_novo or '').strip().lower()
                    if getattr(item, 'litros_por_embalagem', None):
                        unidade_mov = 'L'
                    elif getattr(item, 'grandeza_referencia', None):
                        unidade_mov = 'Kg'
                    elif tipo_emb == 'rolo':
                        unidade_mov = 'm'
                    elif tipo_emb in ('caixa', 'pacote'):
                        unidade_mov = 'un'

                text += f"├─ Saldo anterior: <b>{prev_balance:g}</b> {unidade_mov}\n"
                text += f"├─ Variação: <b>{delta:+g}</b> {unidade_mov} {variacao_icon}\n"
                text += f"└─ Saldo atual: <b>{new_balance:g}</b> {unidade_mov}\n"

                # Sempre anexar o estoque físico (embalagens + soltas) quando aplicável
                if tem_emb:
                    estoque_detalhado = EmbalagemService.formatar_estoque(item)
                    text += f"📦 <b>Estoque físico:</b> {estoque_detalhado}\n"

                totals = TelegramService._format_balance_totals(item, prefix="")
                if totals:
                    text += totals + "\n"
                text += "\n"

            categoria = (item.categoria or "Material").strip()

            emoji_map = {

                "ferramentas": "🔧",

                "ferramenta": "🔧",

                "material elétrico": "⚡",

                "material eletrico": "âš¡",

                "eletrico": "âš¡",

                "elétrico": "⚡",

                "material hidráulico": "🚰",

                "material hidraulico": "🚰",

                "hidraulico": "🚰",

                "hidráulico": "🚰",

                "limpeza": "🧹",

                "construção": "🏗️",

                "construcao": "🏗️",

                "pintura": "🎨",

                "piscina": "🏊",

                "epi": "🦺",

            }

            emoji = emoji_map.get(categoria.lower(), "📦")

            

            # Status do estoque

            if saldo <= 0:

                status_emoji = "â­•"

                status_text = "SEM ESTOQUE"

            elif saldo <= (item.estoque_minimo or 0):

                status_emoji = "⚠️"

                status_text = "ESTOQUE BAIXO"

            else:

                status_emoji = "✅"

                status_text = "DISPONÍVEL"

            

            # Montar mensagem

            message = (

                f"{status_emoji} <b>{status_text}</b>\n"

                f"{emoji} <b>{html.escape(item.descricao or 'N/D')}</b>\n"

                f"━━━━━━━━━━━━━━━━━━━━\n\n"

                f"🏷️ <b>Código:</b> <code>{html.escape(item.codigo_item or 'N/D')}</code>\n"

                f"📂 <b>Categoria:</b> {html.escape(categoria)}\n"

            )

            

            if item.marca:

                message += f"🏭 <b>Marca:</b> {html.escape(item.marca)}\n"

            

            if item.localizacao:

                message += f"📍 <b>Localização:</b> {html.escape(item.localizacao)}\n"

            

            message += f"\n📊 <b>Estoque Atual:</b> {html.escape(estoque_str)}\n"

            

            if item.estoque_minimo:

                message += f"📉 <b>Estoque Mínimo:</b> {item.estoque_minimo} {item.unidade or 'un'}\n"

            

            # Botões de ação

            keyboard = {"inline_keyboard": []}



            if saldo > 0:

                keyboard["inline_keyboard"].append([

                    {"text": "📤 Fazer Retirada", "callback_data": f"withdraw:{item.codigo_item}"}

                ])

            else:

                message += "\n\n⚠️ <i>Sem estoque para retirada.</i>"



            message += "\n\nℹ️ <i>Devoluções só via APK ou painel Web.</i>"

            

            # Verificar permissão de edição

            allowed_edit, _ = TelegramService._can_user_create_item_via_telegram(chat_id)

            

            keyboard["inline_keyboard"].append([

                {"text": "📊 Ver Detalhes", "callback_data": f"details:{item.codigo_item}"}

            ])

            

            if allowed_edit:

                keyboard["inline_keyboard"].append([

                    {"text": "✏️ Editar Item", "callback_data": f"edit_item:{item.codigo_item}"}

                ])

            

            keyboard["inline_keyboard"].append([

                {"text": "❌ Cancelar", "callback_data": "cancel"}

            ])

            

            message += "\n\n💡 <i>Escolha uma ação abaixo:</i>"

            

            return TelegramService.send_message(chat_id, message, parse_mode="HTML", reply_markup=keyboard)

            

        except Exception as e:

            logger.exception(f"Erro ao mostrar detalhes do item: {e}")

            return TelegramService.send_message(

                chat_id,

                f"❌ Erro ao mostrar detalhes: {str(e)}",

                parse_mode=None

            )



    @staticmethod

    def _send_item_details(chat_id: str, codigo_item: str) -> dict[str, Any]:

        """Envia detalhes completos do item sem botões de ação."""

        item = db.session.query(Item).filter_by(codigo_item=codigo_item).first()

        if not item:

            return TelegramService.send_message(

                chat_id,

                f"❌ Item não encontrado: {html.escape(codigo_item)}",

                parse_mode="HTML",

            )



        try:

            saldo = int(item.get_saldo_atual() or 0)

        except Exception:

            saldo = 0



        unidade = (item.unidade or "un").strip()

        categoria = (item.categoria or "Material").strip()

        message = (

            f"📊 <b>Detalhes do Item</b>\n"

            "━━━━━━━━━━━━━━━━━━━━\n\n"

            f"🏷️ <b>Código:</b> <code>{html.escape(item.codigo_item or 'N/D')}</code>\n"

            f"📝 <b>Descrição:</b> {html.escape(item.descricao or 'N/D')}\n"

            f"📂 <b>Categoria:</b> {html.escape(categoria)}\n"

            f"📊 <b>Saldo:</b> {saldo} {html.escape(unidade)}\n"

        )

        if item.marca:

            message += f"🏭 <b>Marca:</b> {html.escape(item.marca)}\n"

        if item.localizacao:

            message += f"📍 <b>Localização:</b> {html.escape(item.localizacao)}\n"

        if item.estoque_minimo:

            message += f"📉 <b>Mínimo:</b> {item.estoque_minimo} {html.escape(unidade)}\n"



        return TelegramService.send_message(chat_id, message, parse_mode="HTML")



    @staticmethod

    def _handle_withdrawal_by_barcode(chat_id: str, codigo_item: str) -> dict[str, Any]:

        """Registra retirada simples (1 unidade) via Telegram scanner."""

        can_withdraw, telegram_user = TelegramService._can_user_withdraw_via_telegram(chat_id)

        if not telegram_user:

            return TelegramService.send_message(chat_id, "❌ Usuário não vinculado.", parse_mode=None)

        if not can_withdraw:

            return TelegramService.send_message(

                chat_id,

                "❌ Você não tem permissão para fazer retiradas via Telegram.",

                parse_mode=None,

            )



        item = db.session.query(Item).filter_by(codigo_item=codigo_item).first()

        if not item:

            return TelegramService.send_message(

                chat_id,

                f"❌ Item não encontrado: {html.escape(codigo_item)}",

                parse_mode="HTML",

            )



        try:

            saldo = float(item.get_saldo_atual() or 0)

        except Exception:

            saldo = 0

        if saldo <= 0:

            return TelegramService.send_message(

                chat_id,

                "❌ Item sem estoque disponível para retirada.",

                parse_mode=None,

            )



        # Dedupe: evita retirada dupla acidental em curto intervalo

        try:

            cutoff = datetime.utcnow() - timedelta(minutes=2)

            recent = (

                db.session.query(Saida)

                .filter(Saida.codigo_item == item.codigo_item)

                .filter(Saida.matricula == telegram_user.matricula)

                .filter(Saida.quantidade == 1)

                .filter(Saida.observacao == "Retirada via Telegram")

                .filter(Saida.data_saida >= cutoff)

                .order_by(Saida.data_saida.desc())

                .first()

            )

            if recent:

                return TelegramService.send_message(

                    chat_id,

                    "⚠️ Retirada já registrada recentemente. Se precisar, tente novamente em alguns minutos.",

                    parse_mode=None,

                )

        except Exception:

            pass



        try:

            from ..services.inventory import MovimentoPayload, inventory_service



            payload = MovimentoPayload(

                codigo=item.codigo_item,

                quantidade=1,

                matricula=telegram_user.matricula,

                observacao="Retirada via Telegram",

                local_servico="Telegram",

            )

            saida_id = inventory_service.registrar_saida(payload)

        except Exception as exc:

            logger.exception(f"Erro ao registrar retirada via Telegram: {exc}")

            return TelegramService.send_message(

                chat_id,

                f"❌ Falha ao registrar retirada: {exc}",

                parse_mode=None,

            )



        return TelegramService.send_message(

            chat_id,

            (

                "✅ Retirada registrada com sucesso.\n\n"

                f"🧾 Código: <code>{html.escape(item.codigo_item or 'N/D')}</code>\n"

                f"📝 Item: {html.escape(item.descricao or 'N/D')}\n"

                f"🔢 Quantidade: 1 {html.escape(item.unidade or 'un')}\n"

                f"📌 Saída: {saida_id}"

            ),

            parse_mode="HTML",

        )



    @staticmethod

    def is_item_create_active(chat_id: str) -> bool:

        try:

            conv = TelegramConversation.query.filter_by(chat_id=str(chat_id)).first()

            return bool(conv and conv.state and conv.state.startswith("item_create:"))

        except Exception:

            return False



    @staticmethod

    def _item_create_get_meta(chat_id: str) -> dict[str, Any]:

        try:

            conv = TelegramConversation.query.filter_by(chat_id=str(chat_id)).first()

            if not conv or not conv.celular_informado:

                return {}

            data = json.loads(conv.celular_informado) or {}

            if not isinstance(data, dict):

                return {}

            meta = data.get("item_create")

            return meta if isinstance(meta, dict) else {}

        except Exception:

            return {}



    @staticmethod

    def _item_create_update(chat_id: str, state: str, updates: dict[str, Any] | None = None) -> None:

        try:

            conv = TelegramConversation.query.filter_by(chat_id=str(chat_id)).first()

            if not conv:

                conv = TelegramConversation(chat_id=str(chat_id))

                db.session.add(conv)



            conv.state = state

            current: dict[str, Any] = {}

            try:

                if conv.celular_informado:

                    current = json.loads(conv.celular_informado) or {}

            except Exception:

                current = {}

            if not isinstance(current, dict):

                current = {}

            item_meta = current.get("item_create") if isinstance(current.get("item_create"), dict) else {}

            if updates:

                item_meta.update(updates)

            current["item_create"] = item_meta

            conv.celular_informado = json.dumps(current)

            db.session.commit()

        except Exception as e:

            db.session.rollback()

            logger.error(f"Erro ao atualizar conversa de item: {e}")



    @staticmethod

    def _start_item_create_flow(chat_id: str) -> bool:

        allowed, _ = TelegramService._can_user_create_item_via_telegram(chat_id)

        if not allowed:

            TelegramService.send_message(

                chat_id,

                "❌ Você não tem permissão para cadastrar itens via Telegram.",

                parse_mode=None,

            )

            return True



        try:

            TelegramConversation.query.filter_by(chat_id=str(chat_id)).delete()

            db.session.commit()

        except Exception:

            db.session.rollback()



        TelegramService._item_create_update(chat_id, "item_create:codigo", {})

        TelegramService.send_message(

            chat_id,

            (

                "🆕 <b>Cadastro de Item</b>\n"

                "━━━━━━━━━━━━━━━━━━━━\n\n"

                "Informe os dados do item.\n"

                "Use <b>/pular</b> para campos opcionais e <b>/cancelar</b> para sair.\n\n"

                "<b>1) Código de barras:</b>"

            ),

            parse_mode="HTML",

        )

        return True



    @staticmethod

    def _handle_item_create_text(chat_id: str, text: str) -> bool:

        conv = TelegramConversation.query.filter_by(chat_id=str(chat_id)).first()

        if not conv or not conv.state or not conv.state.startswith("item_create:"):

            return False



        t = (text or "").strip()

        t_lower = t.lower()

        if t_lower in ("/cancel", "/cancelar", "cancelar", "cancel") or t == "❌ Cancelar":

            try:

                db.session.delete(conv)

                db.session.commit()

            except Exception:

                db.session.rollback()

            TelegramService.send_message(chat_id, "❌ Cadastro cancelado.", parse_mode=None)

            return True



        def is_skip(value: str) -> bool:

            return value in ("/pular", "pular", "skip")



        def parse_date(value: str) -> str | None:

            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):

                try:

                    return datetime.strptime(value, fmt).date().isoformat()

                except Exception:

                    continue

            return None



        def choose_from_list(value: str, options: list[str]) -> str | None:

            if value.isdigit():

                idx = int(value)

                if 1 <= idx <= len(options):

                    return options[idx - 1]

            for opt in options:

                if value.strip().lower() == opt.lower():

                    return opt

            return None



        state = conv.state.split(":", 1)[1]

        meta = TelegramService._item_create_get_meta(chat_id)



        if state == "codigo":

            if not t:

                TelegramService.send_message(chat_id, "❌ Código é obrigatório.", parse_mode=None)

                return True

            TelegramService._item_create_update(chat_id, "item_create:nota_fiscal", {"codigo": t})

            TelegramService.send_message(chat_id, "<b>2) Número da NF</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "nota_fiscal":

            nf = None if is_skip(t_lower) else t

            TelegramService._item_create_update(chat_id, "item_create:descricao", {"nota_fiscal": nf})

            TelegramService.send_message(chat_id, "<b>3) Descrição do produto:</b>", parse_mode="HTML")

            return True



        if state == "descricao":

            if not t:

                TelegramService.send_message(chat_id, "❌ Descrição é obrigatória.", parse_mode=None)

                return True

            TelegramService._item_create_update(chat_id, "item_create:marca", {"descricao": t})

            TelegramService.send_message(chat_id, "<b>4) Marca/Fabricante</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "marca":

            marca = None if is_skip(t_lower) else t

            TelegramService._item_create_update(chat_id, "item_create:categoria", {"marca": marca})

            options = "\n".join([f"{i+1}. {c}" for i, c in enumerate(TelegramService.ITEM_CATEGORIES)])

            TelegramService.send_message(

                chat_id,

                "<b>5) Categoria</b> (digite o numero ou nome):\n" + options,

                parse_mode="HTML",

            )

            return True



        if state == "categoria":

            categoria = choose_from_list(t, TelegramService.ITEM_CATEGORIES)

            if not categoria:

                TelegramService.send_message(chat_id, "❌ Categoria inválida. Tente novamente.", parse_mode=None)

                return True

            TelegramService._item_create_update(chat_id, "item_create:localizacao", {"categoria": categoria})

            TelegramService.send_message(chat_id, "<b>6) Localização</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "localizacao":

            localizacao = None if is_skip(t_lower) else t

            TelegramService._item_create_update(chat_id, "item_create:unidade", {"localizacao": localizacao})

            options = "\n".join([f"{i+1}. {u}" for i, u in enumerate(TelegramService.ITEM_UNITS)])

            TelegramService.send_message(

                chat_id,

                "<b>7) Unidade</b> (digite o numero ou nome):\n" + options,

                parse_mode="HTML",

            )

            return True



        if state == "unidade":

            unidade = choose_from_list(t, TelegramService.ITEM_UNITS)

            if not unidade:

                TelegramService.send_message(chat_id, "❌ Unidade inválida. Tente novamente.", parse_mode=None)

                return True

            TelegramService._item_create_update(chat_id, "item_create:numero_serie", {"unidade": unidade})

            TelegramService.send_message(chat_id, "<b>8) Número de série</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "numero_serie":

            numero_serie = None if is_skip(t_lower) else t

            TelegramService._item_create_update(chat_id, "item_create:modelo", {"numero_serie": numero_serie})

            TelegramService.send_message(chat_id, "<b>9) Modelo</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "modelo":

            modelo = None if is_skip(t_lower) else t

            TelegramService._item_create_update(chat_id, "item_create:data_entrada", {"modelo": modelo})

            TelegramService.send_message(chat_id, "<b>10) Data de entrada</b> (YYYY-MM-DD ou DD/MM/YYYY, ou /pular):", parse_mode="HTML")

            return True



        if state == "data_entrada":

            data_entrada = None if is_skip(t_lower) else parse_date(t)

            if t and not is_skip(t_lower) and not data_entrada:

                TelegramService.send_message(chat_id, "❌ Data inválida. Use YYYY-MM-DD ou DD/MM/YYYY.", parse_mode=None)

                return True

            TelegramService._item_create_update(chat_id, "item_create:lote", {"data_entrada": data_entrada})

            TelegramService.send_message(chat_id, "<b>11) Lote</b> (ou /auto, ou /pular):", parse_mode="HTML")

            return True



        if state == "lote":

            gerar_lote_automatico = False

            lote = None

            if t_lower in ("/auto", "auto", "automatico", "automático"):

                gerar_lote_automatico = True

            elif not is_skip(t_lower):

                lote = t

            TelegramService._item_create_update(

                chat_id,

                "item_create:data_fabricacao",

                {"lote": lote, "gerar_lote_automatico": gerar_lote_automatico},

            )

            TelegramService.send_message(chat_id, "<b>12) Data de fabricação</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "data_fabricacao":

            data_fabricacao = None if is_skip(t_lower) else parse_date(t)

            if t and not is_skip(t_lower) and not data_fabricacao:

                TelegramService.send_message(chat_id, "❌ Data inválida. Use YYYY-MM-DD ou DD/MM/YYYY.", parse_mode=None)

                return True

            TelegramService._item_create_update(chat_id, "item_create:data_validade", {"data_fabricacao": data_fabricacao})

            TelegramService.send_message(chat_id, "<b>13) Data de validade</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "data_validade":

            data_validade = None if is_skip(t_lower) else parse_date(t)

            if t and not is_skip(t_lower) and not data_validade:

                TelegramService.send_message(chat_id, "❌ Data inválida. Use YYYY-MM-DD ou DD/MM/YYYY.", parse_mode=None)

                return True

            TelegramService._item_create_update(chat_id, "item_create:embalagem_confirm", {"data_validade": data_validade})

            TelegramService.send_message(chat_id, "<b>14) Deseja informar embalagem?</b> (sim/não):", parse_mode="HTML")

            return True



        if state == "embalagem_confirm":

            if t_lower in ("sim", "s", "yes"):

                TelegramService._item_create_update(chat_id, "item_create:embalagem_tipo")

                TelegramService.send_message(

                    chat_id,

                    "<b>15) Tipo de embalagem</b> (lata, balde, rolo, pacote, caixa, litro) ou /pular:",

                    parse_mode="HTML",

                )

                return True

            TelegramService._item_create_update(chat_id, "item_create:voltagem")

            TelegramService.send_message(chat_id, "<b>15) Voltagem</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "embalagem_tipo":

            if is_skip(t_lower) or t_lower in ("nenhum", "nao", "não"):

                TelegramService._item_create_update(chat_id, "item_create:voltagem", {"tipo_embalagem_novo": None})

                TelegramService.send_message(chat_id, "<b>15) Voltagem</b> (ou /pular):", parse_mode="HTML")

                return True



            tipo = t_lower

            if tipo not in ("lata", "balde", "rolo", "pacote", "caixa", "litro"):

                TelegramService.send_message(chat_id, "❌ Tipo inválido. Informe lata/balde/rolo/pacote/caixa/litro.", parse_mode=None)

                return True

            TelegramService._item_create_update(chat_id, "item_create:embalagem_unidade", {"tipo_embalagem_novo": tipo})

            if tipo in ("lata", "balde", "litro"):

                TelegramService.send_message(chat_id, "<b>16) Unidade da embalagem</b> (litro ou kg):", parse_mode="HTML")

            else:

                TelegramService.send_message(chat_id, "<b>16) Unidades por embalagem</b> (numero):", parse_mode="HTML")

            return True



        if state == "embalagem_unidade":

            tipo = (meta.get("tipo_embalagem_novo") or "").lower()

            if tipo in ("lata", "balde", "litro"):

                if t_lower not in ("litro", "kg"):

                    TelegramService.send_message(chat_id, "❌ Unidade inválida. Use litro ou kg.", parse_mode=None)

                    return True

                TelegramService._item_create_update(chat_id, "item_create:embalagem_quantidade", {"unidade_embalagem_novo": t_lower})

                TelegramService.send_message(chat_id, "<b>17) Quantidade por embalagem</b> (numero):", parse_mode="HTML")

                return True



            try:

                val = float(t.replace(",", "."))

            except Exception:

                TelegramService.send_message(chat_id, "❌ Valor inválido. Informe um número.", parse_mode=None)

                return True

            TelegramService._item_create_update(chat_id, "item_create:voltagem", {"unidades_por_embalagem": val})

            TelegramService.send_message(chat_id, "<b>17) Voltagem</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "embalagem_quantidade":

            try:

                val = float(t.replace(",", "."))

            except Exception:

                TelegramService.send_message(chat_id, "❌ Valor inválido. Informe um número.", parse_mode=None)

                return True

            unidade_emb = (meta.get("unidade_embalagem_novo") or "").lower()

            updates: dict[str, Any] = {}

            if unidade_emb == "litro":

                updates["litros_por_embalagem"] = val

            else:

                updates["grandeza_referencia"] = val

            TelegramService._item_create_update(chat_id, "item_create:voltagem", updates)

            TelegramService.send_message(chat_id, "<b>18) Voltagem</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "voltagem":

            voltagem = None if is_skip(t_lower) else t

            TelegramService._item_create_update(chat_id, "item_create:amperagem", {"voltagem": voltagem})

            TelegramService.send_message(chat_id, "<b>19) Amperagem</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "amperagem":

            amperagem = None if is_skip(t_lower) else t

            TelegramService._item_create_update(chat_id, "item_create:local_instalacao", {"amperagem": amperagem})

            TelegramService.send_message(chat_id, "<b>20) Local da instalação</b> (ou /pular):", parse_mode="HTML")

            return True



        if state == "local_instalacao":

            local_instalacao = None if is_skip(t_lower) else t

            TelegramService._item_create_update(chat_id, "item_create:confirm", {"local_instalacao": local_instalacao})

            meta = TelegramService._item_create_get_meta(chat_id)

            resumo = (

                "✅ <b>Resumo do cadastro</b>\n"

                "━━━━━━━━━━━━━━━━━━━━\n\n"

                f"Código: <code>{html.escape(meta.get('codigo') or '')}</code>\n"

                f"Descrição: {html.escape(meta.get('descricao') or '')}\n"

                f"Categoria: {html.escape(meta.get('categoria') or '')}\n"

                f"Unidade: {html.escape(meta.get('unidade') or '')}\n"

                f"Marca: {html.escape(meta.get('marca') or '-') }\n"

                f"Localização: {html.escape(meta.get('localizacao') or '-') }\n"

                "\n⚠️ Saldo inicial será 0. Entradas só via APK ou Web.\n\n"

                "Digite <b>CONFIRMAR</b> para salvar ou <b>CANCELAR</b> para sair."

            )

            TelegramService.send_message(chat_id, resumo, parse_mode="HTML")

            return True



        if state == "confirm":

            if t_lower not in ("confirmar", "confirm", "ok", "sim"):

                TelegramService.send_message(chat_id, "❌ Cadastro cancelado.", parse_mode=None)

                try:

                    db.session.delete(conv)

                    db.session.commit()

                except Exception:

                    db.session.rollback()

                return True



            meta = TelegramService._item_create_get_meta(chat_id)

            payload = {

                "codigo": (meta.get("codigo") or "").strip(),

                "descricao": (meta.get("descricao") or "").strip(),

                "nota_fiscal": (meta.get("nota_fiscal") or "").strip() or None,

                "localizacao": (meta.get("localizacao") or "").strip() or None,

                "categoria": meta.get("categoria") or "Material Elétrico",

                "marca": (meta.get("marca") or "").strip() or None,

                "unidade": (meta.get("unidade") or "").strip() or "Unidade",

                "numero_serie": (meta.get("numero_serie") or "").strip() or None,

                "modelo": (meta.get("modelo") or "").strip() or None,

                "data_entrada": meta.get("data_entrada") or None,

                "data_fabricacao": meta.get("data_fabricacao") or None,

                "data_validade": meta.get("data_validade") or None,

                "lote": (meta.get("lote") or "").strip() or None,

                "gerar_lote_automatico": bool(meta.get("gerar_lote_automatico")),

                "tipo_embalagem_novo": meta.get("tipo_embalagem_novo"),

                "unidades_por_embalagem": meta.get("unidades_por_embalagem"),

                "litros_por_embalagem": meta.get("litros_por_embalagem"),

                "grandeza_referencia": meta.get("grandeza_referencia"),

                "voltagem": (meta.get("voltagem") or "").strip() or None,

                "amperagem": (meta.get("amperagem") or "").strip() or None,

                "local_instalacao": (meta.get("local_instalacao") or "").strip() or None,

                "quantidade": 0,

            }



            try:

                if not payload["codigo"] or not payload["descricao"]:

                    raise ValueError("Código e descrição são obrigatórios")

                from ..services.inventory import inventory_service

                codigo = inventory_service.create_item(payload)

                try:

                    TelegramService.notify_item_created(codigo.replace("UPDATED:", ""))

                except Exception:

                    pass

                TelegramService.send_message(chat_id, "✅ Item cadastrado com sucesso.", parse_mode=None)

            except Exception as e:

                TelegramService.send_message(chat_id, f"❌ Erro ao cadastrar item: {e}", parse_mode=None)



            try:

                db.session.delete(conv)

                db.session.commit()

            except Exception:

                db.session.rollback()

            return True



        return True



    @staticmethod

    def _start_item_edit_flow(chat_id: str, codigo_item: str) -> bool:

        """Inicia fluxo de edição de item existente."""

        allowed, _ = TelegramService._can_user_create_item_via_telegram(chat_id)

        if not allowed:

            TelegramService.send_message(

                chat_id,

                "❌ Você não tem permissão para editar itens via Telegram.",

                parse_mode=None,

            )

            return True



        # Buscar item existente

        item = db.session.query(Item).filter_by(codigo_item=codigo_item).first()

        if not item:

            TelegramService.send_message(

                chat_id,

                f"❌ Item não encontrado: {html.escape(codigo_item)}",

                parse_mode="HTML",

            )

            return True



        # Limpar conversa anterior

        try:

            TelegramConversation.query.filter_by(chat_id=str(chat_id)).delete()

            db.session.commit()

        except Exception:

            db.session.rollback()



        # Preparar dados do item para edição

        meta = {

            "item_id": item.id,

            "codigo": item.codigo_item,

            "descricao_atual": item.descricao or "",

            "categoria_atual": item.categoria or "",

            "unidade_atual": item.unidade or "",

            "marca_atual": item.marca or "",

            "localizacao_atual": item.localizacao or "",

        }



        TelegramService._item_edit_update(chat_id, "item_edit:descricao", meta)



        TelegramService.send_message(

            chat_id,

            (

                "✏️ <b>Edição de Item</b>\n"

                "━━━━━━━━━━━━━━━━━━━━\n\n"

                f"📦 <b>Item:</b> {html.escape(item.descricao or 'N/D')}\n"

                f"🏷️ <b>Código:</b> <code>{html.escape(item.codigo_item)}</code>\n\n"

                "━━━━━━━━━━━━━━━━━━━━\n"

                "Envie os novos valores ou <b>/pular</b> para manter o valor atual.\n"

                "Use <b>/cancelar</b> para sair.\n\n"

                f"<b>1) Descrição</b>\n"

                f"   Atual: <i>{html.escape(item.descricao or '-')}</i>"

            ),

            parse_mode="HTML",

        )

        return True



    @staticmethod

    def _handle_item_edit_text(chat_id: str, text: str) -> bool:

        """Processa texto do fluxo de edição de item."""

        conv = TelegramConversation.query.filter_by(chat_id=str(chat_id)).first()

        if not conv or not conv.state or not conv.state.startswith("item_edit:"):

            return False



        t = (text or "").strip()

        t_lower = t.lower()



        # Cancelar

        if t_lower in ("/cancel", "/cancelar", "cancelar", "cancel") or t == "❌ Cancelar":

            try:

                db.session.delete(conv)

                db.session.commit()

            except Exception:

                db.session.rollback()

            TelegramService.send_message(chat_id, "❌ Edição cancelada.", parse_mode=None)

            return True



        is_skip = lambda x: x in ("/pular", "/skip", "pular", "skip")

        state = conv.state.split(":", 1)[1] if ":" in conv.state else ""



        # Fluxo de edição

        if state == "descricao":

            if not is_skip(t_lower):

                TelegramService._item_edit_update(chat_id, "item_edit:categoria", {"descricao": t})

            else:

                TelegramService._item_edit_update(chat_id, "item_edit:categoria", {})

            

            meta = TelegramService._item_edit_get_meta(chat_id)

            TelegramService.send_message(

                chat_id,

                (

                    f"<b>2) Categoria</b>\n"

                    f"   Atual: <i>{html.escape(meta.get('categoria_atual') or '-')}</i>"

                ),

                parse_mode="HTML",

            )

            return True



        if state == "categoria":

            if not is_skip(t_lower):

                TelegramService._item_edit_update(chat_id, "item_edit:unidade", {"categoria": t})

            else:

                TelegramService._item_edit_update(chat_id, "item_edit:unidade", {})

            

            meta = TelegramService._item_edit_get_meta(chat_id)

            TelegramService.send_message(

                chat_id,

                (

                    f"<b>3) Unidade</b>\n"

                    f"   Atual: <i>{html.escape(meta.get('unidade_atual') or '-')}</i>"

                ),

                parse_mode="HTML",

            )

            return True



        if state == "unidade":

            if not is_skip(t_lower):

                TelegramService._item_edit_update(chat_id, "item_edit:marca", {"unidade": t})

            else:

                TelegramService._item_edit_update(chat_id, "item_edit:marca", {})

            

            meta = TelegramService._item_edit_get_meta(chat_id)

            TelegramService.send_message(

                chat_id,

                (

                    f"<b>4) Marca</b>\n"

                    f"   Atual: <i>{html.escape(meta.get('marca_atual') or '-')}</i>"

                ),

                parse_mode="HTML",

            )

            return True



        if state == "marca":

            if not is_skip(t_lower):

                TelegramService._item_edit_update(chat_id, "item_edit:localizacao", {"marca": t})

            else:

                TelegramService._item_edit_update(chat_id, "item_edit:localizacao", {})

            

            meta = TelegramService._item_edit_get_meta(chat_id)

            TelegramService.send_message(

                chat_id,

                (

                    f"<b>5) Localização</b>\n"

                    f"   Atual: <i>{html.escape(meta.get('localizacao_atual') or '-')}</i>"

                ),

                parse_mode="HTML",

            )

            return True



        if state == "localizacao":

            if not is_skip(t_lower):

                TelegramService._item_edit_update(chat_id, "item_edit:confirm", {"localizacao": t})

            else:

                TelegramService._item_edit_update(chat_id, "item_edit:confirm", {})

            

            meta = TelegramService._item_edit_get_meta(chat_id)

            

            resumo = (

                "✅ <b>Resumo das alterações</b>\n"

                "━━━━━━━━━━━━━━━━━━━━\n\n"

                f"🏷️ Código: <code>{html.escape(meta.get('codigo') or '')}</code>\n\n"

            )

            

            if "descricao" in meta:

                resumo += f"📝 Descrição: {html.escape(meta['descricao'])}\n"

            if "categoria" in meta:

                resumo += f"📂 Categoria: {html.escape(meta['categoria'])}\n"

            if "unidade" in meta:

                resumo += f"📦 Unidade: {html.escape(meta['unidade'])}\n"

            if "marca" in meta:

                resumo += f"🏭 Marca: {html.escape(meta['marca'])}\n"

            if "localizacao" in meta:

                resumo += f"📍 Localização: {html.escape(meta['localizacao'])}\n"

            

            if not any(k in meta for k in ["descricao", "categoria", "unidade", "marca", "localizacao"]):

                resumo += "\n<i>Nenhuma alteração foi feita.</i>\n"

            

            resumo += "\n\nDigite <b>CONFIRMAR</b> para salvar ou <b>CANCELAR</b> para sair."

            

            TelegramService.send_message(chat_id, resumo, parse_mode="HTML")

            return True



        if state == "confirm":

            if t_lower not in ("confirmar", "confirm", "ok", "sim"):

                TelegramService.send_message(chat_id, "❌ Edição cancelada.", parse_mode=None)

                try:

                    db.session.delete(conv)

                    db.session.commit()

                except Exception:

                    db.session.rollback()

                return True



            meta = TelegramService._item_edit_get_meta(chat_id)

            item_id = meta.get("item_id")

            

            if not item_id:

                TelegramService.send_message(chat_id, "❌ Erro: Item não identificado.", parse_mode=None)

                try:

                    db.session.delete(conv)

                    db.session.commit()

                except Exception:

                    db.session.rollback()

                return True



            try:

                item = db.session.query(Item).filter_by(id=item_id).first()

                if not item:

                    raise ValueError("Item não encontrado")



                # Aplicar alterações

                if "descricao" in meta and meta["descricao"]:

                    item.descricao = meta["descricao"].strip()

                if "categoria" in meta and meta["categoria"]:

                    item.categoria = meta["categoria"].strip()

                if "unidade" in meta and meta["unidade"]:

                    item.unidade = meta["unidade"].strip()

                if "marca" in meta and meta["marca"]:

                    item.marca = meta["marca"].strip()

                if "localizacao" in meta and meta["localizacao"]:

                    item.localizacao = meta["localizacao"].strip()



                db.session.commit()

                TelegramService.send_message(chat_id, "✅ Item atualizado com sucesso!", parse_mode=None)

            except Exception as e:

                db.session.rollback()

                TelegramService.send_message(chat_id, f"❌ Erro ao atualizar item: {e}", parse_mode=None)



            try:

                db.session.delete(conv)

                db.session.commit()

            except Exception:

                db.session.rollback()

            return True



        return True



    @staticmethod

    def _item_edit_update(chat_id: str, state: str, updates: dict[str, Any] | None = None) -> None:

        """Atualiza o estado da conversa de edição de item."""

        try:

            conv = TelegramConversation.query.filter_by(chat_id=str(chat_id)).first()

            if not conv:

                conv = TelegramConversation(chat_id=str(chat_id))

                db.session.add(conv)



            conv.state = state

            current: dict[str, Any] = {}

            try:

                if conv.celular_informado:

                    current = json.loads(conv.celular_informado) or {}

            except Exception:

                current = {}

            if not isinstance(current, dict):

                current = {}

            

            item_meta = current.get("item_edit") if isinstance(current.get("item_edit"), dict) else {}

            if updates:

                item_meta.update(updates)

            current["item_edit"] = item_meta

            conv.celular_informado = json.dumps(current)

            db.session.commit()

        except Exception:

            db.session.rollback()



    @staticmethod

    def _item_edit_get_meta(chat_id: str) -> dict[str, Any]:

        """Recupera os dados de edição do item em andamento."""

        try:

            conv = TelegramConversation.query.filter_by(chat_id=str(chat_id)).first()

            if not conv or not conv.celular_informado:

                return {}

            data = json.loads(conv.celular_informado) or {}

            if not isinstance(data, dict):

                return {}

            return data.get("item_edit") if isinstance(data.get("item_edit"), dict) else {}

        except Exception:

            return {}



    @staticmethod

    def _handle_return_by_barcode(chat_id: str, codigo_item: str) -> dict[str, Any]:

        """Registra devolução simples (1 unidade) via Telegram scanner."""

        return TelegramService.send_message(

            chat_id,

            "⚠️ Devoluções estão bloqueadas no Telegram. Use o APK ou o painel Web.",

            parse_mode=None,

        )

