# -*- coding: utf-8 -*-
"""
Serviço de Gestão de Códigos Patrimoniais
==========================================
Gerencia múltiplos códigos patrimoniais por item (relacionamento 1-para-muitos).

Funcionalidades:
- Adicionar códigos patrimoniais em lote (PAT-001 a PAT-020)
- Consultar códigos disponíveis para retirada
- Atribuir código patrimonial a saída (vincular a colaborador)
- Devolver código patrimonial (liberar para reuso)
- Histórico completo de uso por código patrimonial
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import func, or_

from ..extensions import db
from ..models import PatrimonioFerramenta, Item, Usuario, FerramentaEmUso


class PatrimonioService:
    """Serviço para gestão de códigos patrimoniais de ferramentas."""
    
    @staticmethod
    def adicionar_codigos_lote(
        codigo_item: str,
        prefixo: str,
        quantidade: int,
        numero_inicial: int = 1,
        observacao: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Adiciona múltiplos códigos patrimoniais em lote para um item.
        
        Args:
            codigo_item: Código do item (EAN/SKU)
            prefixo: Prefixo dos códigos (ex: 'PAT', 'FER', 'EQP')
            quantidade: Quantos códigos gerar
            numero_inicial: Número inicial da sequência (padrão: 1)
            observacao: Observação opcional para todos os códigos
            
        Returns:
            Dict com status, códigos criados e erros (se houver)
            
        Example:
            >>> result = PatrimonioService.adicionar_codigos_lote(
            ...     codigo_item='7891234567890',
            ...     prefixo='PAT',
            ...     quantidade=20,
            ...     numero_inicial=1
            ... )
            >>> # Cria: PAT-001, PAT-002, ..., PAT-020
        """
        try:
            # Verifica se item existe
            item = db.session.get(Item, codigo_item)
            if not item:
                return {
                    'success': False,
                    'error': f'Item {codigo_item} não encontrado',
                    'codigos_criados': []
                }
            
            codigos_criados = []
            codigos_duplicados = []
            
            for i in range(quantidade):
                numero = numero_inicial + i
                codigo_patrimonial = f"{prefixo}-{numero:03d}"
                
                # Verifica se já existe
                existente = PatrimonioFerramenta.query.filter_by(
                    codigo_patrimonial=codigo_patrimonial
                ).first()
                
                if existente:
                    codigos_duplicados.append(codigo_patrimonial)
                    continue
                
                # Cria novo código patrimonial
                patrimonio = PatrimonioFerramenta(
                    codigo_patrimonial=codigo_patrimonial,
                    codigo_item=codigo_item,
                    status='disponivel',
                    observacao=observacao
                )
                db.session.add(patrimonio)
                codigos_criados.append(codigo_patrimonial)
            
            db.session.commit()
            
            return {
                'success': True,
                'codigos_criados': codigos_criados,
                'quantidade_criada': len(codigos_criados),
                'codigos_duplicados': codigos_duplicados,
                'item_descricao': item.descricao
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': str(e),
                'codigos_criados': []
            }
    
    @staticmethod
    def listar_disponiveis(codigo_item: str) -> List[Dict[str, Any]]:
        """
        Lista códigos patrimoniais disponíveis para retirada.
        
        Args:
            codigo_item: Código do item
            
        Returns:
            Lista de códigos patrimoniais disponíveis com detalhes
        """
        patrimonios = PatrimonioFerramenta.query.filter_by(
            codigo_item=codigo_item,
            status='disponivel'
        ).order_by(PatrimonioFerramenta.codigo_patrimonial).all()
        
        return [p.to_dict() for p in patrimonios]
    
    @staticmethod
    def listar_todos(codigo_item: str) -> List[Dict[str, Any]]:
        """
        Lista TODOS os códigos patrimoniais de um item (qualquer status).
        
        Args:
            codigo_item: Código do item
            
        Returns:
            Lista completa de códigos patrimoniais
        """
        patrimonios = PatrimonioFerramenta.query.filter_by(
            codigo_item=codigo_item
        ).order_by(
            PatrimonioFerramenta.status,
            PatrimonioFerramenta.codigo_patrimonial
        ).all()
        
        return [p.to_dict() for p in patrimonios]
    
    @staticmethod
    def atribuir_a_usuario(
        codigo_patrimonial: str,
        matricula: str
    ) -> Dict[str, Any]:
        """
        Atribui um código patrimonial a um usuário (marca como 'em_uso').
        
        Args:
            codigo_patrimonial: Código patrimonial a atribuir
            matricula: Matrícula do colaborador
            
        Returns:
            Dict com status da operação
        """
        try:
            patrimonio = PatrimonioFerramenta.query.filter_by(
                codigo_patrimonial=codigo_patrimonial
            ).first()
            
            if not patrimonio:
                return {
                    'success': False,
                    'error': f'Código patrimonial {codigo_patrimonial} não encontrado'
                }
            
            if patrimonio.status != 'disponivel':
                return {
                    'success': False,
                    'error': f'Código {codigo_patrimonial} não está disponível (status: {patrimonio.status})'
                }
            
            # Verifica se usuário existe
            usuario = db.session.get(Usuario, matricula)
            if not usuario:
                return {
                    'success': False,
                    'error': f'Usuário com matrícula {matricula} não encontrado'
                }
            
            # Atribui ao usuário
            patrimonio.status = 'em_uso'
            patrimonio.matricula = matricula
            
            db.session.commit()
            
            return {
                'success': True,
                'codigo_patrimonial': codigo_patrimonial,
                'matricula': matricula,
                'usuario_nome': usuario.nome
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def devolver(codigo_patrimonial: str) -> Dict[str, Any]:
        """
        Devolve um código patrimonial (marca como 'disponivel').
        
        Args:
            codigo_patrimonial: Código a devolver
            
        Returns:
            Dict com status da operação
        """
        try:
            patrimonio = PatrimonioFerramenta.query.filter_by(
                codigo_patrimonial=codigo_patrimonial
            ).first()
            
            if not patrimonio:
                return {
                    'success': False,
                    'error': f'Código patrimonial {codigo_patrimonial} não encontrado'
                }
            
            # Libera o código
            patrimonio.status = 'disponivel'
            patrimonio.matricula = None
            
            db.session.commit()
            
            return {
                'success': True,
                'codigo_patrimonial': codigo_patrimonial
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def historico_uso(codigo_patrimonial: str) -> List[Dict[str, Any]]:
        """
        Retorna histórico completo de uso de um código patrimonial.
        
        Args:
            codigo_patrimonial: Código para consultar histórico
            
        Returns:
            Lista de registros de uso ordenados por data
        """
        historico = FerramentaEmUso.query.filter_by(
            codigo_patrimonial=codigo_patrimonial
        ).order_by(FerramentaEmUso.data_retirada.desc()).all()
        
        return [h.to_dict() for h in historico]
    
    @staticmethod
    def estatisticas_item(codigo_item: str) -> Dict[str, Any]:
        """
        Retorna estatísticas de códigos patrimoniais de um item.
        
        Args:
            codigo_item: Código do item
            
        Returns:
            Dict com contadores por status
        """
        stats = db.session.query(
            PatrimonioFerramenta.status,
            func.count(PatrimonioFerramenta.id).label('quantidade')
        ).filter_by(
            codigo_item=codigo_item
        ).group_by(PatrimonioFerramenta.status).all()
        
        resultado = {
            'total': 0,
            'disponivel': 0,
            'em_uso': 0,
            'manutencao': 0,
            'baixado': 0
        }
        
        for status, qtd in stats:
            resultado[status] = qtd
            resultado['total'] += qtd
        
        return resultado
    
    @staticmethod
    def buscar_por_codigo(codigo_patrimonial: str) -> Optional[Dict[str, Any]]:
        """
        Busca informações de um código patrimonial específico.
        
        Args:
            codigo_patrimonial: Código a buscar
            
        Returns:
            Dict com informações ou None se não encontrado
        """
        patrimonio = PatrimonioFerramenta.query.filter_by(
            codigo_patrimonial=codigo_patrimonial
        ).first()
        
        if patrimonio:
            return patrimonio.to_dict()
        return None
    
    @staticmethod
    def deletar_codigo(codigo_patrimonial: str) -> Dict[str, Any]:
        """
        Remove um código patrimonial do sistema.
        
        Args:
            codigo_patrimonial: Código a remover
            
        Returns:
            Dict com status da operação
        """
        try:
            patrimonio = PatrimonioFerramenta.query.filter_by(
                codigo_patrimonial=codigo_patrimonial
            ).first()
            
            if not patrimonio:
                return {
                    'success': False,
                    'error': f'Código patrimonial {codigo_patrimonial} não encontrado'
                }
            
            # Não permite deletar se estiver em uso
            if patrimonio.status == 'em_uso':
                return {
                    'success': False,
                    'error': f'Código {codigo_patrimonial} está em uso e não pode ser removido'
                }
            
            db.session.delete(patrimonio)
            db.session.commit()
            
            return {
                'success': True,
                'codigo_patrimonial': codigo_patrimonial
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def alterar_status(
        codigo_patrimonial: str,
        novo_status: str,
        observacao: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Altera o status de um código patrimonial.
        
        Args:
            codigo_patrimonial: Código a alterar
            novo_status: Novo status (disponivel, em_uso, manutencao, baixado)
            observacao: Observação opcional sobre a mudança
            
        Returns:
            Dict com status da operação
        """
        try:
            if novo_status not in ['disponivel', 'em_uso', 'manutencao', 'baixado']:
                return {
                    'success': False,
                    'error': f'Status inválido: {novo_status}'
                }
            
            patrimonio = PatrimonioFerramenta.query.filter_by(
                codigo_patrimonial=codigo_patrimonial
            ).first()
            
            if not patrimonio:
                return {
                    'success': False,
                    'error': f'Código patrimonial {codigo_patrimonial} não encontrado'
                }
            
            status_anterior = patrimonio.status
            patrimonio.status = novo_status
            
            if observacao:
                patrimonio.observacao = observacao
            
            # Se mudar para disponível, limpa matrícula
            if novo_status == 'disponivel':
                patrimonio.matricula = None
            
            db.session.commit()
            
            return {
                'success': True,
                'codigo_patrimonial': codigo_patrimonial,
                'status_anterior': status_anterior,
                'status_novo': novo_status
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
