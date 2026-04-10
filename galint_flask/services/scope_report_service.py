"""Serviço de geração de Relatório de Escopo - análise executiva multinível."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..models import Item


class ScopeReportService:
    """Geração de relatório executivo de escopo - análise multinível de categorias."""

    # Cores corporativas
    COLOR_HEADER = "1e3a8a"  # Azul escuro
    COLOR_SUBHEADER = "3b82f6"  # Azul médio
    COLOR_ACCENT = "06b6d4"  # Cyan
    COLOR_SUCCESS = "10b981"  # Verde
    COLOR_WARNING = "f59e0b"  # Laranja
    COLOR_DANGER = "ef4444"  # Vermelho
    COLOR_LIGHT = "f1f5f9"  # Cinza claro
    COLOR_WHITE = "ffffff"

    @classmethod
    def generate_executive_scope_report(cls, category_name: str | None = None) -> BytesIO:
        """Gera relatório executivo completo de escopo."""
        scope_category = cls._normalize_scope_category(category_name)
        scope_label = scope_category or "Geral"

        wb = Workbook()
        wb.remove(wb.active)  # Remove aba padrão

        # Coletar dados
        items = cls._collect_inventory_data(scope_category)
        if not items:
            if scope_category:
                raise ValueError(f"Nenhum item encontrado para a categoria '{scope_category}'.")
            raise ValueError("Nenhum item encontrado para gerar o relatório.")

        category_analysis = cls._analyze_by_category(items)
        brand_analysis = cls._analyze_by_brand(items)
        top_rankings = cls._generate_rankings(items)

        # Criar abas
        cls._create_executive_summary_sheet(wb, category_analysis, items, scope_label)
        cls._create_brand_analysis_sheet(wb, brand_analysis, scope_label)
        cls._create_rankings_sheet(wb, top_rankings, scope_label)
        cls._create_detailed_sheet(wb, items, scope_label)

        # Salvar em buffer
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer

    @classmethod
    def _normalize_scope_category(cls, category_name: str | None) -> str | None:
        normalized = (category_name or "").strip()
        return normalized or None

    @classmethod
    def _collect_inventory_data(cls, category_name: str | None = None) -> list[dict[str, Any]]:
        """Coleta dados do inventário com preços e movimentações."""
        scope_category = cls._normalize_scope_category(category_name)
        items_query = Item.query.order_by(Item.categoria.asc(), Item.descricao.asc()).all()

        result = []
        for item_obj in items_query:
            category_label = str(item_obj.categoria or "Sem categoria").strip() or "Sem categoria"
            if scope_category and category_label.casefold() != scope_category.casefold():
                continue

            # Calcular saldo e movimentações
            saldo = item_obj.get_saldo_fisico_total()
            total_entradas = sum(e.quantidade for e in item_obj.entradas) if item_obj.entradas else 0
            total_saidas = sum(s.quantidade for s in item_obj.saidas) if item_obj.saidas else 0

            # Determinar preço e origem
            preco_real = None
            preco_estimado = None
            origem_preco = "Sem preço"
            preco_compra_base = item_obj.preco_compra_unitario_base or item_obj.preco_compra_unitario
            preco_reposicao_base = item_obj.preco_reposicao_unitario_base or item_obj.preco_reposicao_unitario

            if preco_compra_base and preco_compra_base > 0:
                if item_obj.preco_compra_documento:
                    preco_real = preco_compra_base
                    origem_preco = f"NF/Cupom: {item_obj.preco_compra_documento}"
                else:
                    preco_estimado = preco_compra_base
                    fonte_compra = (item_obj.preco_compra_fonte or "cadastro manual").strip()
                    origem_preco = f"Estimado ({fonte_compra})"

            elif preco_reposicao_base and preco_reposicao_base > 0:
                preco_estimado = preco_reposicao_base
                fonte = item_obj.preco_reposicao_fonte or "Desconhecida"
                origem_preco = f"Especulativo ({fonte})"

            # Valor total em estoque
            valor_total_real = (preco_real or 0) * saldo if preco_real else 0
            valor_total_estimado = (preco_estimado or 0) * saldo if preco_estimado else 0

            result.append({
                "codigo": item_obj.codigo_item,
                "descricao": item_obj.descricao or "",
                "categoria": category_label,
                "marca": item_obj.marca or "",
                "unidade": item_obj.unidade or "un",
                "saldo": saldo,
                "total_entradas": total_entradas,
                "total_saidas": total_saidas,
                "preco_real": preco_real,
                "preco_estimado": preco_estimado,
                "origem_preco": origem_preco,
                "valor_total_real": valor_total_real,
                "valor_total_estimado": valor_total_estimado,
                "url_fonte": item_obj.preco_reposicao_url or "",
            })

        return result

    @classmethod
    def _analyze_by_category(cls, items: list[dict]) -> dict[str, dict]:
        """Analisa itens agrupados por categoria."""
        categories = {}
        for item in items:
            cat = item["categoria"]
            if cat not in categories:
                categories[cat] = {
                    "total_itens": 0,
                    "total_saldo": 0,
                    "valor_real": 0,
                    "valor_estimado": 0,
                    "itens_com_marca": 0,
                    "itens_sem_marca": 0,
                    "total_entradas": 0,
                    "total_saidas": 0,
                }

            categories[cat]["total_itens"] += 1
            categories[cat]["total_saldo"] += item["saldo"]
            categories[cat]["valor_real"] += item["valor_total_real"]
            categories[cat]["valor_estimado"] += item["valor_total_estimado"]
            categories[cat]["total_entradas"] += item["total_entradas"]
            categories[cat]["total_saidas"] += item["total_saidas"]

            if item["marca"]:
                categories[cat]["itens_com_marca"] += 1
            else:
                categories[cat]["itens_sem_marca"] += 1

        return categories

    @classmethod
    def _analyze_by_brand(cls, items: list[dict]) -> dict[str, dict]:
        """Analisa itens agrupados por categoria e marca."""
        brands = {}
        for item in items:
            cat = item["categoria"]
            marca = item["marca"] or "Sem marca"
            key = f"{cat}||{marca}"

            if key not in brands:
                brands[key] = {
                    "categoria": cat,
                    "marca": marca,
                    "total_itens": 0,
                    "valor_real": 0,
                    "valor_estimado": 0,
                }

            brands[key]["total_itens"] += 1
            brands[key]["valor_real"] += item["valor_total_real"]
            brands[key]["valor_estimado"] += item["valor_total_estimado"]

        return brands

    @classmethod
    def _generate_rankings(cls, items: list[dict]) -> dict[str, list[dict]]:
        """Gera rankings top 10."""
        # Mais caros (por valor total em estoque)
        mais_caros = sorted(
            [i for i in items if i["valor_total_real"] + i["valor_total_estimado"] > 0],
            key=lambda x: x["valor_total_real"] + x["valor_total_estimado"],
            reverse=True
        )[:10]

        # Maior quantidade em estoque
        maior_quantidade = sorted(
            [i for i in items if i["saldo"] > 0],
            key=lambda x: x["saldo"],
            reverse=True
        )[:10]

        # Mais movimentados (saídas)
        mais_usados = sorted(
            [i for i in items if i["total_saidas"] > 0],
            key=lambda x: x["total_saidas"],
            reverse=True
        )[:10]

        return {
            "mais_caros": mais_caros,
            "maior_quantidade": maior_quantidade,
            "mais_usados": mais_usados,
        }

    @classmethod
    def _create_executive_summary_sheet(cls, wb: Workbook, category_analysis: dict, items: list[dict], scope_label: str):
        """Cria aba de Resumo Executivo."""
        ws = wb.create_sheet("Resumo Executivo")

        # Título
        ws.merge_cells("A1:H1")
        cell = ws["A1"]
        cell.value = "RELATÓRIO DE ESCOPO - ANÁLISE EXECUTIVA DE CATEGORIAS"
        cell.font = Font(size=16, bold=True, color=cls.COLOR_WHITE)
        cell.fill = PatternFill(start_color=cls.COLOR_HEADER, end_color=cls.COLOR_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 30

        # Timestamp e totais gerais
        now = datetime.now().strftime("%d/%m/%Y às %H:%M")
        ws["A2"] = f"Escopo selecionado: {scope_label}"
        ws["A2"].font = Font(size=10, bold=True, color=cls.COLOR_HEADER)
        ws["A3"] = f"Gerado em: {now}"
        ws["A3"].font = Font(size=10, italic=True)

        total_valor_real = sum(c["valor_real"] for c in category_analysis.values())
        total_valor_estimado = sum(c["valor_estimado"] for c in category_analysis.values())
        total_itens = len(items)

        ws["A4"] = f"Total de itens: {total_itens}"
        ws["A5"] = f"Valor total bruto (documentado): R$ {total_valor_real:,.2f}"
        ws["A6"] = f"Valor total estimado/especulativo: R$ {total_valor_estimado:,.2f}"
        ws["A7"] = f"Valor total geral: R$ {total_valor_real + total_valor_estimado:,.2f}"

        for row in range(4, 8):
            ws[f"A{row}"].font = Font(size=11, bold=True)

        # Cabeçalho da tabela
        headers = [
            "Categoria",
            "Itens",
            "Com Marca",
            "Sem Marca",
            "Saldo Total",
            "Valor Real (R$)",
            "Valor Estimado (R$)",
            "Valor Total (R$)",
        ]

        header_row = 9
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=header_row, column=col_num)
            cell.value = header
            cell.font = Font(bold=True, color=cls.COLOR_WHITE)
            cell.fill = PatternFill(start_color=cls.COLOR_SUBHEADER, end_color=cls.COLOR_SUBHEADER, fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = Border(
                left=Side(style="thin"),
                right=Side(style="thin"),
                top=Side(style="thin"),
                bottom=Side(style="thin"),
            )

        # Dados
        row_num = header_row + 1
        for cat_name, data in sorted(category_analysis.items()):
            valor_total = data["valor_real"] + data["valor_estimado"]
            ws.cell(row=row_num, column=1, value=cat_name)
            ws.cell(row=row_num, column=2, value=data["total_itens"])
            ws.cell(row=row_num, column=3, value=data["itens_com_marca"])
            ws.cell(row=row_num, column=4, value=data["itens_sem_marca"])
            ws.cell(row=row_num, column=5, value=f'{data["total_saldo"]:.2f}')
            ws.cell(row=row_num, column=6, value=data["valor_real"]).number_format = '"R$" #,##0.00'
            ws.cell(row=row_num, column=7, value=data["valor_estimado"]).number_format = '"R$" #,##0.00'
            ws.cell(row=row_num, column=8, value=valor_total).number_format = '"R$" #,##0.00'

            # Bordas
            for col in range(1, 9):
                ws.cell(row=row_num, column=col).border = Border(
                    left=Side(style="thin"),
                    right=Side(style="thin"),
                    top=Side(style="thin"),
                    bottom=Side(style="thin"),
                )

            # Alinhamento
            ws.cell(row=row_num, column=1).alignment = Alignment(horizontal="left")
            for col in range(2, 9):
                ws.cell(row=row_num, column=col).alignment = Alignment(horizontal="right")

            row_num += 1

        # Legenda
        legend_row = row_num + 2
        ws.merge_cells(f"A{legend_row}:H{legend_row}")
        ws[f"A{legend_row}"] = "LEGENDA:"
        ws[f"A{legend_row}"].font = Font(size=12, bold=True, color=cls.COLOR_HEADER)

        ws[f"A{legend_row + 1}"] = "• Valor Real: Preços documentados via NF/cupom fiscal"
        ws[f"A{legend_row + 2}"] = "• Valor Estimado: Preços especulativos (cotações, cadastro manual, fontes web)"
        ws[f"A{legend_row + 3}"] = "• Valor Total: Soma do valor real + estimado (inventário bruto)"

        for i in range(4):
            ws[f"A{legend_row + i}"].font = Font(size=10, italic=True)

        # Ajustar larguras
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 10
        ws.column_dimensions["C"].width = 12
        ws.column_dimensions["D"].width = 12
        ws.column_dimensions["E"].width = 14
        ws.column_dimensions["F"].width = 18
        ws.column_dimensions["G"].width = 20
        ws.column_dimensions["H"].width = 18

    @classmethod
    def _create_brand_analysis_sheet(cls, wb: Workbook, brand_analysis: dict, scope_label: str):
        """Cria aba de Análise por Marca."""
        ws = wb.create_sheet("Análise por Marca")

        # Título
        ws.merge_cells("A1:E1")
        cell = ws["A1"]
        cell.value = "ANÁLISE DE CATEGORIAS POR MARCA"
        cell.font = Font(size=14, bold=True, color=cls.COLOR_WHITE)
        cell.fill = PatternFill(start_color=cls.COLOR_HEADER, end_color=cls.COLOR_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 25
        ws["A2"] = f"Escopo selecionado: {scope_label}"
        ws["A2"].font = Font(size=10, bold=True, color=cls.COLOR_HEADER)

        # Cabeçalho
        headers = ["Categoria", "Marca", "Qtd Itens", "Valor Real (R$)", "Valor Estimado (R$)"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_num)
            cell.value = header
            cell.font = Font(bold=True, color=cls.COLOR_WHITE)
            cell.fill = PatternFill(start_color=cls.COLOR_SUBHEADER, end_color=cls.COLOR_SUBHEADER, fill_type="solid")
            cell.alignment = Alignment(horizontal="center")

        # Dados
        row_num = 5
        for data in sorted(brand_analysis.values(), key=lambda x: (x["categoria"], x["marca"])):
            ws.cell(row=row_num, column=1, value=data["categoria"])
            ws.cell(row=row_num, column=2, value=data["marca"])
            ws.cell(row=row_num, column=3, value=data["total_itens"])
            ws.cell(row=row_num, column=4, value=data["valor_real"]).number_format = '"R$" #,##0.00'
            ws.cell(row=row_num, column=5, value=data["valor_estimado"]).number_format = '"R$" #,##0.00'
            row_num += 1

        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 25
        ws.column_dimensions["C"].width = 12
        ws.column_dimensions["D"].width = 18
        ws.column_dimensions["E"].width = 20

    @classmethod
    def _create_rankings_sheet(cls, wb: Workbook, rankings: dict, scope_label: str):
        """Cria aba de Rankings Top 10."""
        ws = wb.create_sheet("Rankings Top 10")

        # Título
        ws.merge_cells("A1:F1")
        cell = ws["A1"]
        cell.value = "RANKINGS DE DESEMPENHO - TOP 10"
        cell.font = Font(size=14, bold=True, color=cls.COLOR_WHITE)
        cell.fill = PatternFill(start_color=cls.COLOR_HEADER, end_color=cls.COLOR_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 25
        ws["A2"] = f"Escopo selecionado: {scope_label}"
        ws["A2"].font = Font(size=10, bold=True, color=cls.COLOR_HEADER)

        current_row = 4

        # 1. Mais Caros
        ws.merge_cells(f"A{current_row}:F{current_row}")
        ws[f"A{current_row}"] = "TOP 10 MAIS CAROS (por valor total em estoque)"
        ws[f"A{current_row}"].font = Font(size=12, bold=True, color=cls.COLOR_DANGER)
        current_row += 1

        most_expensive_header_row = current_row
        headers = ["#", "Código", "Descrição", "Categoria", "Marca", "Valor Total (R$)"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num)
            cell.value = header
            cell.font = Font(bold=True, size=10)
            cell.fill = PatternFill(start_color=cls.COLOR_LIGHT, end_color=cls.COLOR_LIGHT, fill_type="solid")
        current_row += 1

        most_expensive_start_row = current_row
        for idx, item in enumerate(rankings["mais_caros"], 1):
            valor_total = item["valor_total_real"] + item["valor_total_estimado"]
            ws.cell(row=current_row, column=1, value=idx)
            ws.cell(row=current_row, column=2, value=item["codigo"])
            ws.cell(row=current_row, column=3, value=item["descricao"])
            ws.cell(row=current_row, column=4, value=item["categoria"])
            ws.cell(row=current_row, column=5, value=item["marca"] or "N/D")
            ws.cell(row=current_row, column=6, value=valor_total).number_format = '"R$" #,##0.00'
            current_row += 1

        most_expensive_end_row = current_row - 1
        cls._add_ranking_chart(
            ws=ws,
            title="Itens mais caros",
            header_row=most_expensive_header_row,
            category_col=3,
            value_col=6,
            data_start_row=most_expensive_start_row,
            data_end_row=most_expensive_end_row,
            anchor="H3",
            color=cls.COLOR_DANGER,
            value_axis_title="Valor total em estoque (R$)",
        )

        current_row += 2

        # 2. Maior Quantidade
        ws.merge_cells(f"A{current_row}:F{current_row}")
        ws[f"A{current_row}"] = "TOP 10 MAIOR QUANTIDADE EM ESTOQUE"
        ws[f"A{current_row}"].font = Font(size=12, bold=True, color=cls.COLOR_WARNING)
        current_row += 1

        quantity_header_row = current_row
        headers = ["#", "Código", "Descrição", "Categoria", "Unidade", "Saldo"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num)
            cell.value = header
            cell.font = Font(bold=True, size=10)
            cell.fill = PatternFill(start_color=cls.COLOR_LIGHT, end_color=cls.COLOR_LIGHT, fill_type="solid")
        current_row += 1

        quantity_start_row = current_row
        for idx, item in enumerate(rankings["maior_quantidade"], 1):
            ws.cell(row=current_row, column=1, value=idx)
            ws.cell(row=current_row, column=2, value=item["codigo"])
            ws.cell(row=current_row, column=3, value=item["descricao"])
            ws.cell(row=current_row, column=4, value=item["categoria"])
            ws.cell(row=current_row, column=5, value=item["unidade"])
            ws.cell(row=current_row, column=6, value=item["saldo"]).number_format = "#,##0.00"
            current_row += 1

        quantity_end_row = current_row - 1
        cls._add_ranking_chart(
            ws=ws,
            title="Itens com maior quantidade",
            header_row=quantity_header_row,
            category_col=3,
            value_col=6,
            data_start_row=quantity_start_row,
            data_end_row=quantity_end_row,
            anchor=f"H{quantity_header_row - 1}",
            color=cls.COLOR_WARNING,
            value_axis_title="Saldo em estoque",
        )

        current_row += 2

        # 3. Mais Usados
        ws.merge_cells(f"A{current_row}:F{current_row}")
        ws[f"A{current_row}"] = "TOP 10 MAIS UTILIZADOS (saídas acumuladas)"
        ws[f"A{current_row}"].font = Font(size=12, bold=True, color=cls.COLOR_SUCCESS)
        current_row += 1

        usage_header_row = current_row
        headers = ["#", "Código", "Descrição", "Categoria", "Unidade", "Total Saídas"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num)
            cell.value = header
            cell.font = Font(bold=True, size=10)
            cell.fill = PatternFill(start_color=cls.COLOR_LIGHT, end_color=cls.COLOR_LIGHT, fill_type="solid")
        current_row += 1

        usage_start_row = current_row
        for idx, item in enumerate(rankings["mais_usados"], 1):
            ws.cell(row=current_row, column=1, value=idx)
            ws.cell(row=current_row, column=2, value=item["codigo"])
            ws.cell(row=current_row, column=3, value=item["descricao"])
            ws.cell(row=current_row, column=4, value=item["categoria"])
            ws.cell(row=current_row, column=5, value=item["unidade"])
            ws.cell(row=current_row, column=6, value=item["total_saidas"]).number_format = "#,##0.00"
            current_row += 1

        usage_end_row = current_row - 1
        cls._add_ranking_chart(
            ws=ws,
            title="Itens mais utilizados",
            header_row=usage_header_row,
            category_col=3,
            value_col=6,
            data_start_row=usage_start_row,
            data_end_row=usage_end_row,
            anchor=f"H{usage_header_row - 1}",
            color=cls.COLOR_SUCCESS,
            value_axis_title="Saídas acumuladas",
        )

        # Ajustar larguras
        ws.column_dimensions["A"].width = 5
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 45
        ws.column_dimensions["D"].width = 25
        ws.column_dimensions["E"].width = 15
        ws.column_dimensions["F"].width = 18
        ws.column_dimensions["H"].width = 2
        ws.column_dimensions["I"].width = 14
        ws.column_dimensions["J"].width = 14
        ws.column_dimensions["K"].width = 14
        ws.column_dimensions["L"].width = 14
        ws.column_dimensions["M"].width = 14
        ws.column_dimensions["N"].width = 14

    @classmethod
    def _add_ranking_chart(
        cls,
        ws,
        title: str,
        header_row: int,
        category_col: int,
        value_col: int,
        data_start_row: int,
        data_end_row: int,
        anchor: str,
        color: str,
        value_axis_title: str,
    ):
        """Adiciona gráfico horizontal para um ranking top 10."""
        if data_end_row < data_start_row:
            return

        data = Reference(ws, min_col=value_col, min_row=header_row, max_row=data_end_row)
        categories = Reference(ws, min_col=category_col, min_row=data_start_row, max_row=data_end_row)

        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = title
        chart.grouping = "clustered"
        chart.overlap = 0
        chart.height = 7.5
        chart.width = 13.5
        chart.y_axis.title = "Itens"
        chart.x_axis.title = value_axis_title
        chart.legend = None

        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)

        if chart.series:
            series = chart.series[0]
            series.graphicalProperties.solidFill = color
            series.graphicalProperties.line.solidFill = color

        chart.dataLabels = DataLabelList()
        chart.dataLabels.showVal = True

        ws.add_chart(chart, anchor)

    @classmethod
    def _create_detailed_sheet(cls, wb: Workbook, items: list[dict], scope_label: str):
        """Cria aba de Detalhamento Completo."""
        ws = wb.create_sheet("Detalhamento Completo")

        # Título
        ws.merge_cells("A1:J1")
        cell = ws["A1"]
        cell.value = "DETALHAMENTO COMPLETO - TODOS OS ITENS"
        cell.font = Font(size=14, bold=True, color=cls.COLOR_WHITE)
        cell.fill = PatternFill(start_color=cls.COLOR_HEADER, end_color=cls.COLOR_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 25
        ws["A2"] = f"Escopo selecionado: {scope_label}"
        ws["A2"].font = Font(size=10, bold=True, color=cls.COLOR_HEADER)

        # Cabeçalho
        headers = [
            "Código",
            "Descrição",
            "Categoria",
            "Marca",
            "Unidade",
            "Saldo",
            "Preço Real",
            "Preço Estimado",
            "Valor Total",
            "Origem do Preço",
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_num)
            cell.value = header
            cell.font = Font(bold=True, size=10, color=cls.COLOR_WHITE)
            cell.fill = PatternFill(start_color=cls.COLOR_SUBHEADER, end_color=cls.COLOR_SUBHEADER, fill_type="solid")
            cell.alignment = Alignment(horizontal="center")

        # Dados
        row_num = 5
        for item in sorted(items, key=lambda x: (x["categoria"], x["descricao"])):
            valor_total = item["valor_total_real"] + item["valor_total_estimado"]

            ws.cell(row=row_num, column=1, value=item["codigo"])
            ws.cell(row=row_num, column=2, value=item["descricao"])
            ws.cell(row=row_num, column=3, value=item["categoria"])
            ws.cell(row=row_num, column=4, value=item["marca"] or "N/D")
            ws.cell(row=row_num, column=5, value=item["unidade"])
            ws.cell(row=row_num, column=6, value=item["saldo"]).number_format = "#,##0.00"
            ws.cell(row=row_num, column=7, value=item["preco_real"] or 0).number_format = '"R$" #,##0.00'
            ws.cell(row=row_num, column=8, value=item["preco_estimado"] or 0).number_format = '"R$" #,##0.00'
            ws.cell(row=row_num, column=9, value=valor_total).number_format = '"R$" #,##0.00'
            ws.cell(row=row_num, column=10, value=item["origem_preco"])

            row_num += 1

        # Ajustar larguras
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 50
        ws.column_dimensions["C"].width = 25
        ws.column_dimensions["D"].width = 22
        ws.column_dimensions["E"].width = 10
        ws.column_dimensions["F"].width = 12
        ws.column_dimensions["G"].width = 15
        ws.column_dimensions["H"].width = 18
        ws.column_dimensions["I"].width = 15
        ws.column_dimensions["J"].width = 35
