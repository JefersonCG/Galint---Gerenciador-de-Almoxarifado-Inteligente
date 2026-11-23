"""Relatórios do GALINT em PDF e em Excel, com o mesmo conteúdo.

Pedido do usuário em 23/11/2026: compartilhar os relatórios do app no WhatsApp em PDF e em XLS e
conferir se as células dos PDFs estão legíveis ("se não está uma entrando dentro da outra").

Erros que originaram este módulo:
- os PDFs antigos punham texto solto nas células, sem quebra de linha, e o que não cabia invadia a
  coluna vizinha (mensal: descrição cortada em 24 letras e mesmo assim larga demais; consumo: local e
  material em destaque sem quebra);
- o mensal saía com o título "RELATÓRIO DIÁRIO" e parava em 500 linhas sem avisar;
- o do dia buscava das 3h de hoje às 3h de amanhã: convertia o dia para UTC, mas o banco grava a
  saída na hora de São Paulo sem fuso (convenção do TimeService.now_db).

Cada relatório é montado uma vez (Report: resumo + seções com colunas) e sai em PDF ou em Excel pelo
mesmo desenho. No PDF toda célula é um Paragraph (quebra a linha e, com splitLongWords, até palavra
comprida), a largura das colunas é proporcional ao espaço da página, o cabeçalho da tabela se repete
em cada página e o rodapé traz "Página X de Y". No Excel cada seção vira uma aba com números de
verdade (quantidade, R$, data), filtro e cabeçalho fixo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from ..extensions import db
from ..models import InventarioEvento, Item, Saida, Usuario
from ..utils.time_service import TimeService
from .operation_visual_payload import human_observation

MONTHS = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
SCOPES = {"all": "Tudo", "materials": "Materiais", "tools": "Ferramentas"}
FORMATS = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
RETURN_TYPES = {
    "all": ("devolucao_material", "devolucao_ferramenta"),
    "materials": ("devolucao_material",),
    "tools": ("devolucao_ferramenta",),
}

INK = "#111827"
MUTED = "#4b5563"
HEAD_BG = "#1f2937"
LINE = "#d1d5db"
ZEBRA = "#f3f4f6"
TOTAL_BG = "#e5e7eb"


@dataclass
class Column:
    title: str
    weight: float
    kind: str = "text"  # text | qty | int | money | datetime | date | time

    @property
    def align(self) -> str:
        return "right" if self.kind in {"qty", "int", "money"} else "left"


@dataclass
class Section:
    title: str
    columns: list[Column]
    rows: list[list[Any]]
    totals: list[Any] | None = None


@dataclass
class Report:
    title: str
    period: str
    file_stem: str
    scope: str | None = None
    summary: list[tuple[str, str]] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    preview: list[dict[str, str]] = field(default_factory=list)
    empty_message: str = "Nada registrado no período."

    @property
    def is_empty(self) -> bool:
        return not any(section.rows for section in self.sections)

    def filename(self, fmt: str) -> str:
        return f"{self.file_stem}.{fmt}"

    def render(self, fmt: str) -> bytes:
        if fmt == "pdf":
            return render_pdf(self)
        if fmt == "xlsx":
            return render_xlsx(self)
        raise ValueError(f"Formato inválido: {fmt}")

    def as_summary_json(self) -> dict[str, Any]:
        return {
            "titulo": self.title,
            "arquivo": self.file_stem,
            "periodo": self.period,
            "escopo": self.scope,
            "resumo": [{"rotulo": label, "valor": value} for label, value in self.summary],
            "linhas": self.preview[:80],
            "total_linhas": sum(len(section.rows) for section in self.sections[:1]),
            "vazio": self.is_empty,
            "mensagem_vazio": self.empty_message,
        }


# ---------------------------------------------------------------- formatação

def _br_number(text: str) -> str:
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_qty(value: Any) -> str:
    number = float(value or 0)
    if abs(number - round(number)) < 1e-9:
        return _br_number(f"{int(round(number)):,}")
    return _br_number(f"{number:,.3f}".rstrip("0").rstrip("."))


def fmt_money(value: Any) -> str:
    return "R$ " + _br_number(f"{float(value or 0):,.2f}")


def fmt_cell(value: Any, kind: str) -> str:
    if value is None or value == "":
        return "-"
    if kind == "qty":
        return fmt_qty(value)
    if kind == "int":
        return fmt_qty(int(value))
    if kind == "money":
        return fmt_money(value)
    if isinstance(value, datetime):
        if kind == "time":
            return value.strftime("%H:%M")
        if kind == "date":
            return value.strftime("%d/%m/%Y")
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)


def _local_naive(value: datetime | None) -> datetime | None:
    """Data do banco para mostrar: hora de São Paulo, sem fuso (o Excel não aceita fuso)."""
    if value is None:
        return None
    return TimeService.to_local(value).replace(tzinfo=None)


def _company_line() -> str:
    try:
        from ..utils.report_branding import get_company_header_lines

        return " · ".join(get_company_header_lines())
    except Exception:
        return ""


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


# ---------------------------------------------------------------- PDF

def render_pdf(report: Report) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    page_w, page_h = landscape(A4)
    margin = 1.0 * cm
    usable = page_w - 2 * margin
    generated = TimeService.now_local().strftime("%d/%m/%Y %H:%M")
    footer_left = f"GALINT · {report.title} · gerado em {generated}"

    class _NumberedCanvas(Canvas):
        """Rodapé com "Página X de Y": guarda as páginas e escreve o total no fim."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages: list[dict] = []

        def showPage(self):  # noqa: N802 (nome da API do ReportLab)
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self.setFont("Helvetica", 7.5)
                self.setFillColor(colors.HexColor(MUTED))
                self.drawString(margin, 0.6 * cm, footer_left)
                self.drawRightString(page_w - margin, 0.6 * cm, f"Página {self._pageNumber} de {total}")
                super().showPage()
            super().save()

    title_style = ParagraphStyle("RelTitulo", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=colors.HexColor(INK))
    meta_style = ParagraphStyle("RelMeta", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor(MUTED))
    section_style = ParagraphStyle(
        "RelSecao", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor(INK), spaceBefore=8, spaceAfter=4,
    )
    kpi_label = ParagraphStyle("RelKpiRotulo", fontName="Helvetica", fontSize=7.5, leading=9, textColor=colors.HexColor(MUTED))
    kpi_value = ParagraphStyle("RelKpiValor", fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.HexColor(INK))

    def _cell_style(name: str, align: str, bold: bool = False, color: str = INK) -> ParagraphStyle:
        return ParagraphStyle(
            name,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=8,
            leading=10,
            alignment=TA_RIGHT if align == "right" else TA_LEFT,
            textColor=colors.HexColor(color),
            splitLongWords=1,
        )

    body = {align: _cell_style(f"RelCel{align}", align) for align in ("left", "right")}
    head = {align: _cell_style(f"RelCab{align}", align, bold=True, color="#ffffff") for align in ("left", "right")}
    total = {align: _cell_style(f"RelTot{align}", align, bold=True) for align in ("left", "right")}

    def _p(text: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(text), style)

    story: list[Any] = [_p(report.title, title_style)]
    meta = " · ".join(part for part in (report.period, report.scope, _company_line()) if part)
    if meta:
        story.append(_p(meta, meta_style))
    story.append(Spacer(1, 0.3 * cm))

    if report.summary:
        per_row = min(6, len(report.summary))
        cells = [[_p(label, kpi_label), _p(value, kpi_value)] for label, value in report.summary]
        rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
        rows[-1] += [""] * (per_row - len(rows[-1]))
        kpis = Table(rows, colWidths=[usable / per_row] * per_row)
        kpis.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(ZEBRA)),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ffffff")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [kpis, Spacer(1, 0.25 * cm)]

    shown = [section for section in report.sections if section.rows]
    for section in shown:
        if len(report.sections) > 1 or section.title:
            story.append(_p(section.title, section_style))
        columns = section.columns
        weight_sum = sum(column.weight for column in columns) or 1
        widths = [usable * column.weight / weight_sum for column in columns]
        data = [[_p(column.title, head[column.align]) for column in columns]]
        for row in section.rows:
            data.append([_p(fmt_cell(value, column.kind), body[column.align]) for value, column in zip(row, columns)])
        if section.totals:
            data.append([
                _p("" if value is None else fmt_cell(value, column.kind), total[column.align])
                for value, column in zip(section.totals, columns)
            ])
        table = Table(data, colWidths=widths, repeatRows=1)
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(HEAD_BG)),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(LINE)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(ZEBRA)]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if section.totals:
            commands.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(TOTAL_BG)))
        table.setStyle(TableStyle(commands))
        story.append(table)

    if not shown:
        story.append(_p(report.empty_message, meta_style))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(page_w, page_h),
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=1.3 * cm,
        title=report.title,
        author="GALINT",
    )
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()


