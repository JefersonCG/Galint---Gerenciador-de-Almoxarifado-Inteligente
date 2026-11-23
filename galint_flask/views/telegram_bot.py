"""Blueprint para integração do Bot Telegram usando pyTelegramBotAPI (telebot).

Contém funções de geração de teclado, busca de movimentações e rota webhook.
"""
from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import List

from flask import Blueprint, request, jsonify, current_app

from ..extensions import db
from ..models import Usuario, TelegramUser, Item, Saida, TelegramConfig
from ..services.telegram_service import TelegramService
from ..utils.time_service import TimeService

logger = logging.getLogger(__name__)

bp = Blueprint("telegram_bot", __name__, url_prefix="/telegram")

try:
    import telebot
    from telebot import types
except Exception:  # pragma: no cover - allow import failure in environments without telebot
    telebot = None
    types = None


def _get_bot(token: str):
    if not telebot:
        raise RuntimeError("pyTelegramBotAPI (telebot) não está instalado")
    return telebot.TeleBot(token)


def gerar_menu_principal(is_admin: bool, can_create_item: bool = False):
    """Gera ReplyKeyboardMarkup dinâmico conforme permissão.

    Retorna um objeto `telebot.types.ReplyKeyboardMarkup`.
    """
    if not types:
        return None

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin:
        kb.row("📤 Consultar Retiradas", "📦 Consultar Estoque")
        kb.row("🔍 Buscar Item", "🕓 Histórico Geral")
        kb.row("📸 Escanear Código")
        if can_create_item:
            kb.row("🆕 Cadastrar Item")
        kb.row("📄 Saídas do Dia (PDF)", "📊 Relatórios Gerenciais")
        kb.row("⚙️ Config")
    else:
        kb.row("📤 Consultar Retiradas", "🔍 Buscar Item")
        kb.row("📸 Escanear Código")
        if can_create_item:
            kb.row("🆕 Cadastrar Item")
        kb.row("🕓 Minhas Movimentações")
    return kb


def gerar_submenu_retiradas():
    """Cria InlineKeyboard para selecionar categoria de retirada."""
    if not types:
        return None
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛠️ Ferramentas", callback_data="retiradas_ferramentas"))
    kb.add(types.InlineKeyboardButton("🧱 Materiais", callback_data="retiradas_materiais"))
    return kb


def gerar_submenu_estoque():
    """Cria InlineKeyboard para opções de estoque (apenas admin)."""
    if not types:
        return None
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📉 Baixar Planilha de Baixo Estoque", callback_data="baixar_estoque_baixo"))
    return kb


def buscar_movimentacoes_saida(user_matricula: str | None, is_admin: bool) -> List[Saida]:
    """Retorna lista de `Saida` filtrada por regra de 6 meses para operacional.

    - `user_matricula`: matrícula do usuário (usada para perfil operacional).
    - `is_admin`: se True, retorna histórico completo (sem filtro de 6 meses).
    """
    q = db.session.query(Saida)
    if not is_admin:
        cutoff = TimeService.now_db() - timedelta(days=180)
        q = q.filter(Saida.data_saida >= cutoff)
        if user_matricula:
            q = q.filter(Saida.matricula == user_matricula)
    else:
        # admin pode ver tudo; se quiser por usuário, aplicamos matricula
        if user_matricula:
            q = q.filter(Saida.matricula == user_matricula)

    results = q.order_by(Saida.data_saida.desc()).limit(1000).all()
    return results


