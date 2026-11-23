"""Relatórios em PDF e Excel (report_export_service) e as rotas do app /api/mobile/relatorios/*.

Pedido do usuário em 23/11/2026: compartilhar os relatórios no WhatsApp em PDF e XLS e PDFs com as
células legíveis. Os testes usam SQLite em memória com as tabelas de saída, item, usuário e evento.
"""
from datetime import date, datetime
from io import BytesIO

import openpyxl
import pytest
from flask import Flask

from galint_flask.extensions import db
from galint_flask.models import InventarioEvento, Item, Saida, Usuario
from galint_flask.services import report_export_service as rs
from galint_flask.views import api_mobile

TABLES = [Item.__table__, Usuario.__table__, Saida.__table__, InventarioEvento.__table__]
LONG = "DISJUNTOR TERMOMAGNÉTICO BIPOLAR 2X40A CURVA C TRILHO DIN 35MM PARA QUADRO DE DISTRIBUIÇÃO DO BLOCO C"


class _Admin:
    matricula = "adm-1"
    nome = "Administrador"
    is_admin = 1


class _Operador(_Admin):
    matricula = "op-1"
    is_admin = 0


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="report-export-test",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GALINT_DISABLE_BACKGROUND_SERVICES=True,
    )
    app.register_blueprint(api_mobile.blueprint)
    users = {"adm": _Admin, "op": _Operador}
    monkeypatch.setattr(api_mobile, "get_mobile_user", lambda token: users[token]() if token in users else None)
    monkeypatch.setattr(api_mobile, "_mobile_user_block_info", lambda user: (False, None))
    monkeypatch.setattr(api_mobile, "_validate_mobile_session_token", lambda token, user: (True, None))
    with app.app_context():
        db.init_app(app)
        db.metadata.create_all(bind=db.engine, tables=TABLES)
        db.session.add_all([
            Item(codigo_item="7896451824813", descricao=LONG, categoria="Material Elétrico", unidade="Unidade", setor="Estoque"),
            Item(codigo_item="FER-1", descricao="FURADEIRA DE IMPACTO", categoria="Ferramentas Elétricas", unidade="Unidade", setor="Estoque"),
            Usuario(matricula="1001", nome="MARIA APARECIDA DOS SANTOS OLIVEIRA"),
        ])
        db.session.flush()

        def saida(code, when, qty=1.0, obs=None, local=None):
            db.session.add(Saida(codigo_item=code, matricula="1001", data_saida=when, quantidade=qty, observacao=obs, local_servico=local))

        # Datas na hora de São Paulo sem fuso, como o banco grava (TimeService.now_db).
        saida("7896451824813", datetime(2026, 11, 22, 23, 59))  # ontem: fora do dia 23
        saida("7896451824813", datetime(2026, 11, 23, 0, 30), 2.5, "UNIDADE=UNIDADE;QTD_ORIGINAL=1", "BLOCO C")
        saida("FER-1", datetime(2026, 11, 23, 23, 50), 1, "Troca no quadro", "PORTARIA")
        saida("7896451824813", datetime(2026, 11, 30, 22, 0), 1)  # último dia do mês, à noite
        saida("7896451824813", datetime(2026, 12, 1, 0, 10), 1)  # mês seguinte
        db.session.add(InventarioEvento(codigo_item="FER-1", matricula="1001", tipo="devolucao_ferramenta", quantidade=1, data_evento=datetime(2026, 11, 23, 18, 0)))
        db.session.commit()
        yield app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=TABLES)


def _sheet_values(content: bytes) -> dict[str, list[list]]:
    book = openpyxl.load_workbook(BytesIO(content))
    return {sheet.title: [list(row) for row in sheet.iter_rows(values_only=True)] for sheet in book.worksheets}


