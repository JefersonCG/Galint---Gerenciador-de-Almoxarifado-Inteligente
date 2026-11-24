"""Proteções da bateria de testes (24/11/2026).

Erro que originou: tests/test_analytics_forecast_cards.py chama create_app(), que lê o .env do workspace —
e esse .env aponta para o banco de PRODUÇÃO (localhost:5432/galint_db). Cada rodada completa da bateria
subia um GALINT inteiro por alguns segundos: disparava a saudação de "sistema religado" no Telegram para
as 6 pessoas (14 vezes entre 21 e 24/11/2026, pelo log/actions.log do workspace) e processava a fila real
de mensagens do Telegram.

Aqui, antes de qualquer import do galint_flask:
- serviços de fundo, saudação de startup e envio da fila do Telegram ficam desligados;
- teste que precisa de create_app() (banco de verdade) só roda com GALINT_TESTS_ALLOW_REAL_DB=1.
"""
import os

import pytest

os.environ["GALINT_DISABLE_BACKGROUND_SERVICES"] = "true"
os.environ["GALINT_TELEGRAM_STARTUP_GREETING"] = "false"
os.environ["GALINT_TELEGRAM_OUTBOX_ENABLED"] = "false"

REAL_DB_ALLOWED = os.environ.get("GALINT_TESTS_ALLOW_REAL_DB") == "1"


def pytest_collection_modifyitems(config, items):
    if REAL_DB_ALLOWED:
        return
    skip = pytest.mark.skip(reason="usa create_app() com o banco do .env (produção); rode com GALINT_TESTS_ALLOW_REAL_DB=1")
    for item in items:
        if "real_db" in item.keywords:
            item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_db: teste que sobe o app com create_app() e o banco do .env")