# ---------------------------------------------------------------- Excel

_SHEET_FORBIDDEN = str.maketrans({ch: " " for ch in "[]:*?/\\"})


def _sheet_name(title: str, used: set[str]) -> str:
    base = (title or "Relatório").translate(_SHEET_FORBIDDEN).strip()[:31] or "Relatório"
    name, n = base, 2
    while name.lower() in used:
        suffix = f" {n}"
        name = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(name.lower())
    return name


def render_xlsx(report: Report) -> bytes:
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    formats = {
        "qty": "General",  # "#,##0.###" deixaria "85." no número inteiro
        "int": "#,##0",
        "money": '"R$" #,##0.00',
        "datetime": "dd/mm/yyyy hh:mm",
        "date": "dd/mm/yyyy",
        "time": "hh:mm",
    }
    head_fill = PatternFill("solid", fgColor=HEAD_BG.lstrip("#"))
    total_fill = PatternFill("solid", fgColor=TOTAL_BG.lstrip("#"))
    thin = Side(style="thin", color=LINE.lstrip("#"))
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def _value(value: Any, kind: str) -> Any:
        if value is None or value == "":
            return None
        if kind in {"qty", "money"}:
            return float(value)
        if kind == "int":
            return int(value)
        if isinstance(value, (datetime, date)):
            return value
        return ILLEGAL_CHARACTERS_RE.sub("", str(value))

    workbook = Workbook()
    sections = [section for section in report.sections if section.rows] or report.sections[:1]
    used: set[str] = set()
    meta = " · ".join(part for part in (report.period, report.scope) if part)
    summary = "   ".join(f"{label}: {value}" for label, value in report.summary)

    for index, section in enumerate(sections or [Section(report.title, [], [])]):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = _sheet_name(section.title if len(sections) > 1 else report.title, used)
        sheet["A1"] = report.title + (f" — {section.title}" if len(sections) > 1 else "")
        sheet["A1"].font = Font(bold=True, size=14)
        sheet["A2"] = meta
        sheet["A2"].font = Font(color=MUTED.lstrip("#"))
        row = 3
        if summary:
            sheet.cell(row=3, column=1, value=summary).font = Font(bold=True)
            row = 4
        header_row = row + 1
        columns = section.columns
        if not section.rows:
            sheet.cell(row=header_row, column=1, value=report.empty_message)
            continue

        widths = [len(column.title) for column in columns]
        for col, column in enumerate(columns, start=1):
            cell = sheet.cell(row=header_row, column=col, value=column.title)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head_fill
            cell.border = border
            cell.alignment = Alignment(horizontal=column.align, vertical="center", wrap_text=True)

        def _write(values: list[Any], at: int, bold: bool = False) -> None:
            for col, (value, column) in enumerate(zip(values, columns), start=1):
                cell = sheet.cell(row=at, column=col, value=_value(value, column.kind))
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.data_type = "s"  # texto digitado pela pessoa, nunca fórmula
                if column.kind in formats:
                    cell.number_format = formats[column.kind]
                cell.border = border
                cell.alignment = Alignment(horizontal=column.align, vertical="top", wrap_text=column.kind == "text")
                if bold:
                    cell.font = Font(bold=True)
                    cell.fill = total_fill
                shown = len(fmt_cell(value, column.kind)) if value not in (None, "") else 1
                widths[col - 1] = max(widths[col - 1], min(shown, 60))

        at = header_row
        for values in section.rows:
            at += 1
            _write(values, at)
        last_data_row = at
        if section.totals:
            at += 1
            _write(section.totals, at, bold=True)

        for col, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(col)].width = max(8, width + 2)
        sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(len(columns))}{last_data_row}"
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.print_title_rows = f"{header_row}:{header_row}"

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------- dados comuns

