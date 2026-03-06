"""Serviço de gerenciamento de equipamentos em reparo."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import desc, or_
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import EquipamentoReparo, Item

logger = logging.getLogger(__name__)


class ReparoService:
    """Serviço para gerenciar o ciclo de vida de equipamentos em reparo."""

    def enviar_para_reparo(
        self,
        codigo_item: str,
        matricula_responsavel: str,
        problema_descrito: str,
        fornecedor_oficina: str | None = None,
        custo_estimado: float | None = None,
        prazo_previsto: date | None = None,
        observacoes: str | None = None,
    ) -> EquipamentoReparo:
        """
        Envia um equipamento para reparo.
        
        Args:
            codigo_item: Código do item a ser reparado
            matricula_responsavel: Matrícula do responsável pelo envio
            problema_descrito: Descrição do problema
            fornecedor_oficina: Nome do fornecedor/oficina (opcional)
            custo_estimado: Custo estimado do reparo (opcional)
            prazo_previsto: Data prevista de retorno (opcional)
            observacoes: Observações adicionais (opcional)
            
        Returns:
            EquipamentoReparo: Registro criado
            
        Raises:
            ValueError: Se o item não existir
        """
        # Validar se o item existe
        item = db.session.get(Item, codigo_item)
        if not item:
            raise ValueError(f"Item {codigo_item} não encontrado")
        
        # Criar registro de reparo (atribuição explícita evita falsos positivos de tipagem)
        reparo = EquipamentoReparo()
        reparo.codigo_item = codigo_item
        reparo.matricula_responsavel = matricula_responsavel
        reparo.problema_descrito = problema_descrito
        reparo.fornecedor_oficina = fornecedor_oficina
        reparo.custo_estimado = custo_estimado
        reparo.prazo_previsto = prazo_previsto
        reparo.observacoes = observacoes
        reparo.status = "aguardando_orcamento"
        reparo.data_envio = datetime.now()
        
        try:
            db.session.add(reparo)
            db.session.commit()
            logger.info(f"Equipamento {codigo_item} enviado para reparo (ID: {reparo.id})")
            return reparo
        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Erro ao enviar equipamento para reparo: {e}")
            raise ValueError("Erro ao registrar envio para reparo")

    def atualizar_status(
        self,
        reparo_id: int,
        novo_status: str,
        matricula_atualizador: str,
        solucao_aplicada: str | None = None,
        custo_real: float | None = None,
        observacoes: str | None = None,
    ) -> EquipamentoReparo:
        """
        Atualiza o status de um reparo.
        
        Args:
            reparo_id: ID do reparo
            novo_status: Novo status (aguardando_orcamento, em_reparo, concluido, sem_conserto)
            matricula_atualizador: Matrícula do usuário que está atualizando
            solucao_aplicada: Descrição da solução aplicada (opcional)
            custo_real: Custo real do reparo (opcional)
            observacoes: Observações adicionais (opcional)
            
        Returns:
            EquipamentoReparo: Registro atualizado
            
        Raises:
            ValueError: Se o reparo não existir ou status for inválido
        """
        # Validar status
        status_validos = ["aguardando_orcamento", "em_reparo", "concluido", "sem_conserto"]
        if novo_status not in status_validos:
            raise ValueError(f"Status inválido. Use: {', '.join(status_validos)}")
        
        # Buscar reparo
        reparo = db.session.get(EquipamentoReparo, reparo_id)
        if not reparo:
            raise ValueError(f"Reparo {reparo_id} não encontrado")
        
        # Atualizar campos
        reparo.status = novo_status
        reparo.atualizado_por = matricula_atualizador
        reparo.atualizado_em = datetime.now()
        
        if solucao_aplicada:
            reparo.solucao_aplicada = solucao_aplicada
        if custo_real is not None:
            reparo.custo_real = custo_real
        if observacoes:
            if reparo.observacoes:
                reparo.observacoes += f"\n{observacoes}"
            else:
                reparo.observacoes = observacoes
        
        # Se concluído ou sem conserto, marcar data de retorno
        if novo_status in ["concluido", "sem_conserto"] and not reparo.data_retorno:
            reparo.data_retorno = datetime.now()
        
        try:
            db.session.commit()
            logger.info(f"Reparo {reparo_id} atualizado para status '{novo_status}'")
            return reparo
        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Erro ao atualizar reparo: {e}")
            raise ValueError("Erro ao atualizar reparo")

    def finalizar_reparo(
        self,
        reparo_id: int,
        matricula_atualizador: str,
        status_final: str,
        solucao_aplicada: str | None = None,
        custo_real: float | None = None,
    ) -> EquipamentoReparo:
        """
        Finaliza um reparo (concluído ou sem conserto).
        
        Args:
            reparo_id: ID do reparo
            matricula_atualizador: Matrícula do usuário
            status_final: 'concluido' ou 'sem_conserto'
            solucao_aplicada: Descrição da solução (opcional)
            custo_real: Custo real do reparo (opcional)
            
        Returns:
            EquipamentoReparo: Registro finalizado
        """
        if status_final not in ["concluido", "sem_conserto"]:
            raise ValueError("Status final deve ser 'concluido' ou 'sem_conserto'")
        
        return self.atualizar_status(
            reparo_id=reparo_id,
            novo_status=status_final,
            matricula_atualizador=matricula_atualizador,
            solucao_aplicada=solucao_aplicada,
            custo_real=custo_real,
        )

    def listar_reparos(
        self,
        status: str | None = None,
        codigo_item: str | None = None,
        apenas_abertos: bool = False,
        limit: int = 100,
    ) -> list[EquipamentoReparo]:
        """
        Lista reparos com filtros opcionais.
        
        Args:
            status: Filtrar por status específico (opcional)
            codigo_item: Filtrar por código de item (opcional)
            apenas_abertos: Se True, retorna apenas aguardando_orcamento e em_reparo
            limit: Limite de resultados
            
        Returns:
            Lista de EquipamentoReparo
        """
        query = db.session.query(EquipamentoReparo)
        
        if status:
            query = query.filter(EquipamentoReparo.status == status)
        
        if codigo_item:
            query = query.filter(EquipamentoReparo.codigo_item == codigo_item)
        
        if apenas_abertos:
            query = query.filter(
                EquipamentoReparo.status.in_(["aguardando_orcamento", "em_reparo"])
            )
        
        # Ordenar por data de envio (mais recentes primeiro)
        query = query.order_by(desc(EquipamentoReparo.data_envio))
        
        return query.limit(limit).all()

    def get_reparo_by_id(self, reparo_id: int) -> EquipamentoReparo | None:
        """Busca um reparo pelo ID."""
        return db.session.get(EquipamentoReparo, reparo_id)

    def get_estatisticas(self) -> dict[str, Any]:
        """
        Retorna estatísticas sobre reparos.
        
        Returns:
            Dicionário com contadores por status e custos
        """
        total = db.session.query(EquipamentoReparo).count()
        
        aguardando = db.session.query(EquipamentoReparo).filter_by(status="aguardando_orcamento").count()
        em_reparo = db.session.query(EquipamentoReparo).filter_by(status="em_reparo").count()
        concluido = db.session.query(EquipamentoReparo).filter_by(status="concluido").count()
        sem_conserto = db.session.query(EquipamentoReparo).filter_by(status="sem_conserto").count()
        
        # Custos totais
        from sqlalchemy import func
        custo_total = db.session.query(
            func.sum(EquipamentoReparo.custo_real)
        ).filter(
            EquipamentoReparo.custo_real.isnot(None)
        ).scalar() or 0.0
        
        return {
            "total": total,
            "aguardando_orcamento": aguardando,
            "em_reparo": em_reparo,
            "concluido": concluido,
            "sem_conserto": sem_conserto,
            "abertos": aguardando + em_reparo,
            "custo_total": float(custo_total),
        }

    def buscar_reparos(
        self,
        termo_busca: str,
        limit: int = 50
    ) -> list[EquipamentoReparo]:
        """
        Busca reparos por código de item, descrição ou fornecedor.
        
        Args:
            termo_busca: Termo a buscar
            limit: Limite de resultados
            
        Returns:
            Lista de EquipamentoReparo
        """
        termo = f"%{termo_busca}%"
        
        query = (
            db.session.query(EquipamentoReparo)
            .join(Item, EquipamentoReparo.codigo_item == Item.codigo_item)
            .filter(
                or_(
                    EquipamentoReparo.codigo_item.ilike(termo),
                    Item.descricao.ilike(termo),
                    EquipamentoReparo.fornecedor_oficina.ilike(termo),
                    EquipamentoReparo.problema_descrito.ilike(termo),
                )
            )
            .order_by(desc(EquipamentoReparo.data_envio))
        )
        
        return query.limit(limit).all()


# Instância singleton
reparo_service = ReparoService()