def test_daily_report_uses_the_local_day_and_cleans_the_observation(app):
    report = rs.daily_report(date(2026, 11, 23))

    withdrawals = report.sections[0].rows
    assert [row[0] for row in withdrawals] == [datetime(2026, 11, 23, 0, 30), datetime(2026, 11, 23, 23, 50)]
    assert withdrawals[0][6] == "BLOCO C"  # sem "UNIDADE=UNIDADE;QTD_ORIGINAL=1"
    assert withdrawals[1][6] == "PORTARIA · Troca no quadro"
    assert dict(report.summary)["Devoluções"] == "1"
    assert report.sections[1].rows[0][1] == "FER-1"


def test_daily_report_scope_keeps_only_tools(app):
    report = rs.daily_report(date(2026, 11, 23), "tools")

    assert [row[1] for row in report.sections[0].rows] == ["FER-1"]
    assert report.scope == "Ferramentas"


def test_monthly_report_counts_the_last_evening_and_has_the_right_title(app):
    report = rs.monthly_report(2026, 11)

    assert report.title == "Saídas do mês"
    assert report.period == "Novembro de 2026"
    dates = [row[0] for row in report.sections[1].rows]
    assert datetime(2026, 11, 30, 22, 0) in dates
    assert datetime(2026, 12, 1, 0, 10) not in dates
    totals = {row[0]: row for row in report.sections[0].rows}
    assert totals["7896451824813"][2] == 4.5  # 22/11 (1) + 23/11 (2,5) + 30/11 (1)


def test_xlsx_keeps_full_text_and_real_numbers(app):
    sheets = _sheet_values(rs.monthly_report(2026, 11).render("xlsx"))

    assert list(sheets) == ["Total por item", "Saídas"]
    rows = sheets["Saídas"]
    header = rows.index(["Data", "Código", "Descrição", "Categoria", "Qtd", "Un.", "Colaborador", "Local / observação"])
    first = rows[header + 1]
    assert first[2] == LONG  # sem corte em 24 letras
    assert isinstance(first[0], datetime)
    assert first[4] == 1
    assert first[1] == "7896451824813"  # código fica texto (sem notação científica)


def test_pdf_builds_with_long_words_and_page_count(app):
    content = rs.daily_report(date(2026, 11, 23)).render("pdf")

    assert content.startswith(b"%PDF")
    assert b"/Count 1" in content


def test_money_and_quantity_format():
    assert rs.fmt_money(123456.789) == "R$ 123.456,79"
    assert rs.fmt_qty(2.5) == "2,5"
    assert rs.fmt_qty(1200) == "1.200"


def test_route_summary_and_files(app):
    client = app.test_client()
    auth = {"Authorization": "Bearer adm"}

    summary = client.get("/api/mobile/relatorios/dia", query_string={"data": "2026-11-23"}, headers=auth)
    data = summary.get_json()["data"]
    assert summary.status_code == 200
    assert data["titulo"] == "Saídas do dia"
    assert data["total_linhas"] == 2
    assert data["linhas"][0]["titulo"] == LONG

    pdf = client.get("/api/mobile/relatorios/dia", query_string={"data": "2026-11-23", "formato": "pdf"}, headers=auth)
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
    assert "saidas-2026-11-23-tudo.pdf" in pdf.headers["Content-Disposition"]

    xlsx = client.get("/api/mobile/relatorios/mes", query_string={"ano": 2026, "mes": 11, "formato": "xlsx"}, headers=auth)
    assert xlsx.status_code == 200
    assert xlsx.mimetype == rs.FORMATS["xlsx"]
    assert "Saídas" in _sheet_values(xlsx.data)


def test_route_rejects_non_admin_and_bad_input(app):
    client = app.test_client()

    assert client.get("/api/mobile/relatorios/dia", headers={"Authorization": "Bearer op"}).status_code == 403
    bad = client.get("/api/mobile/relatorios/mes", query_string={"mes": 13}, headers={"Authorization": "Bearer adm"})
    assert bad.status_code == 400
    assert client.get("/api/mobile/relatorios/outro", headers={"Authorization": "Bearer adm"}).status_code == 400


def test_old_app_route_still_answers_with_the_new_pdf(app):
    client = app.test_client()

    response = client.get("/api/mobile/reports/daily", query_string={"scope": "all"}, headers={"Authorization": "Bearer adm"})
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF")