def _scope_filter(query, scope: str):
    if scope == "tools":
        return query.filter(Item.categoria.ilike("%ferramenta%"))
    if scope == "materials":
        return query.filter(~Item.categoria.ilike("%ferramenta%"))
    return query


def _withdrawals(
    start: datetime, end: datetime, scope: str, category: str | None = None,
) -> list[tuple[Saida, Item | None, Usuario | None]]:
    query = (
        db.session.query(Saida, Item, Usuario)
        .outerjoin(Item, Saida.codigo_item == Item.codigo_item)
        .outerjoin(Usuario, Saida.matricula == Usuario.matricula)
        .filter(Saida.data_saida >= start, Saida.data_saida < end)
    )
    if category:
        query = query.filter(Item.categoria == category)
    return _scope_filter(query, scope).order_by(Saida.data_saida.asc(), Saida.id_saida.asc()).all()


def _withdrawal_place(saida: Saida) -> str:
    """Local do serviço e a observação que uma pessoa escreveu (sem os dados técnicos gravados)."""
    parts: list[str] = []
    if getattr(saida, "usou_fracao", False):
        fractions = []
        if saida.quantidade_retirada_em_litros:
            fractions.append(f"{fmt_qty(saida.quantidade_retirada_em_litros)} L")
        if saida.quantidade_retirada_em_quilos:
            fractions.append(f"{fmt_qty(saida.quantidade_retirada_em_quilos)} kg")
        if fractions:
            parts.append(" / ".join(fractions))
    local = _clean(saida.local_servico)
    if local:
        parts.append(local)
    note = _clean(human_observation(saida.observacao)).replace("→", "->")  # a Helvetica do PDF não tem a seta
    if note and note.upper() != local.upper():
        parts.append(note)
    return " · ".join(parts)


