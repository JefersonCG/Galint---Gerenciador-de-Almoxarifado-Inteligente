"""Serviço para gerenciamento de ciclos de entradas de 90 dias."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, and_

from ..extensions import db
from ..models import Entrada, Item, EntradaRegistro30Dias


# Renomeando para 90 dias mas mantendo compatibilidade com modelo existente
DIAS_CICLO = 90


class CicloEntradasService:
    """Gerencia ciclos de 90 dias para registro de entradas."""
    
    @staticmethod
    def obter_ciclo_atual() -> EntradaRegistro30Dias | None:
        """Retorna o ciclo ativo atual ou None se não houver."""
        return (
            db.session.query(EntradaRegistro30Dias)
            .filter(EntradaRegistro30Dias.ativo == True)
            .order_by(EntradaRegistro30Dias.data_inicio.desc())
            .first()
        )
    
    @staticmethod
    def criar_novo_ciclo() -> EntradaRegistro30Dias:
        """Cria um novo ciclo de entradas."""
        agora = datetime.now()
        ciclo = EntradaRegistro30Dias()
        ciclo.data_inicio = agora
        ciclo.data_fim = None
        ciclo.pdf_gerado = False
        ciclo.ativo = True
        db.session.add(ciclo)
        db.session.commit()
        return ciclo
    
    @staticmethod
    def obter_ou_criar_ciclo_atual() -> EntradaRegistro30Dias:
        """Obtém o ciclo atual ou cria um novo se não existir."""
        ciclo = CicloEntradasService.obter_ciclo_atual()
        if not ciclo:
            ciclo = CicloEntradasService.criar_novo_ciclo()
        return ciclo
    
    @staticmethod
    def verificar_ciclo_expirado() -> bool:
        """Verifica se o ciclo atual expirou (mais de 90 dias)."""
        ciclo = CicloEntradasService.obter_ciclo_atual()
        if not ciclo:
            return False
        
        dias_passados = (datetime.now() - ciclo.data_inicio).days
        return dias_passados >= DIAS_CICLO
    
    @staticmethod
    def calcular_data_fechamento() -> datetime | None:
        """Calcula a data prevista de fechamento do ciclo atual."""
        ciclo = CicloEntradasService.obter_ciclo_atual()
        if not ciclo:
            return None
        
        return ciclo.data_inicio + timedelta(days=DIAS_CICLO)
    
    @staticmethod
    def dias_restantes_ciclo() -> int:
        """Retorna quantos dias faltam para fechar o ciclo."""
        ciclo = CicloEntradasService.obter_ciclo_atual()
        if not ciclo:
            return DIAS_CICLO
        
        dias_passados = (datetime.now() - ciclo.data_inicio).days
        return max(0, DIAS_CICLO - dias_passados)
    
    @staticmethod
    def contar_entradas_ciclo_atual() -> int:
        """Conta as entradas registradas no ciclo atual."""
        ciclo = CicloEntradasService.obter_ciclo_atual()
        if not ciclo:
            return 0
        
        return (
            db.session.query(func.count(Entrada.id_entrada))
            .filter(Entrada.data_entrada >= ciclo.data_inicio)
            .scalar() or 0
        )
    
    @staticmethod
    def listar_entradas_ciclo_atual() -> list[dict[str, Any]]:
        """Lista todas as entradas do ciclo atual."""
        ciclo = CicloEntradasService.obter_ciclo_atual()
        if not ciclo:
            return []
        
        entradas = (
            db.session.query(Entrada)
            .filter(Entrada.data_entrada >= ciclo.data_inicio)
            .order_by(Entrada.data_entrada.desc())
            .all()
        )
        
        resultado = []
        for entrada in entradas:
            item = db.session.get(Item, entrada.codigo_item)
            resultado.append({
                "id": entrada.id_entrada,
                "codigo_item": entrada.codigo_item,
                "descricao": item.descricao if item else "Item removido",
                "categoria": item.categoria if item else "N/D",
                "quantidade": entrada.quantidade,
                "data_entrada": entrada.data_entrada,
                "nota_fiscal": entrada.nota_fiscal,
                "lote": getattr(entrada, 'lote', None),
            })
        
        return resultado
    
    @staticmethod
    def gerar_resumo_ciclo() -> dict[str, Any]:
        """Gera um resumo do ciclo atual para relatório."""
        ciclo = CicloEntradasService.obter_ciclo_atual()
        if not ciclo:
            return {"erro": "Nenhum ciclo ativo encontrado"}
        
        entradas = CicloEntradasService.listar_entradas_ciclo_atual()
        
        # Agrupar por categoria
        por_categoria = {}
        for entrada in entradas:
            cat = entrada.get("categoria", "Outros")
            if cat not in por_categoria:
                por_categoria[cat] = {"quantidade_total": 0, "registros": 0}
            por_categoria[cat]["quantidade_total"] += entrada.get("quantidade", 0)
            por_categoria[cat]["registros"] += 1
        
        # Calcular totais
        total_quantidade = sum(e.get("quantidade", 0) for e in entradas)
        total_registros = len(entradas)
        
        # Produtos únicos (por código)
        codigos_unicos = set(e.get("codigo_item") for e in entradas)
        
        data_fechamento = CicloEntradasService.calcular_data_fechamento()
        
        return {
            "ciclo_id": ciclo.id,
            "data_inicio": ciclo.data_inicio,
            "data_fechamento_prevista": data_fechamento,
            "dias_restantes": CicloEntradasService.dias_restantes_ciclo(),
            "total_registros": total_registros,
            "total_quantidade": total_quantidade,
            "produtos_unicos": len(codigos_unicos),
            "por_categoria": por_categoria,
            "entradas": entradas,
        }
    
    @staticmethod
    def fechar_ciclo_atual() -> dict[str, Any]:
        """Fecha o ciclo atual e prepara para um novo."""
        ciclo = CicloEntradasService.obter_ciclo_atual()
        if not ciclo:
            return {"sucesso": False, "erro": "Nenhum ciclo ativo para fechar"}
        
        # Gerar resumo antes de fechar
        resumo = CicloEntradasService.gerar_resumo_ciclo()
        
        # Marcar ciclo como fechado
        ciclo.data_fim = datetime.now()
        ciclo.ativo = False
        db.session.commit()
        
        # Criar novo ciclo
        novo_ciclo = CicloEntradasService.criar_novo_ciclo()
        
        return {
            "sucesso": True,
            "ciclo_fechado_id": ciclo.id,
            "novo_ciclo_id": novo_ciclo.id,
            "resumo": resumo,
        }
    
    @staticmethod
    def listar_ciclos_anteriores() -> list[dict[str, Any]]:
        """Lista todos os ciclos já fechados."""
        ciclos = (
            db.session.query(EntradaRegistro30Dias)
            .filter(EntradaRegistro30Dias.ativo == False)
            .order_by(EntradaRegistro30Dias.data_inicio.desc())
            .all()
        )
        
        resultado = []
        for ciclo in ciclos:
            # Contar entradas deste ciclo
            data_fim = ciclo.data_fim or (ciclo.data_inicio + timedelta(days=DIAS_CICLO))
            
            contagem = (
                db.session.query(func.count(Entrada.id_entrada))
                .filter(
                    and_(
                        Entrada.data_entrada >= ciclo.data_inicio,
                        Entrada.data_entrada <= data_fim
                    )
                )
                .scalar() or 0
            )
            
            resultado.append({
                "id": ciclo.id,
                "data_inicio": ciclo.data_inicio,
                "data_fim": ciclo.data_fim,
                "total_entradas": contagem,
                "pdf_gerado": ciclo.pdf_gerado,
                "pdf_caminho": ciclo.pdf_caminho,
            })
        
        return resultado
    
    @staticmethod
    def obter_entradas_ciclo(ciclo_id: int) -> list[dict[str, Any]]:
        """Obtém entradas de um ciclo específico (mesmo fechado)."""
        ciclo = db.session.get(EntradaRegistro30Dias, ciclo_id)
        if not ciclo:
            return []
        
        data_fim = ciclo.data_fim or datetime.now()
        
        entradas = (
            db.session.query(Entrada)
            .filter(
                and_(
                    Entrada.data_entrada >= ciclo.data_inicio,
                    Entrada.data_entrada <= data_fim
                )
            )
            .order_by(Entrada.data_entrada.desc())
            .all()
        )
        
        resultado = []
        for entrada in entradas:
            item = db.session.get(Item, entrada.codigo_item)
            resultado.append({
                "id": entrada.id_entrada,
                "codigo_item": entrada.codigo_item,
                "descricao": item.descricao if item else "Item removido",
                "categoria": item.categoria if item else "N/D",
                "quantidade": entrada.quantidade,
                "data_entrada": entrada.data_entrada,
                "nota_fiscal": entrada.nota_fiscal,
            })
        
        return resultado


# Instância singleton
ciclo_entradas_service = CicloEntradasService()
