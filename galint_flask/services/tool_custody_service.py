"""Serviço para controle de custódia de ferramentas."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_
from ..extensions import db
from ..models import Item, RetiradaFerramenta, Saida, Usuario, InventarioEvento
from ..utils.time_service import TimeService


class ToolCustodyService:
    """Gerencia custódia de ferramentas por funcionário."""

    _PERMANENT_MARKERS = (
        "responsab",
        "uso no condominio",
        "uso no condomínio",
        "uso no condomin",
        "uso exclusivo",
        "ficou sob",
        "permanente",
    )

    @classmethod
    def _infer_tipo_custodia(cls, saida: Saida, days_in_use: int) -> str:
        raw = (getattr(saida, "tipo_custodia", None) or "").strip().lower()
        if raw == "permanente":
            return "permanente"

        texto = f"{saida.local_servico or ''} {saida.observacao or ''}".lower()
        if any(marker in texto for marker in cls._PERMANENT_MARKERS):
            return "permanente"

        if days_in_use >= 90:
            return "permanente"
        return "temporaria"

    @staticmethod
    def get_all_employees_with_tools() -> list[dict[str, Any]]:
        """Retorna todos os funcionários que possuem ferramentas ativas."""
        # Buscar saídas sem devolução (ferramentas ativas)
        query = (
            db.session.query(
                Usuario.matricula,
                Usuario.nome,
                Usuario.setor,
                Usuario.cargo,
                func.count(Saida.id_saida).label("total_ferramentas"),
                func.min(Saida.data_saida).label("mais_antiga"),
            )
            .join(Saida, Usuario.matricula == Saida.matricula)
            .join(Item, Saida.codigo_item == Item.codigo_item)
            .filter(Item.categoria == "Ferramentas")
            .group_by(Usuario.matricula, Usuario.nome, Usuario.setor, Usuario.cargo)
            .order_by(Usuario.nome)
        )
        
        results = query.all()
        employees = []
        
        for row in results:
            # Verificar se tem ferramentas sem devolução
            active_tools = ToolCustodyService._get_active_tools_for_employee(row.matricula)
            if not active_tools:
                continue
                
            days_oldest = (datetime.utcnow() - row.mais_antiga).days if row.mais_antiga else 0
            
            # Contar alertas (ferramentas há mais de 30 dias)
            alerts = sum(1 for tool in active_tools if tool["days_in_use"] > 30)
            
            # Separar por tipo de custódia
            tools_temporaria = [t for t in active_tools if t.get("tipo_custodia") == "temporaria"]
            tools_permanente = [t for t in active_tools if t.get("tipo_custodia") == "permanente"]
            
            employees.append({
                "matricula": row.matricula,
                "nome": row.nome,
                "setor": row.setor or "N/D",
                "cargo": row.cargo or "N/D",
                "total_ferramentas": len(active_tools),
                "days_oldest": days_oldest,
                "has_alerts": alerts > 0,
                "alerts_count": alerts,
                "tools": active_tools,
                "has_temporaria": len(tools_temporaria) > 0,
                "has_permanente": len(tools_permanente) > 0,
                "total_temporaria": len(tools_temporaria),
                "total_permanente": len(tools_permanente),
            })
        
        return employees

    @staticmethod
    def _get_active_tools_for_employee(matricula: str) -> list[dict[str, Any]]:
        """Retorna ferramentas ativas (sem devolução) de um funcionário."""
        # Buscar todas as saídas de ferramentas
        saidas = (
            db.session.query(Saida, Item)
            .join(Item, Saida.codigo_item == Item.codigo_item)
            .filter(
                Saida.matricula == matricula,
                Item.categoria == "Ferramentas"
            )
            .order_by(Saida.data_saida.desc())
            .all()
        )
        
        active_tools = []
        
        for saida, item in saidas:
            # Verificar se tem devolução registrada
            devolucao = (
                db.session.query(InventarioEvento)
                .filter(
                    InventarioEvento.matricula == matricula,
                    InventarioEvento.codigo_item == saida.codigo_item,
                    InventarioEvento.tipo.in_([
                        "devolucao_ferramenta",
                        "devolucao_material",
                        "quebra_ferramenta",
                        "reparo_ferramenta",
                    ]),
                    InventarioEvento.data_evento >= saida.data_saida,
                )
                .first()
            )
            
            if not devolucao:
                days_in_use = (datetime.utcnow() - saida.data_saida).days
                # Tratar NULL como 'temporaria' (getattr não trata None)
                tipo_custodia = ToolCustodyService._infer_tipo_custodia(saida, days_in_use)
                
                # Alertas só para ferramentas temporárias
                is_alert = (tipo_custodia == 'temporaria' and days_in_use > 30)
                
                active_tools.append({
                    "saida_id": saida.id_saida,
                    "codigo_item": item.codigo_item,
                    "descricao": item.descricao,
                    "categoria": item.categoria,
                    "marca": item.marca or "N/D",
                    "quantidade": saida.quantidade,
                    "data_saida": saida.data_saida,
                    "data_saida_formatada": TimeService.format_local(saida.data_saida, "%d/%m/%Y %H:%M"),
                    "local_servico": saida.local_servico or "Não informado",
                    "observacao": saida.observacao or "",
                    "days_in_use": days_in_use,
                    "is_alert": is_alert,
                    "tipo_custodia": tipo_custodia,
                })
        
        return active_tools

    @staticmethod
    def get_employee_details(matricula: str) -> dict[str, Any] | None:
        """Retorna detalhes completos de um funcionário e suas ferramentas."""
        usuario = Usuario.query.get(matricula)
        if not usuario:
            return None
        
        active_tools = ToolCustodyService._get_active_tools_for_employee(matricula)
        history = ToolCustodyService._get_employee_history(matricula, days=30)
        
        # Separar por tipo de custódia
        tools_permanente = [t for t in active_tools if t.get("tipo_custodia") == "permanente"]
        tools_temporaria = [t for t in active_tools if t.get("tipo_custodia") != "permanente"]
        
        return {
            "matricula": usuario.matricula,
            "nome": usuario.nome,
            "setor": usuario.setor or "N/D",
            "cargo": usuario.cargo or "N/D",
            "active_tools": active_tools,
            "tools_permanente": tools_permanente,
            "tools_temporaria": tools_temporaria,
            "history": history,
            "total_active": len(active_tools),
            "total_history": len(history),
        }

    @staticmethod
    def _get_employee_history(matricula: str, days: int = 30) -> list[dict[str, Any]]:
        """Retorna histórico de devoluções dos últimos N dias."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        devolucoes = (
            db.session.query(InventarioEvento, Item, Usuario)
            .join(Item, InventarioEvento.codigo_item == Item.codigo_item)
            .outerjoin(Usuario, Usuario.matricula == InventarioEvento.matricula)
            .filter(
                InventarioEvento.matricula == matricula,
                InventarioEvento.tipo.in_([
                    "devolucao_ferramenta",
                    "devolucao_material",
                    "quebra_ferramenta",
                    "reparo_ferramenta",
                ]),
                InventarioEvento.data_evento >= cutoff,
            )
            .order_by(InventarioEvento.data_evento.desc())
            .all()
        )
        
        history = []
        for evento, item, usuario_dev in devolucoes:
            tipo_label = {
                "devolucao_ferramenta": "Devolveu",
                "devolucao_material": "Devolveu",
                "quebra_ferramenta": "Quebrou/Danificou",
                "reparo_ferramenta": "Enviou para Reparo",
            }.get(evento.tipo, "Ação")
            
            history.append({
                "data": evento.data_evento,
                "tipo": tipo_label,
                "descricao": item.descricao,
                "observacao": evento.descricao or "",
                "devolvido_por": usuario_dev.nome if usuario_dev else None,
                "matricula_dev": usuario_dev.matricula if usuario_dev else None,
            })
        
        return history

    @staticmethod
    def register_return(retirada_id: int, observacao: str | None = None) -> None:
        """Registra devolução de ferramenta (custódia diária)."""
        retirada = RetiradaFerramenta.query.get(retirada_id)

        if not retirada:
            # Compatibilidade: alguns fluxos enviam id da Saida
            saida = Saida.query.get(retirada_id)
            if not saida:
                raise ValueError("Retirada não encontrada")

            # Garantir que é ferramenta
            categoria = (saida.item.categoria or "").lower() if saida.item else ""
            if "ferrament" not in categoria:
                raise ValueError("Saída não é ferramenta")

            retirada = (
                RetiradaFerramenta.query
                .filter(
                    RetiradaFerramenta.codigo_item == saida.codigo_item,
                    RetiradaFerramenta.matricula == saida.matricula,
                    RetiradaFerramenta.status.in_(["em_uso", "atrasada"]),
                )
                .order_by(RetiradaFerramenta.data_retirada.desc())
                .first()
            )
            if not retirada:
                raise ValueError("Retirada não encontrada")

        if retirada.status == "devolvida":
            raise ValueError("Ferramenta já foi devolvida")

        if retirada.status == "para_reparo":
            raise ValueError("Ferramenta está marcada para reparo")

        retirada.registrar_devolucao(observacao)

        # Criar evento de devolução (sem ajustar estoque aqui)
        evento = InventarioEvento(
            codigo_item=retirada.codigo_item,
            matricula=retirada.matricula,
            quantidade=retirada.quantidade,
            tipo="devolucao_ferramenta",
            descricao=observacao or f"Devolução de Ferramenta: {retirada.item.descricao if retirada.item else 'Item'}",
            data_evento=datetime.utcnow(),
        )
        db.session.add(evento)
        db.session.commit()

        # Notificação opcional
        try:
            from ..services.telegram_service import TelegramService

            TelegramService.notify_inventory_event(evento.id_evento)
        except Exception:
            pass

    @staticmethod
    def register_damage(saida_id: int, observacao: str | None = None) -> None:
        """Registra ferramenta quebrada/danificada."""
        saida = Saida.query.get(saida_id)
        if not saida:
            raise ValueError("Saída não encontrada")
        
        evento = InventarioEvento(
            codigo_item=saida.codigo_item,
            matricula=saida.matricula,
            quantidade=saida.quantidade,
            tipo="quebra_ferramenta",
            descricao=observacao or f"Ferramenta danificada/perdida: {saida.item.descricao if saida.item else 'Item'}",
            data_evento=datetime.utcnow(),
        )
        
        db.session.add(evento)
        # Não ajusta estoque - ferramenta foi perdida/quebrada
        db.session.commit()

        try:
            from ..services.telegram_service import TelegramService

            TelegramService.notify_tool_damage(evento.id_evento)
        except Exception:
            pass

    @staticmethod
    def register_repair(saida_id: int, observacao: str | None = None) -> None:
        """Registra envio para reparo."""
        saida = Saida.query.get(saida_id)
        if not saida:
            raise ValueError("Saída não encontrada")
        
        evento = InventarioEvento(
            codigo_item=saida.codigo_item,
            matricula=saida.matricula,
            quantidade=saida.quantidade,
            tipo="reparo_ferramenta",
            descricao=observacao or f"Enviada para reparo: {saida.item.descricao if saida.item else 'Item'}",
            data_evento=datetime.utcnow(),
        )
        
        db.session.add(evento)
        db.session.commit()

        try:
            from ..services.telegram_service import TelegramService

            TelegramService.notify_tool_repair(evento.id_evento)
        except Exception:
            pass

    @staticmethod
    def get_statistics() -> dict[str, Any]:
        """Retorna estatísticas gerais do controle de ferramentas."""
        employees = ToolCustodyService.get_all_employees_with_tools()
        
        total_tools = sum(e["total_ferramentas"] for e in employees)
        total_alerts = sum(e["alerts_count"] for e in employees)
        
        # Devoluções hoje
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        returns_today = (
            db.session.query(func.count(InventarioEvento.id_evento))
            .filter(
                InventarioEvento.tipo.in_(["devolucao_ferramenta", "devolucao_material"]),
                InventarioEvento.data_evento >= today_start,
            )
            .scalar()
        ) or 0
        
        return {
            "total_employees": len(employees),
            "total_tools": total_tools,
            "total_alerts": total_alerts,
            "returns_today": returns_today,
        }

    @staticmethod
    def delete_tool_record(saida_id: int) -> None:
        """Exclui registro de saída de ferramenta (APENAS PARA ADMINISTRADORES)."""
        saida = Saida.query.get(saida_id)
        if not saida:
            raise ValueError("Registro não encontrado")
        
        # Excluir eventos relacionados (inventario)
        InventarioEvento.query.filter(
            InventarioEvento.codigo_item == saida.codigo_item,
            InventarioEvento.matricula == saida.matricula,
            InventarioEvento.data_evento >= saida.data_saida,
        ).delete()
        
        # Excluir registro de saída
        db.session.delete(saida)
        db.session.commit()

    @staticmethod
    def change_custody_type(saida_id: int, novo_tipo: str) -> None:
        """Altera tipo de custódia (permanente ou temporaria)."""
        saida = Saida.query.get(saida_id)
        if not saida:
            raise ValueError("Registro não encontrado")
        
        if novo_tipo not in ["temporaria", "permanente"]:
            raise ValueError("Tipo inválido. Use 'temporaria' ou 'permanente'")
        
        saida.tipo_custodia = novo_tipo
        db.session.commit()

    @staticmethod
    def send_telegram_alert(saida_id: int) -> bool:
        """Envia alerta via Telegram sobre ferramenta não devolvida."""
        saida = db.session.query(Saida, Item, Usuario).join(
            Item, Saida.codigo_item == Item.codigo_item
        ).join(
            Usuario, Saida.matricula == Usuario.matricula
        ).filter(
            Saida.id_saida == saida_id
        ).first()
        
        if not saida:
            raise ValueError("Registro não encontrado")
        
        saida_obj, item, usuario = saida
        
        # Verificar se já foi devolvida
        devolucao = db.session.query(InventarioEvento).filter(
            InventarioEvento.matricula == saida_obj.matricula,
            InventarioEvento.codigo_item == saida_obj.codigo_item,
            InventarioEvento.tipo.in_([
                "devolucao_ferramenta",
                "devolucao_material",
                "quebra_ferramenta",
                "reparo_ferramenta",
            ]),
            InventarioEvento.data_evento >= saida_obj.data_saida,
        ).first()
        
        if devolucao:
            raise ValueError("Ferramenta já foi devolvida")
        
        try:
            from ..services.telegram_service import TelegramService
            from ..utils.time_service import TimeService
            from ..models import TelegramUser
            
            days_late = (datetime.utcnow() - saida_obj.data_saida).days
            data_retirada = TimeService.format_local(saida_obj.data_saida, "%d/%m/%Y")
            
            mensagem = (
                f"⚠️ <b>ALERTA DE FERRAMENTA NÃO DEVOLVIDA</b>\n\n"
                f"<b>Funcionário:</b> {usuario.nome}\n"
                f"<b>Matrícula:</b> {usuario.matricula}\n"
                f"<b>Ferramenta:</b> {item.descricao}\n"
                f"<b>Marca:</b> {item.marca or 'N/D'}\n"
                f"<b>Quantidade:</b> {saida_obj.quantidade}\n"
                f"<b>Data da retirada:</b> {data_retirada}\n"
                f"<b>Dias sem devolução:</b> {days_late}\n"
                f"<b>Status:</b> ❌ NÃO DEVOLVIDA"
            )
            
            # Buscar todos os usuários Telegram habilitados
            telegram_users = db.session.query(TelegramUser).filter_by(enabled=True).all()
            
            # Enviar para todos os usuários habilitados
            success_count = 0
            for telegram_user in telegram_users:
                result = TelegramService.send_message(
                    chat_id=telegram_user.chat_id,
                    text=mensagem,
                    parse_mode="HTML"
                )
                if result.get("success", False):
                    success_count += 1
            
            return success_count > 0
        except Exception as e:
            import logging
            logging.error(f"Erro ao enviar alerta Telegram: {e}")
            return False

    @staticmethod
    def send_grouped_alert_by_employee(matricula: str) -> bool:
        """Envia alerta agrupado de todas as ferramentas atrasadas de um funcionário."""
        from ..services.telegram_service import TelegramService
        from ..utils.time_service import TimeService
        
        # Buscar funcionário
        usuario = Usuario.query.get(matricula)
        if not usuario:
            raise ValueError("Funcionário não encontrado")
        
        # Buscar todas as ferramentas ativas (sem devolução)
        active_tools = ToolCustodyService._get_active_tools_for_employee(matricula)
        
        # Filtrar apenas ferramentas temporárias atrasadas (> 30 dias)
        overdue_tools = [
            tool for tool in active_tools 
            if tool.get('tipo_custodia') == 'temporaria' and tool.get('days_in_use', 0) > 30
        ]
        
        if not overdue_tools:
            raise ValueError("Nenhuma ferramenta atrasada encontrada para este funcionário")
        
        # Criar mensagem consolidada
        if len(overdue_tools) == 1:
            # Se tiver apenas 1, usar formato individual
            tool = overdue_tools[0]
            data_retirada = TimeService.format_local(tool['data_saida'], "%d/%m/%Y")
            mensagem = (
                f"⚠️ <b>ALERTA: Ferramenta não devolvida</b>\n\n"
                f"👤 <b>{usuario.nome}</b>\n"
                f"📋 Matrícula: {usuario.matricula}\n"
                f"🏢 Setor: {usuario.setor or 'N/D'}\n\n"
                f"🔧 <b>{tool['descricao']}</b>\n"
                f"📦 Marca: {tool['marca']}\n"
                f"📅 Desde: {data_retirada}\n"
                f"⏰ <b>{tool['days_in_use']} dias sem devolução</b>"
            )
        else:
            # Múltiplas ferramentas - formato agrupado
            mensagem = (
                f"⚠️ <b>ALERTA: Múltiplas ferramentas não devolvidas</b>\n\n"
                f"👤 <b>{usuario.nome}</b>\n"
                f"📋 Matrícula: {usuario.matricula}\n"
                f"🏢 Setor: {usuario.setor or 'N/D'}\n"
                f"📦 <b>{len(overdue_tools)} ferramentas pendentes:</b>\n\n"
            )
            
            for i, tool in enumerate(overdue_tools, 1):
                data_retirada = TimeService.format_local(tool['data_saida'], "%d/%m/%Y")
                mensagem += (
                    f"<b>{i}. {tool['descricao']}</b>\n"
                    f"   • Marca: {tool['marca']}\n"
                    f"   • Desde: {data_retirada}\n"
                    f"   • ⏰ <b>{tool['days_in_use']} dias sem devolução</b>\n\n"
                )
        
        try:
            from ..models import TelegramUser
            
            # Buscar todos os usuários Telegram habilitados
            telegram_users = db.session.query(TelegramUser).filter_by(enabled=True).all()
            
            # Enviar para todos os usuários habilitados
            success_count = 0
            for telegram_user in telegram_users:
                result = TelegramService.send_message(
                    chat_id=telegram_user.chat_id,
                    text=mensagem,
                    parse_mode="HTML"
                )
                if result.get("success", False):
                    success_count += 1
            
            return success_count > 0
        except Exception as e:
            import logging
            logging.error(f"Erro ao enviar alerta agrupado: {e}")
            return False


tool_custody_service = ToolCustodyService()
