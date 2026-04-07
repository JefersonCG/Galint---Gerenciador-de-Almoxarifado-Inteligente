"""Regressoes para inflacao de saldo em itens com embalagem."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask.services.balance_provider import BalanceSnapshot
from galint_flask.services.embalagem_service import EmbalagemService
from galint_flask.services.inventory import InventoryService, MovimentoPayload
from galint_flask.services.ledger_cutover import LedgerCutoverService
from galint_flask.services.ledger_reconciliation import ReconciliationResult
from galint_flask.services.legacy_stock_normalizer import resolve_packaging_quantity_and_unit, uses_packaging_legacy_normalization


class MockPackagingItem:
    def __init__(
        self,
        *,
        codigo_item: str,
        tipo_embalagem: str,
        unidades_por_embalagem: float,
        unidade: str = "un",
        categoria: str | None = None,
        descricao: str | None = None,
    ):
        self.codigo_item = codigo_item
        self.descricao = descricao or codigo_item
        self.categoria = categoria
        self.tipo_embalagem_novo = tipo_embalagem
        self.tipo_embalagem = tipo_embalagem
        self.unidades_por_embalagem = unidades_por_embalagem
        self.litros_por_embalagem = None
        self.estoque_embalagens = 0.0
        self.estoque_unidades_soltas = 0.0
        self.unidade = unidade
        self.grandeza_referencia = None
        self.product_units = []
        self.product_unit_conversions = []

    def get_nome_embalagem(self) -> str:
        return self.tipo_embalagem_novo or "embalagem"

    def get_nome_embalagem_plural(self) -> str:
        nome = self.get_nome_embalagem()
        if nome.endswith("s"):
            return nome
        return f"{nome}s"

    def get_saldo_atual(self) -> float:
        return (self.estoque_embalagens * float(self.unidades_por_embalagem or 0)) + float(self.estoque_unidades_soltas or 0)


class FakeBalance:
    def __init__(self):
        self.product_id = ""
        self.quantity_base = 0.0
        self.read_model_ready = False


class FakeSession:
    def __init__(self):
        self._storage: dict[str, FakeBalance] = {}
        self.commit_count = 0

    def get(self, _model, product_id: str):
        return self._storage.get(product_id)

    def add(self, balance: FakeBalance) -> None:
        self._storage[balance.product_id] = balance

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.commit_count += 1


class FakeReconciliationService:
    def __init__(self, result: ReconciliationResult):
        self._result = result

    def reconcile_product(self, product_id: str) -> ReconciliationResult:
        assert product_id == self._result.product_id
        return self._result


def test_sync_legacy_nao_transforma_unidades_em_pacotes_explodidos() -> None:
    item = MockPackagingItem(codigo_item="SACO-100L-TESTE", tipo_embalagem="pacote", unidades_por_embalagem=100)
    snapshot = BalanceSnapshot(
        product_id=item.codigo_item,
        quantity_base=4900.0,
        unit_base="un",
        source="stock_balance",
        migrated=True,
    )

    with patch("galint_flask.services.balance_provider.balance_provider.get_balance", return_value=snapshot), patch(
        "galint_flask.services.legacy_stock_normalizer.resolve_packaging_factor",
        return_value=100.0,
    ), patch(
        "galint_flask.services.legacy_stock_normalizer.is_packaging_unit_code",
        return_value=False,
    ):
        changed = EmbalagemService.tentar_sincronizar_estoque_de_legacy(item)

    assert changed is True
    assert item.estoque_embalagens == 49.0
    assert item.estoque_unidades_soltas == 0.0


def test_sync_legacy_respeita_quando_snapshot_ja_esta_em_pacotes() -> None:
    item = MockPackagingItem(codigo_item="SACO-200L-TESTE", tipo_embalagem="pacote", unidades_por_embalagem=100)
    snapshot = BalanceSnapshot(
        product_id=item.codigo_item,
        quantity_base=79.0,
        unit_base="pacote",
        source="legacy",
        migrated=False,
    )

    with patch("galint_flask.services.balance_provider.balance_provider.get_balance", return_value=snapshot), patch(
        "galint_flask.services.legacy_stock_normalizer.resolve_packaging_factor",
        return_value=100.0,
    ), patch(
        "galint_flask.services.legacy_stock_normalizer.is_packaging_unit_code",
        side_effect=lambda unit_code: unit_code == "pacote",
    ):
        changed = EmbalagemService.tentar_sincronizar_estoque_de_legacy(item)

    assert changed is True
    assert item.estoque_embalagens == 79.0
    assert item.estoque_unidades_soltas == 0.0


def test_cutover_grava_ledger_balance_no_cache() -> None:
    result = ReconciliationResult(
        product_id="SACO-300L-TESTE",
        description="Saco 300L",
        legacy_balance=14800.0,
        ledger_balance=14800.0,
        stock_balance=1480000.0,
        divergence_legacy_vs_ledger=0.0,
        divergence_ledger_vs_cache=1465200.0,
        classification="divergencia_zero",
        details={},
    )
    session = FakeSession()
    service = LedgerCutoverService(reconciliation_service=FakeReconciliationService(result))

    with patch("galint_flask.services.ledger_cutover.stock_balance_supports_read_model_ready", return_value=True), patch(
        "galint_flask.services.ledger_cutover.db",
        SimpleNamespace(session=session),
    ), patch(
        "galint_flask.services.ledger_cutover.StockBalance",
        FakeBalance,
    ):
        decision = service.activate_product(result.product_id)

    balance = session.get(FakeBalance, result.product_id)
    assert decision.activated is True
    assert balance is not None
    assert balance.quantity_base == 14800.0
    assert balance.read_model_ready is True
    assert session.commit_count == 1


def test_cutover_desativa_mantendo_ledger_balance_no_cache() -> None:
    result = ReconciliationResult(
        product_id="SACO-60L-TESTE",
        description="Saco 60L",
        legacy_balance=1900.0,
        ledger_balance=1900.0,
        stock_balance=190000.0,
        divergence_legacy_vs_ledger=0.0,
        divergence_ledger_vs_cache=188100.0,
        classification="divergencia_zero",
        details={},
    )
    session = FakeSession()
    existing = FakeBalance()
    existing.product_id = result.product_id
    existing.quantity_base = result.stock_balance
    existing.read_model_ready = True
    session.add(existing)
    service = LedgerCutoverService(reconciliation_service=FakeReconciliationService(result))

    with patch("galint_flask.services.ledger_cutover.stock_balance_supports_read_model_ready", return_value=True), patch(
        "galint_flask.services.ledger_cutover.db",
        SimpleNamespace(session=session),
    ), patch(
        "galint_flask.services.ledger_cutover.StockBalance",
        FakeBalance,
    ):
        decision = service.deactivate_product(result.product_id)

    balance = session.get(FakeBalance, result.product_id)
    assert decision.activated is False
    assert balance is not None
    assert balance.quantity_base == 1900.0
    assert balance.read_model_ready is False
    assert session.commit_count == 1


def test_ferramenta_jogo_nao_usa_normalizacao_legada_de_embalagem() -> None:
    item = MockPackagingItem(
        codigo_item="KIT-ALLEN-TESTE",
        tipo_embalagem="pacote",
        unidades_por_embalagem=6,
        categoria="Ferramentas",
        descricao="JOGO DE CHAVE TESTE 6 PECAS",
    )

    assert EmbalagemService.tem_embalagem(item) is False
    assert uses_packaging_legacy_normalization(item) is False
    assert resolve_packaging_quantity_and_unit(item, 2.0) is None


def test_dual_write_legado_de_ferramenta_jogo_nao_multiplica_quantidade() -> None:
    item = MockPackagingItem(
        codigo_item="KIT-FENDA-TESTE",
        tipo_embalagem="caixa",
        unidades_por_embalagem=9,
        categoria="Ferramentas",
        descricao="JOGO DE CHAVE TESTE ISOLADA",
    )
    payload = MovimentoPayload(codigo=item.codigo_item, quantidade=1.0)
    metadata = {"reference_type": "legacy_movimento"}

    assert InventoryService._should_use_packaging_dual_write(item, payload, metadata) is False
    assert InventoryService._resolve_packaging_dual_write(item, 1.0, payload, metadata) is None


def test_toolkit_payload_e_normalizado_para_unidade() -> None:
    payload = {
        "categoria": "Ferramentas",
        "descricao": "JOGO DE CHAVE ALLEN LONGA",
        "unidade": "Caixa",
        "tipo_embalagem_novo": "caixa",
        "unidades_por_embalagem": 7,
        "estoque_embalagens": 3,
        "estoque_unidades_soltas": 2,
    }

    normalized = InventoryService._normalize_toolkit_registration_payload(payload)

    assert normalized["unidade"] == "Unidade"
    assert normalized["tipo_embalagem_novo"] is None
    assert normalized["unidades_por_embalagem"] is None
    assert normalized["estoque_embalagens"] == 0.0
    assert normalized["estoque_unidades_soltas"] == 0.0


def test_resolve_ledger_input_para_embalagem_legada_usa_base_canonica() -> None:
    item = MockPackagingItem(
        codigo_item="PACOTE-100-TESTE",
        tipo_embalagem="pacote",
        unidades_por_embalagem=100,
    )
    payload = MovimentoPayload(codigo=item.codigo_item, quantidade=2.0, em_embalagens=True)

    quantity_value, unit_value = InventoryService._resolve_ledger_input_for_mirror(
        item,
        payload,
        metadata={"reference_type": "legacy_movimento"},
    )

    assert quantity_value == 200.0
    assert unit_value == "un"


def test_finalize_ledger_mirror_sincroniza_read_model_antes_da_auditoria() -> None:
    result = SimpleNamespace(product_id="PACOTE-100-TESTE")

    with patch("galint_flask.services.inventory.inventory_engine.sync_packaging_read_model") as sync_mock, patch(
        "galint_flask.services.inventory.inventory_engine.record_operation_audit"
    ) as audit_mock:
        InventoryService.finalize_ledger_mirror(result)

    sync_mock.assert_called_once_with(product_id="PACOTE-100-TESTE", commit=True)
    audit_mock.assert_called_once_with(result)


def test_formatar_estoque_nao_sincroniza_legacy_em_contexto_de_leitura() -> None:
    item = MockPackagingItem(
        codigo_item="CAIXA-LEITURA-TESTE",
        tipo_embalagem="caixa",
        unidades_por_embalagem=50,
    )
    item.estoque_embalagens = 2.0
    item.estoque_unidades_soltas = 10.0

    with patch(
        "galint_flask.services.embalagem_service.EmbalagemService.tentar_sincronizar_estoque_de_legacy",
        side_effect=AssertionError("nao deveria sincronizar em leitura"),
    ):
        formatted = EmbalagemService.formatar_estoque(item)

    assert formatted == "2 caixas + 10 unidades"


def main() -> int:
    test_sync_legacy_nao_transforma_unidades_em_pacotes_explodidos()
    test_sync_legacy_respeita_quando_snapshot_ja_esta_em_pacotes()
    test_cutover_grava_ledger_balance_no_cache()
    test_cutover_desativa_mantendo_ledger_balance_no_cache()
    test_ferramenta_jogo_nao_usa_normalizacao_legada_de_embalagem()
    test_dual_write_legado_de_ferramenta_jogo_nao_multiplica_quantidade()
    test_toolkit_payload_e_normalizado_para_unidade()
    test_resolve_ledger_input_para_embalagem_legada_usa_base_canonica()
    test_finalize_ledger_mirror_sincroniza_read_model_antes_da_auditoria()
    test_formatar_estoque_nao_sincroniza_legacy_em_contexto_de_leitura()
    print("OK - regressao de embalagem/cache")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError:
        import traceback

        traceback.print_exc()
        sys.exit(1)