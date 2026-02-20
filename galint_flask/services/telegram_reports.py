"""Serviço de geração de relatórios avançados para Telegram.

Responsável por gerar relatórios detalhados em XLSX e PDF com:
- Suporte a período configurável (1-6 meses)
- Agrupamento por categoria
- Múltiplos formatos de exportação
- Download direto via Telegram
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import tempfile
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import func

from ..extensions import db
from ..models import Saida, Item, Usuario, InventarioEvento
from ..utils.time_service import TimeService

logger = logging.getLogger(__name__)


class TelegramReportService:
    """Serviço de relatórios avançados para Telegram."""

    MONTHS = {
        1: "Último mês (30 dias)",
        2: "Últimos 2 meses (60 dias)",
        3: "Últimos 3 meses (90 dias)",
        4: "Últimos 4 meses (120 dias)",
        5: "Últimos 5 meses (150 dias)",
        6: "Últimos 6 meses (180 dias)",
    }

    @staticmethod
    def _format_codigo_barra(value: object) -> str:
        if value is None:
            return "N/D"
        text = str(value).strip()
        if not text:
            return "N/D"
        return text[-4:] if len(text) >= 4 else text

    @staticmethod
    def get_period_days(months: int) -> int:
        """Converte meses para dias."""
        return months * 30

    @staticmethod
    def get_categories(scope: str = "all") -> list[str]:
        """Retorna lista de categorias disponíveis, filtrando por escopo.

        scope:
            - all: todas
            - tools: categorias contendo "ferramenta"
            - materials: categorias exceto "ferramenta"
        """
        try:
            q = db.session.query(Item.categoria).distinct().filter(Item.categoria.isnot(None))
            if scope == "tools":
                q = q.filter(Item.categoria.ilike("%ferramenta%"))
            elif scope == "materials":
                q = q.filter(~Item.categoria.ilike("%ferramenta%"))
            categories = q.order_by(Item.categoria).all()
            return [c[0] for c in categories if c[0]]
        except Exception as e:
            logger.error(f"Erro ao buscar categorias: {e}")
            return []

    @staticmethod
    def get_withdrawals_by_period_and_category(
        months: int,
        category: Optional[str] = None,
        scope: str = "all",
    ) -> list[dict]:
        """Retorna dados de retiradas filtrados por período e categoria.
        
        Args:
            months: Número de meses para o período
            category: Categoria para filtrar (None = todas)
            
        Returns:
            Lista de dicts com dados das retiradas
        """
        cutoff = datetime.utcnow() - timedelta(days=TelegramReportService.get_period_days(months))
        
        q = db.session.query(
            Saida.id_saida,
            Saida.codigo_item,
            Item.descricao,
            Item.categoria,
            Item.marca,
            Saida.quantidade,
            Saida.data_saida,
            Usuario.nome,
            Saida.local_servico,
            Saida.observacao,
        ).join(
            Item, Saida.codigo_item == Item.codigo_item, isouter=True
        ).join(
            Usuario, Saida.matricula == Usuario.matricula, isouter=True
        ).filter(
            Saida.data_saida >= cutoff
        )

        if scope == "tools":
            q = q.filter(Item.categoria.ilike("%ferramenta%"))
        elif scope == "materials":
            q = q.filter(~Item.categoria.ilike("%ferramenta%"))
        
        if category:
            q = q.filter(Item.categoria == category)
        
        q = q.order_by(Saida.data_saida.desc())
        
        results = q.all()
        
        data = []
        for row in results:
            local_info = row.local_servico or "N/D"
            if row.observacao and str(row.observacao).strip():
                local_info = f"{local_info} | {str(row.observacao).strip()}"
            data.append({
                "id": row.id_saida,
                "codigo": row.codigo_item or "N/D",
                "descricao": row.descricao or "N/D",
                "categoria": row.categoria or "Sem categoria",
                "marca": row.marca or "N/D",
                "quantidade": float(row.quantidade or 0),
                "data": row.data_saida,
                "usuario": row.nome or "N/D",
                "local_info": local_info,
                "observacao": row.observacao or "",
            })
        
        return data

    @staticmethod
    def generate_xlsx_report(
        months: int,
        category: Optional[str] = None,
        scope: str = "all",
    ) -> Path:
        """Gera relatório XLSX com dados de retiradas.
        
        Args:
            months: Número de meses
            category: Categoria (None = todas)
            
        Returns:
            Caminho do arquivo gerado
        """
        data = TelegramReportService.get_withdrawals_by_period_and_category(months, category, scope=scope)
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Retiradas"

        # Cabecalho (titulo + empresa)
        from ..utils.report_branding import get_company_header_lines

        period_text = TelegramReportService.MONTHS.get(months, f"{months} meses")
        scope_label = {
            "tools": "Ferramentas",
            "materials": "Materiais",
            "all": "Geral",
        }.get(scope, "Geral")
        category_text = f"Categoria: {category}" if category else "Categoria: Todas"

        ws.append(["RELATORIO DE RETIRADAS"])
        for line in get_company_header_lines():
            ws.append([line])
        ws.append([f"Periodo: {period_text} | Escopo: {scope_label}"])
        ws.append([category_text])
        ws.append([f"Total de registros: {len(data)}"])
        ws.append([])
        
        # Cabeçalhos
        headers = [
            "Data",
            "Horário",
            "Código",
            "Descrição",
            "Categoria",
            "Marca",
            "Quantidade",
            "Usuário",
            "Período",
            "Local",
        ]
        
        # Estilo para cabeçalhos
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="0066CC", end_color="0066CC", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )
        
        header_row_index = ws.max_row + 1
        ws.append(headers)
        for cell in ws[header_row_index]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = border
        
        # Largura das colunas
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 10
        ws.column_dimensions["C"].width = 8
        ws.column_dimensions["D"].width = 25
        ws.column_dimensions["E"].width = 18
        ws.column_dimensions["F"].width = 15
        ws.column_dimensions["G"].width = 12
        ws.column_dimensions["H"].width = 18
        ws.column_dimensions["I"].width = 20
        ws.column_dimensions["J"].width = 30
        
        # Dados
        data_alignment = Alignment(vertical="top", wrap_text=True)
        for row_data in data:
            data_movimento = row_data["data"]
            business_tag = TimeService.get_business_day_tag(data_movimento)
            
            ws.append([
                TimeService.format_local(data_movimento, "%d/%m/%Y"),
                TimeService.format_local(data_movimento, "%H:%M"),
                TelegramReportService._format_codigo_barra(row_data.get("codigo")),
                row_data["descricao"],
                row_data["categoria"],
                row_data["marca"],
                row_data["quantidade"],
                row_data["usuario"],
                business_tag,
                (row_data.get("local_info") or "N/D")[:150],
            ])
        
        # Aplicar estilo de dados
        data_start_row = header_row_index + 1
        for row in ws.iter_rows(min_row=data_start_row, max_row=ws.max_row):
            for cell in row:
                cell.border = border
                cell.alignment = data_alignment
        
        # Resumo por categoria (segunda aba)
        if not category:  # Apenas se não filtrada por categoria
            summary_ws = wb.create_sheet("Resumo por Categoria")

            summary_ws.append(["RELATORIO DE RETIRADAS - RESUMO POR CATEGORIA"])
            for line in get_company_header_lines():
                summary_ws.append([line])
            summary_ws.append([f"Periodo: {period_text} | Escopo: {scope_label}"])
            summary_ws.append(["Categoria: Todas"])
            summary_ws.append([])
            
            category_summary = db.session.query(
                Item.categoria,
                func.count(Saida.id_saida).label("quantidade_movimentacoes"),
                func.sum(Saida.quantidade).label("quantidade_total"),
            ).join(
                Item, Saida.codigo_item == Item.codigo_item, isouter=True
            ).filter(
                Saida.data_saida >= datetime.utcnow() - timedelta(days=TelegramReportService.get_period_days(months))
            )

            if scope == "tools":
                category_summary = category_summary.filter(Item.categoria.ilike("%ferramenta%"))
            elif scope == "materials":
                category_summary = category_summary.filter(~Item.categoria.ilike("%ferramenta%"))

            category_summary = category_summary.group_by(
                Item.categoria
            ).order_by(
                func.sum(Saida.quantidade).desc()
            ).all()
            
            summary_headers = ["Categoria", "Movimentações", "Quantidade Total"]
            summary_header_row = summary_ws.max_row + 1
            summary_ws.append(summary_headers)

            for cell in summary_ws[summary_header_row]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = border
            
            summary_ws.column_dimensions["A"].width = 25
            summary_ws.column_dimensions["B"].width = 18
            summary_ws.column_dimensions["C"].width = 20
            
            for row_data in category_summary:
                summary_ws.append([
                    row_data.categoria or "Sem categoria",
                    row_data.quantidade_movimentacoes or 0,
                    float(row_data.quantidade_total or 0),
                ])
            
            summary_data_start = summary_header_row + 1
            for row in summary_ws.iter_rows(min_row=summary_data_start, max_row=summary_ws.max_row):
                for cell in row:
                    cell.border = border
                    cell.alignment = data_alignment
        
        # Salvar em arquivo temporário
        temp_dir = Path(tempfile.gettempdir()) / "galint_reports"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
        category_suffix = f"_{category.replace('/', '_')}" if category else ""
        scope_suffix = ""
        if scope == "tools":
            scope_suffix = "_ferramentas"
        elif scope == "materials":
            scope_suffix = "_materiais"
        filename = f"retiradas{scope_suffix}_{months}m{category_suffix}_{timestamp}.xlsx"
        filepath = temp_dir / filename
        
        try:
            wb.save(filepath)
            logger.info(f"Relatório XLSX gerado: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Erro ao salvar XLSX: {e}")
            raise

    @staticmethod
    def _get_month_range(year: int, month: int) -> tuple[datetime, datetime]:
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
        return start, end

    @staticmethod
    def get_withdrawals_by_month_year(
        year: int,
        month: int,
        category: Optional[str] = None,
        scope: str = "all",
    ) -> list[dict]:
        start, end = TelegramReportService._get_month_range(year, month)

        q = db.session.query(
            Saida.id_saida,
            Saida.codigo_item,
            Item.descricao,
            Item.categoria,
            Item.marca,
            Saida.quantidade,
            Saida.data_saida,
            Usuario.nome,
            Saida.local_servico,
            Saida.observacao,
        ).join(
            Item, Saida.codigo_item == Item.codigo_item, isouter=True
        ).join(
            Usuario, Saida.matricula == Usuario.matricula, isouter=True
        ).filter(
            Saida.data_saida >= start,
            Saida.data_saida < end,
        )

        if scope == "tools":
            q = q.filter(Item.categoria.ilike("%ferramenta%"))
        elif scope == "materials":
            q = q.filter(~Item.categoria.ilike("%ferramenta%"))

        if category:
            q = q.filter(Item.categoria == category)

        q = q.order_by(Saida.data_saida.desc())

        results = q.all()
        data = []
        for row in results:
            local_info = row.local_servico or "N/D"
            if row.observacao and str(row.observacao).strip():
                local_info = f"{local_info} | {str(row.observacao).strip()}"
            data.append({
                "id": row.id_saida,
                "codigo": row.codigo_item or "N/D",
                "descricao": row.descricao or "N/D",
                "categoria": row.categoria or "Sem categoria",
                "marca": row.marca or "N/D",
                "quantidade": float(row.quantidade or 0),
                "data": row.data_saida,
                "usuario": row.nome or "N/D",
                "local_info": local_info,
                "observacao": row.observacao or "",
            })
        return data

    @staticmethod
    def generate_daily_xlsx(scope: str = "all") -> Path:
        now_local = TimeService.now_local()
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)

        q = db.session.query(
            Saida.codigo_item,
            Item.descricao,
            Item.categoria,
            Item.marca,
            Saida.quantidade,
            Saida.data_saida,
            Usuario.nome,
            Saida.local_servico,
            Saida.observacao,
        ).join(
            Item, Saida.codigo_item == Item.codigo_item, isouter=True
        ).join(
            Usuario, Saida.matricula == Usuario.matricula, isouter=True
        ).filter(
            Saida.data_saida >= start_utc,
            Saida.data_saida < end_utc,
        )

        if scope == "tools":
            q = q.filter(Item.categoria.ilike("%ferramenta%"))
        elif scope == "materials":
            q = q.filter(~Item.categoria.ilike("%ferramenta%"))

        data = q.order_by(Saida.data_saida.asc()).all()

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

        wb = Workbook()
        ws = wb.active
        ws.title = "Saídas do Dia"

        # Cabecalho (titulo + empresa)
        from ..utils.report_branding import get_company_header_lines

        scope_label = {
            "tools": "Ferramentas",
            "materials": "Materiais",
            "all": "Geral",
        }.get(scope, "Geral")

        ws.append(["RELATORIO DE SAIDAS DO DIA"])
        for line in get_company_header_lines():
            ws.append([line])
        ws.append([f"Periodo: {TimeService.format_local(start_local, '%d/%m/%Y')} | Escopo: {scope_label}"])
        ws.append([f"Total de registros: {len(data)}"])
        ws.append([])

        headers = ["Data", "Código", "Descrição", "Categoria", "Marca", "Quantidade", "Usuário", "Local"]
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="0066CC", end_color="0066CC", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        header_row_index = ws.max_row + 1
        ws.append(headers)
        for cell in ws[header_row_index]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = border

        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 8
        ws.column_dimensions["C"].width = 28
        ws.column_dimensions["D"].width = 20
        ws.column_dimensions["E"].width = 16
        ws.column_dimensions["F"].width = 12
        ws.column_dimensions["G"].width = 18
        ws.column_dimensions["H"].width = 30

        data_alignment = Alignment(vertical="top", wrap_text=True)
        for row in data:
            local_info = row.local_servico or "N/D"
            observacao = row.observacao or ""
            if observacao.strip():
                local_info = f"{local_info} | {observacao.strip()}"
            
            devolvido_qtd = devolucoes_map.get(row.codigo_item)
            if devolvido_qtd and devolvido_qtd > 0:
                devolucao_txt = f"DEVOLUÇÃO: {devolvido_qtd:g}"
                local_info = f"{local_info} | {devolucao_txt}" if local_info else devolucao_txt
            
            ws.append([
                TimeService.format_local(row.data_saida),
                TelegramReportService._format_codigo_barra(row.codigo_item),
                row.descricao or "N/D",
                row.categoria or "Sem categoria",
                row.marca or "N/D",
                float(row.quantidade or 0),
                row.nome or "N/D",
                local_info[:200],
            ])

        data_start_row = header_row_index + 1
        for row_cells in ws.iter_rows(min_row=data_start_row, max_row=ws.max_row):
            for cell in row_cells:
                cell.border = border
                cell.alignment = data_alignment

        temp_dir = Path(tempfile.gettempdir()) / "galint_reports"
        temp_dir.mkdir(parents=True, exist_ok=True)
        timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
        filename = f"saidas_dia_{scope}_{timestamp}.xlsx"
        filepath = temp_dir / filename
        wb.save(filepath)
        return filepath

    @staticmethod
    def generate_monthly_xlsx_report(year: int, month: int, scope: str = "all") -> Path:
        data = TelegramReportService.get_withdrawals_by_month_year(year, month, scope=scope)

        wb = Workbook()
        ws = wb.active
        ws.title = "Retiradas Mensais"

        # Cabecalho (titulo + empresa)
        from ..utils.report_branding import get_company_header_lines

        scope_label = {
            "tools": "Ferramentas",
            "materials": "Materiais",
            "all": "Geral",
        }.get(scope, "Geral")

        ws.append(["RELATORIO DE RETIRADAS - MENSAL"])
        for line in get_company_header_lines():
            ws.append([line])
        ws.append([f"Periodo: {month:02d}/{year} | Escopo: {scope_label}"])
        ws.append([f"Total de registros: {len(data)}"])
        ws.append([])

        headers = ["Data", "Código", "Descrição", "Categoria", "Marca", "Quantidade", "Usuário", "Local"]
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="0066CC", end_color="0066CC", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        header_row_index = ws.max_row + 1
        ws.append(headers)
        for cell in ws[header_row_index]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = border

        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 8
        ws.column_dimensions["C"].width = 28
        ws.column_dimensions["D"].width = 20
        ws.column_dimensions["E"].width = 16
        ws.column_dimensions["F"].width = 12
        ws.column_dimensions["G"].width = 18
        ws.column_dimensions["H"].width = 30

        data_alignment = Alignment(vertical="top", wrap_text=True)
        for row in data:
            ws.append([
                TimeService.format_local(row["data"]),
                TelegramReportService._format_codigo_barra(row.get("codigo")),
                row["descricao"],
                row["categoria"],
                row["marca"],
                row["quantidade"],
                row["usuario"],
                (row.get("local_info") or "N/D")[:200],
            ])

        data_start_row = header_row_index + 1
        for row_cells in ws.iter_rows(min_row=data_start_row, max_row=ws.max_row):
            for cell in row_cells:
                cell.border = border
                cell.alignment = data_alignment

        temp_dir = Path(tempfile.gettempdir()) / "galint_reports"
        temp_dir.mkdir(parents=True, exist_ok=True)
        timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
        filename = f"retiradas_{year}_{month:02d}_{scope}_{timestamp}.xlsx"
        filepath = temp_dir / filename
        wb.save(filepath)
        return filepath

    @staticmethod
    def generate_monthly_pdf_report(year: int, month: int, scope: str = "all") -> Path:
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER
        except ImportError:
            logger.error("ReportLab não instalado. Impossível gerar PDF.")
            raise RuntimeError("ReportLab não disponível. Instale com: pip install reportlab")

        data = TelegramReportService.get_withdrawals_by_month_year(year, month, scope=scope)

        temp_dir = Path(tempfile.gettempdir()) / "galint_reports"
        temp_dir.mkdir(parents=True, exist_ok=True)

        timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
        filename = f"retiradas_{year}_{month:02d}_{scope}_{timestamp}.pdf"
        filepath = temp_dir / filename

        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=landscape(A4),
            rightMargin=0.5 * inch,
            leftMargin=0.5 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "TitleGalint",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=colors.HexColor("#111827"),
            alignment=TA_CENTER,
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "SubtitleGalint",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#374151"),
            alignment=TA_CENTER,
            leading=12,
            spaceAfter=10,
        )

        elements = []
        elements.append(Paragraph("RELATÓRIO DIÁRIO DE RETIRADAS DE MATERIAIS", title_style))
        from ..utils.report_branding import get_company_header_html

        elements.append(Paragraph(get_company_header_html(), subtitle_style))

        scope_label = {
            "tools": "Ferramentas",
            "materials": "Materiais",
            "all": "Geral",
        }.get(scope, "Geral")
        elements.append(Paragraph(f"Período: {month:02d}/{year} — Escopo: {scope_label}", styles["Normal"]))
        elements.append(Spacer(1, 0.15 * inch))

        if data:
            table_data = [["Data", "Código", "Descrição", "Categoria", "Marca", "Qtd", "Usuário", "Local"]]
            for row in data[:500]:
                table_data.append([
                    TimeService.format_local(row["data"])[:10],
                    row["codigo"][:15],
                    row["descricao"][:24],
                    row["categoria"][:16],
                    row["marca"][:12],
                    str(row["quantidade"]),
                    row["usuario"][:18],
                    (row.get("local_info") or "N/D")[:28],
                ])

            table = Table(table_data, colWidths=[1.0*inch, 1.2*inch, 1.9*inch, 1.3*inch, 1.1*inch, 0.7*inch, 1.2*inch, 2.0*inch], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("0066CC")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("Nenhum registro encontrado no período solicitado.", styles["Normal"]))

        try:
            doc.build(elements)
            logger.info(f"Relatório PDF gerado: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Erro ao gerar PDF: {e}")
            raise

    @staticmethod
    def generate_pdf_report(
        months: int,
        category: Optional[str] = None,
        scope: str = "all",
    ) -> Path:
        """Gera relatório PDF com dados de retiradas.
        
        Args:
            months: Número de meses
            category: Categoria (None = todas)
            
        Returns:
            Caminho do arquivo gerado
        """
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
        except ImportError:
            logger.error("ReportLab não instalado. Impossível gerar PDF.")
            raise RuntimeError("ReportLab não disponível. Instale com: pip install reportlab")
        
        data = TelegramReportService.get_withdrawals_by_period_and_category(months, category, scope=scope)
        
        # Preparar diretório
        temp_dir = Path(tempfile.gettempdir()) / "galint_reports"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
        category_suffix = f"_{category.replace('/', '_')}" if category else ""
        scope_suffix = ""
        if scope == "tools":
            scope_suffix = "_ferramentas"
        elif scope == "materials":
            scope_suffix = "_materiais"
        filename = f"retiradas{scope_suffix}_{months}m{category_suffix}_{timestamp}.pdf"
        filepath = temp_dir / filename
        
        # Criar documento
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=landscape(A4),
            rightMargin=0.5 * inch,
            leftMargin=0.5 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch,
        )
        
        elements = []
        styles = getSampleStyleSheet()
        
        # Cabeçalho padrão
        title_style = ParagraphStyle(
            "TitleGalint",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=colors.HexColor("#111827"),
            alignment=TA_CENTER,
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "SubtitleGalint",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#374151"),
            alignment=TA_CENTER,
            leading=12,
            spaceAfter=10,
        )

        header_title = Paragraph("RELATÓRIO DIÁRIO DE RETIRADAS DE MATERIAIS", title_style)
        from ..utils.report_branding import get_company_header_html

        header_subtitle = Paragraph(get_company_header_html(), subtitle_style)

        elements.append(header_title)
        elements.append(header_subtitle)

        period_text = TelegramReportService.MONTHS.get(months, f"{months} meses")
        category_text = f"Categoria: {category}" if category else "Todas as categorias"
        scope_label = {
            "tools": "Ferramentas",
            "materials": "Materiais",
            "all": "Geral",
        }.get(scope, "Geral")
        elements.append(Paragraph(f"Período: {period_text} — Escopo: {scope_label} — {category_text}", styles["Normal"]))
        elements.append(Spacer(1, 0.15 * inch))

        footer_dt = TimeService.now_local()
        footer_text = f"{footer_dt.day}/{footer_dt.month}/{footer_dt.strftime('%y')} - {footer_dt.hour}h{footer_dt.strftime('%M')}m"

        def _draw_footer(canvas, _doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#374151"))
            canvas.drawCentredString(landscape(A4)[0] / 2, 0.4 * inch, footer_text)
            canvas.restoreState()
        
        # Tabela de dados
        if data:
            table_data = [["Data", "Código", "Descrição", "Categoria", "Marca", "Qtd", "Usuário"]]
            
            for row in data[:500]:  # Limitar a 500 linhas por página
                table_data.append([
                    TimeService.format_local(row["data"])[:10],
                    row["codigo"][:15],
                    (row["descricao"][:20] + "...") if len(row["descricao"]) > 20 else row["descricao"],
                    row["categoria"][:15],
                    row["marca"][:10],
                    str(row["quantidade"]),
                    row["usuario"][:15],
                ])
            
            table = Table(table_data, colWidths=[1.0*inch, 1.2*inch, 1.5*inch, 1.2*inch, 1.0*inch, 0.8*inch, 1.2*inch], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("0066CC")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            
            elements.append(table)
        else:
            elements.append(Paragraph("Nenhum registro encontrado no período solicitado.", styles["Normal"]))
        
        # Gerar PDF
        try:
            doc.build(elements, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
            logger.info(f"Relatório PDF gerado: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Erro ao gerar PDF: {e}")
            raise
