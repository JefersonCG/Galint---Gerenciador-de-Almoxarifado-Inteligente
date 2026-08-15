from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from galint_flask import create_app
from galint_flask.models import RetiradaFerramenta, Saida
from galint_flask.services.tool_custody_service import ToolCustodyService


class ToolCustodyDamageFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self) -> None:
        self.app_context.pop()

    @patch("galint_flask.services.tool_custody_service.inventory_service.finalize_ledger_mirror")
    @patch("galint_flask.services.tool_custody_service.inventory_service.invalidate_realtime_views")
    @patch("galint_flask.services.tool_custody_service.inventory_service.mirror_legacy_movement")
    @patch("galint_flask.services.tool_custody_service.db.session.commit")
    @patch("galint_flask.services.tool_custody_service.db.session.add")
    @patch("galint_flask.services.tool_custody_service.db.session.query")
    def test_register_damage_on_saida_reduces_stock(
        self,
        session_query,
        session_add,
        session_commit,
        mirror_legacy_movement,
        invalidate_realtime_views,
        finalize_ledger_mirror,
    ) -> None:
        saida = Mock()
        saida.id_saida = 42
        saida.codigo_item = "FERR-1"
        saida.matricula = "M-001"
        saida.quantidade = 2
        saida.data_saida = datetime.utcnow()
        saida.local_servico = "Obra 1"
        saida.observacao = "Sem uso"
        saida.item = Mock(categoria="Ferramentas", descricao="Martelo")

        with patch.object(Saida, "query", new=Mock(get=Mock(return_value=saida))), \
             patch.object(RetiradaFerramenta, "query", new=Mock(filter=Mock(return_value=Mock(order_by=Mock(return_value=Mock(first=Mock(return_value=None))))))):
            session_query.return_value.filter.return_value.first.return_value = None

            ToolCustodyService.register_damage(42, "Quebrou na obra", kind="quebrada", source="saida")

        mirror_legacy_movement.assert_called_once()
        _, kwargs = mirror_legacy_movement.call_args
        self.assertEqual(kwargs["quantity"], -2.0)
        self.assertEqual(kwargs["metadata"]["legacy_event_type"], "quebra_ferramenta")
        self.assertEqual(kwargs["payload"].quantidade, 2.0)


if __name__ == "__main__":
    unittest.main()
