from __future__ import annotations

import os

os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask.services.inventory_category_summary import build_category_balance_summary, build_category_value_summary


def test_build_category_balance_summary_quebra_por_unidade_interna() -> None:
    summary = build_category_balance_summary(
        [
            {"saldo": 144000.0, "unidade_interna_display": "un"},
            {"saldo": 232.0, "unidade_interna_display": "L"},
            {"saldo": 129.5, "unidade_interna_display": "L"},
            {"saldo": 184.0, "unidade_interna_display": "Peça"},
        ]
    )

    assert summary == [
        {"unit": "un", "quantity": 144000.0, "display": "144.000 un"},
        {"unit": "L", "quantity": 361.5, "display": "361,5 L"},
        {"unit": "Peça", "quantity": 184.0, "display": "184 Peça"},
    ]


def test_build_category_balance_summary_agrupar_unidade_numerica_como_inconsistente() -> None:
    summary = build_category_balance_summary(
        [
            {"saldo": 3.0, "unidade_interna_display": "1"},
            {"saldo": 5.0, "unidade_interna_display": "2"},
            {"saldo": 10.0, "unidade_interna_display": "un"},
        ]
    )

    assert summary == [
        {"unit": "un", "quantity": 10.0, "display": "10 un"},
        {"unit": "Cadastro inconsistente", "quantity": 8.0, "display": "8 Cadastro inconsistente"},
    ]


def test_build_category_value_summary_separa_itens_sem_preco() -> None:
    summary = build_category_value_summary(
        [
            {"valor_estoque_compra_total": 1200.0, "valor_estoque_reposicao_total": 1400.0},
            {"valor_estoque_compra_total": None, "valor_estoque_reposicao_total": 500.0},
            {"valor_estoque_compra_total": 300.0, "valor_estoque_reposicao_total": None},
        ]
    )

    assert summary == {
        "total_compra": 1500.0,
        "total_reposicao": 1900.0,
        "with_compra": 2,
        "with_reposicao": 2,
        "missing_compra": 1,
        "missing_reposicao": 1,
    }


def main() -> int:
    test_build_category_balance_summary_quebra_por_unidade_interna()
    test_build_category_balance_summary_agrupar_unidade_numerica_como_inconsistente()
    test_build_category_value_summary_separa_itens_sem_preco()
    print("OK - category cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())