def _person(usuario: Usuario | None, matricula: str | None) -> str:
    if usuario is not None and usuario.nome:
        return _clean(usuario.nome)
    return _clean(matricula) or "-"


# ---------------------------------------------------------------- relatório do dia

def daily_report(day: date | None = None, scope: str = "all") -> Report:
    scope = scope if scope in SCOPES else "all"
    day = day or TimeService.now_local().date()
    start = datetime.combine(day, time.min)  # hora de São Paulo sem fuso, como o banco grava
    end = start + timedelta(days=1)
    rows = _withdrawals(start, end, scope)

    withdrawals: list[list[Any]] = []
    preview: list[dict[str, str]] = []
    people: set[str] = set()
    items: set[str] = set()
    for saida, item, usuario in rows:
        when = _local_naive(saida.data_saida)
        description = _clean(item.descricao if item else "") or "Item removido"
        person = _person(usuario, saida.matricula)
        place = _withdrawal_place(saida)
        unit = _clean(item.unidade if item else "")
        withdrawals.append([when, saida.codigo_item or "-", description, saida.quantidade, unit, person, place])
        people.add(person)
        items.add(saida.codigo_item or description)
        preview.append({
            "titulo": description,
            "detalhe": " · ".join(part for part in (fmt_cell(when, "time"), person, place) if part and part != "-"),
            "valor": fmt_qty(saida.quantidade),
        })

    returns_query = (
        db.session.query(InventarioEvento, Item, Usuario)
        .outerjoin(Item, InventarioEvento.codigo_item == Item.codigo_item)
        .outerjoin(Usuario, InventarioEvento.matricula == Usuario.matricula)
        .filter(InventarioEvento.data_evento >= start, InventarioEvento.data_evento < end)
        .filter(InventarioEvento.tipo.in_(RETURN_TYPES[scope]))
        .order_by(InventarioEvento.data_evento.asc())
    )
    returns: list[list[Any]] = []
    for evento, item, usuario in returns_query.all():
        returns.append([
            _local_naive(evento.data_evento),
            evento.codigo_item or "-",
            _clean(item.descricao if item else "") or "Item removido",
            evento.quantidade,
            _clean(item.unidade if item else ""),
            _person(usuario, evento.matricula),
        ])

    summary = [("Saídas", fmt_qty(len(withdrawals))), ("Itens", fmt_qty(len(items))), ("Colaboradores", fmt_qty(len(people)))]
    if returns:
        summary.append(("Devoluções", fmt_qty(len(returns))))

    return Report(
        title="Saídas do dia",
        period=day.strftime("%d/%m/%Y"),
        scope=SCOPES[scope],
        file_stem=f"saidas-{day.strftime('%Y-%m-%d')}-{SCOPES[scope].lower()}",
        summary=summary,
        sections=[
            Section("Saídas", [
                Column("Hora", 1.1, "time"),
                Column("Código", 2.0),
                Column("Descrição", 6.0),
                Column("Qtd", 1.1, "qty"),
                Column("Un.", 1.3),
                Column("Colaborador", 3.2),
                Column("Local / observação", 5.3),
            ], withdrawals),
            Section("Devoluções", [
                Column("Hora", 1.1, "time"),
                Column("Código", 2.0),
                Column("Descrição", 7.0),
                Column("Qtd", 1.1, "qty"),
                Column("Un.", 1.3),
                Column("Colaborador", 3.2),
            ], returns),
        ],
        preview=preview,
        empty_message="Nenhuma saída registrada neste dia.",
    )


