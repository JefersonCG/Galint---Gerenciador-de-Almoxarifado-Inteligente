from __future__ import annotations

from io import BytesIO
import math
from typing import Any

from openpyxl import Workbook
from openpyxl.drawing.image import Image as SpreadsheetImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils.units import pixels_to_EMU

from ..utils.report_branding import get_company_header_lines
from ..utils.time_service import TimeService

BARCODE_WIDTH_PX = 160
BARCODE_HEIGHT_PX = 34
BARCODE_LEFT_GAP_PX = 10  # coluna B (largura 25) tem ~180 px
# Em ~42 mm impressos, 160 módulos dão ~0,26 mm por barra; acima disso o leitor falha.
# EAN-13 dá ~101 módulos; "BOMBA AUTOASPIRANTE" daria 244.
BARCODE_MAX_MODULES = 160
EMU_PER_POINT = 12700


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
    def build(items: list[dict[str, Any]]) -> BytesIO:
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

        for line in get_company_header_lines():
            sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)
            company = sheet.cell(row=current_row, column=1, value=line)
            company.font = Font(size=9, bold=current_row == 2, color="334155")
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

        sorted_items = sorted(
            items,
            key=lambda row: (str(row.get("descricao") or "").casefold(), str(row.get("codigo") or "")),
        )
        for item_index, item in enumerate(sorted_items):
            row = current_row + item_index
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

            wrapped_lines = max(
                2,
                math.ceil(len(description) / 38),
                math.ceil(len(system_balance) / 18),
                math.ceil(len(code_text) / 25),
            )
            row_height_pt = min(72, max(39, wrapped_lines * 13 + 8))
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

        last_row = max(header_row, current_row + len(sorted_items) - 1)
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
