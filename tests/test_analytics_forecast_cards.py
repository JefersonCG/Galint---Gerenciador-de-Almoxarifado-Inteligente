from datetime import datetime

from galint_flask.services.analytics_service import AnalyticsService
from galint_flask.services.finance_service import FinanceService


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