# ---------------------------------------------------------------- mês e período

def _withdrawal_listing(
    *, title: str, period: str, file_stem: str, start: datetime, end: datetime, scope: str,
    category: str | None = None, empty_message: str,
) -> Report:
    """Saídas de um intervalo: total por item (o que mais saiu primeiro) e a lista completa."""
    scope = scope if scope in SCOPES else "all"
    rows = _withdrawals(start, end, scope, category)

    detail: list[list[Any]] = []
    per_item: dict[str, dict[str, Any]] = {}
    people: set[str] = set()
    for saida, item, usuario in rows:
        description = _clean(item.descricao if item else "") or "Item removido"
        person = _person(usuario, saida.matricula)
        unit = _clean(item.unidade if item else "")
        code = saida.codigo_item or "-"
        detail.append([
            _local_naive(saida.data_saida), code, description, _clean(item.categoria if item else ""),
            saida.quantidade, unit, person, _withdrawal_place(saida),
        ])
        people.add(person)
        bucket = per_item.setdefault(code, {"codigo": code, "descricao": description, "unidade": unit, "qtd": 0.0, "saidas": 0, "pessoas": set()})
        bucket["qtd"] += float(saida.quantidade or 0)
        bucket["saidas"] += 1
        bucket["pessoas"].add(person)

    ranking = sorted(per_item.values(), key=lambda row: (-row["saidas"], row["descricao"]))
    by_item = [[row["codigo"], row["descricao"], row["qtd"], row["unidade"], row["saidas"], len(row["pessoas"])] for row in ranking]
    preview = [
        {"titulo": row["descricao"], "detalhe": f"{row['saidas']} saída(s) · {len(row['pessoas'])} colaborador(es)", "valor": fmt_qty(row["qtd"])}
        for row in ranking
    ]
    scope_label = SCOPES[scope] + (f" · {category}" if category else "")
    return Report(
        title=title,
        period=period,
        scope=scope_label,
        file_stem=file_stem,
        summary=[("Saídas", fmt_qty(len(detail))), ("Itens", fmt_qty(len(per_item))), ("Colaboradores", fmt_qty(len(people)))],
        sections=[
            Section("Total por item", [
                Column("Código", 2.0),
                Column("Descrição", 8.0),
                Column("Qtd", 1.3, "qty"),
                Column("Un.", 1.3),
                Column("Saídas", 1.2, "int"),
                Column("Colaboradores", 1.8, "int"),
            ], by_item),
            Section("Saídas", [
                Column("Data", 2.1, "datetime"),
                Column("Código", 2.0),
                Column("Descrição", 5.2),
                Column("Categoria", 2.6),
                Column("Qtd", 1.1, "qty"),
                Column("Un.", 1.2),
                Column("Colaborador", 2.8),
                Column("Local / observação", 4.0),
            ], detail),
        ],
        preview=preview,
        empty_message=empty_message,
    )


