"""Gerenciador de conversas Telegram para menus avançados de relatórios.

Implementa máquina de estados para:
1. Seleção de período (1-6 meses)
2. Seleção de categoria
3. Confirmação de saída em PDF
4. Geração e envio de relatório
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..extensions import db
from ..models import TelegramConversation
from .telegram_reports import TelegramReportService
from .telegram_service import TelegramService

logger = logging.getLogger(__name__)


class TelegramConversationManager:
    """Gerencia fluxos de conversação multi-etapa no Telegram."""

    # Estados possíveis
    STATE_PERIOD_SELECTION = "awaiting_period"
    STATE_CATEGORY_SELECTION = "awaiting_category"
    STATE_FORMAT_SELECTION = "awaiting_format"
    STATE_COMPLETED = "completed"

    @staticmethod
    def start_withdrawals_report_flow(chat_id: str, scope: str = "all") -> None:
        """Inicia o fluxo de geração de relatório de retiradas.
        
        Mostra menu com opções de período (1-6 meses).
        """
        try:
            # Limpar conversação anterior se existir
            TelegramConversation.query.filter_by(chat_id=chat_id).delete()
            db.session.commit()
            
            # Criar nova conversa
            conversation = TelegramConversation(
                chat_id=chat_id,
                state=TelegramConversationManager.STATE_PERIOD_SELECTION,
            )
            db.session.add(conversation)
            db.session.commit()

            TelegramConversationManager._update_conversation(
                chat_id,
                TelegramConversationManager.STATE_PERIOD_SELECTION,
                {"scope": scope},
            )
            
            # Enviar menu de período
            TelegramConversationManager._send_period_menu(chat_id, scope=scope)
        except Exception as e:
            logger.exception(f"Erro ao iniciar fluxo de relatório: {e}")
            TelegramService.send_message(
                chat_id,
                "❌ Erro ao iniciar relatório. Tente novamente.",
            )

    @staticmethod
    def _send_period_menu(chat_id: str, scope: str = "all") -> None:
        """Envia menu de seleção de período."""
        # Construir inline keyboard manualmente (sem telebot)
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📅 1 Mês (30 dias)", "callback_data": "period_1"},
                    {"text": "📅 2 Meses (60 dias)", "callback_data": "period_2"},
                ],
                [
                    {"text": "📅 3 Meses (90 dias)", "callback_data": "period_3"},
                    {"text": "📅 4 Meses (120 dias)", "callback_data": "period_4"},
                ],
                [
                    {"text": "📅 5 Meses (150 dias)", "callback_data": "period_5"},
                    {"text": "📅 6 Meses (180 dias)", "callback_data": "period_6"},
                ],
                [
                    {"text": "❌ Cancelar", "callback_data": "report_cancel"}
                ],
            ]
        }
        
        scope_label = {
            "tools": "Ferramentas",
            "materials": "Materiais",
            "all": "Geral",
        }.get(scope, "Geral")

        message = (
            "📊 <b>Relatório de Retiradas</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Escopo: <b>{scope_label}</b>\n"
            "Período: <b>1–6 meses</b>\n\n"
            "Selecione o período que deseja analisar:" 
        )
        
        TelegramService.send_message(chat_id, message, reply_markup=keyboard, parse_mode="HTML")

    @staticmethod
    def _send_category_menu(chat_id: str, months: int, scope: str = "all") -> None:
        """Envia menu de seleção de categoria."""
        categories = TelegramReportService.get_categories(scope=scope)
        
        # Construir inline keyboard manualmente
        buttons = []
        
        # Adicionar opção "Todas as categorias"
        buttons.append([{"text": "📦 Todas as Categorias", "callback_data": f"category_all_{months}"}])
        
        # Adicionar cada categoria (limitar a 12)
        for category in categories[:12]:
            safe_category = category.replace(" ", "_").replace("/", "_")
            buttons.append([{"text": f"• {category}", "callback_data": f"category_{safe_category}_{months}"}])
        
        # Navegação
        buttons.append([
            {"text": "⬅️ Voltar", "callback_data": "report_back_period"},
            {"text": "❌ Cancelar", "callback_data": "report_cancel"}
        ])
        
        keyboard = {"inline_keyboard": buttons}
        
        period_text = TelegramReportService.MONTHS.get(months, f"{months} meses")
        scope_label = {
            "tools": "Ferramentas",
            "materials": "Materiais",
            "all": "Geral",
        }.get(scope, "Geral")
        message = (
            "🏷️ <b>Seleção de Categoria</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Período: <b>{period_text}</b>\n"
            f"Escopo: <b>{scope_label}</b>\n\n"
            "Escolha uma categoria (ou <b>Todas</b>):"
        )
        
        TelegramService.send_message(chat_id, message, reply_markup=keyboard, parse_mode="HTML")

    @staticmethod
    def _send_format_menu(chat_id: str, months: int, category: Optional[str], scope: str = "all") -> None:
        """Envia menu de confirmação da saída em PDF."""
        safe_category = category.replace(" ", "_").replace("/", "_") if category else "all"
        
        # Construir inline keyboard manualmente
        keyboard = {
            "inline_keyboard": [
                [{"text": "📕 PDF (Documento)", "callback_data": f"format_pdf_{months}_{safe_category}"}],
                [
                    {"text": "⬅️ Voltar", "callback_data": f"report_back_category_{months}"},
                    {"text": "❌ Cancelar", "callback_data": "report_cancel"}
                ],
            ]
        }
        
        period_text = TelegramReportService.MONTHS.get(months, f"{months} meses")
        category_text = category if category else "Todas as categorias"
        scope_label = {
            "tools": "Ferramentas",
            "materials": "Materiais",
            "all": "Geral",
        }.get(scope, "Geral")
        
        message = (
            "📥 <b>Saída do Relatório</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Período:</b> {period_text}\n"
            f"<b>Escopo:</b> {scope_label}\n"
            f"<b>Categoria:</b> {category_text}\n\n"
            "Confirme o envio do relatório em PDF:" 
        )
        
        TelegramService.send_message(chat_id, message, reply_markup=keyboard, parse_mode="HTML")

    @staticmethod
    def handle_callback(callback_data: str, chat_id: str) -> bool:
        """Processa callbacks do teclado inline.
        
        Returns:
            True se processou o callback
        """
        try:
            parts = callback_data.split("_", 2)
            
            if callback_data.startswith("period_"):
                # Seleção de período
                months = int(callback_data.split("_")[1])
                meta = TelegramConversationManager._get_metadata(chat_id)
                scope = (meta.get("scope") if isinstance(meta, dict) else None) or "all"
                TelegramConversationManager._update_conversation(
                    chat_id,
                    TelegramConversationManager.STATE_CATEGORY_SELECTION,
                    {"months": months},
                )
                TelegramConversationManager._send_category_menu(chat_id, months, scope=scope)
                return True
            
            elif callback_data.startswith("category_"):
                # Seleção de categoria
                parts = callback_data.split("_")
                months = int(parts[-1])
                category_safe = "_".join(parts[1:-1])
                
                # Converter de volta para nome original
                if category_safe == "all":
                    category = None
                else:
                    # Buscar categoria original
                    meta = TelegramConversationManager._get_metadata(chat_id)
                    scope = (meta.get("scope") if isinstance(meta, dict) else None) or "all"
                    categories = TelegramReportService.get_categories(scope=scope)
                    category = None
                    for cat in categories:
                        if cat.replace(" ", "_").replace("/", "_") == category_safe:
                            category = cat
                            break

                meta2 = TelegramConversationManager._get_metadata(chat_id)
                scope2 = (meta2.get("scope") if isinstance(meta2, dict) else None) or "all"
                
                TelegramConversationManager._update_conversation(
                    chat_id,
                    TelegramConversationManager.STATE_FORMAT_SELECTION,
                    {"months": months, "category": category},
                )
                TelegramConversationManager._send_format_menu(chat_id, months, category, scope=scope2)
                return True
            
            elif callback_data.startswith("format_"):
                # Geração de relatório
                parts = callback_data.split("_")
                file_format = "pdf"
                months = int(parts[2])
                category_safe = "_".join(parts[3:]) if len(parts) > 3 else "all"
                
                # Converter de volta para nome original
                if category_safe == "all":
                    category = None
                else:
                    meta = TelegramConversationManager._get_metadata(chat_id)
                    scope = (meta.get("scope") if isinstance(meta, dict) else None) or "all"
                    categories = TelegramReportService.get_categories(scope=scope)
                    category = None
                    for cat in categories:
                        if cat.replace(" ", "_").replace("/", "_") == category_safe:
                            category = cat
                            break

                meta2 = TelegramConversationManager._get_metadata(chat_id)
                scope2 = (meta2.get("scope") if isinstance(meta2, dict) else None) or "all"
                
                TelegramConversationManager._generate_and_send_report(
                    chat_id, months, category, file_format, scope=scope2
                )
                TelegramConversationManager._update_conversation(
                    chat_id,
                    TelegramConversationManager.STATE_COMPLETED,
                )
                return True
            
            elif callback_data == "report_back_period":
                # Voltar para seleção de período
                meta = TelegramConversationManager._get_metadata(chat_id)
                scope = (meta.get("scope") if isinstance(meta, dict) else None) or "all"
                TelegramConversationManager._send_period_menu(chat_id, scope=scope)
                return True
            
            elif callback_data.startswith("report_back_category_"):
                # Voltar para seleção de categoria
                months = int(callback_data.split("_")[-1])
                meta = TelegramConversationManager._get_metadata(chat_id)
                scope = (meta.get("scope") if isinstance(meta, dict) else None) or "all"
                TelegramConversationManager._send_category_menu(chat_id, months, scope=scope)
                return True
            
            elif callback_data == "report_cancel":
                # Cancelar
                TelegramService.send_message(
                    chat_id,
                    "❌ Operação cancelada.",
                )
                TelegramConversation.query.filter_by(chat_id=chat_id).delete()
                db.session.commit()
                return True
            
            return False
        except Exception as e:
            logger.exception(f"Erro ao processar callback {callback_data}: {e}")
            TelegramService.send_message(
                chat_id,
                "❌ Erro ao processar sua solicitação.",
            )
            return False

    @staticmethod
    def _generate_and_send_report(
        chat_id: str,
        months: int,
        category: Optional[str],
        file_format: str,
        scope: str = "all",
    ) -> None:
        """Gera relatório e envia para o usuário."""
        try:
            TelegramService.send_message(
                chat_id,
                "⏳ Gerando relatório... Aguarde.",
            )
            
            period_text = TelegramReportService.MONTHS.get(months, f"{months} meses")
            category_text = f" - {category}" if category else " - Todas as categorias"

            scope_label = {
                "tools": "Ferramentas",
                "materials": "Materiais",
                "all": "Geral",
            }.get(scope, "Geral")
            scope_text = f" - {scope_label}"

            try:
                filepath = TelegramReportService.generate_pdf_report(months, category, scope=scope)
                caption = f"📕 Relatório PDF: {period_text}{scope_text}{category_text}"
                TelegramService.send_document(chat_id, str(filepath), caption=caption)
            except Exception as e:
                logger.error(f"Erro ao gerar PDF: {e}")
                TelegramService.send_message(
                    chat_id,
                    f"⚠️ Erro ao gerar PDF: {str(e)[:100]}",
                )
            
            TelegramService.send_message(
                chat_id,
                "✅ Relatório enviado com sucesso!\n\nO que deseja fazer agora?",
                parse_mode=None,
                reply_markup={
                    "inline_keyboard": [
                        [
                            {"text": "📊 Voltar aos Relatórios", "callback_data": "reports:menu"},
                            {"text": "⬅️ Menu Principal", "callback_data": "menu:main"},
                        ]
                    ]
                },
            )
        except Exception as e:
            logger.exception(f"Erro ao gerar/enviar relatório: {e}")
            TelegramService.send_message(
                chat_id,
                f"❌ Erro ao processar relatório: {str(e)[:100]}",
            )

    @staticmethod
    def _update_conversation(
        chat_id: str,
        state: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Atualiza estado da conversa."""
        try:
            conv = TelegramConversation.query.filter_by(chat_id=chat_id).first()
            if not conv:
                conv = TelegramConversation(chat_id=chat_id)
                db.session.add(conv)
            
            conv.state = state
            if metadata:
                # Merge de metadata (não sobrescreve o que já existe)
                current = {}
                try:
                    if conv.celular_informado:
                        current = json.loads(conv.celular_informado) or {}
                except Exception:
                    current = {}
                if not isinstance(current, dict):
                    current = {}
                current.update(metadata)
                conv.celular_informado = json.dumps(current)
            
            db.session.commit()
        except Exception as e:
            logger.error(f"Erro ao atualizar conversa: {e}")

    @staticmethod
    def _get_metadata(chat_id: str) -> dict:
        try:
            conv = TelegramConversation.query.filter_by(chat_id=chat_id).first()
            if not conv or not conv.celular_informado:
                return {}
            data = json.loads(conv.celular_informado) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
