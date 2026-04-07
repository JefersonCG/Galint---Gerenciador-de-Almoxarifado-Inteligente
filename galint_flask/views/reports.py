"""Views para gerenciamento e histórico de relatórios."""
from __future__ import annotations

import logging
import math
import os
from io import BytesIO
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import NormalDist, mean, stdev
import unicodedata
from pathlib import Path

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from galint_flask.utils.time_service import TimeService
from sqlalchemy import func, not_, or_

from ..services.general_search_service import general_search_service

logger = logging.getLogger(__name__)

bp = Blueprint("reports", __name__, url_prefix="/relatorios")


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _get_item_value(item: object, key: str, default: object = None) -> object:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _format_codigo_barra(value: object) -> str:
    if value is None:
        return "N/D"
    text = str(value).strip()
    if not text:
        return "N/D"
    return text[-4:] if len(text) >= 4 else text


def _normalize_report_type(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _normalize_search(value: str) -> str:
    """Remove acentos de uma string para busca normalizada."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _build_photo_url(photo_path: str | None) -> str | None:
    if not photo_path:
        return None
    return url_for("static", filename=photo_path)


def _parse_period_days_arg(raw_value: object, *, default: int = 0) -> int:
    try:
        period_days = int(str(raw_value or default).strip())
    except (TypeError, ValueError):
        return default

    return period_days


def _format_date_like(value: object, fmt: str = "%d/%m/%Y") -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return TimeService.format_local(value, fmt)
    if isinstance(value, date):
        return value.strftime(fmt)
    return _safe_text(value)


def _convert_pdf_to_jpeg(pdf_path: str, jpeg_path: str, dpi: int = 200) -> None:
    """Converte PDF para JPEG de alta qualidade usando pdf2image + Pillow."""
    try:
        from pdf2image import convert_from_path
        from PIL import Image
    except ImportError as exc:
        raise ImportError(
            "Para gerar JPEG, instale: pip install pdf2image pillow\n"
            "Windows: Também instale poppler (https://github.com/oschwartz10612/poppler-windows/releases)"
        ) from exc

    images = convert_from_path(pdf_path, dpi=dpi)
    if len(images) == 1:
        images[0].save(jpeg_path, "JPEG", quality=95, optimize=True)
        return

    total_width = max(img.width for img in images)
    total_height = sum(img.height for img in images)
    combined = Image.new("RGB", (total_width, total_height), "white")
    y_offset = 0
    for img in images:
        combined.paste(img, (0, y_offset))
        y_offset += img.height
    combined.save(jpeg_path, "JPEG", quality=95, optimize=True)


def _generate_item_report_pdf(*, item, saidas, period_days: int, time_service) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise ValueError(
            "Biblioteca de PDF não instalada. Instale 'reportlab' (pip install reportlab)."
        ) from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
        title="Relatório por item",
        author="GALINT",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 8
    body_style.leading = 9
    story = []

    title_style = styles["Title"]
    title_style.alignment = 1
    title_style.fontSize = 16
    subtitle_style = styles["Normal"]
    subtitle_style.alignment = 1

    story.append(Paragraph("RELATÓRIO DE RETIRADAS POR ITEM", title_style))
    from ..utils.report_branding import get_company_header_html

    story.append(Paragraph(get_company_header_html(), subtitle_style))
    story.append(Spacer(1, 0.2 * cm))
    
    gerado_em = TimeService.now_local().strftime('%d/%m/%Y %H:%M')
    story.append(Paragraph(f"Gerado em: {gerado_em}", styles["Normal"]))

    period_label = "Todo histórico" if period_days <= 0 else f"Últimos {period_days} dias"
    item_descricao = _get_item_value(item, "descricao")
    item_codigo = _get_item_value(item, "codigo_item")
    item_categoria = _get_item_value(item, "categoria")
    item_marca = _get_item_value(item, "marca")
    story.append(Paragraph(f"Item: <b>{_safe_text(item_descricao)}</b>", styles["Normal"]))
    story.append(Paragraph(f"Código: {_format_codigo_barra(item_codigo)}", styles["Normal"]))
    story.append(Paragraph(f"Categoria: {_safe_text(item_categoria or 'N/D')}", styles["Normal"]))
    story.append(Paragraph(f"Marca: {_safe_text(item_marca or 'N/D')}", styles["Normal"]))
    
    # Informações de rastreabilidade
    item_lote = _get_item_value(item, "lote")
    if item_lote:
        story.append(Paragraph(f"Lote: <b>{_safe_text(item_lote)}</b>", styles["Normal"]))
    item_data_entrada = _get_item_value(item, "data_entrada")
    if item_data_entrada and hasattr(item_data_entrada, "strftime"):
        story.append(
            Paragraph(
                f"Data de Entrada: {item_data_entrada.strftime('%d/%m/%Y')}",
                styles["Normal"],
            )
        )
    item_data_validade = _get_item_value(item, "data_validade")
    if item_data_validade and hasattr(item_data_validade, "strftime"):
        dias_validade = (item_data_validade - TimeService.now_local().date()).days
        status_validade = "✓" if dias_validade > 30 else "⚠️"
        story.append(
            Paragraph(
                f"Validade: {item_data_validade.strftime('%d/%m/%Y')} {status_validade} ({dias_validade} dias)",
                styles["Normal"],
            )
        )
    
    story.append(Paragraph(f"Período: {period_label}", styles["Normal"]))
    story.append(Paragraph(f"Total de movimentações: {len(saidas)}", styles["Normal"]))
    story.append(
        Paragraph(
            f"Quantidade total movimentada: {sum((s.get('quantidade', 0) if isinstance(s, dict) else s.quantidade) for s in saidas) if saidas else 0}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    header = ["Data", "Hora", "Usuário", "Qtd.", "Período", "Local"]
    data = [header]
    for saida in saidas:
        # Busca atributos com try/except para evitar AttributeError do SQLAlchemy
        try:
            nome_usuario = saida.usuario_nome or "N/D"
        except AttributeError:
            nome_usuario = "N/D"
        
        local_info = getattr(saida, "local_servico", None) or "N/D"
        if getattr(saida, "observacao", None) and str(saida.observacao).strip():
            local_info = f"{local_info} | {str(saida.observacao).strip()}"

        data.append(
            [
                time_service.format_local(saida.data_saida, "%d/%m/%Y"),
                time_service.format_local(saida.data_saida, "%H:%M"),
                Paragraph(_safe_text(nome_usuario), body_style),
                _safe_text(saida.quantidade or ""),
                _safe_text(time_service.get_business_day_tag(saida.data_saida) or "Expediente"),
                Paragraph(_safe_text(local_info[:200]), body_style),
            ]
        )

    if len(data) == 1:
        story.append(Paragraph("Nenhuma retirada registrada para este item.", styles["Italic"]))
        doc.build(story)
        return buffer.getvalue()

    table = Table(
        data,
        colWidths=[2.2 * cm, 1.6 * cm, 8.5 * cm, 1.5 * cm, 3.0 * cm, 11.9 * cm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def _generate_custom_report_pdf(*, results, date_from, date_to, report_type, time_service) -> bytes:
    """Gera PDF para relatório customizado."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise ValueError(
            "Biblioteca de PDF não instalada. Instale 'reportlab' (pip install reportlab)."
        ) from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
        title="Relatório Customizado",
        author="GALINT",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 8
    body_style.leading = 9
    story = []

    title_style = styles["Title"]
    title_style.alignment = 1
    title_style.fontSize = 16
    subtitle_style = styles["Normal"]
    subtitle_style.alignment = 1

    story.append(Paragraph("RELATÓRIO DE SAÍDAS - PERÍODO CUSTOMIZADO", title_style))
    from ..utils.report_branding import get_company_header_html

    story.append(Paragraph(get_company_header_html(), subtitle_style))
    story.append(Spacer(1, 0.2 * cm))

    period_label = f"{date_from.strftime('%d/%m/%Y')} a {date_to.strftime('%d/%m/%Y')}"
    story.append(Paragraph(f"Período: <b>{period_label}</b>", styles["Normal"]))
    story.append(Paragraph(f"Total de registros: {len(results)}", styles["Normal"]))
    
    # Adicionar timestamp
    story.append(Paragraph(f"Gerado em: {TimeService.now_local().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 0.4 * cm))

    header = ["Data", "Hora", "Funcionário", "Item", "Categoria", "Qtd.", "Local"]
    data = [header]
    
    for row in results:
        # Mesclar local e observação
        local_info = row.local_servico or "N/D"
        if row.observacao and row.observacao.strip():
            local_info = f"{local_info} | {row.observacao}"
        
        data.append([
            time_service.format_local(row.data_saida, "%d/%m/%Y"),
            time_service.format_local(row.data_saida, "%H:%M"),
            Paragraph(_safe_text(row.usuario_nome or "N/D"), body_style),
            Paragraph(_safe_text(row.item_descricao or "Item removido"), body_style),
            _safe_text(row.item_categoria or "N/D"),
            _safe_text(row.quantidade),
            Paragraph(_safe_text(local_info[:150]), body_style),
        ])

    if len(data) == 1:
        story.append(Paragraph("Nenhuma saída registrada no período selecionado.", styles["Italic"]))
        doc.build(story)
        return buffer.getvalue()

    table = Table(
        data,
        colWidths=[2.2 * cm, 1.3 * cm, 6.0 * cm, 8.0 * cm, 3.3 * cm, 1.3 * cm, 7.0 * cm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, 0), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def _generate_usuario_report_pdf(*, usuario, saidas, period_days: int, time_service) -> bytes:
    """Gera PDF do relatório de retiradas por funcionário."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise ValueError(
            "Biblioteca de PDF não instalada. Instale 'reportlab' (pip install reportlab)."
        ) from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
        title="Relatório por funcionário",
        author="GALINT",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 8
    body_style.leading = 9
    story = []

    title_style = styles["Title"]
    title_style.alignment = 1
    title_style.fontSize = 16
    subtitle_style = styles["Normal"]
    subtitle_style.alignment = 1

    story.append(Paragraph("RELATÓRIO DE RETIRADAS E DEVOLUÇÕES POR FUNCIONÁRIO", title_style))
    from ..utils.report_branding import get_company_header_html

    story.append(Paragraph(get_company_header_html(), subtitle_style))
    story.append(Spacer(1, 0.2 * cm))
    
    gerado_em = TimeService.now_local().strftime('%d/%m/%Y %H:%M')
    story.append(Paragraph(f"Gerado em: {gerado_em}", styles["Normal"]))

    period_label = "Todo histórico" if period_days <= 0 else f"Últimos {period_days} dias"
    story.append(Paragraph(f"Funcionário: <b>{_safe_text(usuario['nome'])}</b>", styles["Normal"]))
    story.append(Paragraph(f"Matrícula: {_safe_text(usuario['matricula'])}", styles["Normal"]))
    story.append(Paragraph(f"Cargo: {_safe_text(usuario['cargo'])}", styles["Normal"]))
    story.append(Paragraph(f"Período: {period_label}", styles["Normal"]))
    story.append(Paragraph(f"Total de movimentações: {len(saidas)}", styles["Normal"]))
    story.append(
        Paragraph(
            f"Quantidade total movimentada: {sum((s.get('quantidade', 0) if isinstance(s, dict) else getattr(s, 'quantidade', 0)) for s in saidas) if saidas else 0}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    header = ["Data", "Hora", "Item", "Código", "Qtd.", "Tipo", "Período", "Local"]
    data = [header]
    for saida in saidas:
        data_saida = saida.get("data") if isinstance(saida, dict) else getattr(saida, "data_saida", None)
        item_descricao = saida.get("item_descricao") if isinstance(saida, dict) else getattr(saida, "item_descricao", None)
        codigo_item = saida.get("codigo_item") if isinstance(saida, dict) else getattr(saida, "codigo_item", None)
        quantidade = saida.get("quantidade") if isinstance(saida, dict) else getattr(saida, "quantidade", None)
        periodo = saida.get("periodo") if isinstance(saida, dict) else time_service.get_business_day_tag(data_saida)
        observacao = saida.get("observacao") if isinstance(saida, dict) else getattr(saida, "observacao", None)
        local_servico = saida.get("local_servico") if isinstance(saida, dict) else getattr(saida, "local_servico", None)
        local_info = local_servico or "N/D"
        if observacao and str(observacao).strip():
            local_info = f"{local_info} | {str(observacao).strip()}"
        tipo_movimentacao = saida.get("tipo") if isinstance(saida, dict) else "Retirada"

        data.append(
            [
                time_service.format_local(data_saida, "%d/%m/%Y"),
                time_service.format_local(data_saida, "%H:%M"),
                Paragraph(_safe_text(item_descricao or "Item removido"), body_style),
                _format_codigo_barra(codigo_item),
                _safe_text(quantidade or ""),
                tipo_movimentacao,
                _safe_text(periodo or "Expediente"),
                Paragraph(_safe_text(local_info[:200]), body_style),
            ]
        )

    if len(data) == 1:
        story.append(Paragraph("Nenhuma retirada registrada para este funcionário.", styles["Italic"]))
        doc.build(story)
        return buffer.getvalue()

    table = Table(
        data,
        colWidths=[2.1 * cm, 1.5 * cm, 9.0 * cm, 1.3 * cm, 1.3 * cm, 1.7 * cm, 2.5 * cm, 9.3 * cm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def _parse_report_filename(filename: str) -> dict:
    """Extrai informações do nome do arquivo de relatório.
    
    Formatos esperados:
    - saidas_dia_<scope>_<timestamp>.pdf
    - saidas_dia_<timestamp>.pdf
    - estoque_baixo_<timestamp>.pdf
    - monthly_<scope>_<year>_<month>_<timestamp>.pdf
    """
    parts = filename.split("_")
    
    info = {
        "filename": filename,
        "type": "Desconhecido",
        "scope": "all",
        "format": filename.split(".")[-1].upper() if "." in filename else "?",
        "date": None,
        "size": 0,
    }
    
    # Identificar tipo
    if filename.startswith("saidas_dia"):
        info["type"] = "Saídas do Dia"
        # Extrair scope se existir
        if len(parts) >= 4 and parts[2] in ["all", "materials", "tools"]:
            info["scope"] = parts[2]
            timestamp_part = parts[3].split(".")[0]
        elif len(parts) >= 3:
            timestamp_part = parts[2].split(".")[0]
        else:
            timestamp_part = None
            
        if timestamp_part:
            try:
                info["date"] = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")
            except ValueError:
                pass

    elif filename.startswith("relatorio_saidas"):
        info["type"] = "Saídas no Período"
    elif filename.startswith("alertas_estoque"):
        info["type"] = "Estoque Baixo"
    elif filename.startswith("relatorio_entradas"):
        info["type"] = "Entradas no Período"
    elif filename.startswith("inventario_entradas_ciclo"):
        info["type"] = "Entradas (Ciclo)"
    elif filename.startswith("relatorio_customizado"):
         info["type"] = "Relatório Customizado"
    elif filename.startswith("relatorio_item"):
        info["type"] = "Relatório por Item"
    elif filename.startswith("relatorio_funcionario"):
         info["type"] = "Relatório por Funcionário"
    elif filename.startswith("historico_retiradas"):
        info["type"] = "Histórico de Retiradas"
    
    elif filename.startswith("estoque_baixo"):
        info["type"] = "Estoque Baixo"
        if len(parts) >= 3:
            timestamp_part = parts[2].split(".")[0]
            try:
                info["date"] = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")
            except ValueError:
                pass
    
    elif filename.startswith("monthly"):
        info["type"] = "Relatório Mensal"
        if len(parts) >= 5:
            info["scope"] = parts[1]
            # monthly_<scope>_<year>_<month>_<timestamp>
            try:
                year = int(parts[2])
                month = int(parts[3])
                info["type"] = f"Relatório Mensal ({month:02d}/{year})"
            except (ValueError, IndexError):
                pass
            
            if len(parts) >= 5:
                timestamp_part = parts[4].split(".")[0]
                try:
                    info["date"] = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")
                except ValueError:
                    pass
    
    return info


def _get_reports_list(reports_dir: Path, filters: dict = None) -> list[dict]:
    """Lista todos os relatórios da pasta reports.
    
    Args:
        reports_dir: Caminho da pasta de relatórios
        filters: Dicionário com filtros opcionais (date_from, date_to, type, format)
    
    Returns:
        Lista de dicionários com informações dos relatórios
    """
    if not reports_dir.exists():
        return []
    
    filters = filters or {}
    reports = []
    
    # Listar apenas arquivos (não pastas)
    for item in reports_dir.iterdir():
        if item.is_file() and item.suffix.lower() == ".pdf":
            info = _parse_report_filename(item.name)
            
            # Adicionar tamanho do arquivo
            try:
                info["size"] = item.stat().st_size
                info["size_mb"] = round(item.stat().st_size / (1024 * 1024), 2)
            except Exception:
                info["size"] = 0
                info["size_mb"] = 0
            
            # Se não conseguiu extrair data do nome, usar data de modificação
            if not info["date"]:
                try:
                    info["date"] = TimeService.to_local(
                        datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
                    ).replace(tzinfo=None)
                except Exception:
                    info["date"] = TimeService.now_local().replace(tzinfo=None)
            
            # Aplicar filtros
            if filters.get("date_from"):
                try:
                    date_from = datetime.strptime(filters["date_from"], "%Y-%m-%d")
                    if info["date"] < date_from:
                        continue
                except ValueError:
                    pass
            
            if filters.get("date_to"):
                try:
                    date_to = datetime.strptime(filters["date_to"], "%Y-%m-%d")
                    date_to = date_to.replace(hour=23, minute=59, second=59)
                    if info["date"] > date_to:
                        continue
                except ValueError:
                    pass
            
            if filters.get("type") and filters["type"] != "all":
                normalized_type = _normalize_report_type(info["type"])
                if filters["type"] not in normalized_type:
                    continue
            
            if filters.get("format") and filters["format"] != "all":
                target_format = filters["format"].lower()
                if target_format != "pdf":
                    continue
            
            reports.append(info)
    
    # Ordenar por data (mais recente primeiro)
    reports.sort(key=lambda x: x["date"], reverse=True)
    
    return reports


@bp.route("/")
@login_required
def index():
    """Página principal de relatórios gerais."""
    from flask import current_app
    
    reports_dir = Path(current_app.instance_path) / "reports"
    
    requested_format = (request.args.get("format") or "").strip().lower()
    if requested_format not in {"", "all", "pdf"}:
        requested_format = "pdf"

    # Obter filtros da query string
    filters = {
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
        "type": request.args.get("type"),
        "format": "pdf",
    }
    
    # Remover filtros vazios
    filters = {k: v for k, v in filters.items() if v}
    
    reports = _get_reports_list(reports_dir, filters)
    
    # Busca rápida (texto livre)
    search_query = request.args.get("search", "").strip().lower()
    if search_query:
        reports = [
            r for r in reports
            if search_query in r["type"].lower() or search_query in r["filename"].lower()
        ]
    
    # Paginação
    page = request.args.get("page", 1, type=int)
    per_page = 12
    total_reports = len(reports)
    total_pages = (total_reports + per_page - 1) // per_page
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_reports = reports[start_idx:end_idx]
    
    # Calcular estatísticas (sobre todos os relatórios, não apenas a página)
    total_size_mb = sum(r["size_mb"] for r in reports)
    
    stats = {
        "total": len(reports),
        "total_size_mb": round(total_size_mb, 2),
        "pdf_count": sum(1 for r in reports if r["format"] == "PDF"),
    }
    
    # Modo de visualização (cards ou table)
    view_mode = request.args.get("view", "cards")
    
    return render_template(
        "reports/index.html",
        reports=paginated_reports,
        stats=stats,
        filters=filters,
        search_query=search_query,
        page=page,
        total_pages=total_pages,
        total_reports=total_reports,
        view_mode=view_mode,
    )




@bp.route("/percentual-movimentos")
@login_required
def percentual_movimentos():
    """Alias legado para a Central Analítica."""
    flash("A página Percentual Movimentos foi incorporada à Central Analítica.", "info")
    return redirect(url_for("analytics.index"))

    from ..extensions import db
    from ..models import InventarioEvento, Item, Saida, Usuario

    def _merge_employee(target, matricula, nome, movimentos, quantidade):
        key = (matricula or "N/D").strip() or "N/D"
        entry = target.setdefault(
            key,
            {
                "matricula": key,
                "nome": (nome or "").strip() or f"Matricula {key}",
                "movimentos": 0,
                "quantidade": 0.0,
            },
        )
        entry["movimentos"] += int(movimentos or 0)
        entry["quantidade"] += float(quantidade or 0)
        if nome and (not entry.get("nome") or entry["nome"].startswith("Matricula ")):
            entry["nome"] = nome

    def _merge_item(target, codigo, descricao, retiradas_count, retiradas_qty):
        key = (codigo or "N/D").strip() or "N/D"
        entry = target.setdefault(
            key,
            {
                "codigo": key,
                "descricao": (descricao or "").strip() or "Item removido",
                "retiradas_count": 0,
                "retiradas_qty": 0.0,
            },
        )
        entry["retiradas_count"] += int(retiradas_count or 0)
        entry["retiradas_qty"] += float(retiradas_qty or 0)
        if descricao and entry.get("descricao") in ("", "Item removido"):
            entry["descricao"] = descricao

    def _merge_return(target, codigo, descricao, devolucoes_count, devolucoes_qty):
        key = (codigo or "N/D").strip() or "N/D"
        entry = target.setdefault(
            key,
            {
                "codigo": key,
                "descricao": (descricao or "").strip() or "Item removido",
                "devolucoes_count": 0,
                "devolucoes_qty": 0.0,
            },
        )
        entry["devolucoes_count"] += int(devolucoes_count or 0)
        entry["devolucoes_qty"] += float(devolucoes_qty or 0)
        if descricao and entry.get("descricao") in ("", "Item removido"):
            entry["descricao"] = descricao

    def _sort_people(values):
        return sorted(values, key=lambda item: (item.get("quantidade", 0), item.get("movimentos", 0)), reverse=True)

    def _sort_items(values):
        return sorted(values, key=lambda item: (item.get("retiradas_qty", 0), item.get("retiradas_count", 0)), reverse=True)

    def _build_pie(items, total_value, label_key, value_key, max_slices=6):
        if total_value <= 0:
            return {"labels": [], "values": []}
        sorted_items = sorted(items, key=lambda item: item.get(value_key, 0), reverse=True)
        top_items = sorted_items[:max_slices]
        labels = [item.get(label_key, "N/D") for item in top_items]
        values = [int(item.get(value_key, 0) or 0) for item in top_items]
        top_sum = sum(values)
        restante = max(0, int(total_value - top_sum))
        if restante > 0:
            labels.append("Outros")
            values.append(restante)
        return {"labels": labels, "values": values}

    def _as_float(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _clamp_probability(value):
        return max(0.0, min(1.0, float(value or 0.0)))

    def _format_window_label(start_dt, end_dt):
        last_day = end_dt - timedelta(days=1)
        if last_day < start_dt:
            last_day = start_dt
        return f"{start_dt.strftime('%d/%m/%Y')} - {last_day.strftime('%d/%m/%Y')}"

    def _build_sequential_buckets(withdrawal_events, return_events, start_dt, end_dt, bucket_days=30):
        if not start_dt or not end_dt or start_dt > end_dt:
            return []

        buckets = []
        cursor = start_dt
        while cursor <= end_dt:
            bucket_end = cursor + timedelta(days=bucket_days)
            withdrawals_in_bucket = [qty for dt, qty in withdrawal_events if cursor <= dt < bucket_end]
            returns_in_bucket = [qty for dt, qty in return_events if cursor <= dt < bucket_end]
            withdrawals_qty = sum(withdrawals_in_bucket)
            returns_qty = sum(returns_in_bucket)
            net_qty = max(0.0, withdrawals_qty - returns_qty)
            buckets.append(
                {
                    "start": cursor,
                    "end": bucket_end,
                    "label": _format_window_label(cursor, bucket_end),
                    "withdrawals_qty": withdrawals_qty,
                    "returns_qty": returns_qty,
                    "net_qty": net_qty,
                    "withdrawals_count": len(withdrawals_in_bucket),
                    "returns_count": len(returns_in_bucket),
                    "movements_count": len(withdrawals_in_bucket) + len(returns_in_bucket),
                }
            )
            cursor = bucket_end

        return buckets

    def _build_monthly_buckets(withdrawal_events, return_events):
        monthly_map = {}

        def _get_entry(year, month):
            key = (year, month)
            if key not in monthly_map:
                monthly_map[key] = {
                    "year": year,
                    "month": month,
                    "label": f"{month:02d}/{year}",
                    "withdrawals_qty": 0.0,
                    "returns_qty": 0.0,
                    "net_qty": 0.0,
                    "withdrawals_count": 0,
                    "returns_count": 0,
                    "movements_count": 0,
                }
            return monthly_map[key]

        for dt, qty in withdrawal_events:
            entry = _get_entry(dt.year, dt.month)
            entry["withdrawals_qty"] += _as_float(qty)
            entry["withdrawals_count"] += 1
            entry["movements_count"] += 1

        for dt, qty in return_events:
            entry = _get_entry(dt.year, dt.month)
            entry["returns_qty"] += _as_float(qty)
            entry["returns_count"] += 1
            entry["movements_count"] += 1

        buckets = []
        for key in sorted(monthly_map.keys()):
            entry = monthly_map[key]
            entry["net_qty"] = max(0.0, entry["withdrawals_qty"] - entry["returns_qty"])
            buckets.append(entry)
        return buckets

    def _probability_stockout(threshold, average_demand, std_dev):
        threshold = _as_float(threshold)
        average_demand = _as_float(average_demand)
        std_dev = _as_float(std_dev)
        if average_demand <= 0 and std_dev <= 0:
            return 0.0
        if std_dev <= 1e-9:
            return 1.0 if average_demand >= threshold else 0.0
        z_score = (threshold - average_demand) / std_dev
        return _clamp_probability(1 - NormalDist().cdf(z_score))

    def _ci_95(average_demand, std_dev):
        average_demand = _as_float(average_demand)
        std_dev = _as_float(std_dev)
        margin = 1.96 * std_dev if std_dev > 0 else 0.0
        return max(0.0, average_demand - margin), max(0.0, average_demand + margin)

    def _safe_projected_date(base_dt, days, fallback="Sem previsao pratica"):
        if base_dt is None:
            return fallback

        normalized_days = _as_float(days)
        if not math.isfinite(normalized_days) or normalized_days < 0:
            return fallback

        max_supported_days = max(0, (datetime.max.date() - base_dt.date()).days)
        if normalized_days > max_supported_days:
            return fallback

        try:
            return (base_dt + timedelta(days=normalized_days)).date().isoformat()
        except (OverflowError, ValueError):
            return fallback

    tool_filter = func.coalesce(Item.categoria, "").ilike("Ferrament%")

    # Funcionarios (materiais)
    materiais_emps = {}
    materiais_emps_rows = (
        db.session.query(
            Saida.matricula,
            Usuario.nome,
            func.count(Saida.id_saida),
            func.coalesce(func.sum(Saida.quantidade), 0),
        )
        .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
        .join(Usuario, Saida.matricula == Usuario.matricula, isouter=True)
        .filter(not_(tool_filter))
        .group_by(Saida.matricula, Usuario.nome)
        .all()
    )
    for row in materiais_emps_rows:
        _merge_employee(materiais_emps, row[0], row[1], row[2], row[3])

    # Funcionários (ferramentas)
    ferramentas_emps = {}
    ferramentas_emps_rows = (
        db.session.query(
            Saida.matricula,
            Usuario.nome,
            func.count(Saida.id_saida),
            func.coalesce(func.sum(Saida.quantidade), 0),
        )
        .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
        .join(Usuario, Saida.matricula == Usuario.matricula, isouter=True)
        .filter(tool_filter)
        .group_by(Saida.matricula, Usuario.nome)
        .all()
    )
    for row in ferramentas_emps_rows:
        _merge_employee(ferramentas_emps, row[0], row[1], row[2], row[3])

    # Itens (materiais)
    materiais_itens = {}
    materiais_itens_rows = (
        db.session.query(
            Saida.codigo_item,
            Item.descricao,
            func.count(Saida.id_saida),
            func.coalesce(func.sum(Saida.quantidade), 0),
        )
        .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
        .filter(not_(tool_filter))
        .group_by(Saida.codigo_item, Item.descricao)
        .all()
    )
    for row in materiais_itens_rows:
        _merge_item(materiais_itens, row[0], row[1], row[2], row[3])

    # Itens (ferramentas)
    ferramentas_itens = {}
    ferramentas_itens_rows = (
        db.session.query(
            Saida.codigo_item,
            Item.descricao,
            func.count(Saida.id_saida),
            func.coalesce(func.sum(Saida.quantidade), 0),
        )
        .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
        .filter(tool_filter)
        .group_by(Saida.codigo_item, Item.descricao)
        .all()
    )
    for row in ferramentas_itens_rows:
        _merge_item(ferramentas_itens, row[0], row[1], row[2], row[3])

    # Devoluções por item
    devolucoes_materiais = {}
    devolucoes_materiais_rows = (
        db.session.query(
            InventarioEvento.codigo_item,
            Item.descricao,
            func.count(InventarioEvento.id_evento),
            func.coalesce(func.sum(InventarioEvento.quantidade), 0),
        )
        .join(Item, InventarioEvento.codigo_item == Item.codigo_item, isouter=True)
        .filter(InventarioEvento.tipo == "devolucao_material")
        .group_by(InventarioEvento.codigo_item, Item.descricao)
        .all()
    )
    for row in devolucoes_materiais_rows:
        _merge_return(devolucoes_materiais, row[0], row[1], row[2], row[3])

    devolucoes_ferramentas = {}
    devolucoes_ferramentas_rows = (
        db.session.query(
            InventarioEvento.codigo_item,
            Item.descricao,
            func.count(InventarioEvento.id_evento),
            func.coalesce(func.sum(InventarioEvento.quantidade), 0),
        )
        .join(Item, InventarioEvento.codigo_item == Item.codigo_item, isouter=True)
        .filter(InventarioEvento.tipo.in_(["devolucao_ferramenta", "devolucao"]))
        .group_by(InventarioEvento.codigo_item, Item.descricao)
        .all()
    )
    for row in devolucoes_ferramentas_rows:
        _merge_return(devolucoes_ferramentas, row[0], row[1], row[2], row[3])

    material_withdrawal_event_rows = (
        db.session.query(
            Saida.codigo_item,
            Item.descricao,
            Saida.data_saida,
            func.coalesce(Saida.quantidade, 0),
        )
        .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
        .filter(not_(tool_filter))
        .order_by(Saida.data_saida.asc())
        .all()
    )
    material_return_event_rows = (
        db.session.query(
            InventarioEvento.codigo_item,
            Item.descricao,
            InventarioEvento.data_evento,
            func.coalesce(InventarioEvento.quantidade, 0),
        )
        .join(Item, InventarioEvento.codigo_item == Item.codigo_item, isouter=True)
        .filter(InventarioEvento.tipo == "devolucao_material")
        .order_by(InventarioEvento.data_evento.asc())
        .all()
    )

    material_withdrawals_by_item = defaultdict(list)
    material_returns_by_item = defaultdict(list)
    material_descriptions = {}
    all_material_withdrawals = []
    all_material_returns = []

    for codigo_item, descricao, data_saida, quantidade in material_withdrawal_event_rows:
        if not codigo_item or not data_saida:
            continue
        qty = _as_float(quantidade)
        material_withdrawals_by_item[codigo_item].append((data_saida, qty))
        all_material_withdrawals.append((data_saida, qty))
        if descricao:
            material_descriptions[codigo_item] = descricao

    for codigo_item, descricao, data_evento, quantidade in material_return_event_rows:
        if not codigo_item or not data_evento:
            continue
        qty = _as_float(quantidade)
        material_returns_by_item[codigo_item].append((data_evento, qty))
        all_material_returns.append((data_evento, qty))
        if descricao:
            material_descriptions[codigo_item] = descricao

    # Consolidacao
    materiais_emps_list = _sort_people(list(materiais_emps.values()))
    ferramentas_emps_list = _sort_people(list(ferramentas_emps.values()))

    materiais_itens_rows = []
    for item in materiais_itens.values():
        devolucao = devolucoes_materiais.get(item["codigo"], {})
        devol_count = int(devolucao.get("devolucoes_count", 0) or 0)
        devol_qty = float(devolucao.get("devolucoes_qty", 0) or 0)
        retiradas_count = int(item.get("retiradas_count", 0) or 0)
        retiradas_qty = float(item.get("retiradas_qty", 0) or 0)
        # Taxa calculada por quantidade (não por contagem), limitada a 100%
        taxa = min(1.0, (devol_qty / retiradas_qty)) if retiradas_qty > 0 else 0.0
        materiais_itens_rows.append({
            **item,
            "devolucoes_count": devol_count,
            "devolucoes_qty": devol_qty,
            "taxa_devolucao": taxa,
        })

    ferramentas_itens_rows = []
    for item in ferramentas_itens.values():
        devolucao = devolucoes_ferramentas.get(item["codigo"], {})
        devol_count = int(devolucao.get("devolucoes_count", 0) or 0)
        devol_qty = float(devolucao.get("devolucoes_qty", 0) or 0)
        retiradas_count = int(item.get("retiradas_count", 0) or 0)
        retiradas_qty = float(item.get("retiradas_qty", 0) or 0)
        # Taxa calculada por quantidade (não por contagem), limitada a 100%
        taxa = min(1.0, (devol_qty / retiradas_qty)) if retiradas_qty > 0 else 0.0
        ferramentas_itens_rows.append({
            **item,
            "devolucoes_count": devol_count,
            "devolucoes_qty": devol_qty,
            "taxa_devolucao": taxa,
        })

    materiais_itens_list = _sort_items(materiais_itens_rows)
    ferramentas_itens_list = _sort_items(ferramentas_itens_rows)

    total_materiais_retiradas = sum(item.get("retiradas_count", 0) for item in materiais_itens_list)
    total_ferramentas_retiradas = sum(item.get("retiradas_count", 0) for item in ferramentas_itens_list)
    total_materiais_devolucoes = sum(item.get("devolucoes_count", 0) for item in devolucoes_materiais.values())
    total_ferramentas_devolucoes = sum(item.get("devolucoes_count", 0) for item in devolucoes_ferramentas.values())

    total_materiais_qtd = sum(item.get("retiradas_qty", 0) for item in materiais_itens_list)
    total_ferramentas_qtd = sum(item.get("retiradas_qty", 0) for item in ferramentas_itens_list)
    total_materiais_devolucoes_qtd = sum(item.get("devolucoes_qty", 0) for item in devolucoes_materiais.values())
    total_ferramentas_devolucoes_qtd = sum(item.get("devolucoes_qty", 0) for item in devolucoes_ferramentas.values())

    material_forecasts = []
    now_utc = datetime.utcnow()
    for codigo_item, withdrawal_events in material_withdrawals_by_item.items():
        if not withdrawal_events:
            continue

        item_obj = db.session.get(Item, codigo_item)
        if not item_obj:
            continue

        return_events = material_returns_by_item.get(codigo_item, [])
        first_withdrawal_at = min(event_dt for event_dt, _ in withdrawal_events)
        rolling_buckets = _build_sequential_buckets(withdrawal_events, return_events, first_withdrawal_at, now_utc, 30)
        if not rolling_buckets:
            continue

        bucket_net_values = [bucket["net_qty"] for bucket in rolling_buckets]
        average_30d = mean(bucket_net_values)
        std_dev_30d = stdev(bucket_net_values) if len(bucket_net_values) > 1 else 0.0
        ci_95_low, ci_95_high = _ci_95(average_30d, std_dev_30d)
        avg_daily = average_30d / 30.0 if average_30d > 0 else 0.0
        enough_history = len(rolling_buckets) >= 3

        current_stock = _as_float(item_obj.get_saldo_atual())
        reorder_point = _as_float(item_obj.estoque_minimo)
        threshold_to_reorder = max(0.0, current_stock - reorder_point)
        probability_stockout_30d = _probability_stockout(current_stock, average_30d, std_dev_30d) if enough_history else 0.0
        probability_reorder_30d = (1.0 if current_stock <= reorder_point else _probability_stockout(threshold_to_reorder, average_30d, std_dev_30d)) if enough_history else 0.0

        days_to_zero = (current_stock / avg_daily) if avg_daily > 0 else None
        days_to_reorder = 0.0 if current_stock <= reorder_point else ((current_stock - reorder_point) / avg_daily if avg_daily > 0 else None)

        reorder_date = _safe_projected_date(now_utc, days_to_reorder)
        stockout_date = _safe_projected_date(now_utc, days_to_zero)

        material_forecasts.append(
            {
                "codigo": codigo_item,
                "descricao": material_descriptions.get(codigo_item) or item_obj.descricao or "Item sem descrição",
                "saldo_atual": current_stock,
                "estoque_minimo": reorder_point,
                "media_30d": average_30d,
                "desvio_padrao_30d": std_dev_30d,
                "ic95_baixo": ci_95_low,
                "ic95_alto": ci_95_high,
                "prob_ruptura_30d": probability_stockout_30d,
                "prob_repor_30d": probability_reorder_30d,
                "dias_para_ruptura": days_to_zero,
                "dias_para_reposicao": days_to_reorder,
                "data_prevista_ruptura": stockout_date,
                "data_sugerida_pedido": reorder_date,
                "janelas_30d": len(rolling_buckets),
                "primeira_retirada": first_withdrawal_at.strftime("%d/%m/%Y"),
                "confianca_modelo": "Alta" if len(rolling_buckets) >= 6 else "Média" if len(rolling_buckets) >= 3 else "Insuficiente",
                "historico_suficiente": enough_history,
            }
        )

    material_forecasts.sort(
        key=lambda item: (
            0 if item.get("historico_suficiente") else 1,
            -item.get("prob_ruptura_30d", 0),
            item.get("dias_para_ruptura") if item.get("dias_para_ruptura") is not None else float("inf"),
            -item.get("media_30d", 0),
        )
    )

    eligible_material_forecasts = [item for item in material_forecasts if item.get("historico_suficiente")]
    top_risk_material = eligible_material_forecasts[0] if eligible_material_forecasts else None

    rolling_30d_materials = []
    if all_material_withdrawals:
        overall_first_withdrawal = min(event_dt for event_dt, _ in all_material_withdrawals)
        rolling_30d_materials = _build_sequential_buckets(
            all_material_withdrawals,
            all_material_returns,
            overall_first_withdrawal,
            now_utc,
            30,
        )

    monthly_materials = _build_monthly_buckets(all_material_withdrawals, all_material_returns)
    rolling_30d_materials_display = rolling_30d_materials[-12:]
    monthly_materials_display = monthly_materials[-12:]
    risk_chart_items = [item for item in eligible_material_forecasts if item.get("prob_ruptura_30d", 0) > 0][:8]
    forecast_audit = {
        "materiais_com_historico": len(material_forecasts),
        "materiais_elegiveis": len(eligible_material_forecasts),
        "materiais_com_risco": len(risk_chart_items),
        "janelas_30d_gerais": len(rolling_30d_materials),
        "meses_gerais": len(monthly_materials),
    }

    chart_data = {
        "overall": {
            "labels": [
                "Retiradas de Materiais",
                "Retiradas de Ferramentas",
                "Devolucoes de Materiais",
                "Devolucoes de Ferramentas",
            ],
            "values": [
                int(total_materiais_retiradas),
                int(total_ferramentas_retiradas),
                int(total_materiais_devolucoes),
                int(total_ferramentas_devolucoes),
            ],
        },
        "employees_materials": _build_pie(materiais_emps_list, sum(e.get("movimentos", 0) for e in materiais_emps_list), "nome", "movimentos"),
        "employees_tools": _build_pie(ferramentas_emps_list, sum(e.get("movimentos", 0) for e in ferramentas_emps_list), "nome", "movimentos"),
        "items_materials": _build_pie(materiais_itens_list, total_materiais_retiradas, "descricao", "retiradas_count"),
        "items_tools": _build_pie(ferramentas_itens_list, total_ferramentas_retiradas, "descricao", "retiradas_count"),
        "materials_30d": {
            "labels": [bucket["label"] for bucket in rolling_30d_materials_display],
            "withdrawals_qty": [round(bucket["withdrawals_qty"], 2) for bucket in rolling_30d_materials_display],
            "returns_qty": [round(bucket["returns_qty"], 2) for bucket in rolling_30d_materials_display],
            "net_qty": [round(bucket["net_qty"], 2) for bucket in rolling_30d_materials_display],
            "movements_count": [int(bucket["movements_count"]) for bucket in rolling_30d_materials_display],
        },
        "materials_monthly": {
            "labels": [bucket["label"] for bucket in monthly_materials_display],
            "withdrawals_qty": [round(bucket["withdrawals_qty"], 2) for bucket in monthly_materials_display],
            "returns_qty": [round(bucket["returns_qty"], 2) for bucket in monthly_materials_display],
            "net_qty": [round(bucket["net_qty"], 2) for bucket in monthly_materials_display],
            "movements_count": [int(bucket["movements_count"]) for bucket in monthly_materials_display],
        },
        "stockout_risk": {
            "labels": [item["descricao"][:38] for item in risk_chart_items],
            "values": [round(item["prob_ruptura_30d"] * 100, 2) for item in risk_chart_items],
        },
    }

    summary = {
        "materiais": {
            "retiradas_count": int(total_materiais_retiradas),
            "retiradas_qty": float(total_materiais_qtd),
            "devolucoes_count": int(total_materiais_devolucoes),
            "devolucoes_qty": float(total_materiais_devolucoes_qtd),
            "janelas_30d": len(rolling_30d_materials),
            "meses": len(monthly_materials),
            "itens_auditados": len(material_forecasts),
            "itens_elegiveis": len(eligible_material_forecasts),
        },
        "ferramentas": {
            "retiradas_count": int(total_ferramentas_retiradas),
            "retiradas_qty": float(total_ferramentas_qtd),
            "devolucoes_count": int(total_ferramentas_devolucoes),
            "devolucoes_qty": float(total_ferramentas_devolucoes_qtd),
        },
    }

    return render_template(
        "reports/percentual_movimentos.html",
        summary=summary,
        chart_data=chart_data,
        materiais_emps=materiais_emps_list,
        ferramentas_emps=ferramentas_emps_list,
        materiais_itens=materiais_itens_list,
        ferramentas_itens=ferramentas_itens_list,
        material_forecasts=material_forecasts,
        top_risk_material=top_risk_material,
        forecast_audit=forecast_audit,
        gerado_em=TimeService.now_local().strftime("%d/%m/%Y %H:%M"),
    )


@bp.route("/download/<path:filename>")
@login_required
def download(filename: str):
    """Baixa um relatório específico."""
    from flask import current_app
    
    # Validar nome do arquivo para evitar path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        abort(400, "Nome de arquivo inválido")
    
    reports_dir = Path(current_app.instance_path) / "reports"
    file_path = reports_dir / filename
    
    if not file_path.exists() or not file_path.is_file():
        abort(404, "Relatório não encontrado")
    
    ext = file_path.suffix.lower()
    if ext != ".pdf":
        abort(404, "Somente relatórios PDF estão disponíveis.")
    
    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@bp.route("/delete/<path:filename>", methods=["POST"])
@login_required
def delete(filename: str):
    """Deleta um relatório específico (apenas admin)."""
    from flask import current_app, flash, redirect, url_for
    from flask_login import current_user
    
    # Verificar permissão de admin
    if not bool(getattr(current_user, "is_admin", 0)):
        flash("Apenas administradores podem deletar relatórios.", "danger")
        return redirect(url_for("reports.index"))
    
    # Validar nome do arquivo
    if ".." in filename or "/" in filename or "\\" in filename:
        flash("Nome de arquivo inválido.", "danger")
        return redirect(url_for("reports.index"))
    
    reports_dir = Path(current_app.instance_path) / "reports"
    file_path = reports_dir / filename
    
    if not file_path.exists():
        flash("Relatório não encontrado.", "warning")
        return redirect(url_for("reports.index"))
    
    try:
        file_path.unlink()
        flash(f"Relatório '{filename}' deletado com sucesso.", "success")
    except Exception as e:
        logger.error(f"Erro ao deletar relatório {filename}: {e}")
        flash(f"Erro ao deletar relatório: {str(e)}", "danger")
    
    return redirect(url_for("reports.index"))


@bp.route("/gerar", methods=["POST"])
@login_required
def gerar_relatorio():
    """Gera relatório customizado com base nos filtros de data."""
    from flask import current_app, flash, redirect, url_for
    from ..models import Saida, Item, Usuario
    from ..extensions import db
    from ..utils.time_service import TimeService
    
    # Obter parâmetros do formulário
    date_from_str = request.form.get("date_from", "").strip()
    date_to_str = request.form.get("date_to", "").strip()
    report_type = request.form.get("type", "saidas").strip()
    requested_format = request.form.get("format", "pdf").strip().lower()
    
    # Validar formato
    if requested_format not in ["pdf", "xlsx", "jpeg", "jpg"]:
        flash("Formato inválido. Use PDF.", "danger")
        return redirect(url_for("reports.index"))
    if requested_format in {"xlsx", "jpeg", "jpg"}:
        flash("Os relatórios agora são gerados somente em PDF. O arquivo foi salvo em PDF.", "info")
    
    # Converter datas
    try:
        if date_from_str:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d")
        else:
            date_from = datetime.utcnow() - timedelta(days=30)  # Últimos 30 dias por padrão
        
        if date_to_str:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d")
            date_to = date_to.replace(hour=23, minute=59, second=59)  # Fim do dia
        else:
            date_to = datetime.utcnow()
    except ValueError:
        flash("Formato de data inválido. Use DD/MM/AAAA.", "danger")
        return redirect(url_for("reports.index"))
    
    # Validar intervalo de datas
    if date_from > date_to:
        flash("Data início deve ser anterior à data fim.", "danger")
        return redirect(url_for("reports.index"))
    
    # Buscar dados de acordo com o tipo de relatório
    try:
        if report_type == "saidas":
            # Relatório de saídas
            query = db.session.query(
                Saida.id_saida,
                Saida.quantidade,
                Saida.data_saida,
                Saida.observacao,
                Saida.local_servico,
                Saida.codigo_item,
                Saida.matricula,
                Item.descricao.label("item_descricao"),
                Item.categoria.label("item_categoria"),
                Item.marca.label("item_marca"),
                Usuario.nome.label("usuario_nome"),
            ).join(
                Item, Saida.codigo_item == Item.codigo_item, isouter=True
            ).join(
                Usuario, Saida.matricula == Usuario.matricula, isouter=True
            ).filter(
                Saida.data_saida >= date_from,
                Saida.data_saida <= date_to
            ).order_by(Saida.data_saida.desc())
            
            results = query.all()
            
            if not results:
                flash("Nenhuma saída encontrada no período selecionado.", "warning")
                return redirect(url_for("reports.index"))
            
            # Gerar arquivo
            reports_dir = Path(current_app.instance_path) / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
            period_label = f"{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}"

            pdf_bytes = _generate_custom_report_pdf(
                results=results,
                date_from=date_from,
                date_to=date_to,
                report_type=report_type,
                time_service=TimeService,
            )

            pdf_filename = f"relatorio_saidas_{period_label}_{timestamp}.pdf"
            pdf_path = reports_dir / pdf_filename

            with open(pdf_path, "wb") as pdf_file:
                pdf_file.write(pdf_bytes)

            flash(f"Relatório gerado com sucesso: {pdf_filename}", "success")
            return redirect(url_for("reports.index"))
        
        else:
            flash("Tipo de relatório não implementado ainda.", "warning")
            return redirect(url_for("reports.index"))
    
    except Exception as e:
        logger.error(f"Erro ao gerar relatório: {e}")
        flash(f"Erro ao gerar relatório: {str(e)}", "danger")
        return redirect(url_for("reports.index"))


def _redirect_to_general_search(*, scope: str, query: str | None = None, period: int | None = None, selected_date: str | None = None):
    redirect_kwargs: dict[str, object] = {
        "open_general_search": "1",
        "general_scope": scope,
    }
    normalized_query = str(query or "").strip()
    if normalized_query:
        redirect_kwargs["general_query"] = normalized_query
    if period is not None:
        redirect_kwargs["general_period"] = int(period)
    normalized_date = str(selected_date or "").strip()
    if normalized_date:
        redirect_kwargs["general_date"] = normalized_date

    flash("A consulta foi incorporada a Pesquisa geral da barra superior.", "info")
    return redirect(url_for("reports.index", **redirect_kwargs))


@bp.route("/api/pesquisa-geral/sugestoes")
@login_required
def general_search_suggestions_api():
    scope = (request.args.get("scope") or "funcionario").strip().lower()
    query = (request.args.get("q") or "").strip()

    if scope == "funcionario":
        results = general_search_service.search_employees(query)
    elif scope == "item":
        results = general_search_service.search_items(query)
    else:
        return jsonify({"success": False, "message": "Escopo de sugestao invalido."}), 400

    return jsonify({
        "success": True,
        "scope": scope,
        "results": results,
    })


@bp.route("/api/pesquisa-geral/funcionario/<matricula>")
@login_required
def general_search_employee_api(matricula: str):
    try:
        payload = general_search_service.build_employee_payload(matricula)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404

    return jsonify({"success": True, **payload})


@bp.route("/api/pesquisa-geral/item/<codigo_item>")
@login_required
def general_search_item_api(codigo_item: str):
    period_days = _parse_period_days_arg(request.args.get("period", "0"))
    if period_days not in [0, 7, 30, 90, 180, 365]:
        period_days = 0

    try:
        payload = general_search_service.build_item_payload(codigo_item, period_days=period_days)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404

    return jsonify({"success": True, **payload})


@bp.route("/api/pesquisa-geral/diario")
@login_required
def general_search_daily_api():
    raw_date = (request.args.get("date") or "").strip()
    selected_date = TimeService.now_local().date()
    if raw_date:
        try:
            selected_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "message": "Data invalida informada."}), 400

    payload = general_search_service.build_daily_payload(
        selected_date=selected_date,
        search_term=(request.args.get("search") or "").strip(),
    )
    return jsonify({"success": True, **payload})


@bp.route("/by-item")
@login_required
def by_item():
    """Alias legado da Pesquisa geral para item ou funcionario."""
    search_type = (request.args.get("type") or "item").strip().lower()
    search_term = (request.args.get("search") or "").strip()
    period_days = _parse_period_days_arg(request.args.get("period", "0"))
    if period_days not in [0, 7, 30, 90, 180, 365]:
        period_days = 0

    target_scope = "funcionario" if search_type == "usuario" else "item"
    redirect_period = None if target_scope == "funcionario" else period_days
    return _redirect_to_general_search(scope=target_scope, query=search_term, period=redirect_period)


@bp.route("/by-item-day")
@login_required
def by_item_day():
    """Alias legado da Pesquisa geral para a visao diaria agrupada."""
    selected_date_raw = (request.args.get("date") or "").strip()
    selected_date = TimeService.now_local().date().isoformat()
    if selected_date_raw:
        try:
            selected_date = datetime.strptime(selected_date_raw, "%Y-%m-%d").date().isoformat()
        except ValueError:
            flash("Data invalida informada. Exibindo o dia atual.", "warning")

    return _redirect_to_general_search(
        scope="diario",
        query=(request.args.get("search") or "").strip(),
        selected_date=selected_date,
    )


@bp.route("/by_item_download")
@login_required
def by_item_download():
    """Download do relatório por item ou funcionário em PDF."""
    from flask import current_app
    from ..models import Item, Saida, Usuario, InventarioEvento
    from ..extensions import db
    from ..utils.time_service import TimeService
    from datetime import datetime, timedelta
    
    search_term = request.args.get("search", "").strip()
    search_type = request.args.get("type", "item").strip().lower()
    # Por padrão, ao baixar relatório de usuário, usar TODO o histórico
    if search_type == "usuario":
        period_days = 0  # Sempre histórico completo para usuários
    else:
        period_days = _parse_period_days_arg(request.args.get("period", "0"))
        if period_days not in [7, 30, 90, 180, 365, 0]:
            period_days = 0
    requested_format = (request.args.get("format") or "pdf").strip().lower()
    if requested_format not in {"pdf", "xlsx", "jpeg", "jpg"}:
        abort(400, "Formato inválido. Use pdf.")
    
    if not search_term:
        abort(400, "Termo de busca não fornecido")
    
    item_info = None
    usuario_info = None
    saidas = []
    
    if search_type == "usuario":
        # Buscar por funcionário
        usuario = Usuario.query.filter(
            db.or_(
                Usuario.nome.ilike(f"%{search_term}%"),
                Usuario.matricula.ilike(f"%{search_term}%")
            )
        ).first()
        
        if not usuario:
            abort(404, "Funcionário não encontrado")
        
        usuario_info = {
            "matricula": usuario.matricula,
            "nome": usuario.nome,
            "cargo": usuario.setor if usuario.setor else (usuario.cargo if usuario.cargo else "N/D"),
        }
        
        # Buscar saídas do funcionário com informações do item
        query = db.session.query(
            Saida.quantidade,
            Saida.data_saida,
            Saida.observacao,
            Saida.local_servico,
            Saida.codigo_item,
            Item.descricao.label("item_descricao"),
            Item.categoria.label("item_categoria"),
            Item.marca.label("item_marca"),
        ).join(
            Item, Saida.codigo_item == Item.codigo_item, isouter=True
        ).filter(
            Saida.matricula == usuario.matricula
        )
        
        cutoff = None
        # Filtro de periodo removido para usuarios
        # if period_days > 0:
        #    cutoff = datetime.utcnow() - timedelta(days=period_days)
        #    query = query.filter(Saida.data_saida >= cutoff)
        
        query = query.order_by(Saida.data_saida.desc())
        saidas = query.all()

        movimentos = []
        for saida in saidas:
            movimentos.append({
                "data": saida.data_saida,
                "quantidade": saida.quantidade,
                "observacao": saida.observacao or "",
                "local_servico": saida.local_servico or "",
                "codigo_item": saida.codigo_item,
                "item_descricao": saida.item_descricao or "Item removido",
                "item_categoria": saida.item_categoria or "N/D",
                "item_marca": saida.item_marca or "N/D",
                "periodo": TimeService.get_business_day_tag(saida.data_saida),
                "tipo": "Retirada",
            })

        devolucoes_query = db.session.query(
            InventarioEvento.quantidade,
            InventarioEvento.data_evento,
            InventarioEvento.descricao,
            InventarioEvento.codigo_item,
            Item.descricao.label("item_descricao"),
            Item.categoria.label("item_categoria"),
            Item.marca.label("item_marca"),
        ).join(
            Item, InventarioEvento.codigo_item == Item.codigo_item, isouter=True
        ).filter(
            InventarioEvento.matricula == usuario.matricula,
            InventarioEvento.tipo.in_(["devolucao_ferramenta", "devolucao_material"]),
        )
        if cutoff is not None:
            devolucoes_query = devolucoes_query.filter(InventarioEvento.data_evento >= cutoff)

        devolucoes = devolucoes_query.all()
        for devolucao in devolucoes:
            movimentos.append({
                "data": devolucao.data_evento,
                "quantidade": devolucao.quantidade,
                "observacao": devolucao.descricao or "",
                "local_servico": "",
                "codigo_item": devolucao.codigo_item,
                "item_descricao": devolucao.item_descricao or "Item removido",
                "item_categoria": devolucao.item_categoria or "N/D",
                "item_marca": devolucao.item_marca or "N/D",
                "periodo": TimeService.get_business_day_tag(devolucao.data_evento),
                "tipo": "Devolução",
            })

        movimentos.sort(key=lambda mov: mov["data"] or datetime.min, reverse=True)
        saidas = movimentos
        
    else:
        # Buscar por item (comportamento original)
        # Primeiro tenta busca direta
        item = Item.query.filter(
            db.or_(
                Item.descricao.ilike(f"%{search_term}%"),
                Item.codigo_item.ilike(f"%{search_term}%")
            )
        ).first()
        
        # Se não encontrar, tenta busca normalizada (sem acentos)
        if not item:
            search_normalized = _normalize_search(search_term)
            todos_itens = Item.query.all()
            for it in todos_itens:
                desc_normalized = _normalize_search(it.descricao or "")
                if search_normalized.lower() in desc_normalized.lower():
                    item = it
                    break
                if search_normalized.lower() in (it.codigo_item or "").lower():
                    item = it
                    break
        
        if not item:
            abort(404, "Item não encontrado")
        
        item_info = {
            "codigo": item.codigo_item,
            "descricao": item.descricao,
            "categoria": item.categoria or "N/D",
            "marca": item.marca or "N/D",
        }

        # Buscar saídas do item
        query = db.session.query(
            Saida.quantidade,
            Saida.data_saida,
            Saida.observacao,
            Saida.local_servico,
            Saida.matricula.label("saida_matricula"),
            Usuario.nome.label("usuario_nome"),
        ).join(
            Usuario, Saida.matricula == Usuario.matricula, isouter=True
        ).filter(
            Saida.codigo_item == item.codigo_item
        )
        
        if period_days > 0:
            cutoff = datetime.utcnow() - timedelta(days=period_days)
            query = query.filter(Saida.data_saida >= cutoff)
        
        query = query.order_by(Saida.data_saida.desc())
        saidas = query.all()
    
    reports_dir = Path(current_app.instance_path) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
    
    if search_type == "usuario":
        safe_filename = "".join(c for c in usuario_info['matricula'] if c.isalnum() or c in ('-', '_'))
        pdf_bytes = _generate_usuario_report_pdf(
            usuario=usuario_info,
            saidas=saidas,
            period_days=period_days,
            time_service=TimeService,
        )
        pdf_filename = f"relatorio_funcionario_{safe_filename}_{timestamp}.pdf"
    else:
        safe_filename = "".join(c for c in item_info['codigo'] if c.isalnum() or c in ('-', '_'))
        pdf_bytes = _generate_item_report_pdf(
            item=item_info,
            saidas=saidas,
            period_days=period_days,
            time_service=TimeService,
        )
        pdf_filename = f"relatorio_item_{safe_filename}_{timestamp}.pdf"

    pdf_path = reports_dir / pdf_filename
    with open(pdf_path, "wb") as pdf_file:
        pdf_file.write(pdf_bytes)

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=pdf_filename,
    )
