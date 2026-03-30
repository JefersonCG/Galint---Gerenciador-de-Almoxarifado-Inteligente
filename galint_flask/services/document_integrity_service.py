from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
from typing import Any

from flask import has_request_context, request
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import event
from sqlalchemy.orm import Session

from ..models import DocumentoEntradaEstoqueItem

logger = logging.getLogger(__name__)

_quantity_update_origin: ContextVar[str | None] = ContextVar(
    "document_quantity_update_origin",
    default=None,
)
_guard_installed = False


@contextmanager
def allow_document_quantity_update(origin: str):
    token = _quantity_update_origin.set((origin or "").strip() or "unspecified")
    try:
        yield
    finally:
        _quantity_update_origin.reset(token)


@event.listens_for(Session, "before_flush")
def _block_unauthorized_document_quantity_changes(session: Session, flush_context: Any, instances: Any) -> None:
    origin = _quantity_update_origin.get()
    for obj in session.dirty:
        if not isinstance(obj, DocumentoEntradaEstoqueItem):
            continue

        state = sa_inspect(obj)
        quantidade_attr = getattr(getattr(state, "attrs", None), "quantidade", None)
        if quantidade_attr is None:
            continue
        history = quantidade_attr.history
        if not history.has_changes():
            continue
        if origin:
            continue

        previous = history.deleted[0] if history.deleted else None
        current = history.added[0] if history.added else getattr(obj, "quantidade", None)
        endpoint = request.endpoint if has_request_context() else None
        path = request.path if has_request_context() else None
        logger.error(
            "Bloqueio de integridade: tentativa nao autorizada de alterar quantidade documental "
            "(documento_item_id=%s, documento_id=%s, codigo_item=%s, anterior=%s, atual=%s, endpoint=%s, path=%s)",
            getattr(obj, "id_documento_item", None),
            getattr(obj, "documento_id", None),
            getattr(obj, "codigo_item", None),
            previous,
            current,
            endpoint,
            path,
        )
        raise ValueError(
            "Alteracao bloqueada: a quantidade da NF/CUPOM so pode ser modificada pelos fluxos autorizados do documento fiscal."
        )


_REGISTERED_DOCUMENT_QUANTITY_GUARD = _block_unauthorized_document_quantity_changes


def install_document_integrity_guards() -> None:
    global _guard_installed
    if _guard_installed:
        return
    _guard_installed = True
