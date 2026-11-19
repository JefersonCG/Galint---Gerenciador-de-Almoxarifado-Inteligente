from __future__ import annotations

from io import BytesIO
import math
from typing import Any, Sequence

from openpyxl import Workbook
from openpyxl.drawing.image import Image as SpreadsheetImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.worksheet.pagebreak import Break

from ..utils.report_branding import get_company_header_lines
from ..utils.time_service import TimeService

BARCODE_WIDTH_PX = 160
BARCODE_HEIGHT_PX = 34
BARCODE_LEFT_GAP_PX = 10  # coluna B (largura 25) tem ~180 px
# Em ~42 mm impressos, 160 módulos dão ~0,26 mm por barra; acima disso o leitor falha.
# EAN-13 dá ~101 módulos; "BOMBA AUTOASPIRANTE" daria 244.
BARCODE_MAX_MODULES = 160
EMU_PER_POINT = 12700
# Letras por linha que cabem em cada coluna na impressão A4 (medido no PDF do Excel, com folga).
ITEM_CHARS_PER_LINE = 36
SYSTEM_CHARS_PER_LINE = 19
CODE_TEXT_CHARS_PER_LINE = 30
LINE_HEIGHT_PT = 15
MIN_ROW_HEIGHT_PT = 39
MAX_ROW_HEIGHT_PT = 81


