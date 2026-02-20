"""Serviço para gerar relatórios automáticos de entradas a cada 1000 registros."""
from __future__ import annotations

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from flask import current_app, has_app_context

from ..extensions import db
from ..models import Entrada, Item, Usuario, EntradaRegistro30Dias
from ..utils.time_service import TimeService
from ..utils.report_branding import get_company_header_lines
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER

logger = logging.getLogger(__name__)


class EntradaReportService:
    """Gerencia geração automática de PDFs de entradas a cada 1000 registros."""
    
    CONTADOR_CICLO = 1000  # Gerar relatório a cada 1000 entradas
    
    def __init__(self):
        pass
    
    def _get_pdf_dir(self) -> Path:
        """Retorna o diretório para salvar os PDFs."""
        if has_app_context():
            base = Path(current_app.instance_path)
        else:
            base = Path("instance")
        pdf_dir = base / "reports" / "entradas_automaticas"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        return pdf_dir
    
    def get_total_entradas(self) -> int:
        """Retorna o total de entradas registradas no sistema."""
        from sqlalchemy import func
        total = db.session.query(func.count(Entrada.id_entrada)).scalar() or 0
        return total
    
    def get_ultimo_ciclo_gerado(self) -> int:
        """Retorna o número do último ciclo de 1000 entradas que teve PDF gerado."""
        # Buscar na tabela de controle ou em arquivo de estado
        state_file = self._get_pdf_dir() / ".ultimo_ciclo.txt"
        if state_file.exists():
            try:
                return int(state_file.read_text().strip())
            except:
                return 0
        return 0
    
    def set_ultimo_ciclo_gerado(self, ciclo: int) -> None:
        """Salva o número do último ciclo gerado."""
        state_file = self._get_pdf_dir() / ".ultimo_ciclo.txt"
        state_file.write_text(str(ciclo))
    
    def check_e_gerar_relatorio(self) -> Dict[str, Any]:
        """
        Verifica se chegou a 1000 entradas desde o último relatório.
        Se sim, gera PDF e envia para o Telegram automaticamente.
        """
        try:
            total = self.get_total_entradas()
            ultimo_ciclo = self.get_ultimo_ciclo_gerado()
            
            # Calcula qual deveria ser o próximo ciclo
            proximo_ciclo = ultimo_ciclo + 1
            entradas_necessarias = proximo_ciclo * self.CONTADOR_CICLO
            
            logger.info(f"Check relatório: total={total}, último_ciclo={ultimo_ciclo}, necessárias={entradas_necessarias}")
            
            # Verifica se atingiu o limite
            if total >= entradas_necessarias:
                # Calcular o range de entradas deste ciclo
                inicio = ultimo_ciclo * self.CONTADOR_CICLO + 1
                fim = proximo_ciclo * self.CONTADOR_CICLO
                
                logger.info(f"Gerando relatório do ciclo {proximo_ciclo} (entradas {inicio} a {fim})")
                
                # Gerar PDF
                pdf_info = self.gerar_pdf_ciclo(proximo_ciclo, inicio, fim)
                
                # Enviar para o Telegram (silenciosamente)
                self.enviar_para_telegram(pdf_info["filepath"], proximo_ciclo)
                
                # Atualizar contador
                self.set_ultimo_ciclo_gerado(proximo_ciclo)
                
                return {
                    "gerado": True,
                    "ciclo": proximo_ciclo,
                    "total_entradas": total,
                    "pdf": pdf_info["filepath"],
                    "range": f"{inicio}-{fim}"
                }
            else:
                faltam = entradas_necessarias - total
                return {
                    "gerado": False,
                    "total_entradas": total,
                    "proximo_ciclo": proximo_ciclo,
                    "faltam": faltam
                }
                
        except Exception as e:
            logger.exception(f"Erro ao verificar/gerar relatório: {e}")
            return {
                "gerado": False,
                "erro": str(e)
            }
    
    def gerar_pdf_ciclo(self, ciclo: int, id_inicio: int, id_fim: int) -> Dict[str, str]:
        """
        Gera PDF com as entradas do ciclo especificado.
        
        Args:
            ciclo: Número do ciclo (1, 2, 3...)
            id_inicio: ID da primeira entrada do ciclo
            id_fim: ID da última entrada do ciclo
        """
        try:
            # Nome do arquivo
            data_geracao = datetime.now().strftime("%d%m%Y")
            filename = f"Registros_de_Entradas_{data_geracao}_ciclo{ciclo}.pdf"
            filepath = str(self._get_pdf_dir() / filename)
            
            # Buscar entradas do ciclo
            entradas = (
                db.session.query(Entrada)
                .filter(Entrada.id_entrada >= id_inicio)
                .filter(Entrada.id_entrada <= id_fim)
                .order_by(Entrada.data_entrada.asc())
                .all()
            )
            
            logger.info(f"Gerando PDF: {len(entradas)} entradas encontradas para o ciclo {ciclo}")
            
            # Criar PDF
            doc = SimpleDocTemplate(
                filepath,
                pagesize=landscape(A4),
                rightMargin=30,
                leftMargin=30,
                topMargin=30,
                bottomMargin=18,
            )
            
            elements = []
            styles = getSampleStyleSheet()

            # Cabeçalho da empresa (padronizado)
            company_lines = get_company_header_lines()
            if company_lines:
                company_name_style = ParagraphStyle(
                    'CompanyName',
                    parent=styles['Normal'],
                    fontSize=14,
                    alignment=TA_CENTER,
                    fontName='Helvetica-Bold',
                    spaceAfter=2,
                )
                company_details_style = ParagraphStyle(
                    'CompanyDetails',
                    parent=styles['Normal'],
                    fontSize=9,
                    alignment=TA_CENTER,
                    textColor=colors.HexColor('#64748b'),
                    spaceAfter=12,
                )
                elements.append(Paragraph(company_lines[0], company_name_style))
                if len(company_lines) > 1:
                    elements.append(Paragraph('<br/>'.join(company_lines[1:]), company_details_style))
            
            # Título
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor=colors.HexColor('#1e40af'),
                spaceAfter=12,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            
            title = Paragraph(
                f"<b>REGISTROS DE ENTRADAS - CICLO {ciclo}</b>",
                title_style
            )
            elements.append(title)
            
            # Subtítulo com informações
            subtitle_style = ParagraphStyle(
                'Subtitle',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#64748b'),
                spaceAfter=20,
                alignment=TA_CENTER
            )
            
            subtitle = Paragraph(
                f"Entradas de #{id_inicio} a #{id_fim} | Total: {len(entradas)} registros | Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                subtitle_style
            )
            elements.append(subtitle)
            elements.append(Spacer(1, 0.3 * inch))
            
            # Tabela de dados
            if not entradas:
                no_data = Paragraph(
                    "<i>Nenhuma entrada encontrada neste ciclo.</i>",
                    styles['Normal']
                )
                elements.append(no_data)
            else:
                # Cabeçalho da tabela
                table_data = [['ID', 'Data/Hora', 'Código', 'Descrição', 'Qtd', 'Un.', 'NF', 'Usuário', 'Categoria']]
                
                for entrada in entradas:
                    item = entrada.item
                    usuario = entrada.usuario
                    
                    # Formatar data
                    data_hora = TimeService.format_local(entrada.data_entrada, '%d/%m/%Y %H:%M')
                    
                    # Descrição truncada
                    descricao = item.descricao if item else "Item removido"
                    descricao_short = descricao[:35] + '...' if len(descricao) > 35 else descricao
                    
                    # Dados da linha
                    table_data.append([
                        str(entrada.id_entrada),
                        data_hora,
                        entrada.codigo_item or '-',
                        descricao_short,
                        str(int(entrada.quantidade)) if entrada.quantidade == int(entrada.quantidade) else f"{entrada.quantidade:.2f}",
                        item.unidade if item else '-',
                        entrada.nota_fiscal[:15] if entrada.nota_fiscal else '-',
                        usuario.nome[:20] if usuario else entrada.matricula or '-',
                        item.categoria[:18] if item else '-'
                    ])
                
                # Criar tabela
                table = Table(
                    table_data, 
                    colWidths=[0.6*inch, 1.2*inch, 0.9*inch, 2.5*inch, 0.6*inch, 0.6*inch, 1.0*inch, 1.5*inch, 1.3*inch],
                    repeatRows=1
                )
                
                table.setStyle(TableStyle([
                    # Cabeçalho
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    
                    # Corpo
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # ID
                    ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # Data
                    ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # Quantidade
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                    
                    # Bordas
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#1e40af')),
                    
                    # Padding
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING', (0, 1), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ]))
                
                elements.append(table)
            
            # Rodapé
            elements.append(Spacer(1, 0.5 * inch))
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.HexColor('#94a3b8'),
                alignment=TA_CENTER
            )
            footer = Paragraph(
                f"<i>Relatório gerado automaticamente pelo sistema GALINT | Ciclo {ciclo} de 1000 entradas</i>",
                footer_style
            )
            elements.append(footer)
            
            # Construir PDF
            doc.build(elements)
            
            logger.info(f"PDF gerado com sucesso: {filepath}")
            
            return {
                "filepath": filepath,
                "filename": filename,
                "total_entradas": len(entradas)
            }
            
        except Exception as e:
            logger.exception(f"Erro ao gerar PDF do ciclo {ciclo}: {e}")
            raise
    
    def enviar_para_telegram(self, filepath: str, ciclo: int) -> bool:
        """
        Envia o PDF para todos os administradores no Telegram de forma silenciosa.
        """
        try:
            from .telegram_service import TelegramService
            
            if not TelegramService.is_enabled():
                logger.warning("Telegram não está habilitado. PDF não será enviado.")
                return False
            
            # Verificar se o arquivo existe
            if not os.path.exists(filepath):
                logger.error(f"Arquivo não encontrado: {filepath}")
                return False
            
            # Enviar para administradores
            caption = (
                f"📊 <b>Relatório Automático de Entradas</b>\n\n"
                f"🔢 Ciclo: {ciclo}\n"
                f"📦 Entradas: {(ciclo - 1) * self.CONTADOR_CICLO + 1} a {ciclo * self.CONTADOR_CICLO}\n"
                f"📅 Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}\n\n"
                f"<i>Este é um relatório automático gerado a cada 1000 entradas.</i>"
            )
            
            # Buscar administradores com Telegram habilitado
            from ..models import TelegramUser, Usuario
            admins_telegram = (
                db.session.query(TelegramUser)
                .join(Usuario, TelegramUser.matricula == Usuario.matricula)
                .filter(Usuario.is_admin == 1)
                .filter(TelegramUser.enabled == True)
                .all()
            )
            
            if not admins_telegram:
                logger.warning("Nenhum administrador com Telegram habilitado encontrado.")
                return False
            
            # Enviar para cada administrador
            enviados = 0
            for admin in admins_telegram:
                try:
                    TelegramService.send_document(
                        admin.chat_id,
                        filepath,
                        caption=caption
                    )
                    enviados += 1
                    logger.info(f"PDF enviado para admin {admin.matricula} ({admin.chat_id})")
                except Exception as e:
                    logger.error(f"Erro ao enviar PDF para admin {admin.matricula}: {e}")
            
            logger.info(f"PDF enviado para {enviados}/{len(admins_telegram)} administradores")
            return enviados > 0
            
        except Exception as e:
            logger.exception(f"Erro ao enviar PDF para o Telegram: {e}")
            return False


# Instância global do serviço
entrada_report_service = EntradaReportService()
