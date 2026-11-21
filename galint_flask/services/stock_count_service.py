"""Contagem física de um item: consulta e gravação, iguais no site e no app.

O site (modal da busca do topo) e o app (tela "Conferência física") leem o código de
barras da planilha, mostram o saldo do sistema e gravam a quantidade contada pelo motor
auditado de ajuste (`apply_admin_item_adjustments`). Este módulo é o ponto comum: o que
muda entre os dois é só a origem registrada na auditoria e a forma de montar a URL da foto.
"""
from __future__ import annotations

from typing import Any

from ..models import Item
from .inventory import inventory_service

SOURCE_WEB_MODAL = "barcode_stock_count_modal"
SOURCE_MOBILE_APP = "barcode_stock_count_mobile"

MOTIVO_BY_SOURCE = {
    SOURCE_WEB_MODAL: "Contagem física pelo modal de código de barras",
    SOURCE_MOBILE_APP: "Contagem física pelo app (código de barras)",
}


NO_PERMISSION_MESSAGE = (
    "Você pode consultar, mas não alterar o estoque. "
    "Peça a um administrador para marcar \"Pode alterar o estoque\" no seu cadastro."
)


class StockCountError(ValueError):
    """Erro que vira mensagem para quem está contando (status HTTP junto)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def can_adjust_stock(user: Any) -> bool:
    """Gravar a contagem: administradores sempre; os demais só com "Pode alterar o estoque".

    Até 21/11/2026 qualquer usuário logado gravava. A partir daí, por decisão do usuário, a consulta
    continua livre e a gravação depende da permissão marcada em Usuários.
    """
    if user is None:
        return False
    return bool(getattr(user, "is_admin", 0)) or bool(getattr(user, "pode_ajustar_estoque", 0))


def ensure_can_adjust_stock(user: Any) -> None:
    if not can_adjust_stock(user):
        raise StockCountError(NO_PERMISSION_MESSAGE, status=403)


def photo_static_path(item: Item) -> str | None:
    """Caminho da foto dentro de /static (sem barra inicial nem prefixo "static/")."""
    path = str(getattr(item, "foto_path", None) or "").strip().lstrip("/")
    if path.lower().startswith("static/"):
        path = path[len("static/"):]
    return path or None


def item_snapshot(item: Item) -> dict[str, Any]:
    """O que a tela de contagem mostra do item (sem a URL da foto, que cada lado monta)."""
    try:
        snapshot = inventory_service.get_stock_count_snapshot(item.codigo_item)
    except ValueError as exc:
        raise StockCountError(str(exc), status=404) from exc
    return {
        "codigo": snapshot["codigo"],
        "descricao": snapshot["descricao"],
        "unidade": snapshot["unidade"],
        "saldo": snapshot["saldo_exibido"],
        "saldo_display": snapshot["saldo_display"],
        "input": snapshot["admin_balance_input"],
        "pre_cadastro_pendente": snapshot["pre_cadastro_pendente"],
    }


def build_adjustment_payload(data: Any) -> dict[str, Any]:
    """Traduz o corpo enviado pela tela para o formato do motor de ajuste."""
    if not isinstance(data, dict):
        raise StockCountError("Informe a contagem física do item.")
    mode = str(data.get("mode") or "").strip().lower()
    if mode == "packages_plus_internal":
        return {
            "admin_balance_mode": mode,
            "admin_balance_packaging_quantity": data.get("package_quantity"),
            "admin_balance_internal_extra": data.get("internal_quantity"),
        }
    if mode == "direct":
        return {
            "admin_balance_mode": mode,
            "admin_balance_direct_value": data.get("quantity"),
        }
    raise StockCountError("Modo de contagem inválido.")


def apply_count(
    codigo: str,
    data: Any,
    *,
    user_id: str,
    user_name: str | None,
    source: str,
    route: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    extra_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grava a quantidade contada. Erros de validação do motor viram StockCountError."""
    adjustment_payload = build_adjustment_payload(data)
    audit_context = {
        "source": source,
        "route": route,
        "user_id": user_id,
        "user_name": user_name,
        "ip_address": ip_address,
        "user_agent": user_agent,
    }
    if extra_audit:
        audit_context.update(extra_audit)
    try:
        return inventory_service.apply_admin_item_adjustments(
            codigo_atual=codigo,
            novo_codigo=None,
            novo_saldo=None,
            adjustment_payload=adjustment_payload,
            matricula=user_id,
            motivo=MOTIVO_BY_SOURCE.get(source, "Contagem física"),
            audit_context=audit_context,
        )
    except StockCountError:
        raise
    except ValueError as exc:
        raise StockCountError(str(exc)) from exc
