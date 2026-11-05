"""Regressoes das mensagens de indisponibilidade na tela de Registro de Saida.

Defeito que originou: quando a ferramenta ja estava retirada por outro colaborador,
a tela de saida so dizia "Sem saldo disponivel" e escondia o item da busca, sem
informar com quem a ferramenta estava.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask.services.inventory import InventoryService
from galint_flask.services.tool_custody_service import ToolCustodyService


def _tool_holder(
    *,
    nome: str = "Joao da Silva",
    matricula: str = "12345",
    quantidade: float = 1.0,
    status: str = "em_uso",
    desde_label: str | None = "23/09/2026 08:10",
    local_servico: str | None = "Bloco 5",
) -> dict:
    return {
        "matricula": matricula,
        "nome": nome,
        "label": f"{nome} ({matricula})",
        "quantidade": quantidade,
        "quantidade_display": InventoryService._format_availability_quantity(quantidade),
        "status": status,
        "status_label": InventoryService._format_tool_holder_status(status),
        "desde": None,
        "desde_label": desde_label,
        "previsao_devolucao": None,
        "local_servico": local_servico,
    }


def test_ferramenta_toda_em_uso_informa_com_quem_esta() -> None:
    service = InventoryService()
    item = SimpleNamespace(categoria="Ferramentas")
    payload = {"categoria": "Ferramentas", "saldo": 1.0}

    resultado = service._apply_withdrawal_availability(
        item,
        payload,
        tool_state={
            "reserved_quantity": 1.0,
            "repair_quantity": 0.0,
            "has_open_repair": False,
            "holders": [_tool_holder()],
        },
    )

    assert resultado["is_available"] is False
    assert resultado["unavailable_reason"] == "Ferramenta em uso com outro colaborador"
    detalhe = resultado["unavailable_detail"]
    assert "Joao da Silva" in detalhe
    assert "23/09/2026 08:10" in detalhe
    assert "Bloco 5" in detalhe
    assert resultado["custodia_resumo"] == "Em uso com Joao da Silva (12345) desde 23/09/2026 08:10."
    assert resultado["custodia_detalhes"] == [
        "Joao da Silva (12345) — desde 23/09/2026 08:10 — local: Bloco 5"
    ]


def test_ferramenta_em_uso_com_varios_colaboradores_resume_a_fila() -> None:
    service = InventoryService()
    item = SimpleNamespace(categoria="Ferramentas")
    payload = {"categoria": "Ferramentas", "saldo": 2.0}

    resultado = service._apply_withdrawal_availability(
        item,
        payload,
        tool_state={
            "reserved_quantity": 2.0,
            "repair_quantity": 0.0,
            "has_open_repair": False,
            "holders": [
                _tool_holder(),
                _tool_holder(nome="Maria Souza", matricula="54321", status="atrasada"),
            ],
        },
    )

    assert resultado["is_available"] is False
    assert "2 colaboradores" in resultado["unavailable_detail"]
    assert resultado["custodia_resumo"] == "Em uso com Joao da Silva (12345) e mais 1 colaborador(es)."
    assert "situação: devolução atrasada" in resultado["custodia_detalhes"][1]


def test_ferramenta_em_reparo_mantem_motivo_proprio() -> None:
    service = InventoryService()
    item = SimpleNamespace(categoria="Ferramentas")
    payload = {"categoria": "Ferramentas", "saldo": 3.0}

    resultado = service._apply_withdrawal_availability(
        item,
        payload,
        tool_state={
            "reserved_quantity": 0.0,
            "repair_quantity": 1.0,
            "has_open_repair": True,
            "holders": [_tool_holder(status="para_reparo")],
        },
    )

    assert resultado["is_available"] is False
    assert resultado["unavailable_reason"] == "Ferramenta em reparo"
    assert "reparo" in resultado["unavailable_detail"].lower()


def test_ferramenta_com_saldo_livre_continua_disponivel_mas_informa_custodia() -> None:
    service = InventoryService()
    item = SimpleNamespace(categoria="Ferramentas")
    payload = {"categoria": "Ferramentas", "saldo": 3.0}

    resultado = service._apply_withdrawal_availability(
        item,
        payload,
        tool_state={
            "reserved_quantity": 1.0,
            "repair_quantity": 0.0,
            "has_open_repair": False,
            "holders": [_tool_holder()],
        },
    )

    assert resultado["is_available"] is True
    assert resultado["unavailable_reason"] is None
    assert resultado["saldo_disponivel"] == 2.0
    assert resultado["custodia_resumo"].startswith("Em uso com Joao da Silva")


def test_item_comum_zerado_recebe_motivo_estoque_zerado() -> None:
    service = InventoryService()
    item = SimpleNamespace(categoria="Materiais de Limpeza")
    payload = {"categoria": "Materiais de Limpeza", "saldo": 0.0}

    resultado = service._apply_withdrawal_availability(item, payload)

    assert resultado["is_available"] is False
    assert resultado["unavailable_reason"] == "Estoque zerado"
    assert "estoque zerado" in resultado["unavailable_detail"].lower()
    assert resultado["custodia_ativa"] == []
    assert resultado["custodia_resumo"] is None


def test_ferramenta_sem_retirada_aberta_e_sem_saldo_aponta_estoque_zerado() -> None:
    service = InventoryService()
    item = SimpleNamespace(categoria="Ferramentas")
    payload = {"categoria": "Ferramentas", "saldo": 0.0}

    resultado = service._apply_withdrawal_availability(
        item,
        payload,
        tool_state={
            "reserved_quantity": 0.0,
            "repair_quantity": 0.0,
            "has_open_repair": False,
            "holders": [],
        },
    )

    assert resultado["is_available"] is False
    assert resultado["unavailable_reason"] == "Estoque zerado"


def test_descricao_do_detentor_inclui_quantidade_quando_maior_que_uma_unidade() -> None:
    descricao = InventoryService._describe_tool_holder(_tool_holder(quantidade=3.0))

    assert "3 unidades" in descricao
    assert descricao.startswith("Joao da Silva (12345)")


def test_custodia_aberta_nao_vira_permanente_so_por_ter_mais_de_30_dias() -> None:
    assert not ToolCustodyService.is_permanent_custody(
        tipo_custodia_raw="temporaria",
        days_in_use=120,
    )
    assert ToolCustodyService.is_permanent_custody(tipo_custodia_raw="permanente")
