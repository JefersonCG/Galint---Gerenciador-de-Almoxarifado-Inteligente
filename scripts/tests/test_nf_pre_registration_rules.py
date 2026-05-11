from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace

from galint_flask.views import nf


def _make_item(**overrides):
    data = {
        "codigo_item": "ITEM-TESTE",
        "nota_fiscal": None,
        "preco_compra_documento": None,
        "pre_cadastro_pendente": False,
        "pre_cadastro_origem": None,
        "pre_cadastro_documento_item_id": None,
        "pre_cadastro_criado_em": None,
        "pre_cadastro_finalizado_em": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class NfPreRegistrationRulesTests(unittest.TestCase):
    def test_registered_item_is_not_reopened_even_when_forced(self) -> None:
        item = _make_item()

        tracked = nf._mark_item_for_nf_pre_registration(
            item,
            document_item_id=10,
            document_number="NF-001",
            force=True,
        )

        self.assertFalse(tracked)
        self.assertFalse(item.pre_cadastro_pendente)
        self.assertIsNone(item.pre_cadastro_documento_item_id)

    def test_pending_nf_item_keeps_pre_registration_link(self) -> None:
        item = _make_item(pre_cadastro_pendente=True, pre_cadastro_origem="nf")

        tracked = nf._mark_item_for_nf_pre_registration(
            item,
            document_item_id=20,
            document_number="NF-002",
        )

        self.assertTrue(tracked)
        self.assertTrue(item.pre_cadastro_pendente)
        self.assertEqual(item.pre_cadastro_documento_item_id, 20)

    def test_finished_nf_pre_registration_is_not_reopened(self) -> None:
        item = _make_item(
            pre_cadastro_pendente=False,
            pre_cadastro_origem="nf",
            pre_cadastro_documento_item_id=30,
            pre_cadastro_finalizado_em=datetime.utcnow(),
        )

        tracked = nf._mark_item_for_nf_pre_registration(
            item,
            document_item_id=40,
            document_number="NF-003",
            force=True,
        )

        self.assertFalse(tracked)
        self.assertFalse(item.pre_cadastro_pendente)
        self.assertEqual(item.pre_cadastro_documento_item_id, 30)

    def test_seeded_detection_requires_document_number_on_item(self) -> None:
        item = _make_item(nota_fiscal="NF-ANTIGA", preco_compra_documento=None)

        self.assertFalse(
            nf._item_matches_seeded_nf_pre_registration(
                item,
                document_number="NF-NOVA",
            )
        )


if __name__ == "__main__":
    unittest.main()