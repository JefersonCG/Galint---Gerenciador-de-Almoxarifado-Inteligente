"""Serviço para gerenciar histórico de entradas e relatórios de 30 dias."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from sqlalchemy import func, and_, or_

from flask import current_app, has_app_context

from galint_flask.extensions import db
from galint_flask.models import Entrada, Item, Usuario, EntradaRegistro30Dias
from galint_flask.utils.time_service import TimeService
from galint_flask.utils.report_branding import get_company_header_lines
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT


class EntradaService:
    """Gerencia histórico de entradas e ciclos de 30 dias."""

    def __init__(self):
        self.pdf_subdir = os.path.join('reports', 'entradas_30_dias')

    def _get_pdf_dir(self) -> str:
        if has_app_context():
            app_root = current_app.root_path
            base_dir = os.path.join(os.path.dirname(app_root), 'instance')
        else:
            base_dir = os.path.join(os.getcwd(), 'instance')
        pdf_dir = os.path.join(base_dir, self.pdf_subdir)
        os.makedirs(pdf_dir, exist_ok=True)
        return pdf_dir

    def get_current_cycle(self) -> EntradaRegistro30Dias | None:
        """Retorna o ciclo de 30 dias ativo atual."""
        return db.session.query(EntradaRegistro30Dias).filter(EntradaRegistro30Dias.ativo.is_(True)).first()

    def create_new_cycle(self) -> EntradaRegistro30Dias:
        """Cria um novo ciclo de 30 dias."""
        # Desativa ciclos anteriores
        db.session.query(EntradaRegistro30Dias).filter(EntradaRegistro30Dias.ativo.is_(True)).update({'ativo': False})
        
        new_cycle = EntradaRegistro30Dias(
            data_inicio=datetime.now(timezone.utc),
            ativo=True
        )
        db.session.add(new_cycle)
        db.session.commit()
        return new_cycle

    def ensure_active_cycle(self) -> EntradaRegistro30Dias:
        """Garante que existe um ciclo ativo. Cria se necessário."""
        cycle = self.get_current_cycle()
        if not cycle:
            cycle = self.create_new_cycle()
        return cycle

    def check_and_finalize_cycle(self) -> Dict[str, Any]:
        """Verifica se o ciclo atual completou 30 dias e finaliza se necessário."""
        cycle = self.get_current_cycle()
        if not cycle:
            return {'status': 'no_active_cycle'}

        data_inicio = cycle.data_inicio
        if data_inicio and data_inicio.tzinfo is None:
            data_inicio = data_inicio.replace(tzinfo=timezone.utc)
        days_passed = (datetime.now(timezone.utc) - data_inicio).days
        
        if days_passed >= 30 and not cycle.pdf_gerado:
            # Finaliza o ciclo gerando PDF
            end_dt = datetime.now(timezone.utc)
            pdf_info = self.generate_pdf_for_cycle(cycle, end_dt=end_dt)
            
            # Marca ciclo como finalizado
            cycle.data_fim = end_dt
            cycle.pdf_gerado = True
            cycle.pdf_caminho = pdf_info['path']
            cycle.pdf_nome_arquivo = pdf_info['filename']
            cycle.data_geracao_pdf = datetime.now(timezone.utc)
            cycle.ativo = False
            db.session.commit()
            
            # Cria novo ciclo
            self.create_new_cycle()
            
            return {
                'status': 'cycle_finalized',
                'pdf_generated': True,
                'pdf_path': pdf_info['path'],
                'pdf_filename': pdf_info['filename']
            }
        
        return {
            'status': 'cycle_active',
            'days_passed': days_passed,
            'days_remaining': 30 - days_passed
        }

    def get_entradas_by_cycle(self, cycle: EntradaRegistro30Dias) -> List[Entrada]:
        """Retorna todas as entradas de um ciclo específico."""
        query = db.session.query(Entrada)
        if cycle.data_inicio:
            query = query.filter(func.date(Entrada.data_entrada) >= func.date(cycle.data_inicio))
        
        if cycle.data_fim:
            query = query.filter(func.date(Entrada.data_entrada) <= func.date(cycle.data_fim))
        
        return query.order_by(Entrada.data_entrada.desc()).all()

    def get_entradas_grouped_by_day(self, cycle: EntradaRegistro30Dias) -> Dict[str, List[Dict]]:
        """Retorna entradas agrupadas por dia dentro do ciclo."""
        entradas = self.get_entradas_by_cycle(cycle)
        grouped = {}
        
        for entrada in entradas:
            day_key = TimeService.format_local(entrada.data_entrada, '%Y-%m-%d')
            
            if day_key not in grouped:
                grouped[day_key] = []
            
            # Busca informações relacionadas
            item = entrada.item
            usuario = entrada.usuario
            
            grouped[day_key].append({
                'id': entrada.id_entrada,
                'codigo_item': entrada.codigo_item,
                'nota_fiscal': entrada.nota_fiscal or '-',
                'descricao': item.descricao if item else '-',
                'quantidade': entrada.quantidade,
                'unidade': item.unidade if item else '-',
                'marca': item.marca if item and item.marca else '-',
                'categoria': item.categoria if item else '-',
                'data_hora': TimeService.format_local(entrada.data_entrada, '%d/%m/%Y %H:%M:%S'),
                'usuario': usuario.nome if usuario else '-'
            })
        
        return dict(sorted(grouped.items(), reverse=True))

    def generate_pdf_for_cycle(self, cycle: EntradaRegistro30Dias, end_dt: datetime | None = None) -> Dict[str, str]:
        """Gera PDF consolidado de 30 dias."""
        start_dt = cycle.data_inicio
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt is None:
            end_dt = cycle.data_fim or datetime.now(timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        filename = f"entradas_30_dias_{start_dt.strftime('%Y%m%d')}_to_{end_dt.strftime('%Y%m%d')}.pdf"
        pdf_dir = self._get_pdf_dir()
        filepath = os.path.join(pdf_dir, filename)
        
        doc = SimpleDocTemplate(
            filepath,
            pagesize=landscape(A4),
            leftMargin=0.5*inch,
            rightMargin=0.5*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
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
            textColor=colors.HexColor('#2563eb'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        title = Paragraph(f"Relatório de Entradas de Material - 30 Dias", title_style)
        elements.append(title)
        
        # Informações do período
        period_style = ParagraphStyle(
            'Period',
            parent=styles['Normal'],
            fontSize=10,
            alignment=TA_CENTER,
            spaceAfter=20
        )
        
        period_text = f"Período: {start_dt.strftime('%d/%m/%Y')} até {end_dt.strftime('%d/%m/%Y')}"
        elements.append(Paragraph(period_text, period_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Dados agrupados por dia
        grouped_data = self.get_entradas_grouped_by_day(cycle)
        
        if not grouped_data:
            no_data = Paragraph("Nenhuma entrada registrada neste período.", styles['Normal'])
            elements.append(no_data)
        else:
            for day, entradas in grouped_data.items():
                # Cabeçalho do dia
                day_formatted = datetime.strptime(day, '%Y-%m-%d').strftime('%d/%m/%Y')
                day_header = Paragraph(
                    f"<b>Data: {day_formatted}</b> ({len(entradas)} {'entrada' if len(entradas) == 1 else 'entradas'})",
                    ParagraphStyle('DayHeader', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#1e40af'), spaceAfter=8)
                )
                elements.append(day_header)
                
                # Tabela de entradas do dia
                table_data = [['Código', 'NF', 'Descrição', 'Qtd', 'Un.', 'Marca', 'Categoria', 'Hora']]
                
                for entrada in entradas:
                    hora = entrada['data_hora'].split(' ')[1]  # Apenas hora
                    table_data.append([
                        entrada['codigo_item'] or '-',
                        entrada['nota_fiscal'],
                        entrada['descricao'][:30] + '...' if len(entrada['descricao']) > 30 else entrada['descricao'],
                        str(entrada['quantidade']),
                        entrada['unidade'],
                        entrada['marca'][:15] if len(entrada['marca']) > 15 else entrada['marca'],
                        entrada['categoria'][:20] if len(entrada['categoria']) > 20 else entrada['categoria'],
                        hora
                    ])
                
                table = Table(table_data, colWidths=[0.8*inch, 0.9*inch, 2.5*inch, 0.7*inch, 0.6*inch, 1.2*inch, 1.5*inch, 0.8*inch], repeatRows=1)
                table.setStyle(TableStyle([
                    # Cabeçalho
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    
                    # Dados
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('TOPPADDING', (0, 1), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                    
                    # Bordas
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#1e40af')),
                    
                    # Zebra
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
                ]))
                
                elements.append(table)
                elements.append(Spacer(1, 0.3*inch))
        
        # Rodapé
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        
        footer_text = f"Gerado automaticamente em {datetime.utcnow().strftime('%d/%m/%Y às %H:%M:%S')} | GALINT - Sistema de Gestão"
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph(footer_text, footer_style))
        
        # Gera PDF
        doc.build(elements)
        
        return {
            'path': filepath,
            'filename': filename
        }

    def list_all_cycles(self, limit: int = 50) -> List[EntradaRegistro30Dias]:
        """Lista todos os ciclos de 30 dias."""
        return db.session.query(EntradaRegistro30Dias).order_by(
            EntradaRegistro30Dias.data_inicio.desc()
        ).limit(limit).all()

    def get_cycle_by_id(self, cycle_id: int) -> EntradaRegistro30Dias | None:
        """Retorna um ciclo específico por ID."""
        return db.session.query(EntradaRegistro30Dias).filter_by(id=cycle_id).first()

    def generate_alertas_estoque_pdf(self) -> Dict[str, str]:
        """Gera PDF simples com itens em baixa no estoque."""
        filename = f"alertas_estoque_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_dir = self._get_pdf_dir()
        filepath = os.path.join(pdf_dir, filename)
        
        doc = SimpleDocTemplate(filepath, pagesize=landscape(A4))
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
            textColor=colors.HexColor('#dc2626'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        title = Paragraph("Alertas de Estoque - Itens em Baixa", title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.3*inch))
        
        # Busca itens com saldo baixo usando saldo calculado e estoque mínimo
        itens = db.session.query(Item).all()
        itens_baixa = []
        for item in itens:
            saldo_atual = item.get_saldo_atual()
            estoque_minimo = item.estoque_minimo or 0
            if saldo_atual > 0 and estoque_minimo > 0 and saldo_atual <= estoque_minimo:
                itens_baixa.append((item, saldo_atual, estoque_minimo))

        # Ordenar por saldo atual crescente
        itens_baixa.sort(key=lambda x: x[1])
        
        if not itens_baixa:
            no_data = Paragraph("✅ Nenhum item em situação crítica de estoque no momento.", styles['Normal'])
            elements.append(no_data)
        else:
            # Tabela de alertas
            table_data = [['Código', 'Descrição', 'Categoria', 'Saldo Atual', 'Unidade', 'Status']]
            
            for item, saldo_atual, estoque_minimo in itens_baixa:
                status = f"Min.: {estoque_minimo}"
                table_data.append([
                    item.codigo_item or '-',
                    item.descricao[:40] + '...' if len(item.descricao) > 40 else item.descricao,
                    item.categoria or '-',
                    f"{saldo_atual:.2f}",
                    item.unidade or '-',
                    status
                ])
            
            table = Table(table_data, colWidths=[0.8*inch, 3.8*inch, 1.5*inch, 0.9*inch, 0.8*inch, 1.3*inch], repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fee2e2')])
            ]))
            
            elements.append(table)
        
        # Rodapé
        footer_text = f"Gerado em {datetime.utcnow().strftime('%d/%m/%Y às %H:%M:%S')} | GALINT"
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph(footer_text, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)))
        
        doc.build(elements)
        
        return {
            'path': filepath,
            'filename': filename
        }


# Instância global do serviço
entrada_service = EntradaService()
