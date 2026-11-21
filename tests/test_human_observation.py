"""Obs. dos avisos (app e imagens do Telegram) só com o que uma pessoa entende de primeira.

Origem: em 21/11/2026 o usuário viu nos avisos do app "Obs.: UNIDADE=UNIDADE;QTD_ORIGINAL=1"
(1.096 saídas têm essa observação técnica) e, numa contagem, o texto de auditoria do ajuste.
"""
import pytest

from galint_flask.services.operation_visual_payload import human_observation


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("UNIDADE=UNIDADE;QTD_ORIGINAL=1", None),
        ("UNIDADE=KG;QTD_ORIGINAL=5", None),
        ("  ", None),
        (None, None),
        ("Associado via Central de Kits", "Associado via Central de Kits"),
        ("FICOU SOB RESPONSABILIDADE", "FICOU SOB RESPONSABILIDADE"),
        ("Retirada fracionada: 9 LITRO", "Retirada fracionada: 9 LITRO"),
        ("UNIDADE=PAR;QTD_ORIGINAL=2;Trocar no bloco B", "Trocar no bloco B"),
        (
            "Ajuste administrativo de saldo [Contagem física pelo app (código de barras)]: "
            "exibido 5 -> 4; legado 5 -> 4; ledger 5 -> 4; cache 5 -> 4",
            "Conferência física: 5 → 4",
        ),
        (
            "Ajuste administrativo de saldo [Contagem física pelo modal de código de barras]: exibido 2.5 -> 3",
            "Conferência física: 2,5 → 3",
        ),
        ("Ajuste administrativo de saldo [Correção manual]: exibido 10 -> 0; legado 10 -> 0", "Ajuste de saldo: 10 → 0"),
    ],
)
def test_human_observation(raw, expected):
    assert human_observation(raw) == expected
