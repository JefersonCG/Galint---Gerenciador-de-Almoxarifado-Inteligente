from datetime import datetime

from galint_flask import create_app
from galint_flask.services.analytics_service import AnalyticsService
from galint_flask.services.finance_service import FinanceService
from galint_flask.services import entrada_report_service as entrada_report_service_module
from galint_flask.services.inventory import inventory_service
from galint_flask.views import dashboard as dashboard_view


def test_finance_service_excludes_tools_from_consumption_analytics():
    rows = [
        {"codigo_item": "M-10", "descricao_item": "Cimento", "categoria": "Materiais", "valor_total": 120.0, "quantidade_base": 10, "data_saida": datetime(2026, 8, 1, 8, 0), "saida_id": 1},
        {"codigo_item": "T-10", "descricao_item": "Martelo", "categoria": "Ferramentas", "valor_total": 80.0, "quantidade_base": 1, "data_saida": datetime(2026, 8, 2, 8, 0), "saida_id": 2},
    ]

    summary = FinanceService._aggregate_consumption_entries(rows)

    assert summary["overview"]["total_valor"] == 120.0
    assert summary["overview"]["saidas"] == 1
    assert all(row["categoria"] != "Ferramentas" for row in summary["categories"])


def test_build_projection_cards_identifies_stock_exhaustion_day():
    exit_rows = [
        {"codigo_item": "F-100", "descricao_item": "Martelo", "categoria": "Ferramentas", "quantidade_base": 2, "data_saida": datetime(2026, 8, 1, 8, 0)},
        {"codigo_item": "F-100", "descricao_item": "Martelo", "categoria": "Ferramentas", "quantidade_base": 3, "data_saida": datetime(2026, 8, 3, 8, 0)},
        {"codigo_item": "F-100", "descricao_item": "Martelo", "categoria": "Ferramentas", "quantidade_base": 2, "data_saida": datetime(2026, 8, 5, 8, 0)},
        {"codigo_item": "F-100", "descricao_item": "Martelo", "categoria": "Ferramentas", "quantidade_base": 4, "data_saida": datetime(2026, 8, 7, 8, 0)},
    ]
    stock_snapshot = {"resumo": [{"codigo": "F-100", "saldo": 7.0, "descricao": "Martelo", "status": "OK"}]}

    cards = AnalyticsService.build_projection_cards(exit_rows, stock_snapshot)

    consumo = next(card for card in cards if card["type"] == "consumo_ferramentas")
    assert consumo["item"] == "Martelo"
    assert consumo["codigo"] == "F-100"
    assert consumo["status"] == "em_atenção"
    assert consumo["date"]


def test_build_projection_cards_predicts_future_damage_and_degradation():
    exit_rows = [
        {"codigo_item": "F-200", "descricao_item": "Chave inglesa", "categoria": "Ferramentas", "quantidade_base": 1, "data_saida": datetime(2026, 8, 1, 8, 0), "is_loss_damage": True, "loss_damage_kind": "quebrada"},
        {"codigo_item": "F-200", "descricao_item": "Chave inglesa", "categoria": "Ferramentas", "quantidade_base": 1, "data_saida": datetime(2026, 8, 4, 8, 0), "is_loss_damage": True, "loss_damage_kind": "quebrada"},
        {"codigo_item": "F-200", "descricao_item": "Chave inglesa", "categoria": "Ferramentas", "quantidade_base": 1, "data_saida": datetime(2026, 8, 7, 8, 0), "is_loss_damage": True, "loss_damage_kind": "quebrada"},
        {"codigo_item": "F-300", "descricao_item": "Serra circular", "categoria": "Ferramentas", "quantidade_base": 2, "data_saida": datetime(2026, 8, 1, 8, 0), "is_loss_damage": False},
        {"codigo_item": "F-300", "descricao_item": "Serra circular", "categoria": "Ferramentas", "quantidade_base": 2, "data_saida": datetime(2026, 8, 4, 8, 0), "is_loss_damage": False},
    ]
    stock_snapshot = {"resumo": [{"codigo": "F-200", "saldo": 6.0, "descricao": "Chave inglesa", "status": "OK"}, {"codigo": "F-300", "saldo": 12.0, "descricao": "Serra circular", "status": "OK"}]}

    cards = AnalyticsService.build_projection_cards(exit_rows, stock_snapshot)

    perdas = next(card for card in cards if card["type"] == "perdas_avarias_futuras")
    degradacao = next(card for card in cards if card["type"] == "degradacao_ferramentas")

    assert perdas["item"] == "Chave inglesa"
    assert perdas["projected_count"] >= 0
    assert degradacao["item"] in {"Chave inglesa", "Serra circular"}


def test_build_projection_cards_includes_entry_date_and_photo():
    exit_rows = [
        {"codigo_item": "F-100", "descricao_item": "Martelo", "categoria": "Ferramentas", "quantidade_base": 2, "data_saida": datetime(2026, 8, 1, 8, 0)},
        {"codigo_item": "F-100", "descricao_item": "Martelo", "categoria": "Ferramentas", "quantidade_base": 3, "data_saida": datetime(2026, 8, 3, 8, 0)},
        {"codigo_item": "F-100", "descricao_item": "Martelo", "categoria": "Ferramentas", "quantidade_base": 2, "data_saida": datetime(2026, 8, 5, 8, 0)},
        {"codigo_item": "F-100", "descricao_item": "Martelo", "categoria": "Ferramentas", "quantidade_base": 4, "data_saida": datetime(2026, 8, 7, 8, 0)},
    ]
    stock_snapshot = {
        "resumo": [{
            "codigo": "F-100",
            "saldo": 7.0,
            "descricao": "Martelo",
            "status": "OK",
            "data_entrada": "2026-07-01",
            "foto_path": "images/ferramentas/martelo.jpg",
        }]
    }

    cards = AnalyticsService.build_projection_cards(exit_rows, stock_snapshot)
    consumo = next(card for card in cards if card["type"] == "consumo_ferramentas")

    assert consumo["entry_date"] == "01/07/2026"
    assert consumo["negative_date"]
    assert consumo["photo_url"] == "/static/images/ferramentas/martelo.jpg"


def test_dashboard_context_exposes_projection_cards(monkeypatch):
    app = create_app()
    with app.app_context():
        monkeypatch.setattr(inventory_service, "dashboard_snapshot", lambda: {
            "resumo": [{"codigo": "F-100", "saldo": 7.0, "status": "OK", "descricao": "Martelo"}],
            "total_quantity": 7,
            "category_summary": [],
        })
        monkeypatch.setattr(dashboard_view.category_catalog_service, "list_visual_catalog", lambda include_inactive=True: [])
        monkeypatch.setattr(entrada_report_service_module.entrada_report_service, "get_ultimo_ciclo_gerado", lambda: 4)
        monkeypatch.setattr(entrada_report_service_module.entrada_report_service, "CONTADOR_CICLO", 10)
        monkeypatch.setattr(dashboard_view.analytics_service, "get_dashboard_payload", lambda **kwargs: {
            "projection_cards": [{
                "type": "consumo_ferramentas",
                "item": "Martelo",
                "codigo": "F-100",
                "date": "15/09/2026",
                "status": "em_atenção",
                "details": "Consumo médio de 1.2 und/dia; estoque previsto para zerar em 10 dias.",
            }]
        })

        context = dashboard_view._dashboard_context()

        assert context["projection_cards"]
        assert context["projection_cards"][0]["item"] == "Martelo"