def enviar_relatorio_falta(bot, chat_id: str) -> dict:
    """Gera CSV de Produtos em Falta (saldo <= estoque_minimo) e envia via bot.

    Usa `/tmp/` para arquivo temporário.
    """
    reports_dir = Path("/tmp")
    reports_dir.mkdir(parents=True, exist_ok=True)
    fname = f"galint_estoque_baixo_{TimeService.now_db().strftime('%Y%m%d_%H%M%S')}.csv"
    target = reports_dir / fname

    items = Item.query.order_by(Item.codigo_item).all()
    rows = []
    for it in items:
        try:
            saldo = it.get_saldo_fisico_display()
        except Exception:
            saldo = 0
        minimo = it.estoque_minimo or 0
        if saldo <= minimo:
            codigo_display = it.codigo_item[-4:] if it.codigo_item and len(it.codigo_item) >= 4 else (it.codigo_item or "N/D")
            rows.append((codigo_display, it.descricao or "", it.categoria or "", saldo, minimo))

    if not rows:
        bot.send_message(chat_id, "✅ Nenhum item em falta (estoque abaixo do mínimo) encontrado.")
        return {"sent": False, "reason": "empty"}

    try:
        with open(target, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["codigo", "descricao", "categoria", "saldo", "minimo"])
            for r in rows:
                writer.writerow(r)

        with open(target, "rb") as fh:
            bot.send_document(chat_id, fh, caption="Relatório: Produtos em Falta")

        return {"sent": True, "path": str(target)}
    except Exception as e:
        logger.exception("Erro ao gerar/enviar relatorio de falta")
        try:
            bot.send_message(chat_id, f"Erro ao gerar relatório: {e}")
        except Exception:
            logger.exception("Falha ao notificar usuário do erro")
        return {"sent": False, "error": str(e)}


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def enviar_saidas_dia_pdf(bot, chat_id: str) -> dict:
    from ..utils.time_service import TimeService

    today = TimeService.now_local().date()

    try:
        # Relatório comum (report_export_service): o mesmo PDF legível do app e do site. Antes este
        # PDF era montado aqui e buscava das 3h de hoje às 3h de amanhã (convertia para UTC uma data
        # que o banco grava na hora de São Paulo).
        from ..services.report_export_service import daily_report

        report = daily_report(today)
        file_obj = BytesIO(report.render("pdf"))
        file_obj.name = f"saidas_dia_{today.strftime('%Y%m%d')}.pdf"
        bot.send_document(chat_id, file_obj, caption="Relatório: Saídas do Dia")
        return {"sent": True, "count": len(report.sections[0].rows)}
    except Exception as e:
        logger.exception("Erro ao gerar/enviar PDF de saídas do dia")
        try:
            bot.send_message(chat_id, f"Erro ao gerar relatório: {e}")
        except Exception:
            logger.exception("Falha ao notificar usuário do erro")
        return {"sent": False, "error": str(e)}