class StockCountWorkbookService:
    @staticmethod
    def _barcode_png(value: str) -> BytesIO | None:
        """PNG Code128 do código, ou None quando ele não sai legível na planilha:
        caractere fora do Code128 (acento) ou código longo demais para a largura da coluna."""
        try:
            import barcode
            from barcode.errors import BarcodeError
            from barcode.writer import ImageWriter
        except ImportError as exc:
            raise RuntimeError("A dependência python-barcode é necessária para gerar a planilha de contagem.") from exc

        buffer = BytesIO()
        try:
            code = barcode.get("code128", value, writer=ImageWriter())
            if len(code.build()[0]) > BARCODE_MAX_MODULES:
                return None
            code.write(
                buffer,
                options={
                    "write_text": False,
                    "module_width": 0.25,
                    "module_height": 8.0,
                    "quiet_zone": 2.0,
                    "background": "white",
                    "foreground": "black",
                },
            )
        except BarcodeError:
            return None
        except Exception as exc:
            raise ValueError(f"Não foi possível gerar o código de barras do item {value}.") from exc
        buffer.seek(0)
        return buffer

    @staticmethod
    def _wrapped_line_count(text: str, chars_per_line: int) -> int:
        """Linhas que o texto ocupa com quebra automática por palavra (como o Excel faz)."""
        if not text:
            return 0
        total = 0
        for paragraph in str(text).split("\n"):
            lines = 1
            current = 0
            for word in paragraph.split():
                if current == 0:
                    current = len(word)
                elif current + 1 + len(word) <= chars_per_line:
                    current += 1 + len(word)
                else:
                    lines += 1
                    current = len(word)
                while current > chars_per_line:  # palavra maior que a linha é partida
                    lines += 1
                    current -= chars_per_line
            total += lines
        return total

    @staticmethod
    def _category_name(item: dict[str, Any]) -> str:
        return " ".join(str(item.get("categoria") or "").split()) or "Sem categoria"

    @staticmethod
    def _group_items(
        items: list[dict[str, Any]],
        *,
        group_by_category: bool,
        category_order: Sequence[str],
    ) -> list[tuple[str | None, list[dict[str, Any]]]]:
        def by_description(row: dict[str, Any]) -> tuple[str, str]:
            return (str(row.get("descricao") or "").casefold(), str(row.get("codigo") or ""))

        if not group_by_category:
            return [(None, sorted(items, key=by_description))]

        groups: dict[str, tuple[str, list[dict[str, Any]]]] = {}
        for item in items:
            name = StockCountWorkbookService._category_name(item)
            groups.setdefault(name.casefold(), (name, []))[1].append(item)
        position = {str(name).casefold(): index for index, name in enumerate(category_order)}
        ordered_keys = sorted(groups, key=lambda key: (position.get(key, len(position)), key))
        return [(groups[key][0], sorted(groups[key][1], key=by_description)) for key in ordered_keys]

    @staticmethod
    def build(
        items: list[dict[str, Any]],
        *,
        scope_label: str | None = None,
        group_by_category: bool = False,
        category_order: Sequence[str] = (),
    ) -> BytesIO:
        """Planilha A4 de contagem.

        scope_label: linha abaixo do título dizendo o que a folha cobre ("Categoria: ...").
        group_by_category: uma faixa por categoria, cada uma começando em folha nova, para
        dividir a contagem entre pessoas; category_order dá a ordem das categorias.
        """
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Contagem de Estoque"
        sheet.sheet_view.showGridLines = False
        sheet.page_setup.orientation = "portrait"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_margins.left = 0.25
        sheet.page_margins.right = 0.25
        sheet.page_margins.top = 0.4
        sheet.page_margins.bottom = 0.4
        sheet.oddFooter.center.text = "Página &P de &N"
        sheet.oddFooter.center.size = 8
        sheet.column_dimensions["A"].width = 38
        sheet.column_dimensions["B"].width = 25
        sheet.column_dimensions["C"].width = 18
        sheet.column_dimensions["D"].width = 20

        border = Border(
            left=Side(style="thin", color="94A3B8"),
            right=Side(style="thin", color="94A3B8"),
            top=Side(style="thin", color="94A3B8"),
            bottom=Side(style="thin", color="94A3B8"),
        )
        title_fill = PatternFill(fill_type="solid", fgColor="0F172A")
        header_fill = PatternFill(fill_type="solid", fgColor="1D4ED8")
        current_row = 1

        sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)
        title = sheet.cell(row=current_row, column=1, value="CONFERÊNCIA FÍSICA DE ESTOQUE")
        title.fill = title_fill
        title.font = Font(bold=True, size=15, color="FFFFFF")
        title.alignment = Alignment(horizontal="center", vertical="center")
        sheet.row_dimensions[current_row].height = 28
        current_row += 1

        if scope_label:
            sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)
            scope = sheet.cell(row=current_row, column=1, value=scope_label)
            scope.font = Font(bold=True, size=11, color="0F172A")
            scope.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            sheet.row_dimensions[current_row].height = min(60, 20 + 14 * (math.ceil(len(scope_label) / 95) - 1))
            current_row += 1

        for line_index, line in enumerate(get_company_header_lines()):
            sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)
            company = sheet.cell(row=current_row, column=1, value=line)
            company.font = Font(size=9, bold=line_index == 0, color="334155")
            company.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            sheet.row_dimensions[current_row].height = 17
            current_row += 1

        sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)
        note = sheet.cell(
            row=current_row,
            column=1,
            value=f"Preencha FÍSICO à mão usando a unidade indicada em SISTEMA. Gerado em {TimeService.now_local():%d/%m/%Y %H:%M}.",
        )
        note.font = Font(size=8, italic=True, color="475569")
        note.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        sheet.row_dimensions[current_row].height = 23
        current_row += 1

        header_row = current_row
        headers = ["ITEM", "CÓDIGO DE BARRAS", "SISTEMA", "FÍSICO"]
        for column, label in enumerate(headers, start=1):
            cell = sheet.cell(row=header_row, column=column, value=label)
            cell.fill = header_fill
            cell.font = Font(bold=True, color="FFFFFF", size=9)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
        sheet.row_dimensions[header_row].height = 25
        current_row += 1

        groups = StockCountWorkbookService._group_items(
            items,
            group_by_category=group_by_category,
            category_order=category_order,
        )
        section_fill = PatternFill(fill_type="solid", fgColor="E2E8F0")
        row = current_row
        for group_index, (group_name, group_items) in enumerate(groups):
            if group_name is not None:
                if group_index > 0:
                    # Cada categoria em folha nova: dá para entregar cada maço a uma pessoa.
                    sheet.row_breaks.append(Break(id=row - 1))
                sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
                total_label = "1 item" if len(group_items) == 1 else f"{len(group_items)} itens"
                section = sheet.cell(row=row, column=1, value=f"{group_name.upper()}  ·  {total_label}")
                section.font = Font(bold=True, size=10, color="0F172A")
                section.alignment = Alignment(horizontal="left", vertical="center", indent=1)
                for column in range(1, 5):
                    sheet.cell(row=row, column=column).border = border
                    sheet.cell(row=row, column=column).fill = section_fill
                sheet.row_dimensions[row].height = 22
                row += 1
            for item_index, item in enumerate(group_items):
                StockCountWorkbookService._write_item_row(sheet, row, item, item_index, border)
                row += 1

        last_row = max(header_row, row - 1)
        sheet.freeze_panes = f"A{header_row + 1}"
        sheet.auto_filter.ref = f"A{header_row}:D{last_row}"
        sheet.print_title_rows = f"1:{header_row}"
        sheet.print_area = f"A1:D{last_row}"
        sheet.sheet_properties.pageSetUpPr.autoPageBreaks = False
        sheet.sheet_format.defaultRowHeight = 39
        sheet.sheet_view.zoomScale = 85

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return output

    @staticmethod
    def _write_item_row(sheet, row: int, item: dict[str, Any], item_index: int, border: Border) -> None:
        description = str(item.get("descricao") or "")
        system_balance = str(item.get("saldo_display") or item.get("saldo") or "0")
        item_cell = sheet.cell(row=row, column=1, value=description)
        item_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        system_cell = sheet.cell(row=row, column=3, value=system_balance)
        system_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        code_cell = sheet.cell(row=row, column=2)
        physical_cell = sheet.cell(row=row, column=4)
        physical_cell.alignment = Alignment(horizontal="center", vertical="center")
        for cell in (item_cell, code_cell, system_cell, physical_cell):
            cell.border = border
            if item_index % 2:
                cell.fill = PatternFill(fill_type="solid", fgColor="F8FAFC")

        code_text = ""
        barcode_buffer = None
        barcode_value = str(item.get("codigo") or "").strip()
        if barcode_value:
            barcode_buffer = StockCountWorkbookService._barcode_png(barcode_value)
            if barcode_buffer is None:
                # Code128 só aceita ASCII: código com acento (ex.: "LUVA LÁTEX") vai em texto,
                # para ser digitado na busca, em vez de derrubar a planilha inteira.
                code_text = f"{barcode_value}\n(sem código de barras: digite na busca)"
                code_cell.value = code_text
                code_cell.font = Font(size=8, color="B91C1C")
                code_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Quebra palavra por palavra: contar só letras cortava "8 caixas + 6 unidades |
        # Total: 134un" na impressão (36 letras = 2 linhas na conta, 3 no papel).
        wrapped_lines = max(
            2,
            StockCountWorkbookService._wrapped_line_count(description, ITEM_CHARS_PER_LINE),
            StockCountWorkbookService._wrapped_line_count(system_balance, SYSTEM_CHARS_PER_LINE),
            StockCountWorkbookService._wrapped_line_count(code_text, CODE_TEXT_CHARS_PER_LINE),
        )
        row_height_pt = min(MAX_ROW_HEIGHT_PT, max(MIN_ROW_HEIGHT_PT, wrapped_lines * LINE_HEIGHT_PT + 6))
        sheet.row_dimensions[row].height = row_height_pt

        if barcode_buffer is not None:
            # Centralizada na célula: colada no topo, a imagem cobria a linha da grade e o
            # Excel imprimia um fiapo dela no pé da página anterior.
            image = SpreadsheetImage(barcode_buffer)
            image.width = BARCODE_WIDTH_PX
            image.height = BARCODE_HEIGHT_PX
            top_gap_pt = max(3.0, (row_height_pt - BARCODE_HEIGHT_PX * 0.75) / 2)
            image.anchor = OneCellAnchor(
                _from=AnchorMarker(
                    col=1,
                    colOff=pixels_to_EMU(BARCODE_LEFT_GAP_PX),
                    row=row - 1,
                    rowOff=int(top_gap_pt * EMU_PER_POINT),
                ),
                ext=XDRPositiveSize2D(pixels_to_EMU(BARCODE_WIDTH_PX), pixels_to_EMU(BARCODE_HEIGHT_PX)),
            )
            sheet.add_image(image)