def monthly_report(year: int, month: int, scope: str = "all") -> Report:
    start = datetime(year, month, 1)  # hora de São Paulo sem fuso, como o banco grava
    end = datetime(year + (month == 12), month % 12 + 1, 1)
    label = f"{MONTHS[month - 1]} de {year}"
    scope = scope if scope in SCOPES else "all"
    return _withdrawal_listing(
        title="Saídas do mês",
        period=label[0].upper() + label[1:],
        file_stem=f"saidas-{year}-{month:02d}-{SCOPES[scope].lower()}",
        start=start,
        end=end,
        scope=scope,
        empty_message="Nenhuma saída registrada neste mês.",
    )


def period_report(months: int, category: str | None = None, scope: str = "all") -> Report:
    """Últimos N meses (30 dias cada), como o relatório por período do Telegram."""
    now = TimeService.now_db()
    start = now - timedelta(days=30 * months)
    scope = scope if scope in SCOPES else "all"
    stem_category = "".join(ch if ch.isalnum() else "-" for ch in (category or "").lower()).strip("-")[:30]
    return _withdrawal_listing(
        title="Saídas no período",
        period=f"{start.strftime('%d/%m/%Y')} a {now.strftime('%d/%m/%Y')}",
        file_stem="-".join(part for part in ("saidas", f"{months}m", SCOPES[scope].lower(), stem_category) if part),
        start=start,
        end=now + timedelta(seconds=1),
        scope=scope,
        category=category,
        empty_message="Nenhuma saída registrada no período.",
    )


# ---------------------------------------------------------------- consumo (valores)

