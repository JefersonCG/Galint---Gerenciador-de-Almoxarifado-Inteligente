"""Unifica documentos manuais sem lastro fiscal no bucket canônico NOTA INTERNA.

Regras:
- considera candidatos os documentos de entrada `manual` que já usam `SEM NF/CUPOM`/`NOTA INTERNA`
  ou que não possuem fornecedor, CNPJ nem chave de acesso;
- move todos os itens desses documentos para um único cabeçalho canônico `NOTA INTERNA`;
- atualiza referências textuais em entradas, ledger financeiro e cadastro de itens.

O script é idempotente e pode ser executado novamente com segurança.
Use `--dry-run` para inspecionar antes de aplicar.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import bindparam, create_engine, text


CANONICAL_NUMBER = "NOTA INTERNA"
LEGACY_ALIASES = (CANONICAL_NUMBER, "SEM NF/CUPOM")
LEGACY_ALIASES_UPPER = tuple(alias.upper() for alias in LEGACY_ALIASES)
GENERIC_OBSERVATION = "Documento interno consolidado automaticamente para itens sem lastro fiscal."

SELECT_CANDIDATE_DOCUMENTS = text(
    """
    SELECT
        id_documento,
        numero_documento,
        data_emissao,
        data_recebimento,
        observacao,
        criado_por,
        criado_em,
        atualizado_em
    FROM entrada_documentos
    WHERE lower(coalesce(tipo_documento, '')) = 'manual'
      AND (
        upper(trim(coalesce(numero_documento, ''))) IN :legacy_aliases
        OR (
            trim(coalesce(chave_acesso, '')) = ''
            AND trim(coalesce(cnpj_emitente, '')) = ''
            AND fornecedor_id IS NULL
            AND trim(coalesce(fornecedor_nome, '')) = ''
        )
      )
    ORDER BY
        CASE
            WHEN upper(trim(coalesce(numero_documento, ''))) = :canonical_upper THEN 0
            WHEN upper(trim(coalesce(numero_documento, ''))) = 'SEM NF/CUPOM' THEN 1
            ELSE 2
        END,
        coalesce(atualizado_em, criado_em) DESC,
        id_documento DESC
    """
).bindparams(bindparam("legacy_aliases", expanding=True))

SELECT_ENTRY_IDS = text(
    """
    SELECT DISTINCT entrada_id
    FROM entrada_documento_itens
    WHERE documento_id IN :document_ids
      AND entrada_id IS NOT NULL
    """
).bindparams(bindparam("document_ids", expanding=True))

COUNT_DOCUMENT_ITEMS = text(
    """
    SELECT count(*)
    FROM entrada_documento_itens
    WHERE documento_id IN :document_ids
    """
).bindparams(bindparam("document_ids", expanding=True))

MOVE_DOCUMENT_ITEMS = text(
    """
    UPDATE entrada_documento_itens
    SET documento_id = :canonical_id
    WHERE documento_id IN :document_ids
    """
).bindparams(bindparam("document_ids", expanding=True))

UPDATE_CANONICAL_DOCUMENT = text(
    """
    UPDATE entrada_documentos
    SET numero_documento = :canonical_number,
        tipo_documento = 'manual',
        fornecedor_id = NULL,
        fornecedor_nome = NULL,
        cnpj_emitente = NULL,
        chave_acesso = NULL,
        status_integracao = 'manual',
        mensagem_integracao = NULL,
        data_emissao = coalesce(:data_emissao, data_emissao, CURRENT_DATE),
        data_recebimento = coalesce(:data_recebimento, data_recebimento, CURRENT_DATE),
        observacao = coalesce(nullif(trim(observacao), ''), :generic_observation),
        atualizado_em = CURRENT_TIMESTAMP
    WHERE id_documento = :canonical_id
    """
)

DELETE_DUPLICATE_DOCUMENTS = text(
    """
    DELETE FROM entrada_documentos
    WHERE id_documento IN :document_ids
    """
).bindparams(bindparam("document_ids", expanding=True))

UPDATE_ENTRADAS = text(
    """
    UPDATE entradas
    SET nota_fiscal = :canonical_number
    WHERE upper(trim(coalesce(nota_fiscal, ''))) IN :candidate_numbers_upper
       OR id_entrada IN :entry_ids
    """
).bindparams(
    bindparam("candidate_numbers_upper", expanding=True),
    bindparam("entry_ids", expanding=True),
)

UPDATE_FINANCE = text(
    """
    UPDATE finance_lancamentos
    SET numero_documento = :canonical_number
    WHERE lower(coalesce(tipo_documento, '')) = 'manual'
      AND trim(coalesce(chave_acesso, '')) = ''
      AND fornecedor_id IS NULL
      AND (
        upper(trim(coalesce(numero_documento, ''))) IN :candidate_numbers_upper
        OR entrada_id IN :entry_ids
      )
    """
).bindparams(
    bindparam("candidate_numbers_upper", expanding=True),
    bindparam("entry_ids", expanding=True),
)

UPDATE_ITEM_NOTA_FISCAL = text(
    """
    UPDATE itens
    SET nota_fiscal = :canonical_number
    WHERE upper(trim(coalesce(nota_fiscal, ''))) IN :candidate_numbers_upper
    """
).bindparams(bindparam("candidate_numbers_upper", expanding=True))

UPDATE_ITEM_PRECO_DOCUMENTO = text(
    """
    UPDATE itens
    SET preco_compra_documento = :canonical_number
    WHERE upper(trim(coalesce(preco_compra_documento, ''))) IN :candidate_numbers_upper
    """
).bindparams(bindparam("candidate_numbers_upper", expanding=True))


def _load_project_env() -> None:
    root = Path(__file__).resolve().parent
    env_path = root / ".env"
    env_local_path = root / ".env.local"
    if env_path.exists():
        load_dotenv(env_path, override=False)
    if env_local_path.exists():
        load_dotenv(env_local_path, override=True)


def _resolve_db_url() -> str:
    _load_project_env()
    db_url = os.environ.get("GALINT_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit(
            "Banco não configurado. Defina GALINT_DATABASE_URI (ou DATABASE_URL) em .env/.env.local ou no ambiente."
        )
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://") :]
    return db_url


def _collect_candidate_numbers(rows: list[dict[str, object]]) -> list[str]:
    normalized = {alias.upper() for alias in LEGACY_ALIASES}
    for row in rows:
        numero = str(row.get("numero_documento") or "").strip()
        if numero:
            normalized.add(numero.upper())
    return sorted(normalized)


def _pick_latest_date(rows: list[dict[str, object]], key: str):
    values = [row.get(key) for row in rows if row.get(key) is not None]
    if not values:
        return None
    return max(values)


def _print_summary(rows: list[dict[str, object]], item_count: int, entry_count: int, candidate_numbers: list[str]) -> None:
    print(f"Documentos candidatos: {len(rows)}")
    print(f"Itens documentais envolvidos: {item_count}")
    print(f"Entradas vinculadas: {entry_count}")
    print("Números candidatos:", ", ".join(candidate_numbers))
    print("Cabeçalhos encontrados:")
    for row in rows:
        print(
            f"- id={row['id_documento']} numero={row['numero_documento']!r} "
            f"emissao={row['data_emissao']} recebimento={row['data_recebimento']}"
        )


def executar_migracao(*, dry_run: bool) -> dict[str, object]:
    db_url = _resolve_db_url()
    print("Conectando em:", db_url)

    engine = create_engine(db_url)
    with engine.begin() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                SELECT_CANDIDATE_DOCUMENTS,
                {
                    "legacy_aliases": list(LEGACY_ALIASES_UPPER),
                    "canonical_upper": CANONICAL_NUMBER.upper(),
                },
            ).mappings()
        ]

        if not rows:
            print("Nenhum documento manual elegível para unificação foi encontrado.")
            return {
                "documents": 0,
                "items_moved": 0,
                "duplicate_documents_removed": 0,
                "entries_updated": 0,
                "finance_rows_updated": 0,
                "items_nf_updated": 0,
                "items_price_doc_updated": 0,
                "dry_run": dry_run,
            }

        document_ids = [int(row["id_documento"]) for row in rows]
        item_count = int(conn.execute(COUNT_DOCUMENT_ITEMS, {"document_ids": document_ids}).scalar() or 0)
        entry_ids = [
            int(row["entrada_id"])
            for row in conn.execute(SELECT_ENTRY_IDS, {"document_ids": document_ids}).mappings()
        ]
        candidate_numbers = _collect_candidate_numbers(rows)
        _print_summary(rows, item_count, len(entry_ids), candidate_numbers)

        if dry_run:
            print("Dry-run concluído. Nenhuma alteração foi aplicada.")
            return {
                "documents": len(rows),
                "items_moved": max(item_count, 0),
                "duplicate_documents_removed": max(len(rows) - 1, 0),
                "entries_updated": len(entry_ids),
                "finance_rows_updated": 0,
                "items_nf_updated": 0,
                "items_price_doc_updated": 0,
                "dry_run": True,
            }

        canonical_row = rows[0]
        canonical_id = int(canonical_row["id_documento"])
        duplicate_ids = [doc_id for doc_id in document_ids if doc_id != canonical_id]
        data_emissao = _pick_latest_date(rows, "data_emissao")
        data_recebimento = _pick_latest_date(rows, "data_recebimento")

        items_moved = 0
        if duplicate_ids:
            items_moved = int(
                conn.execute(
                    MOVE_DOCUMENT_ITEMS,
                    {
                        "canonical_id": canonical_id,
                        "document_ids": duplicate_ids,
                    },
                ).rowcount
                or 0
            )

        conn.execute(
            UPDATE_CANONICAL_DOCUMENT,
            {
                "canonical_id": canonical_id,
                "canonical_number": CANONICAL_NUMBER,
                "data_emissao": data_emissao,
                "data_recebimento": data_recebimento,
                "generic_observation": GENERIC_OBSERVATION,
            },
        )

        duplicate_documents_removed = 0
        if duplicate_ids:
            duplicate_documents_removed = int(
                conn.execute(
                    DELETE_DUPLICATE_DOCUMENTS,
                    {"document_ids": duplicate_ids},
                ).rowcount
                or 0
            )

        update_entry_ids = entry_ids or [-1]
        entries_updated = int(
            conn.execute(
                UPDATE_ENTRADAS,
                {
                    "canonical_number": CANONICAL_NUMBER,
                    "candidate_numbers_upper": candidate_numbers,
                    "entry_ids": update_entry_ids,
                },
            ).rowcount
            or 0
        )

        finance_rows_updated = int(
            conn.execute(
                UPDATE_FINANCE,
                {
                    "canonical_number": CANONICAL_NUMBER,
                    "candidate_numbers_upper": candidate_numbers,
                    "entry_ids": update_entry_ids,
                },
            ).rowcount
            or 0
        )

        items_nf_updated = int(
            conn.execute(
                UPDATE_ITEM_NOTA_FISCAL,
                {
                    "canonical_number": CANONICAL_NUMBER,
                    "candidate_numbers_upper": candidate_numbers,
                },
            ).rowcount
            or 0
        )

        items_price_doc_updated = int(
            conn.execute(
                UPDATE_ITEM_PRECO_DOCUMENTO,
                {
                    "canonical_number": CANONICAL_NUMBER,
                    "candidate_numbers_upper": candidate_numbers,
                },
            ).rowcount
            or 0
        )

    print("Migração concluída com sucesso.")
    return {
        "documents": len(rows),
        "canonical_id": canonical_id,
        "items_moved": items_moved,
        "duplicate_documents_removed": duplicate_documents_removed,
        "entries_updated": entries_updated,
        "finance_rows_updated": finance_rows_updated,
        "items_nf_updated": items_nf_updated,
        "items_price_doc_updated": items_price_doc_updated,
        "dry_run": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Unifica documentos manuais no bucket NOTA INTERNA.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que será alterado sem gravar no banco.")
    args = parser.parse_args()
    resultado = executar_migracao(dry_run=args.dry_run)
    print("Resumo:", resultado)


if __name__ == "__main__":
    main()