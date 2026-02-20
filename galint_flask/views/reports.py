"""Views para gerenciamento e histórico de relatórios."""
from __future__ import annotations

import logging
import os
from io import BytesIO
from datetime import datetime
import unicodedata
from pathlib import Path

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from galint_flask.utils.time_service import TimeService

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
    
    from datetime import datetime
    gerado_em = datetime.now().strftime('%d/%m/%Y %H:%M')
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
        dias_validade = (item_data_validade - datetime.now().date()).days
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
    from datetime import datetime
    story.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))
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
    
    from datetime import datetime
    gerado_em = datetime.now().strftime('%d/%m/%Y %H:%M')
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
    - estoque_baixo_<timestamp>.xlsx
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
        if item.is_file() and item.suffix.lower() in [".pdf", ".xlsx", ".jpeg", ".jpg"]:
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
                    info["date"] = datetime.fromtimestamp(item.stat().st_mtime)
                except Exception:
                    info["date"] = datetime.now()
            
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
                info_format = info["format"].lower()
                if target_format == "jpeg":
                    if info_format not in {"jpeg", "jpg"}:
                        continue
                elif info_format != target_format:
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
    
    # Obter filtros da query string
    filters = {
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
        "type": request.args.get("type"),
        "format": request.args.get("format"),
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
        "xlsx_count": sum(1 for r in reports if r["format"] == "XLSX"),
        "jpeg_count": sum(1 for r in reports if r["format"] in ["JPEG", "JPG"]),
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
    
    # Determinar mimetype
    ext = file_path.suffix.lower()
    mimetype_map = {
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
    }
    
    mimetype = mimetype_map.get(ext, "application/octet-stream")
    
    return send_file(
        file_path,
        mimetype=mimetype,
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
    if not hasattr(current_user, "tipo") or current_user.tipo != "admin":
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
    format_type = request.form.get("format", "pdf").strip().lower()
    
    # Validar formato
    if format_type not in ["pdf", "xlsx", "jpeg"]:
        flash("Formato inválido. Use PDF, XLSX ou JPEG.", "danger")
        return redirect(url_for("reports.index"))
    
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
            
            if format_type == "xlsx":
                from openpyxl import Workbook
                from openpyxl.styles import Font, PatternFill, Alignment
                
                wb = Workbook()
                ws = wb.active
                ws.title = "Saídas"

                # Cabeçalho (título + empresa)
                from ..utils.report_branding import get_company_header_lines

                ws.append(["RELATÓRIO DE SAÍDAS - PERÍODO CUSTOMIZADO"])
                for line in get_company_header_lines():
                    ws.append([line])
                ws.append([f"Período: {date_from.strftime('%d/%m/%Y')} a {date_to.strftime('%d/%m/%Y')}"])
                ws.append([f"Total de registros: {len(results)}"])
                ws.append([])
                
                # Estilos
                header_fill = PatternFill(start_color="1f2937", end_color="1f2937", fill_type="solid")
                header_font = Font(color="FFFFFF", bold=True)
                
                # Cabeçalhos das colunas
                headers = ["Data", "Hora", "Funcionário", "Matrícula", "Item", "Categoria", "Qtd.", "Local"]

                header_row_index = ws.max_row + 1
                ws.append(headers)

                for cell in ws[header_row_index]:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal="center")
                
                # Dados
                for row in results:
                    # Mesclar local e observação
                    local_info = row.local_servico or "N/D"
                    if row.observacao and row.observacao.strip():
                        local_info = f"{local_info} | {row.observacao[:100]}"
                    
                    ws.append([
                        TimeService.format_local(row.data_saida, "%d/%m/%Y"),
                        TimeService.format_local(row.data_saida, "%H:%M"),
                        row.usuario_nome or "N/D",
                        row.matricula or "N/D",
                        row.item_descricao or "Item removido",
                        row.item_categoria or "N/D",
                        row.quantidade,
                        local_info[:200],
                    ])
                
                # Ajustar larguras
                ws.column_dimensions["A"].width = 12
                ws.column_dimensions["B"].width = 8
                ws.column_dimensions["C"].width = 30
                ws.column_dimensions["D"].width = 12
                ws.column_dimensions["E"].width = 40
                ws.column_dimensions["F"].width = 18
                ws.column_dimensions["G"].width = 8
                ws.column_dimensions["H"].width = 60
                
                filename = f"relatorio_saidas_{period_label}_{timestamp}.xlsx"
                filepath = reports_dir / filename
                wb.save(str(filepath))
                
                flash(f"Relatório gerado com sucesso: {filename}", "success")
                return redirect(url_for("reports.index"))
            
            elif format_type in ["pdf", "jpeg"]:
                # Gerar PDF
                pdf_bytes = _generate_custom_report_pdf(
                    results=results,
                    date_from=date_from,
                    date_to=date_to,
                    report_type=report_type,
                    time_service=TimeService
                )
                
                pdf_filename = f"relatorio_saidas_{period_label}_{timestamp}.pdf"
                pdf_path = reports_dir / pdf_filename
                
                with open(pdf_path, "wb") as pdf_file:
                    pdf_file.write(pdf_bytes)
                
                if format_type == "jpeg":
                    jpeg_filename = f"relatorio_saidas_{period_label}_{timestamp}.jpeg"
                    jpeg_path = reports_dir / jpeg_filename
                    _convert_pdf_to_jpeg(str(pdf_path), str(jpeg_path))
                    flash(f"Relatório gerado com sucesso: {jpeg_filename}", "success")
                else:
                    flash(f"Relatório gerado com sucesso: {pdf_filename}", "success")
                
                return redirect(url_for("reports.index"))
        
        else:
            flash("Tipo de relatório não implementado ainda.", "warning")
            return redirect(url_for("reports.index"))
    
    except Exception as e:
        logger.error(f"Erro ao gerar relatório: {e}")
        flash(f"Erro ao gerar relatório: {str(e)}", "danger")
        return redirect(url_for("reports.index"))


@bp.route("/by-item")
@login_required
def by_item():
    """Página de relatório por item específico ou por funcionário."""
    from flask import current_app
    from ..models import Item
    
    # Buscar termo e tipo de busca
    search_term = request.args.get("search", "").strip()
    search_type = request.args.get("type", "item").strip().lower()  # "item" ou "usuario"
    # Por padrão, ao buscar usuário, mostrar TODO o histórico (desde a primeira retirada)
    # Para itens, permitir filtro de período
    if search_type == "usuario":
        period_days = 0  # Sempre mostrar histórico completo para usuários
    else:
        period_days = int(request.args.get("period", "0"))
        if period_days not in [7, 30, 90, 180, 365, 0]:  # 0 = todo histórico
            period_days = 0
    
    results = []
    item_info = None
    usuario_info = None
    today_withdrawals = []
    today_label = None
    
    if search_term:
        from datetime import datetime, timedelta, timezone
        from ..models import Saida, Usuario, InventarioEvento
        from ..extensions import db
        from ..utils.time_service import TimeService
        
        if search_type == "usuario":
            # Buscar por funcionário (nome ou matrícula)
            usuario = Usuario.query.filter(
                db.or_(
                    Usuario.nome.ilike(f"%{search_term}%"),
                    Usuario.matricula.ilike(f"%{search_term}%")
                )
            ).first()
            
            if usuario:
                usuario_info = {
                    "matricula": usuario.matricula,
                    "nome": usuario.nome,
                    "cargo": usuario.setor if usuario.setor else (usuario.cargo if usuario.cargo else "N/D"),
                }

                # Checklist: itens retirados hoje (hora local)
                local_now = TimeService.now_local()
                local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
                local_end = local_start + timedelta(days=1)
                start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
                end_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)
                today_label = local_start.strftime("%d/%m/%Y")

                today_rows = (
                    db.session.query(
                        Saida.codigo_item,
                        Item.descricao.label("item_descricao"),
                        db.func.sum(Saida.quantidade).label("total_quantidade"),
                    )
                    .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
                    .filter(
                        Saida.matricula == usuario.matricula,
                        Saida.data_saida >= start_utc,
                        Saida.data_saida < end_utc,
                    )
                    .group_by(Saida.codigo_item, Item.descricao)
                    .order_by(Item.descricao.asc())
                    .all()
                )

                for row in today_rows:
                    today_withdrawals.append(
                        {
                            "codigo_item": row.codigo_item,
                            "item_codigo": _format_codigo_barra(row.codigo_item),
                            "item_descricao": row.item_descricao or "Item removido",
                            "quantidade": float(row.total_quantidade or 0),
                        }
                    )
                
                # Buscar todas as saídas deste usuário
                query = db.session.query(
                    Saida.id_saida,
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
                # Filtro de periodo removido para usuarios para garantir historico completo
                # if period_days > 0:
                #     cutoff = datetime.utcnow() - timedelta(days=period_days)
                #     query = query.filter(Saida.data_saida >= cutoff)
                
                query = query.order_by(Saida.data_saida.desc())
                
                saidas = query.all()
                movimentos = []
                
                for saida in saidas:
                    business_tag = TimeService.get_business_day_tag(saida.data_saida)
                    movimentos.append({
                        "id": f"saida_{saida.id_saida}",
                        "quantidade": saida.quantidade,
                        "data": saida.data_saida,
                        "data_formatada": TimeService.format_local(saida.data_saida, "%d/%m/%Y"),
                        "hora_formatada": TimeService.format_local(saida.data_saida, "%H:%M"),
                        "observacao": saida.observacao or "",
                        "local_servico": saida.local_servico or "",
                        "codigo_item": saida.codigo_item,
                        "item_codigo": _format_codigo_barra(saida.codigo_item),
                        "item_descricao": saida.item_descricao or "Item removido",
                        "item_categoria": saida.item_categoria or "N/D",
                        "item_marca": saida.item_marca or "N/D",
                        "periodo": business_tag,
                        "tipo": "Retirada",
                    })

                devolucoes_query = db.session.query(
                    InventarioEvento.id_evento,
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
                    business_tag = TimeService.get_business_day_tag(devolucao.data_evento)
                    movimentos.append({
                        "id": f"devolucao_{devolucao.id_evento}",
                        "quantidade": devolucao.quantidade,
                        "data": devolucao.data_evento,
                        "data_formatada": TimeService.format_local(devolucao.data_evento, "%d/%m/%Y"),
                        "hora_formatada": TimeService.format_local(devolucao.data_evento, "%H:%M"),
                        "observacao": devolucao.descricao or "",
                        "local_servico": "",
                        "codigo_item": devolucao.codigo_item,
                        "item_codigo": _format_codigo_barra(devolucao.codigo_item),
                        "item_descricao": devolucao.item_descricao or "Item removido",
                        "item_categoria": devolucao.item_categoria or "N/D",
                        "item_marca": devolucao.item_marca or "N/D",
                        "periodo": business_tag,
                        "tipo": "Devolução",
                    })

                movimentos.sort(key=lambda mov: mov["data"] or datetime.min, reverse=True)
                results.extend(movimentos)
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
                flash("Item não encontrado.", "warning")
                return render_template(
                    "reports/by_item.html",
                    search_term=search_term,
                    search_type=search_type,
                    period_days=period_days,
                    item_info=None,
                    usuario_info=None,
                    results=[],
                    total_quantidade=0,
                )

            item_info = {
                "codigo": item.codigo_item,
                "descricao": item.descricao,
                "categoria": item.categoria,
                "marca": item.marca,
                "saldo_atual": item.get_saldo_atual(),
            }
            
            # Buscar todas as saídas deste item
            query = db.session.query(
                Saida.id_saida,
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
            
            # Aplicar filtro de período
            if period_days > 0:
                cutoff = datetime.utcnow() - timedelta(days=period_days)
                query = query.filter(Saida.data_saida >= cutoff)
            
            query = query.order_by(Saida.data_saida.desc())
            
            saidas = query.all()
            
            for saida in saidas:
                business_tag = TimeService.get_business_day_tag(saida.data_saida)
                results.append({
                    "id": saida.id_saida,
                    "quantidade": saida.quantidade,
                    "data": saida.data_saida,
                    "data_formatada": TimeService.format_local(saida.data_saida, "%d/%m/%Y"),
                    "hora_formatada": TimeService.format_local(saida.data_saida, "%H:%M"),
                    "observacao": saida.observacao or "",
                    "local_servico": saida.local_servico or "",
                    "usuario_nome": saida.usuario_nome or (f"Matrícula {saida.saida_matricula}" if saida.saida_matricula else "N/D"),
                    "usuario_matricula": saida.saida_matricula or "N/D",
                    "periodo": business_tag,
                    # Para compatibilidade quando busca por item
                    "codigo_item": item.codigo_item,
                    "item_descricao": item.descricao,
                    "item_codigo": item.codigo_item,
                })
    
    return render_template(
        "reports/by_item.html",
        search_term=search_term,
        search_type=search_type,
        period_days=period_days,
        item_info=item_info,
        usuario_info=usuario_info,
        results=results,
        total_quantidade=sum(r["quantidade"] for r in results),
        today_withdrawals=today_withdrawals,
        today_label=today_label,
    )


@bp.route("/by_item_download")
@login_required
def by_item_download():
    """Download do relatório por item ou funcionário em XLSX, PDF ou JPEG"""
    from flask import current_app
    from ..models import Item, Saida, Usuario, InventarioEvento
    from ..extensions import db
    from ..utils.time_service import TimeService
    from datetime import datetime, timedelta
    import tempfile
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    
    search_term = request.args.get("search", "").strip()
    search_type = request.args.get("type", "item").strip().lower()
    # Por padrão, ao baixar relatório de usuário, usar TODO o histórico
    if search_type == "usuario":
        period_days = 0  # Sempre histórico completo para usuários
    else:
        period_days = int(request.args.get("period", "0"))
    format_type = request.args.get("format", "xlsx").lower()
    
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
    
    # Gerar XLSX
    wb = Workbook()
    ws = wb.active
    
    if search_type == "usuario":
        ws.title = "Relatório por Funcionário"

        # Cabeçalho (título + empresa)
        from ..utils.report_branding import get_company_header_lines

        ws["A1"] = "RELATÓRIO DE RETIRADAS E DEVOLUÇÕES POR FUNCIONÁRIO"
        ws["A1"].font = Font(bold=True, size=14)

        company_lines = get_company_header_lines()
        row = 2
        for line in company_lines:
            ws[f"A{row}"] = line
            row += 1
        row += 1

        ws[f"A{row}"] = f"Funcionário: {usuario_info['nome']}"
        ws[f"A{row + 1}"] = f"Matrícula: {usuario_info['matricula']}"
        ws[f"A{row + 2}"] = f"Cargo: {usuario_info['cargo']}"
        ws[f"A{row + 4}"] = "Período: Todo histórico (inclui retiradas e devoluções)"
        ws[f"A{row + 5}"] = f"Total de movimentações: {len(saidas)}"
        ws[f"A{row + 6}"] = (
            "Quantidade total movimentada: "
            f"{sum((s.get('quantidade', 0) if isinstance(s, dict) else s.quantidade) for s in saidas)}"
        )
        
        # Cabeçalhos da tabela
        headers = ["Data", "Hora", "Item", "Código", "Quantidade", "Tipo", "Período", "Local"]
        ws.append([""])
        ws.append([""])
        ws.append(headers)
        
    else:
        ws.title = "Relatório por Item"

        # Cabeçalho (título + empresa)
        from ..utils.report_branding import get_company_header_lines

        ws["A1"] = "RELATÓRIO DE RETIRADAS POR ITEM"
        ws["A1"].font = Font(bold=True, size=14)

        company_lines = get_company_header_lines()
        row = 2
        for line in company_lines:
            ws[f"A{row}"] = line
            row += 1
        row += 1

        ws[f"A{row}"] = f"Item: {item_info['descricao']}"
        ws[f"A{row + 1}"] = f"Código: {item_info['codigo']}"
        ws[f"A{row + 2}"] = f"Categoria: {item_info['categoria']}"
        ws[f"A{row + 3}"] = f"Marca: {item_info['marca']}"

        # Adicionar informações de rastreabilidade
        current_row = row + 4
        if hasattr(item, 'lote') and item.lote:
            ws[f"A{current_row}"] = f"Lote: {item.lote}"
            current_row += 1
        if hasattr(item, 'data_entrada') and item.data_entrada:
            ws[f"A{current_row}"] = f"Data de Entrada: {TimeService.format_local(item.data_entrada, '%d/%m/%Y')}"
            current_row += 1
        if hasattr(item, 'data_validade') and item.data_validade:
            from datetime import datetime
            dias_validade = (item.data_validade - datetime.now().date()).days
            ws[f"A{current_row}"] = f"Validade: {item.data_validade.strftime('%d/%m/%Y')} ({dias_validade} dias)"
            current_row += 1
        
        ws[f"A{current_row}"] = f"Período: {period_days} dias" if period_days > 0 else "Período: Todo histórico"
        current_row += 1
        ws[f"A{current_row}"] = f"Total de retiradas: {len(saidas)}"
        current_row += 1
        ws[f"A{current_row}"] = f"Quantidade total retirada: {sum(s.quantidade for s in saidas)}"
        
        # Cabeçalhos da tabela
        headers = ["Data", "Horário", "Usuário", "Matrícula", "Quantidade", "Período", "Local"]
        ws.append([""])
        ws.append(headers)
    
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="0066CC", end_color="0066CC", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    
    header_row = ws.max_row
    for cell in ws[header_row]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = border
    
    # Dados
    for saida in saidas:
        if search_type == "usuario":
            data_saida = saida.get("data")
            business_tag = saida.get("periodo") or TimeService.get_business_day_tag(data_saida)
            # Mostrar apenas os 4 últimos dígitos do código de barras
            codigo_item = saida.get("codigo_item")
            codigo_display = codigo_item[-4:] if codigo_item and len(codigo_item) >= 4 else (codigo_item or "N/D")
            
            ws.append([
                TimeService.format_local(data_saida, "%d/%m/%Y"),
                TimeService.format_local(data_saida, "%H:%M"),
                saida.get("item_descricao") or "Item removido",
                codigo_display,
                saida.get("quantidade"),
                saida.get("tipo") or "Retirada",
                business_tag,
                ((f"{(saida.get('local_servico') or 'N/D')} | {(saida.get('observacao') or '').strip()}" if (saida.get('observacao') or '').strip() else (saida.get('local_servico') or 'N/D'))[:150]),
            ])
        else:
            business_tag = TimeService.get_business_day_tag(saida.data_saida)
            # Para relatório de item, também truncar o código se necessário no futuro
            local_info = saida.local_servico or "N/D"
            if saida.observacao and saida.observacao.strip():
                local_info = f"{local_info} | {saida.observacao.strip()}"
            ws.append([
                TimeService.format_local(saida.data_saida, "%d/%m/%Y"),
                TimeService.format_local(saida.data_saida, "%H:%M"),
                saida.usuario_nome or (f"Matrícula {saida.saida_matricula}" if saida.saida_matricula else "N/D"),
                saida.saida_matricula or "N/D",
                saida.quantidade,
                business_tag,
                local_info[:150],
            ])
    
    # Ajustar larguras das colunas
    if search_type == "usuario":
        ws.column_dimensions["A"].width = 12  # Data
        ws.column_dimensions["B"].width = 10  # Hora
        ws.column_dimensions["C"].width = 32  # Item
        ws.column_dimensions["D"].width = 8   # Código
        ws.column_dimensions["E"].width = 10  # Quantidade
        ws.column_dimensions["F"].width = 12  # Tipo
        ws.column_dimensions["G"].width = 15  # Período
        ws.column_dimensions["H"].width = 60  # Local (local + observação)
    else:
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 10
        ws.column_dimensions["C"].width = 35
        ws.column_dimensions["D"].width = 8
        ws.column_dimensions["E"].width = 12
        ws.column_dimensions["F"].width = 20
        ws.column_dimensions["G"].width = 40
    
    # Salvar arquivo temporário
    reports_dir = Path(current_app.instance_path) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
    
    if search_type == "usuario":
        safe_filename = "".join(c for c in usuario_info['matricula'] if c.isalnum() or c in ('-', '_'))
        filename = f"relatorio_funcionario_{safe_filename}_{timestamp}.xlsx"
    else:
        safe_filename = "".join(c for c in item_info['codigo'] if c.isalnum() or c in ('-', '_'))
        filename = f"relatorio_item_{safe_filename}_{timestamp}.xlsx"
    
    filepath = reports_dir / filename
    
    if format_type == "xlsx":
        wb.save(str(filepath))
        return send_file(
            filepath,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )

    if format_type in ["pdf", "jpeg", "jpg"]:
        if search_type == "usuario":
            pdf_bytes = _generate_usuario_report_pdf(
                usuario=usuario_info,
                saidas=saidas,
                period_days=period_days,
                time_service=TimeService,
            )
            pdf_filename = f"relatorio_funcionario_{safe_filename}_{timestamp}.pdf"
        else:
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

        if format_type in ["jpeg", "jpg"]:
            if search_type == "usuario":
                jpeg_filename = f"relatorio_funcionario_{safe_filename}_{timestamp}.jpeg"
            else:
                jpeg_filename = f"relatorio_item_{safe_filename}_{timestamp}.jpeg"
            jpeg_path = reports_dir / jpeg_filename
            _convert_pdf_to_jpeg(str(pdf_path), str(jpeg_path))
            return send_file(
                jpeg_path,
                mimetype="image/jpeg",
                as_attachment=True,
                download_name=jpeg_filename,
            )

        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=pdf_filename,
        )

    abort(400, "Formato inválido. Use xlsx, pdf ou jpeg.")