@bp.route("/webhook", methods=["POST"])
def webhook():
    """Rota simples para receber updates do Telegram (webhook)."""
    update = request.get_json(force=True, silent=True) or {}

    # Se o polling estiver ativo, ignore webhook para evitar duplicidade.
    try:
        if os.environ.get("GALINT_TELEGRAM_POLLING", "true").strip().lower() in ("1", "true", "yes"):
            return jsonify({"ok": True, "ignored": True, "reason": "polling_enabled"})
    except Exception:
        pass

    # Obter token do config
    cfg = TelegramConfig.query.first()
    token = cfg.bot_token if cfg and cfg.bot_token else None
    if not token:
        logger.warning("Webhook recebido mas bot token não configurado")
        return jsonify({"ok": False, "error": "bot token not configured"}), 400

    try:
        bot = _get_bot(token)
    except Exception as e:
        logger.exception("Falha ao inicializar bot telebot")
        return jsonify({"ok": False, "error": str(e)}), 500

    # Mensagem padrão
    message = update.get("message")
    callback = update.get("callback_query")

    try:
        if callback:
            data = callback.get("data")
            chat_id = callback.get("message", {}).get("chat", {}).get("id")
            chat_id = str(chat_id)
            # tratar callbacks
            if data == "retiradas_ferramentas":
                # Enviar resumo curto
                rows = buscar_movimentacoes_saida(None, True)
                bot.send_message(chat_id, f"Resumo de retiradas (ferramentas): {len(rows)} registros (últimos registros mostrados no painel).")
                return jsonify({"ok": True})
            if data == "retiradas_materiais":
                rows = buscar_movimentacoes_saida(None, True)
                bot.send_message(chat_id, f"Resumo de retiradas (materiais): {len(rows)} registros.")
                return jsonify({"ok": True})
            if data == "baixar_estoque_baixo":
                enviar_relatorio_falta(bot, chat_id)
                return jsonify({"ok": True})

            TelegramService.handle_callback_query(callback)
            return jsonify({"ok": True})

        if message:
            chat_id = message.get("chat", {}).get("id")
            chat_id_str = str(chat_id)
            if message.get("photo"):
                TelegramService.handle_photo(chat_id_str, message.get("photo") or [])
                return jsonify({"ok": True})

            text = message.get("text", "") or ""

            # localizar usuário vinculado para permissões
            tuser = TelegramUser.query.filter_by(chat_id=chat_id_str).first()
            usuario = None
            is_admin = False
            can_create_item = False
            if tuser:
                usuario = Usuario.query.get(tuser.matricula)
                is_admin = bool(getattr(usuario, "is_admin", 0) == 1)
                can_create_item = bool(getattr(tuser, "can_create_item_via_telegram", False))

            # Comando /start -> enviar menu apropriado
            if text.lower().startswith("/start") or text.strip().lower() == "menu":
                kb = gerar_menu_principal(is_admin, can_create_item=can_create_item)
                if kb is None:
                    bot.send_message(chat_id_str, "Menu não disponível (biblioteca telebot ausente)")
                else:
                    bot.send_message(chat_id_str, "Menu — selecione uma opção:", reply_markup=kb)
                return jsonify({"ok": True})

            if text.strip().lower().startswith("/scanear") or text.strip() == "📸 Escanear Código":
                TelegramService.handle_command_scanear(chat_id_str)
                return jsonify({"ok": True})

            if text.strip().lower().startswith("/cadastrar_item") or text.strip() == "🆕 Cadastrar Item":
                TelegramService.handle_menu_text(chat_id_str, "cadastrar item")
                return jsonify({"ok": True})

            try:
                if TelegramService.handle_menu_text(chat_id_str, text):
                    return jsonify({"ok": True})
            except Exception:
                pass

            # Textos de menu simples
            if text == "📤 Consultar Retiradas":
                kb = gerar_submenu_retiradas()
                if kb:
                    bot.send_message(chat_id_str, "Escolha categoria:", reply_markup=kb)
                return jsonify({"ok": True})

            if text == "📦 Consultar Estoque" and is_admin:
                kb = gerar_submenu_estoque()
                if kb:
                    bot.send_message(chat_id_str, "Opções de Estoque:", reply_markup=kb)
                return jsonify({"ok": True})

            if text == "📄 Saídas do Dia (PDF)" and is_admin:
                enviar_saidas_dia_pdf(bot, chat_id_str)
                return jsonify({"ok": True})

            # Buscar item
            if text.startswith("/estoque") or text.startswith("🔍") or text.startswith("/buscar"):
                term = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else None
                if not term:
                    bot.send_message(chat_id_str, "Use: /estoque <codigo ou termo>")
                    return jsonify({"ok": True})
                itens = Item.query.filter((Item.codigo_item == term) | (Item.descricao.ilike(f"%{term}%"))).limit(10).all()
                if not itens:
                    bot.send_message(chat_id_str, f"Nenhum item encontrado: {term}")
                    return jsonify({"ok": True})
                msgs = []
                for it in itens:
                    try:
                        saldo = it.get_saldo_fisico_display()
                    except Exception:
                        saldo = "N/A"
                    msgs.append(f"• {it.codigo_item} — {it.descricao} — Saldo: {saldo}")
                bot.send_message(chat_id_str, "\n".join(msgs))
                return jsonify({"ok": True})

            if text.startswith("/saidas_hoje") and is_admin:
                enviar_saidas_dia_pdf(bot, chat_id_str)
                return jsonify({"ok": True})

    except Exception as e:
        logger.exception("Erro ao processar update do webhook")
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})
