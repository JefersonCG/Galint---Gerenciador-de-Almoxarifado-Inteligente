"""Service para gerenciamento de retirada temporária de ferramentas."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_

from ..extensions import db
from ..models import Item, RetiradaFerramenta, Usuario


class FerramentasService:
    """Gerencia retiradas temporárias de ferramentas com controle de devolução."""
    
    def _calcular_saldo_disponivel(self, codigo_item: str) -> float:
        """Calcula saldo disponível descontando ferramentas em uso.
        
        Saldo disponível = Saldo total - Quantidade em uso (retiradas ativas)
        """
        item = Item.query.get(codigo_item)
        if not item:
            return 0.0
        
        # Saldo total no estoque
        saldo_total = item.get_saldo_atual()
        
        # Quantidade atualmente em uso (retiradas ativas)
        from sqlalchemy import func
        quantidade_em_uso = db.session.query(
            func.coalesce(func.sum(RetiradaFerramenta.quantidade), 0)
        ).filter(
            RetiradaFerramenta.codigo_item == codigo_item,
            RetiradaFerramenta.status == 'em_uso'
        ).scalar() or 0.0
        
        saldo_disponivel = saldo_total - quantidade_em_uso
        return max(0.0, saldo_disponivel)  # Nunca retornar negativo
    
    def retirar_ferramenta(
        self,
        *,
        codigo_item: str,
        matricula: str,
        quantidade: int = 1,
        local_servico: str | None = None,
        observacao: str | None = None,
        dias_previstos: int = 0,
    ) -> int:
        """Registra retirada de ferramenta."""
        # Valida item
        item = Item.query.get(codigo_item)
        if not item:
            raise ValueError("Ferramenta não encontrada")
        
        # Valida usuário
        usuario = Usuario.query.get(matricula)
        if not usuario:
            raise ValueError("Usuário não encontrado")
        
        # CRÍTICO: Verifica saldo disponível DESCONTANDO ferramentas já retiradas
        saldo_disponivel = self._calcular_saldo_disponivel(codigo_item)
        if saldo_disponivel < quantidade:
            # Informar quantas estão em uso para diagnóstico
            from sqlalchemy import func
            em_uso = db.session.query(
                func.coalesce(func.sum(RetiradaFerramenta.quantidade), 0)
            ).filter(
                RetiradaFerramenta.codigo_item == codigo_item,
                RetiradaFerramenta.status == 'em_uso'
            ).scalar() or 0
            
            raise ValueError(
                f"Saldo insuficiente. Disponível: {int(saldo_disponivel)} "
                f"(Em uso: {int(em_uso)}, Total: {int(item.get_saldo_atual())})"
            )
        
        # Calcula data prevista de devolução
        data_prevista = None
        if dias_previstos > 0:
            data_prevista = date.today() + timedelta(days=dias_previstos)
        else:
            # Padrão: mesmo dia (até meia-noite)
            data_prevista = date.today()
        
        # Cria registro
        retirada = RetiradaFerramenta(
            codigo_item=codigo_item,
            matricula=matricula,
            quantidade=quantidade,
            local_servico=local_servico,
            observacao=observacao,
            data_prevista_devolucao=data_prevista,
            status='em_uso',
        )
        
        db.session.add(retirada)
        db.session.commit()
        
        # Atualizar status de atrasadas automaticamente
        self._atualizar_status_atrasadas()
        
        return retirada.id
    
    def devolver_ferramenta(self, retirada_id: int, observacao: str | None = None):
        """Registra devolução de ferramenta."""
        retirada = RetiradaFerramenta.query.get(retirada_id)
        if not retirada:
            raise ValueError("Retirada não encontrada")
        
        if retirada.status == 'devolvida':
            raise ValueError("Ferramenta já foi devolvida")
        
        if retirada.status == 'para_reparo':
            raise ValueError("Ferramenta está marcada para reparo")
        
        retirada.registrar_devolucao(observacao)
        db.session.commit()
        
        # Notificar devolução via Telegram
        try:
            self._notificar_devolucao_telegram(retirada)
        except Exception as e:
            # Não falhar a devolução por causa de erro no Telegram
            print(f"Erro ao notificar devolução via Telegram: {e}")
    
    def _notificar_devolucao_telegram(self, retirada: RetiradaFerramenta):
        """Envia notificação de devolução de ferramenta via Telegram."""
        from .telegram_service import TelegramService
        from ..models import TelegramUser
        from .time_service import TimeService
        
        if not TelegramService.is_enabled():
            return
        
        # Buscar item e usuário
        item = Item.query.get(retirada.codigo_item)
        usuario = Usuario.query.get(retirada.matricula)
        
        if not item:
            return
        
        # Categoria do item
        categoria = (item.categoria or "Material").strip().upper()
        
        # Ajuste para singular
        if "FERRAMENTAS" in categoria:
            categoria_titulo = "FERRAMENTA"
        elif categoria.endswith("S") and len(categoria) > 3:
            categoria_titulo = categoria[:-1]
        else:
            categoria_titulo = categoria
        
        # Emojis por categoria
        emoji_map = {
            "ferramenta": "🔧",
            "ferramentas": "🔧",
            "material elétrico": "⚡",
            "material eletrico": "⚡",
            "material hidráulico": "🚰",
            "material hidraulico": "🚰",
            "material piscina": "🏊",
            "materiais de limpeza": "🧹",
            "material de limpeza": "🧹",
            "material construção": "🏗️",
            "material de ep": "🦺",
            "epi": "🦺",
        }
        emoji = emoji_map.get(categoria.lower(), "📦")
        
        # Calcular saldo atual
        saldo_atual = item.get_saldo_atual()
        
        # Montar mensagem
        data_fmt = TimeService.format_local(retirada.data_devolucao, "%d/%m/%Y %H:%M")
        nome_usuario = usuario.nome if usuario else f"Matrícula {retirada.matricula}"
        
        message = f"✅ <b>DEVOLUÇÃO DE {categoria_titulo}</b>\n\n"
        message += f"{emoji} <b>{item.descricao}</b>\n"
        message += f"🏷️ Código: <code>{item.codigo_item}</code>\n"
        message += f"📦 Quantidade: <b>{retirada.quantidade}</b> {item.unidade or 'un.'}\n\n"
        message += f"👤 <b>Devolvido por:</b> {nome_usuario}\n"
        message += f"📅 <b>Data:</b> {data_fmt}\n"
        message += f"📊 <b>Saldo Atual:</b> {saldo_atual} {item.unidade or 'un.'}\n"
        
        if retirada.observacao_devolucao:
            message += f"\n📝 <b>Obs:</b> {retirada.observacao_devolucao}"
        
        # Enviar para administradores usando sistema de outbox com idempotência
        admins = (
            db.session.query(TelegramUser)
            .filter(TelegramUser.is_admin == True, TelegramUser.chat_id.isnot(None))
            .all()
        )
        
        for admin in admins:
            try:
                # Chave de idempotência baseada no ID da retirada + chat_id do admin
                key = f"tool_return:{retirada.id}:admin:{admin.chat_id}"
                TelegramService.enqueue_outbox_message(
                    chat_id=str(admin.chat_id),
                    recipient_name=admin.usuario.nome if getattr(admin, 'usuario', None) else None,
                    message_type="tool_return",
                    message_text=message,
                    idempotency_key=key,
                    commit=False,
                )
            except Exception:
                pass
        
        # Commit todas as mensagens de uma vez
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    
    def marcar_para_reparo(self, retirada_id: int, observacao: str):
        """Marca ferramenta para reparo."""
        if not observacao or not observacao.strip():
            raise ValueError("Informe o motivo do reparo")
        
        retirada = RetiradaFerramenta.query.get(retirada_id)
        if not retirada:
            raise ValueError("Retirada não encontrada")
        
        if retirada.status == 'devolvida':
            raise ValueError("Ferramenta já foi devolvida")
        
        retirada.marcar_para_reparo(observacao)
        db.session.commit()
    
    def listar_em_uso(self) -> list[dict[str, Any]]:
        """Lista ferramentas ainda em uso (independente da data)."""
        retiradas = (
            RetiradaFerramenta.query
            .filter(RetiradaFerramenta.status == 'em_uso')
            .order_by(RetiradaFerramenta.data_retirada.desc())
            .all()
        )
        return [r.to_dict() for r in retiradas]
    
    def listar_atrasadas(self) -> list[dict[str, Any]]:
        """Lista ferramentas não devolvidas (atrasadas)."""
        self._atualizar_status_atrasadas()
        
        retiradas = (
            RetiradaFerramenta.query
            .filter(RetiradaFerramenta.status == 'atrasada')
            .order_by(RetiradaFerramenta.data_retirada.asc())
            .all()
        )
        return [r.to_dict() for r in retiradas]
    
    def listar_para_reparo(self) -> list[dict[str, Any]]:
        """Lista ferramentas marcadas para reparo."""
        retiradas = (
            RetiradaFerramenta.query
            .filter(RetiradaFerramenta.status == 'para_reparo')
            .order_by(RetiradaFerramenta.updated_at.desc())
            .all()
        )
        return [r.to_dict() for r in retiradas]
    
    def listar_todas(self, limit: int = 100) -> list[dict[str, Any]]:
        """Lista todas as retiradas recentes."""
        retiradas = (
            RetiradaFerramenta.query
            .order_by(RetiradaFerramenta.data_retirada.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in retiradas]
    
    def obter_estatisticas(self) -> dict[str, int]:
        """Retorna estatísticas do painel."""
        self._atualizar_status_atrasadas()

        em_uso = (
            RetiradaFerramenta.query
            .filter(RetiradaFerramenta.status == 'em_uso')
            .count()
        )
        
        atrasadas = (
            RetiradaFerramenta.query
            .filter(RetiradaFerramenta.status == 'atrasada')
            .count()
        )
        
        para_reparo = (
            RetiradaFerramenta.query
            .filter(RetiradaFerramenta.status == 'para_reparo')
            .count()
        )
        
        return {
            'em_uso': em_uso,
            'atrasadas': atrasadas,
            'para_reparo': para_reparo,
        }
    
    def _atualizar_status_atrasadas(self):
        """Atualiza automaticamente o status de ferramentas atrasadas."""
        hoje = date.today()
        
        # Atualiza para atrasada: retiradas antes de hoje que ainda não foram devolvidas
        retiradas_antigas = (
            RetiradaFerramenta.query
            .filter(
                and_(
                    RetiradaFerramenta.status == 'em_uso',
                    db.func.date(RetiradaFerramenta.data_retirada) < hoje,
                )
            )
            .all()
        )
        
        for retirada in retiradas_antigas:
            retirada.status = 'atrasada'
        
        if retiradas_antigas:
            db.session.commit()


# Singleton instance
ferramentas_service = FerramentasService()