def consumption_report(
    exercise_label: str | None = None,
    *,
    local_name: str | None = None,
    category_name: str | None = None,
    employee_id: str | None = None,
    panel: dict[str, Any] | None = None,
) -> Report:
    if panel is None:
        from .finance_service import finance_service

        panel = finance_service.get_consumption_panel_report(
            exercise_label, local_name=local_name, category_name=category_name, employee_id=employee_id,
        )
    exercise = panel.get("exercise") or {}
    overview = panel.get("overview") or {}
    scope_type = panel.get("scope_type") or "geral"

    locations = [
        [_clean(row.get("local")) or "SEM LOCAL", row.get("total_valor"), row.get("saidas"), row.get("itens"),
         row.get("colaboradores"), _clean(row.get("material_destaque"))]
        for row in panel.get("locations") or []
    ]
    categories = [
        [_clean(row.get("categoria")) or "Sem categoria", row.get("total_valor"), row.get("saidas"), row.get("locais"),
         row.get("colaboradores"), _clean(row.get("local_destaque"))]
        for row in panel.get("categories") or []
    ]
    employees = [
        [_clean(row.get("nome")) or "Não informado", _clean(row.get("cargo")), row.get("total_valor"), row.get("saidas"),
         row.get("locais"), _clean((row.get("parecer_administrativo") or {}).get("label"))]
        for row in panel.get("employees") or []
    ]
    entries: list[list[Any]] = []
    for row in panel.get("entries") or []:
        local = _clean(row.get("local")) or "SEM LOCAL"
        context = _clean(row.get("contexto_uso"))
        if context and context.upper() != local.upper():
            local = f"{local} · {context}"
        entries.append([
            _clean(row.get("data_saida_label")) or "-",
            _clean(row.get("colaborador_nome")) or "Não informado",
            _clean(row.get("descricao_item")) or "Item sem descrição",
            _clean(row.get("categoria")) or "Sem categoria",
            local,
            _clean(row.get("quantidade_display")) or "0",
            row.get("valor_total"),
        ])
    total_value = float(overview.get("total_valor") or 0)

    sections: list[Section] = []
    if scope_type != "local":
        sections.append(Section("Por local", [
            Column("Local", 4.5), Column("Valor", 2.2, "money"), Column("Saídas", 1.3, "int"), Column("Itens", 1.2, "int"),
            Column("Colaboradores", 1.8, "int"), Column("Material de destaque", 5.0),
        ], locations, ["Total", total_value, None, None, None, None] if locations else None))
    if scope_type != "categoria":
        sections.append(Section("Por categoria", [
            Column("Categoria", 4.5), Column("Valor", 2.2, "money"), Column("Saídas", 1.3, "int"), Column("Locais", 1.2, "int"),
            Column("Colaboradores", 1.8, "int"), Column("Local de destaque", 5.0),
        ], categories, ["Total", total_value, None, None, None, None] if categories else None))
    if scope_type != "funcionario":
        sections.append(Section("Por colaborador", [
            Column("Colaborador", 4.0), Column("Cargo", 2.8), Column("Valor", 2.2, "money"), Column("Saídas", 1.3, "int"),
            Column("Locais", 1.2, "int"), Column("Parecer", 4.5),
        ], employees, ["Total", None, total_value, None, None, None] if employees else None))
    sections.append(Section("Lançamentos", [
        Column("Data", 2.2), Column("Colaborador", 3.0), Column("Material", 5.2), Column("Categoria", 2.6),
        Column("Local", 3.6), Column("Qtd", 1.8), Column("Valor", 2.0, "money"),
    ], entries, [None, None, None, None, None, "Total", total_value] if entries else None))

    filters = panel.get("filters") or {}
    focus = {
        "local": filters.get("local"),
        "categoria": filters.get("categoria"),
        "funcionario": ((panel.get("current_employee") or {}).get("nome") or filters.get("matricula")),
    }.get(scope_type)
    period = f"Exercício {exercise.get('label') or ''}".strip()
    if exercise.get("start_date") and exercise.get("end_date"):
        period += f" ({fmt_cell(exercise['start_date'], 'date')} a {fmt_cell(exercise['end_date'], 'date')})"

    ranking = sorted(panel.get("categories") or [], key=lambda row: -float(row.get("total_valor") or 0))
    preview_rows = ranking if scope_type != "categoria" else (panel.get("locations") or [])
    preview = [
        {
            "titulo": _clean(row.get("categoria") or row.get("local")) or "-",
            "detalhe": f"{int(row.get('saidas') or 0)} saída(s)",
            "valor": fmt_money(row.get("total_valor")),
        }
        for row in preview_rows
    ]
    stem_focus = "".join(ch if ch.isalnum() else "-" for ch in (focus or "geral").lower()).strip("-")[:40] or "geral"
    return Report(
        title="Consumo",
        period=period,
        scope=_clean(focus) or "Geral",
        file_stem=f"consumo-{exercise.get('label') or 'exercicio'}-{stem_focus}",
        summary=[
            ("Valor total", fmt_money(total_value)),
            ("Saídas", fmt_qty(overview.get("saidas") or 0)),
            ("Itens", fmt_qty(overview.get("itens") or 0)),
            ("Locais", fmt_qty(overview.get("locais") or 0)),
            ("Colaboradores", fmt_qty(overview.get("colaboradores") or 0)),
        ],
        sections=sections,
        preview=preview,
        empty_message="Sem consumo registrado neste recorte.",
    )


def consumption_options(panel: dict[str, Any]) -> dict[str, Any]:
    """Escolhas do recorte de consumo para o app: exercícios, locais, categorias e colaboradores."""
    exercises = []
    for option in panel.get("exercise_options") or []:
        if isinstance(option, dict):
            value = option.get("label") or option.get("value")
        else:
            value = option
        if value:
            exercises.append(str(value))
    return {
        "exercicio": (panel.get("exercise") or {}).get("label"),
        "exercicios": exercises,
        "locais": [_clean(row.get("local")) for row in panel.get("global_locations") or [] if row.get("local")],
        "categorias": [_clean(row.get("categoria")) for row in panel.get("global_categories") or [] if row.get("categoria")],
        "colaboradores": [
            {"matricula": str(row.get("matricula") or ""), "nome": _clean(row.get("nome")) or str(row.get("matricula") or "")}
            for row in panel.get("global_employees") or []
            if row.get("matricula")
        ],
        "filtros": panel.get("filters") or {},
    }

