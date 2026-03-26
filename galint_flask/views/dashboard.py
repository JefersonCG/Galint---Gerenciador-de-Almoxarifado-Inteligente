"""Dashboard routes."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import csv
import io
from typing import Any

from flask import Blueprint, Response, abort, current_app, jsonify, render_template
from flask_login import current_user, login_required

from ..services.inventory import inventory_service
from ..services.finance_service import finance_service
from ..extensions import db
from ..models import Entrada
from ..utils.report_branding import get_company_header_lines
from ..utils.time_service import TimeService
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

blueprint = Blueprint("dashboard", __name__)


def _format_codigo_barra(value: object) -> str:
    if value is None:
        return "N/D"
    text = str(value).strip()
    if not text:
        return "N/D"
    return text[-4:] if len(text) >= 4 else text


def _format_brl(value: object) -> str:
    try:
        amount = float(value or 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_quick_panel_snapshots(competencia: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        finance_report = finance_service.get_stock_value_report()
        supplier_report = finance_service.get_supplier_lab_report()
        suppliers = supplier_report.get("suppliers") or []
        supplier_summary = supplier_report.get("summary") or {}
        active_suppliers = sum(1 for supplier in suppliers if supplier.get("ativo"))
        top_supplier = next(
            (supplier for supplier in suppliers if float(supplier.get("investido_total") or 0.0) > 0.0),
            suppliers[0] if suppliers else None,
        )

        finance_snapshot = {
            "exercise_label": (finance_report.get("exercise") or {}).get("label") or competencia,
            "total_compra": _format_brl(finance_report.get("total_compra")),
            "total_reposicao": _format_brl(finance_report.get("total_reposicao")),
            "total_investido": _format_brl(finance_report.get("total_investido_exercicio")),
            "total_sem_comprovacao": _format_brl(finance_report.get("total_sem_comprovacao_exercicio")),
            "missing_compra": int(finance_report.get("missing_compra") or 0),
            "missing_reposicao": int(finance_report.get("missing_reposicao") or 0),
        }
        supplier_snapshot = {
            "total_lojas": int(supplier_summary.get("total_lojas") or 0),
            "total_ativos": int(active_suppliers),
            "total_docs": int(supplier_summary.get("total_docs") or 0),
            "total_sem_loja": _format_brl(supplier_summary.get("total_sem_loja")),
            "top_nome": (top_supplier or {}).get("nome_exibicao") or "Sem compras vinculadas",
            "top_total": _format_brl((top_supplier or {}).get("investido_total")),
            "top_itens": int((top_supplier or {}).get("itens_distintos") or 0),
        }
        return finance_snapshot, supplier_snapshot
    except Exception:
        return None, None


def _dashboard_context(
    *,
    shared_view: bool = False,
    header_title: str | None = None,
    header_subtitle: str | None = None,
    tag_label: str | None = None,
) -> dict[str, Any]:
    snapshot = inventory_service.dashboard_snapshot()
    resumo = snapshot["resumo"]
    total_quantity = snapshot["total_quantity"]
    competencia = date.today().strftime("%m-%Y")
    total_entradas_registradas = db.session.query(Entrada.id_entrada).count()
    can_view_finance = not shared_view
    
    # Informações sobre relatórios automáticos de entradas
    from ..services.entrada_report_service import entrada_report_service
    ultimo_ciclo = entrada_report_service.get_ultimo_ciclo_gerado()
    proximo_ciclo = ultimo_ciclo + 1
    entradas_necessarias = proximo_ciclo * entrada_report_service.CONTADOR_CICLO
    faltam_entradas = max(0, entradas_necessarias - total_entradas_registradas)
    progresso_pct = min(100, int((total_entradas_registradas % entrada_report_service.CONTADOR_CICLO) / entrada_report_service.CONTADOR_CICLO * 100))
    
    reports = [
        {
            "id": "falta",
            "label": "Produtos em falta",
            "description": "Itens com saldo abaixo do mínimo",
        },
        {
            "id": "perda",
            "label": "Produtos com perda",
            "description": "Eventos de inventário registrados como perda",
        },
        {
            "id": "avariado",
            "label": "Produtos avariados",
            "description": "Eventos registrados como avaria ou dano",
        },
    ]

    return {
        "resumo": resumo,
        "competencia": competencia,
        "total_quantity": total_quantity,
        "total_entradas_registradas": total_entradas_registradas,
        "ultimo_ciclo_relatorio": ultimo_ciclo,
        "proximo_ciclo_relatorio": proximo_ciclo,
        "faltam_entradas": faltam_entradas,
        "progresso_relatorio_pct": progresso_pct,
        "reports": reports,
        "category_summary": snapshot["category_summary"],
        "shared_view": shared_view,
        "can_view_finance": can_view_finance,
        "header_title": header_title or f"Resumo Mensal de Estoque - {competencia}",
        "header_subtitle": header_subtitle or "Resumo Mensal do Estoque",
        "tag_label": tag_label or "Painel de Controle do Almoxarifado",
        "live_feed_enabled": bool(current_app.config.get("FEATURE_LIVE_FEED_ENABLED", False)),
    }


@blueprint.get("/")
@login_required
def index():
    return render_template("dashboard/index.html", **_dashboard_context(shared_view=False))


@blueprint.get("/compartilhar/<token>")
def share(token: str):
    configured = current_app.config.get("DASHBOARD_SHARE_TOKEN")
    if not configured or token != configured:
        abort(404)
    return render_template("dashboard/index.html", **_dashboard_context(shared_view=True))


@blueprint.get("/rede-galint/<token>")
def rede_galint(token: str):
    configured = current_app.config.get("DASHBOARD_SHARE_TOKEN")
    if not configured or token != configured:
        abort(404)
    return render_template(
        "dashboard/index.html",
        **_dashboard_context(
            shared_view=True,
            header_title="Rede Galint",
            header_subtitle="Painel público do almoxarifado para acesso na rede interna",
            tag_label="Rede Galint",
        ),
    )


@blueprint.get("/saidas-feed")
@login_required
def saidas_feed():
    """Retorna as últimas saídas registradas para o feed de saídas."""
    if not bool(current_app.config.get("FEATURE_LIVE_FEED_ENABLED", False)):
        abort(404)

    cutoff = datetime.utcnow() - timedelta(days=14)
    registros = inventory_service.list_saidas_por_usuario(
        current_user.id,
        limit=25,
        data_inicial=cutoff,
    )
    itens: list[dict[str, Any]] = []
    for registro in registros:
        itens.append(
            {
                "id": registro.get("id"),
                "codigo": registro.get("codigo"),
                "descricao": registro.get("descricao"),
                "quantidade": registro.get("quantidade"),
                "data_iso": TimeService.isoformat_utc(registro.get("data")),
                "usuario": registro.get("usuario"),
                "matricula": registro.get("matricula"),
            }
        )
    return jsonify({"items": itens})


@blueprint.get("/api/custody/active")
@login_required
def custody_active():
    """Retorna apenas ferramentas temporárias ativas para o feed do dashboard."""
    from ..services.tool_custody_service import tool_custody_service
    from ..models import Item, RetiradaFerramenta, Usuario
    from sqlalchemy import func

    employees = tool_custody_service.get_all_employees_with_tools()
    itens: list[dict[str, Any]] = []

    for employee in employees:
        matricula_full = employee.get("matricula") or ""
        matricula_short = (
            matricula_full[-5:] if isinstance(matricula_full, str) and len(matricula_full) >= 5 else matricula_full
        )

        for tool in employee.get("tools", []):
            if tool.get("tipo_custodia") == "permanente":
                continue

            data_saida = tool.get("data_saida")
            dias_em_uso = int(tool.get("days_in_use") or 0)

            itens.append(
                {
                    "id": tool.get("saida_id"),
                    "source": "saida",
                    "codigo": tool.get("codigo_item"),
                    "descricao": tool.get("descricao") or "",
                    "quantidade": tool.get("quantidade") or 0,
                    "usuario": employee.get("nome") or "",
                    "matricula": matricula_short,
                    "matricula_full": matricula_full,
                    "local_servico": tool.get("local_servico") or "Não informado",
                    "data_retirada_iso": TimeService.isoformat_utc(data_saida),
                    "dias_em_uso": dias_em_uso,
                    "atrasada": bool(tool.get("is_alert", False)),
                    "data_prevista_devolucao": None,
                }
            )

    # Complemento: retiradas em custódia diária registradas via fluxo novo (RetiradaFerramenta).
    # Importante: o feed legado acima é baseado em Saida; aqui pegamos as que ainda não entram lá.
    pares_ja_no_feed = {
        (str(i.get("matricula_full") or ""), str(i.get("codigo") or ""))
        for i in itens
        if i.get("matricula_full") and i.get("codigo")
    }

    retiradas_abertas = (
        db.session.query(RetiradaFerramenta, Item, Usuario)
        .join(Item, RetiradaFerramenta.codigo_item == Item.codigo_item)
        .join(Usuario, RetiradaFerramenta.matricula == Usuario.matricula)
        .filter(
            RetiradaFerramenta.status.in_(["em_uso", "atrasada"]),
            func.lower(Item.categoria).contains("ferrament"),
        )
        .order_by(RetiradaFerramenta.data_retirada.desc())
        .limit(200)
        .all()
    )

    for retirada, item, usuario in retiradas_abertas:
        matricula_full = usuario.matricula or ""
        matricula_short = (
            matricula_full[-5:]
            if isinstance(matricula_full, str) and len(matricula_full) >= 5
            else matricula_full
        )
        key = (str(matricula_full), str(item.codigo_item))
        if key in pares_ja_no_feed:
            continue

        try:
            dias_em_uso = int((datetime.utcnow() - retirada.data_retirada).days)
        except Exception:
            dias_em_uso = 0

        # Filtrar retiradas que na prática representam custódia permanente.
        if tool_custody_service.is_permanent_custody(
            tipo_custodia_raw=None,
            local_servico=getattr(retirada, "local_servico", None),
            observacao=getattr(retirada, "observacao", None),
            days_in_use=dias_em_uso,
        ):
            continue

        # Regras de atraso no dashboard:
        # - Com data prevista: somente após vencimento.
        # - Sem data prevista: considera atraso apenas acima de 30 dias.
        data_prevista = getattr(retirada, "data_prevista_devolucao", None)
        if data_prevista is not None:
            atrasada = date.today() > data_prevista
        else:
            atrasada = dias_em_uso > 30

        itens.append(
            {
                "id": retirada.id,
                "source": "retirada_ferramenta",
                "codigo": item.codigo_item,
                "descricao": item.descricao or "",
                "quantidade": retirada.quantidade or 0,
                "usuario": usuario.nome or "",
                "matricula": matricula_short,
                "matricula_full": matricula_full,
                "local_servico": retirada.local_servico or "Não informado",
                "data_retirada_iso": TimeService.isoformat_utc(retirada.data_retirada),
                "dias_em_uso": dias_em_uso,
                "atrasada": atrasada,
                "data_prevista_devolucao": (
                    retirada.data_prevista_devolucao.isoformat()
                    if getattr(retirada, "data_prevista_devolucao", None)
                    else None
                ),
            }
        )

    itens.sort(key=lambda item: item.get("data_retirada_iso") or "", reverse=True)
    itens = itens[:50]

    return jsonify({"items": itens, "total": len(itens)})


@blueprint.get("/api/quick-panels")
@login_required
def quick_panels():
    competencia = date.today().strftime("%m-%Y")
    finance_snapshot, supplier_snapshot = _build_quick_panel_snapshots(competencia)
    if not finance_snapshot or not supplier_snapshot:
        return jsonify({"ok": False, "message": "Não foi possível carregar o resumo financeiro agora."}), 500
    return jsonify(
        {
            "ok": True,
            "finance_snapshot": finance_snapshot,
            "supplier_snapshot": supplier_snapshot,
        }
    )


def _build_report(tipo: str) -> tuple[str, list[str], list[list[Any]]]:
    # Esta função será movida para o service
    pass


@blueprint.get("/relatorio/<string:tipo>.csv")
@login_required
def download_report(tipo: str):
    try:
        filename, headers, rows = inventory_service.generate_report_csv(tipo)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        buffer.seek(0)
        response = Response(buffer.getvalue(), mimetype="text/csv")
        response.headers["Content-Disposition"] = f"attachment; filename={filename}.csv"
        return response
    except ValueError:
        abort(404)


@blueprint.get("/relatorio/produtos-em-falta.xlsx")
@login_required
def download_low_stock_template():
    data = inventory_service.report_low_stock()
    workbook = _build_low_stock_workbook(data)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    response = Response(
        buffer.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=material-em-baixa-almoxarifado.xlsx"
    return response


def _build_low_stock_workbook(items: list[dict[str, Any]]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Produtos em falta"
    total_columns = 5
    end_column = get_column_letter(total_columns)

    current_row = 1
    company_lines = get_company_header_lines()
    if company_lines:
        for idx, line in enumerate(company_lines):
            ws.merge_cells(f"A{current_row}:{end_column}{current_row}")
            cell = ws[f"A{current_row}"]
            cell.value = line
            cell.font = Font(bold=(idx == 0), size=20 if idx == 0 else 11)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[current_row].height = 30 if idx == 0 else 18
            current_row += 1

    ws.merge_cells(f"A{current_row}:{end_column}{current_row}")
    title_cell = ws[f"A{current_row}"]
    title_cell.fill = PatternFill("solid", fgColor="0066CC")
    title_cell.font = Font(bold=True, color="FFFFFF")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    title_cell.value = "MATERIAL EM BAIXA NO ALMOXARIFADO"
    ws.row_dimensions[current_row].height = 24
    current_row += 2

    headers = ["Descrição", "Marca/Fabricante", "Setor", "Qtd. Est.", "Código"]
    for col, header in enumerate(headers, start=1):
        ws.cell(row=current_row, column=col, value=header)
    header_fill = PatternFill("solid", fgColor="FDE047")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=current_row, column=col)
        cell.fill = header_fill
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    current_row += 1

    for item in items:
        codigo_display = _format_codigo_barra(item.get("codigo"))
        row = [
            item.get("descricao"),
            item.get("marca"),
            item.get("setor"),
            item.get("saldo_atual"),
            codigo_display,
        ]
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=current_row, column=col_idx, value=value)
        row_idx = current_row
        for col in range(1, len(headers) + 1):
            col_cell = ws.cell(row=row_idx, column=col)
            col_cell.border = thin_border
            col_cell.alignment = Alignment(horizontal="left", vertical="top")

        current_row += 1

    column_widths = [45, 25, 20, 12, 8]
    for idx, width in enumerate(column_widths, start=1):
        column_letter = get_column_letter(idx)
        ws.column_dimensions[column_letter].width = width

    return wb


def _build_event_report_workbook(
    *,
    title: str,
    subtitle: str,
    headers: list[str],
    rows: list[list[Any]],
    column_widths: list[int] | None = None,
) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = subtitle
    total_columns = len(headers)
    if total_columns == 0:
        return wb
    end_column = get_column_letter(total_columns)
    current_row = 1
    company_lines = get_company_header_lines()
    if company_lines:
        for idx, line in enumerate(company_lines):
            ws.merge_cells(f"A{current_row}:{end_column}{current_row}")
            cell = ws[f"A{current_row}"]
            cell.value = line
            cell.font = Font(bold=(idx == 0), size=18 if idx == 0 else 11)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[current_row].height = 28 if idx == 0 else 18
            current_row += 1

    ws.merge_cells(f"A{current_row}:{end_column}{current_row}")
    ws[f"A{current_row}"] = title
    ws[f"A{current_row}"].font = Font(bold=True, size=18)
    ws[f"A{current_row}"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[current_row].height = 30
    current_row += 1

    ws.merge_cells(f"A{current_row}:{end_column}{current_row}")
    ws[f"A{current_row}"] = subtitle
    ws[f"A{current_row}"].alignment = Alignment(horizontal="center")
    ws.row_dimensions[current_row].height = 20
    current_row += 2

    header_row = current_row
    for column_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=column_idx, value=header)
    header_fill = PatternFill("solid", fgColor="FDE047")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    for column_idx in range(1, total_columns + 1):
        cell = ws.cell(row=header_row, column=column_idx)
        cell.fill = header_fill
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    data_row = header_row + 1
    for row_data in rows:
        for column_idx, value in enumerate(row_data, start=1):
            ws.cell(row=data_row, column=column_idx, value=value)
        row_idx = data_row
        for column_idx in range(1, total_columns + 1):
            column_cell = ws.cell(row=row_idx, column=column_idx)
            column_cell.border = thin_border
            column_cell.alignment = Alignment(horizontal="left", vertical="top")
        data_row += 1

    widths = column_widths or [20] * total_columns
    for idx, width in enumerate(widths[:total_columns], start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    return wb


@blueprint.get("/relatorio/perdas.xlsx")
@login_required
def download_loss_template():
    dados = inventory_service.report_inventory_events("perda")
    headers = ["Data", "Código", "Tipo", "Quantidade", "Responsável", "Descrição"]
    rows = [
        [
            registro["data"].isoformat() if registro.get("data") else "",
            _format_codigo_barra(registro.get("codigo")),
            registro.get("tipo", ""),
            registro.get("quantidade", 0),
            registro.get("responsavel", ""),
            registro.get("descricao", ""),
        ]
        for registro in dados
    ]
    workbook = _build_event_report_workbook(
        title="Produtos com perda",
        subtitle="Eventos de inventário registrados como perda",
        headers=headers,
        rows=rows,
        column_widths=[20, 8, 18, 12, 20, 40],
    )
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    response = Response(
        buffer.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response.headers["Content-Disposition"] = "attachment; filename=produtos-com-perda.xlsx"
    return response


@blueprint.get("/relatorio/avariados.xlsx")
@login_required
def download_avariados_template():
    dados = inventory_service.report_inventory_events("avari")
    headers = ["Data", "Código", "Tipo", "Quantidade", "Responsável", "Descrição"]
    rows = [
        [
            registro["data"].isoformat() if registro.get("data") else "",
            _format_codigo_barra(registro.get("codigo")),
            registro.get("tipo", ""),
            registro.get("quantidade", 0),
            registro.get("responsavel", ""),
            registro.get("descricao", ""),
        ]
        for registro in dados
    ]
    workbook = _build_event_report_workbook(
        title="Produtos avariados",
        subtitle="Eventos registrados como avaria ou dano",
        headers=headers,
        rows=rows,
        column_widths=[20, 8, 18, 12, 20, 40],
    )
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    response = Response(
        buffer.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response.headers["Content-Disposition"] = "attachment; filename=produtos-avariados.xlsx"
    return response

