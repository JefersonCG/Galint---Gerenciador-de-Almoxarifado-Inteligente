from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest

from galint_flask.services.finance_service import FinanceService


def _make_document(
    document_id: int,
    *,
    numero_documento: str = "123",
    tipo_documento: str = "nf",
    fornecedor_id: int | None = None,
    fornecedor_nome: str | None = None,
    cnpj_emitente: str | None = None,
    chave_acesso: str | None = None,
    criado_em: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id_documento=document_id,
        numero_documento=numero_documento,
        tipo_documento=tipo_documento,
        fornecedor_id=fornecedor_id,
        fornecedor_nome=fornecedor_nome,
        cnpj_emitente=cnpj_emitente,
        chave_acesso=chave_acesso,
        criado_em=criado_em or (datetime(2026, 4, 1, 12, 0, 0) + timedelta(minutes=document_id)),
        status_integracao="manual",
        observacao=None,
    )


class DocumentoReusoIdentidadeTests(unittest.TestCase):
    def test_select_reusable_existing_document_raises_for_ambiguous_supplierless_number(self) -> None:
        documents = [
            _make_document(1, fornecedor_id=10, cnpj_emitente="11.111.111/0001-11", fornecedor_nome="Fornecedor A"),
            _make_document(2, fornecedor_id=20, cnpj_emitente="22.222.222/0001-22", fornecedor_nome="Fornecedor B"),
        ]

        with self.assertRaisesRegex(ValueError, "mistura documental"):
            FinanceService._select_reusable_existing_document(
                documents,
                require_unambiguous_identity=True,
            )

    def test_select_reusable_existing_document_prefers_best_document_for_same_supplier(self) -> None:
        older = _make_document(
            1,
            fornecedor_id=10,
            cnpj_emitente="11.111.111/0001-11",
            fornecedor_nome="Fornecedor A",
            criado_em=datetime(2026, 4, 1, 12, 0, 0),
        )
        newer = _make_document(
            2,
            fornecedor_id=10,
            cnpj_emitente="11.111.111/0001-11",
            fornecedor_nome="Fornecedor A",
            chave_acesso="35190400000000000000550010000000011000000011",
            criado_em=datetime(2026, 4, 1, 12, 5, 0),
        )

        selected = FinanceService._select_reusable_existing_document(
            [older, newer],
            require_unambiguous_identity=True,
        )

        self.assertIs(selected, newer)


if __name__ == "__main__":
    unittest.main()