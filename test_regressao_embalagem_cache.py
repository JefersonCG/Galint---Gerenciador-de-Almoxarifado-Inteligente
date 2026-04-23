"""Regressoes para inflacao de saldo em itens com embalagem."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from check_stock_unit_integrity import _physical_read_model_target
from galint_flask.services.balance_provider import BalanceSnapshot
from galint_flask.services.embalagem_service import EmbalagemService
from galint_flask.services.finance_service import FinanceService
from galint_flask.services.inventory import InventoryService, MovimentoPayload
from galint_flask.services.inventory import _reconcile_normalized_item_prices, ensure_base_item_unit, resolve_item_base_unit_label
from galint_flask.services.ledger_backfill_normalized import LEGACY_REBUILD_REFERENCE_TYPES
from galint_flask.services.ledger_cutover import LedgerCutoverService
from galint_flask.services.ledger_reconciliation import ReconciliationResult
from galint_flask.services.legacy_stock_normalizer import infer_packaging_measure, is_legacy_liter_packaging_compatible, resolve_packaging_factor, resolve_packaging_quantity_and_unit, uses_packaging_legacy_normalization
from galint_flask.services.price_normalization import infer_document_quantity_unit_for_item, infer_price_unit_for_item
from galint_flask.services.telegram_service import TelegramService
from galint_flask.views.inventory import _uses_packaging_system
from galint_flask.views.nf import _apply_document_item_normalization, _build_nf_new_item_packaging_payload, _item_matches_seeded_nf_pre_registration, _mark_manual_nf_document_items_for_pre_registration, _normalize_nf_new_item_packaging_type
from auditar_realinhamento_unidades_operacionais import _classify_item


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
        grandeza_referencia: float | None = None,
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
        self.grandeza_referencia = grandeza_referencia
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


def test_item_unitario_com_conteudo_em_kg_usa_normalizacao_legada() -> None:
    item = MockPackagingItem(
        codigo_item="CLORO-200G-TESTE",
        tipo_embalagem="",
        unidades_por_embalagem=0,
        unidade="Unidade",
        categoria="Piscina",
        descricao="PASTILHA DE CLORO TRIPLA ACAO 200g",
        grandeza_referencia=0.2,
    )

    assert uses_packaging_legacy_normalization(item) is True
    assert resolve_packaging_quantity_and_unit(item, 50.0) == (10.0, "kg")


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


def test_rebuild_legado_limpa_saidas_multiplas_espelhadas() -> None:
    assert "movements_saida_multipla" in LEGACY_REBUILD_REFERENCE_TYPES


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


def test_rolo_migrado_nao_reaplica_formula_legada_na_exibicao() -> None:
    item = MockPackagingItem(
        codigo_item="ROLO-MIGRADO-TESTE",
        tipo_embalagem="rolo",
        unidades_por_embalagem=100,
        unidade="Metro",
    )
    item.tipo_embalagem = "Rolo"
    item.grandeza_referencia = 100.0
    item.estoque_embalagens = 1.0
    item.estoque_unidades_soltas = 0.0

    assert EmbalagemService.tem_embalagem(item) is True
    assert EmbalagemService.tem_rolo_legacy(item) is False
    assert EmbalagemService.formatar_estoque(item) == "100 metros (1 rolo)"


def test_infer_price_unit_da_nf_prefere_embalagem_documental_do_rolo() -> None:
    item = MockPackagingItem(
        codigo_item="ROLO-NF-TESTE",
        tipo_embalagem="rolo",
        unidades_por_embalagem=100,
        unidade="Metro",
    )

    assert infer_document_quantity_unit_for_item(item) == "rolo"
    assert infer_price_unit_for_item(item) == "rolo"


def test_infer_packaging_measure_detecta_comprimento_em_rotulo_dimensional_de_rolo() -> None:
    item = MockPackagingItem(
        codigo_item="ROLO-DIMENSIONAL-TESTE",
        tipo_embalagem="rolo",
        unidades_por_embalagem=0,
        unidade="Rolo",
        descricao="FITA CREPE MASK 48mmX50M",
    )

    assert infer_packaging_measure(item) == (50.0, "m")
    assert resolve_packaging_factor(item) == 50.0


def test_infer_packaging_measure_detecta_comprimento_em_rolo_com_largura_em_mm() -> None:
    item = MockPackagingItem(
        codigo_item="ROLO-DIMENSIONAL-90X48-TESTE",
        tipo_embalagem="rolo",
        unidades_por_embalagem=0,
        unidade="Rolo",
        descricao="FITA AUTOADESIVA DRYWALL 90X48mm",
    )

    assert infer_packaging_measure(item) == (90.0, "m")
    assert resolve_packaging_factor(item) == 90.0


def test_infer_packaging_measure_converte_gramas_para_quilo_em_pacote() -> None:
    item = MockPackagingItem(
        codigo_item="PACOTE-GRAMAS-TESTE",
        tipo_embalagem="pacote",
        unidades_por_embalagem=0,
        unidade="Pacote",
        descricao="MASSA F12 MOGNO 200G",
    )

    assert infer_packaging_measure(item) == (0.2, "kg")
    assert resolve_packaging_factor(item) == 0.2


def test_hydrate_missing_packaging_metadata_corrige_tinta_acetinada_numerica_legada() -> None:
    normalized = InventoryService._hydrate_missing_packaging_metadata(
        {
            "descricao": "TOQUE SEDA ACETINADO CROMO 18L",
            "unidade": "1",
        }
    )

    assert normalized["tipo_embalagem_novo"] == "lata"
    assert normalized["litros_por_embalagem"] == 18.0
    assert normalized["unidade"] == "Litro"


def test_hydrate_missing_packaging_metadata_corrige_manta_acrilica_kg_numerica_legada() -> None:
    normalized = InventoryService._hydrate_missing_packaging_metadata(
        {
            "descricao": "MANTA ACRILICA FLEXIVEL 12KG",
            "unidade": "1",
        }
    )

    assert normalized["tipo_embalagem_novo"] == "balde"
    assert normalized["grandeza_referencia"] == 12.0
    assert normalized["unidade"] == "Quilo"


def test_legacy_liter_packaging_compatible_aceita_frasco_liquido_legado() -> None:
    item = MockPackagingItem(
        codigo_item="LEGADO-LITRO-500ML",
        tipo_embalagem="litro",
        unidades_por_embalagem=0.5,
        unidade="Litro",
        descricao="DESINFETANTE DE USO GERAL 500ML",
    )
    item.litros_por_embalagem = 0.5

    assert is_legacy_liter_packaging_compatible(item) is True


def test_legacy_liter_packaging_compatible_rejeita_item_com_medida_em_gramas() -> None:
    item = MockPackagingItem(
        codigo_item="LEGADO-LITRO-850G",
        tipo_embalagem="litro",
        unidades_por_embalagem=1,
        unidade="Litro",
        descricao="ADESIVO PLASTICO P/GRANDES DIAMETROS 850G",
    )
    item.litros_por_embalagem = 1.0

    assert is_legacy_liter_packaging_compatible(item) is False


def test_reconcile_normalized_item_prices_corrige_preco_base_legado_de_pacote() -> None:
    item = MockPackagingItem(
        codigo_item="PACOTE-PRECO-LEGADO",
        tipo_embalagem="pacote",
        unidades_por_embalagem=1000,
        unidade="Pacote",
    )
    item.product_units = [
        SimpleNamespace(unit_code="pacote", unit_label="Pacote", is_base=False, active=True),
        SimpleNamespace(unit_code="un", unit_label="Unidade", is_base=True, active=True),
    ]
    item.product_unit_conversions = [
        SimpleNamespace(from_unit="pacote", to_unit="un", factor=1000.0, active=True),
    ]
    item.preco_compra_unitario = 130.0
    item.preco_compra_unitario_base = 130.0
    item.preco_compra_unidade_preco = "pacote"
    item.preco_compra_fator_base = 1.0
    item.preco_reposicao_unitario = None
    item.preco_reposicao_unitario_base = None
    item.preco_reposicao_unidade_preco = None
    item.preco_reposicao_fator_base = None

    changed = _reconcile_normalized_item_prices(item)

    assert changed is True
    assert item.preco_compra_unitario == 130.0
    assert item.preco_compra_unidade_preco == "pacote"
    assert item.preco_compra_unitario_base == 0.13
    assert item.preco_compra_fator_base == 1000.0


def test_reconcile_normalized_item_prices_infere_unidade_embalagem_quando_ausente() -> None:
    item = MockPackagingItem(
        codigo_item="CAIXA-PRECO-INFERIDO",
        tipo_embalagem="caixa",
        unidades_por_embalagem=24,
        unidade="Caixa",
    )
    item.preco_compra_unitario = None
    item.preco_compra_unitario_base = None
    item.preco_compra_unidade_preco = None
    item.preco_compra_fator_base = None
    item.preco_reposicao_unitario = 96.3
    item.preco_reposicao_unitario_base = None
    item.preco_reposicao_unidade_preco = None
    item.preco_reposicao_fator_base = None

    changed = _reconcile_normalized_item_prices(item)

    assert changed is True
    assert item.preco_reposicao_unidade_preco == "caixa"
    assert item.preco_reposicao_fator_base == 24.0
    assert item.preco_reposicao_unitario_base == 4.0125


def test_reconcile_normalized_item_prices_prefere_prova_historica_embalada() -> None:
    item = MockPackagingItem(
        codigo_item="ROLO-PRECO-HISTORICO",
        tipo_embalagem="rolo",
        unidades_por_embalagem=100,
        unidade="Metro",
    )
    item.product_units = [
        SimpleNamespace(unit_code="rolo", unit_label="Rolo", is_base=False, active=True),
        SimpleNamespace(unit_code="m", unit_label="Metro", is_base=True, active=True),
    ]
    item.product_unit_conversions = [
        SimpleNamespace(from_unit="rolo", to_unit="m", factor=100.0, active=True),
    ]
    item.preco_compra_unitario = 235.9
    item.preco_compra_unitario_base = 235.9
    item.preco_compra_unidade_preco = "m"
    item.preco_compra_fator_base = 1.0
    item.preco_reposicao_unitario = None
    item.preco_reposicao_unitario_base = None
    item.preco_reposicao_unidade_preco = None
    item.preco_reposicao_fator_base = None

    with patch(
        "galint_flask.services.inventory._resolve_historical_item_price_proof",
        return_value={
            "unit_price_base": 2.359,
            "price_unit": "rolo",
            "factor_to_base": 100.0,
        },
    ):
        changed = _reconcile_normalized_item_prices(item)

    assert changed is True
    assert item.preco_compra_unitario == 235.9
    assert item.preco_compra_unidade_preco == "rolo"
    assert item.preco_compra_fator_base == 100.0
    assert item.preco_compra_unitario_base == 2.359


def test_apply_document_item_normalization_corrige_linha_pendente_de_rolo_para_embalagem() -> None:
    item = MockPackagingItem(
        codigo_item="ROLO-NF-PENDENTE-TESTE",
        tipo_embalagem="rolo",
        unidades_por_embalagem=100,
        unidade="Metro",
    )
    row = SimpleNamespace(
        item=item,
        codigo_item=item.codigo_item,
        unidade_quantidade="m",
        quantidade_base=3.0,
        unidade_preco="m",
        valor_unitario=None,
        valor_total=None,
        valor_unitario_base=None,
        fator_preco_base=None,
        status_processamento="pendente",
        stock_movement_id=None,
        entrada_id=None,
    )

    valor_unitario, valor_total = _apply_document_item_normalization(
        row,
        quantidade=3.0,
        valor_unitario=100.0,
        valor_total=None,
    )

    assert row.unidade_quantidade == "rolo"
    assert row.quantidade_base == 300.0
    assert row.unidade_preco == "rolo"
    assert row.valor_unitario_base == 1.0
    assert valor_unitario == 100.0
    assert valor_total == 300.0


def test_serialize_stock_document_mostra_conversao_documental_do_rolo() -> None:
    item = MockPackagingItem(
        codigo_item="ROLO-NF-VISUAL-TESTE",
        tipo_embalagem="rolo",
        unidades_por_embalagem=100,
        unidade="Metro",
    )
    row = SimpleNamespace(
        id_documento_item=1,
        entrada_id=None,
        stock_movement_id=None,
        operation_log_id=None,
        codigo_item=item.codigo_item,
        item=item,
        quantidade=3.0,
        quantidade_base=3.0,
        valor_unitario=100.0,
        valor_total=300.0,
        lote=None,
        data_validade=None,
        observacao=None,
        status_processamento="pendente",
        processado_em=None,
        erro_processamento=None,
        unidade_quantidade="m",
        unidade_preco="m",
    )
    document = SimpleNamespace(
        id_documento=99,
        numero_documento="NF-ROLO-TESTE",
        tipo_documento="nf",
        criado_em=datetime(2026, 4, 9, 12, 0, 0),
        data_emissao=None,
        data_recebimento=None,
        movimenta_estoque=True,
        chave_acesso=None,
        fornecedor_id=None,
        fornecedor=None,
        nome_emitente=lambda: None,
        cnpj_emitente=None,
        observacao=None,
        status_integracao="manual",
        mensagem_integracao=None,
        criado_por="admin",
        itens=[row],
    )

    payload = FinanceService._serialize_stock_document(document)
    line = payload["itens"][0]

    assert line["usa_embalagem_documental"] is True
    assert line["autocorrecao_documental_preview"] is True
    assert line["quantidade_documento_display"] == "3 rolos"
    assert line["conteudo_por_embalagem_display"] == "100 metros"
    assert line["quantidade_base_display"] == "300 metros"
    assert line["conversao_display"] == "3 rolos de 100 metros = 300 metros"


def test_resolve_item_base_unit_label_prefere_unidade_canonica_do_rolo() -> None:
    item_like = {
        "unidade": "Unidade",
        "tipo_embalagem_novo": "rolo",
        "unidades_por_embalagem": 100,
    }

    assert resolve_item_base_unit_label(item_like, fallback="Unidade") == "Metro"


def test_resolve_item_base_unit_label_prefere_unidade_canonica_da_bombona() -> None:
    item_like = {
        "unidade": "Unidade",
        "tipo_embalagem_novo": "bombona",
        "litros_por_embalagem": 5,
        "unidades_por_embalagem": 5,
    }

    assert resolve_item_base_unit_label(item_like, fallback="Unidade") == "Litro"


def test_resolve_item_base_unit_label_aceita_product_units_como_dict_no_pre_cadastro() -> None:
    item_like = {
        "unidade": "Unidade",
        "tipo_embalagem_novo": "rolo",
        "unidades_por_embalagem": 25,
        "product_units": [
            {
                "unit_code": "m",
                "is_base": True,
                "active": True,
            }
        ],
    }

    assert resolve_item_base_unit_label(item_like, fallback="Unidade") == "Metro"


def test_ensure_base_item_unit_aceita_par() -> None:
    assert ensure_base_item_unit("pares") == "Par"


def test_resolve_item_base_unit_label_aceita_par_como_base_legitima() -> None:
    item_like = SimpleNamespace(
        unidade="Par",
        tipo_embalagem_novo=None,
        litros_por_embalagem=None,
        grandeza_referencia=None,
        unidades_por_embalagem=None,
        product_units=[],
    )

    assert resolve_item_base_unit_label(item_like, fallback="Unidade") == "Par"


def test_nf_document_unit_aceita_par_quando_base_tambem_e_par() -> None:
    assert _normalize_nf_new_item_packaging_type("par") == "par"
    assert _build_nf_new_item_packaging_payload(
        base_unit="Par",
        packaging_type="par",
        content_per_package=None,
    ) == {}


def test_nf_document_unit_par_exige_base_par() -> None:
    try:
        _build_nf_new_item_packaging_payload(
            base_unit="Unidade",
            packaging_type="par",
            content_per_package=None,
        )
    except ValueError as exc:
        assert "compra/NF vier em Par" in str(exc)
    else:
        raise AssertionError("Esperava ValueError quando Par for usado sem base Par")


def test_material_return_unit_options_prefere_metro_para_rolo_com_grandeza_referencia() -> None:
    item = SimpleNamespace(
        tipo_embalagem_novo="rolo",
        unidade="Rolo",
        litros_por_embalagem=None,
        grandeza_referencia=20,
        unidades_por_embalagem=None,
        categoria="Material Construção",
        descricao="FITA ANTIDERRAPANTE 20M",
        product_units=[],
    )

    options = InventoryService().get_material_return_unit_options(item=item)

    assert options[0]["unit_code"] == "metro"
    assert options[0]["unit_display"] == "m"


def test_telegram_balance_totals_prefere_metros_para_rolo_com_grandeza_referencia() -> None:
    item = SimpleNamespace(
        tipo_embalagem_novo="rolo",
        unidade="Rolo",
        litros_por_embalagem=None,
        grandeza_referencia=20,
        unidades_por_embalagem=None,
        estoque_embalagens=12,
        estoque_unidades_soltas=0,
        categoria="Material Construção",
        descricao="FITA ANTIDERRAPANTE 20M",
        product_units=[],
        product_unit_conversions=[],
    )

    rendered = TelegramService._format_balance_totals(item)

    assert "240 metros" in rendered
    assert "240 kg" not in rendered


def test_infer_packaging_measure_preserva_item_em_par_sem_embalagem() -> None:
    item_like = SimpleNamespace(
        unidade="Par",
        tipo_embalagem_novo=None,
        litros_por_embalagem=None,
        grandeza_referencia=None,
        unidades_por_embalagem=None,
        descricao="Luva nitrilica",
        categoria="Material de EP",
        marca=None,
        product_units=[],
    )

    assert infer_packaging_measure(item_like) == (1.0, "par")


def test_uses_packaging_system_reconhece_bombona_por_litros() -> None:
    assert _uses_packaging_system({"tipo_embalagem_novo": "bombona", "litros_por_embalagem": 5}) is True


def test_uses_packaging_system_reconhece_saco_por_grandeza() -> None:
    assert _uses_packaging_system({"tipo_embalagem_novo": "saco", "grandeza_referencia": 20}) is True


def test_hydrate_missing_packaging_metadata_promove_unidade_de_embalagem() -> None:
    normalized = InventoryService._hydrate_missing_packaging_metadata(
        {
            "descricao": "KLYO LIMPA INOX 5L",
            "unidade": "Bombona",
        }
    )

    assert normalized["tipo_embalagem_novo"] == "bombona"
    assert normalized["litros_por_embalagem"] == 5.0
    assert normalized["unidade"] == "Litro"


def test_hydrate_missing_packaging_metadata_corrige_unidade_numerica() -> None:
    normalized = InventoryService._hydrate_missing_packaging_metadata(
        {
            "descricao": "TINTA PISO PRETO FOSCO 18L",
            "unidade": "1",
        }
    )

    assert normalized["tipo_embalagem_novo"] == "lata"
    assert normalized["litros_por_embalagem"] == 18.0
    assert normalized["unidade"] == "Litro"


def test_hydrate_missing_packaging_metadata_converte_item_eletrico_numerico_para_unidade() -> None:
    normalized = InventoryService._hydrate_missing_packaging_metadata(
        {
            "descricao": "LAMPADA LED SPOT PAR20 5.5W 6500K LUZ FRIA",
            "categoria": "Material Elétrico",
            "unidade": "0",
        }
    )

    assert normalized["unidade"] == "Unidade"
    assert normalized.get("tipo_embalagem_novo") in (None, "")


def test_hydrate_missing_packaging_metadata_converte_luva_epi_numerica_para_par() -> None:
    normalized = InventoryService._hydrate_missing_packaging_metadata(
        {
            "descricao": "LUVA DE PROTEÇÃO EM ALGODÃO",
            "categoria": "Material de EP",
            "unidade": "0",
        }
    )

    assert normalized["unidade"] == "Par"
    assert normalized.get("tipo_embalagem_novo") in (None, "")


def test_auditoria_marca_item_numerico_avulso_como_safe_apply() -> None:
    item = SimpleNamespace(
        codigo_item="AUDIT-LEGACY-UN",
        descricao="LAMPADA LED SPOT PAR20 5.5W 6500K LUZ FRIA",
        categoria="Material Elétrico",
        marca=None,
        unidade="0",
        tipo_embalagem_novo=None,
        tipo_embalagem=None,
        litros_por_embalagem=None,
        grandeza_referencia=None,
        unidades_por_embalagem=None,
        product_units=[],
    )

    result = _classify_item(item, document_index={})

    assert result.status == "safe_apply"
    assert result.proposed_unit == "Unidade"
    assert result.proposed_packaging is None


def test_seed_nf_aceita_numero_do_documento_sem_nota_gravada_no_item() -> None:
    item = SimpleNamespace(
        codigo_item="NF-012901-TESTE",
        nota_fiscal="",
        preco_compra_documento="",
        get_saldo_fisico_total=lambda: 0.0,
    )

    scalar_values = [0, 0]

    class QueryStub:
        def __init__(self, value: int):
            self._value = value

        def filter(self, *_args, **_kwargs):
            return self

        def scalar(self):
            return self._value

    def fake_query(*_args, **_kwargs):
        return QueryStub(scalar_values.pop(0))

    with patch("galint_flask.views.nf.db", SimpleNamespace(session=SimpleNamespace(query=fake_query))):
        assert _item_matches_seeded_nf_pre_registration(item, document_number="012901") is True


def test_manual_nf_forca_pre_cadastro_para_itens_existentes() -> None:
    rows = [
        SimpleNamespace(id_documento_item=10),
        SimpleNamespace(id_documento_item=11),
    ]
    calls: list[tuple[list[int], bool]] = []

    def fake_mark(document_items, *, force=False):
        calls.append(([row.id_documento_item for row in document_items], force))
        return len(document_items)

    with patch("galint_flask.views.nf._mark_document_items_for_nf_pre_registration", side_effect=fake_mark):
        tracked = _mark_manual_nf_document_items_for_pre_registration(rows)

    assert tracked == 2
    assert calls == [([10, 11], True)]


def test_manual_nf_forca_apenas_linhas_editadas_e_mantem_regra_antiga_no_resto() -> None:
    rows = [
        SimpleNamespace(id_documento_item=10),
        SimpleNamespace(id_documento_item=11),
    ]
    calls: list[tuple[list[int], bool]] = []

    def fake_mark(document_items, *, force=False):
        calls.append(([row.id_documento_item for row in document_items], force))
        return len(document_items)

    with patch("galint_flask.views.nf._mark_document_items_for_nf_pre_registration", side_effect=fake_mark):
        tracked = _mark_manual_nf_document_items_for_pre_registration(rows, forced_item_ids={11})

    assert tracked == 2
    assert calls == [([11], True), ([10], False)]


def test_physical_read_model_target_clampa_saldo_negativo() -> None:
    assert _physical_read_model_target(-107478.0) == 0.0
    assert _physical_read_model_target(280.0) == 280.0


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
    test_rolo_migrado_nao_reaplica_formula_legada_na_exibicao()
    test_infer_price_unit_da_nf_prefere_embalagem_documental_do_rolo()
    test_infer_packaging_measure_detecta_comprimento_em_rotulo_dimensional_de_rolo()
    test_infer_packaging_measure_converte_gramas_para_quilo_em_pacote()
    test_hydrate_missing_packaging_metadata_corrige_tinta_acetinada_numerica_legada()
    test_hydrate_missing_packaging_metadata_corrige_manta_acrilica_kg_numerica_legada()
    test_legacy_liter_packaging_compatible_aceita_frasco_liquido_legado()
    test_legacy_liter_packaging_compatible_rejeita_item_com_medida_em_gramas()
    test_reconcile_normalized_item_prices_corrige_preco_base_legado_de_pacote()
    test_reconcile_normalized_item_prices_infere_unidade_embalagem_quando_ausente()
    test_apply_document_item_normalization_corrige_linha_pendente_de_rolo_para_embalagem()
    test_serialize_stock_document_mostra_conversao_documental_do_rolo()
    test_resolve_item_base_unit_label_prefere_unidade_canonica_do_rolo()
    test_resolve_item_base_unit_label_prefere_unidade_canonica_da_bombona()
    test_resolve_item_base_unit_label_aceita_product_units_como_dict_no_pre_cadastro()
    test_ensure_base_item_unit_aceita_par()
    test_resolve_item_base_unit_label_aceita_par_como_base_legitima()
    test_nf_document_unit_aceita_par_quando_base_tambem_e_par()
    test_nf_document_unit_par_exige_base_par()
    test_infer_packaging_measure_preserva_item_em_par_sem_embalagem()
    test_uses_packaging_system_reconhece_bombona_por_litros()
    test_uses_packaging_system_reconhece_saco_por_grandeza()
    test_hydrate_missing_packaging_metadata_promove_unidade_de_embalagem()
    test_hydrate_missing_packaging_metadata_corrige_unidade_numerica()
    test_seed_nf_aceita_numero_do_documento_sem_nota_gravada_no_item()
    test_manual_nf_forca_pre_cadastro_para_itens_existentes()
    test_manual_nf_forca_apenas_linhas_editadas_e_mantem_regra_antiga_no_resto()
    test_physical_read_model_target_clampa_saldo_negativo()
    print("OK - regressao de embalagem/cache")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError:
        import traceback

        traceback.print_exc()
        sys.exit(1)