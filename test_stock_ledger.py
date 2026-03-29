from __future__ import annotations

import unittest

from galint_flask.services.inventory_engine import InventoryEngine


class _FakeItem:
    def __init__(self, *, unidade: str = "un", tipo_embalagem_novo: str | None = None, unidades_por_embalagem: float | None = None):
        self.unidade = unidade
        self.tipo_embalagem_novo = tipo_embalagem_novo
        self.unidades_por_embalagem = unidades_por_embalagem

    def get_unidade_interna_display(self) -> str:
        return self.unidade


class StockLedgerTests(unittest.TestCase):
    def test_convert_unit_sem_embalagem_mantem_quantidade(self):
        item = _FakeItem(unidade="un")
        self.assertEqual(InventoryEngine.convert_unit(item, 5), 5.0)

    def test_convert_unit_com_embalagem_converte_para_base(self):
        item = _FakeItem(unidade="m", tipo_embalagem_novo="rolo", unidades_por_embalagem=100)
        self.assertEqual(
            InventoryEngine.convert_unit(item, 3, unit_type="embalagem", em_embalagens=True),
            300.0,
        )

    def test_signed_amount_para_entrada_saida_e_ajuste(self):
        self.assertEqual(InventoryEngine._signed_amount("IN", 10), 10.0)
        self.assertEqual(InventoryEngine._signed_amount("OUT", 10), -10.0)
        self.assertEqual(InventoryEngine._signed_amount("ADJUST", -4), -4.0)

    def test_agregacao_de_movimentos_reconstroi_saldo(self):
        aggregated = InventoryEngine.aggregate_balance_rows(
            [
                ("ITEM-1", 10.0),
                ("ITEM-1", -3.0),
                ("ITEM-1", 2.0),
                ("ITEM-2", 7.0),
            ]
        )
        self.assertEqual(aggregated["ITEM-1"], 9.0)
        self.assertEqual(aggregated["ITEM-2"], 7.0)

    def test_divergencia_retorna_delta_exato(self):
        record = InventoryEngine.build_divergence_record("ITEM-1", "Produto", 12.0, 10.5)
        self.assertEqual(record["codigo_item"], "ITEM-1")
        self.assertEqual(record["saldo_legado"], 12.0)
        self.assertEqual(record["saldo_ledger"], 10.5)
        self.assertEqual(record["divergencia"], -1.5)


if __name__ == "__main__":
    unittest.main()