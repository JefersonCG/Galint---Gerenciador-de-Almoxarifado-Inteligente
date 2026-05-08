"""Testes de rota para a devolucao expressa."""

from __future__ import annotations

import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from flask_login import UserMixin

os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask import create_app
from galint_flask.extensions import login_manager
from galint_flask.views import movements as movements_view


class _FakeAdmin(UserMixin):
    def __init__(self) -> None:
        self.id = "admin-teste"
        self.matricula = "admin-teste"
        self.nome = "Administrador Teste"
        self.is_admin = 1


class DevolucaoExpressaApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.app.config["TESTING"] = True

    def setUp(self) -> None:
        self.client = self.app.test_client()
        self.user_loader_patcher = patch.object(
            login_manager,
            "_user_callback",
            new=lambda _user_id: _FakeAdmin(),
        )
        self.user_loader_patcher.start()
        with self.client.session_transaction() as session:
            session["_user_id"] = "admin-teste"
            session["_fresh"] = True

    def tearDown(self) -> None:
        self.user_loader_patcher.stop()

    @staticmethod
    def _window_open() -> dict[str, object]:
        start_utc = datetime(2026, 4, 10, 3, 0, 0)
        end_utc = datetime(2026, 4, 10, 15, 0, 0)
        return {
            "window_open": True,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "cutoff_label": "17:00",
            "today_label": "10/04/2026",
        }

    def test_get_devolucao_expressa_lista_itens_elegiveis(self) -> None:
        window = self._window_open()
        itens = [
            {
                "codigo": "ITEM-001",
                "descricao": "Cabo PP 2x2,5",
                "categoria": "Material Elétrico",
                "marca": "Silmec",
                "local_servico": "Bloco 4",
                "atividade_operacional": "eletrica",
                "retirado_hoje": 3.0,
                "retirado_hoje_display": "3 un",
                "pendente_hoje": 2.0,
                "pendente_hoje_display": "2 un",
                "devolucao_unidade_codigo": "unidade",
                "devolucao_unidade_exibicao": "un",
                "devolucao_unidade_label": "Unidade",
                "devolucao_unidades_opcoes": [
                    {
                        "unit_code": "unidade",
                        "unit_display": "un",
                        "unit_label": "Unidade",
                        "input_step": "1",
                        "input_min": "1",
                    }
                ],
                "ultima_saida_em": "2026-04-10T15:00:00Z",
                "ultima_saida_label": "10/04/2026 12:00",
            }
        ]

        with patch.object(
            movements_view,
            "_resolve_usuario",
            return_value=SimpleNamespace(matricula="123456", nome="Colaborador Teste"),
        ), patch.object(
            movements_view,
            "_build_express_return_window",
            return_value=window,
        ), patch.object(
            movements_view.inventory_service,
            "list_express_material_return_candidates",
            return_value=itens,
        ) as list_mock:
            response = self.client.get(
                "/movimentos/api/devolucao-expressa",
                query_string={"usuario": "123456"},
                headers={"Accept": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["items_count"], 1)
        self.assertEqual(payload["usuario"]["matricula"], "123456")
        self.assertEqual(payload["items"][0]["codigo"], "ITEM-001")
        list_mock.assert_called_once_with(
            matricula="123456",
            start_datetime=window["start_utc"],
            end_datetime=window["end_utc"],
        )

    def test_post_devolucao_expressa_registra_evento(self) -> None:
        window = self._window_open()
        unit_options = [
            {
                "unit_code": "unidade",
                "unit_display": "un",
                "unit_label": "Unidade",
                "input_step": "1",
                "input_min": "1",
            }
        ]

        with patch.object(
            movements_view,
            "_resolve_usuario",
            return_value=SimpleNamespace(matricula="123456", nome="Colaborador Teste"),
        ), patch.object(
            movements_view,
            "_build_express_return_window",
            return_value=window,
        ), patch.object(
            movements_view.inventory_service,
            "get_material_return_unit_options",
            return_value=unit_options,
        ), patch.object(
            movements_view.inventory_service,
            "get_material_return_pending_in_window",
            side_effect=[3.0, 2.0],
        ) as pending_mock, patch.object(
            movements_view.inventory_service,
            "registrar_devolucao_material",
            return_value=SimpleNamespace(id_evento=321),
        ) as register_mock, patch.object(
            movements_view.NotificationRouterService,
            "route_inventory_event",
            return_value=None,
        ) as notify_mock:
            response = self.client.post(
                "/movimentos/api/devolucao-expressa",
                json={
                    "usuario": "123456",
                    "codigo": "ITEM-001",
                    "quantidade": 1,
                    "from_unit": "unidade",
                    "observacao": "Teste automatizado",
                },
                headers={"Accept": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["codigo"], "ITEM-001")
        self.assertEqual(payload["matricula"], "123456")
        self.assertEqual(payload["quantidade_registrada"], 1.0)
        self.assertEqual(payload["pendente_restante"], 2.0)
        register_mock.assert_called_once_with(
            codigo="ITEM-001",
            quantidade=1.0,
            matricula="123456",
            retirada_matricula="123456",
            devolvido_por_matricula="123456",
            from_unit="unidade",
            observacao="Teste automatizado",
            commit=True,
        )
        self.assertEqual(pending_mock.call_count, 2)
        notify_mock.assert_called_once_with(321)

    def test_item_info_retorna_ultima_retirada_pendente_para_a_tela(self) -> None:
        item_data = {
            "codigo": "ITEM-001",
            "descricao": "Cabo PP 2x2,5",
            "categoria": "Material Elétrico",
            "marca": "Silmec",
            "unidade": "un",
            "saldo": 10,
            "saldo_display": "10 un",
            "foto_path": None,
        }
        unit_options = [
            {
                "unit_code": "unidade",
                "unit_display": "un",
                "unit_label": "Unidade",
                "input_step": "1",
                "input_min": "1",
            }
        ]
        retirada_info = {
            "matricula": "1111111111111",
            "nome": "Último Retirante",
            "label": "Último Retirante (Mat. 1111111111111)",
            "pendente": 2.0,
            "ultima_saida_em": datetime(2026, 4, 10, 12, 0, 0),
            "ultima_saida_label": "10/04/2026 12:00",
            "local_servico": "Bloco 4",
            "atividade_operacional": "eletrica",
        }

        with patch.object(
            movements_view.inventory_service,
            "get_item",
            return_value=item_data,
        ), patch.object(
            movements_view.db.session,
            "get",
            return_value=None,
        ), patch.object(
            movements_view.inventory_service,
            "get_material_return_unit_options",
            return_value=unit_options,
        ), patch.object(
            movements_view.inventory_service,
            "get_latest_material_return_holder",
            return_value=retirada_info,
        ), patch.object(
            movements_view.inventory_service,
            "get_material_return_pending",
            return_value=2.0,
        ):
            response = self.client.get(
                "/movimentos/item-info/ITEM-001",
                headers={"Accept": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["found"])
        self.assertEqual(payload["codigo"], "ITEM-001")
        self.assertIsNotNone(payload["retirada_pendente"])
        self.assertEqual(payload["retirada_pendente"]["matricula"], "1111111111111")
        self.assertEqual(payload["retirada_pendente"]["label"], "Último Retirante (Mat. 1111111111111)")
        self.assertEqual(payload["retirada_pendente"]["pendente"], 2.0)

    def test_post_devolucao_separa_retirante_e_devolvedor(self) -> None:
        with patch.object(
            movements_view,
            "_resolve_devolucao_operadores",
            return_value=("1111111111111", SimpleNamespace(matricula="2222222222222", nome="Devolvedor Teste")),
        ), patch.object(
            movements_view.inventory_service,
            "registrar_devolucao_material",
            return_value=SimpleNamespace(id_evento=654),
        ) as register_mock, patch.object(
            movements_view.NotificationRouterService,
            "route_inventory_event",
            return_value=None,
        ) as notify_mock:
            response = self.client.post(
                "/movimentos/devolucao",
                data={
                    "codigo": "ITEM-001",
                    "quantidade": "1",
                    "from_unit": "unidade",
                    "retirada_matricula": "1111111111111",
                    "devolvido_por": "2222222222222",
                    "observacao": "Teste separando atores",
                },
                headers={
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        register_mock.assert_called_once_with(
            codigo="ITEM-001",
            quantidade=1.0,
            matricula="1111111111111",
            retirada_matricula="1111111111111",
            devolvido_por_matricula="2222222222222",
            from_unit="unidade",
            observacao="Teste separando atores",
            commit=True,
        )
        notify_mock.assert_called_once_with(654)


if __name__ == "__main__":
    unittest.main()