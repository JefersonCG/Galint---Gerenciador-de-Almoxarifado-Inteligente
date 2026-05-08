from __future__ import annotations

import os

os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from flask import render_template

from app import create_app
from galint_flask.services.inventory import InventoryService


class MockAdminAdjustmentItem:
    def __init__(
        self,
        *,
        tipo_embalagem_novo: str | None,
        unidade: str,
        grandeza_referencia: float | None = None,
        litros_por_embalagem: float | None = None,
        unidades_por_embalagem: float | None = None,
        descricao: str = "ITEM TESTE",
        categoria: str = "Material/Uso geral",
    ) -> None:
        self.tipo_embalagem_novo = tipo_embalagem_novo
        self.tipo_embalagem = tipo_embalagem_novo
        self.unidade = unidade
        self.grandeza_referencia = grandeza_referencia
        self.litros_por_embalagem = litros_por_embalagem
        self.unidades_por_embalagem = unidades_por_embalagem
        self.descricao = descricao
        self.categoria = categoria
        self.marca = "Marca teste"
        self.product_units = []
        self.product_unit_conversions = []

    def get_nome_embalagem(self) -> str:
        return self.tipo_embalagem_novo or "embalagem"

    def get_nome_embalagem_plural(self) -> str:
        nomes = {
            "balde": "baldes",
            "bombona": "bombonas",
            "rolo": "rolos",
            "lata": "latas",
            "caixa": "caixas",
            "pacote": "pacotes",
            "saco": "sacos",
        }
        return nomes.get(self.tipo_embalagem_novo or "", "embalagens")


def test_admin_adjustment_context_for_packaged_item() -> None:
    item = MockAdminAdjustmentItem(
        tipo_embalagem_novo="balde",
        unidade="Quilo",
        grandeza_referencia=23.0,
        descricao="TEXTURA ACRILICA LISA 23KG",
    )

    context = InventoryService._build_admin_balance_input_context(item=item, current_balance=23.0)

    assert context["supports_packaging"] is True
    assert context["package_factor"] == 23.0
    assert context["internal_unit_code"] == "kg"
    assert context["estimated_packages"] == 1
    assert context["estimated_internal_remainder"] == 0.0


def test_admin_adjustment_modes_convert_to_absolute_balance() -> None:
    item = MockAdminAdjustmentItem(
        tipo_embalagem_novo="balde",
        unidade="Quilo",
        grandeza_referencia=23.0,
        descricao="TEXTURA ACRILICA LISA 23KG",
    )

    direct_target, _ = InventoryService._resolve_admin_target_balance_from_inputs(
        item=item,
        raw_target_balance=None,
        adjustment_payload={
            "admin_balance_mode": "direct",
            "admin_balance_direct_value": "46",
        },
    )
    packages_target, _ = InventoryService._resolve_admin_target_balance_from_inputs(
        item=item,
        raw_target_balance=None,
        adjustment_payload={
            "admin_balance_mode": "packages",
            "admin_balance_packaging_quantity": "5",
        },
    )
    mixed_target, _ = InventoryService._resolve_admin_target_balance_from_inputs(
        item=item,
        raw_target_balance=None,
        adjustment_payload={
            "admin_balance_mode": "packages_plus_internal",
            "admin_balance_packaging_quantity": "5",
            "admin_balance_internal_extra": "3",
        },
    )
    internal_target, _ = InventoryService._resolve_admin_target_balance_from_inputs(
        item=item,
        raw_target_balance=None,
        adjustment_payload={
            "admin_balance_mode": "internal_only",
            "admin_balance_internal_only_value": "23",
        },
    )

    assert direct_target == 46.0
    assert packages_target == 115.0
    assert mixed_target == 118.0
    assert internal_target == 23.0


def test_admin_adjustment_packaging_mode_requires_packaging_support() -> None:
    item = MockAdminAdjustmentItem(
        tipo_embalagem_novo=None,
        unidade="Unidade",
        unidades_por_embalagem=None,
        descricao="PARAFUSO TESTE",
    )

    try:
        InventoryService._resolve_admin_target_balance_from_inputs(
            item=item,
            raw_target_balance=None,
            adjustment_payload={
                "admin_balance_mode": "packages",
                "admin_balance_packaging_quantity": "5",
            },
        )
    except ValueError as exc:
        assert "não possui embalagem configurada" in str(exc)
    else:
        raise AssertionError("Era esperado bloquear o modo por embalagens para item sem embalagem")


def test_admin_adjustment_fallback_context_for_legacy_preview() -> None:
    fallback = InventoryService.build_admin_balance_input_fallback({
        "unidade": "Quilo",
        "saldo_exibido": 23.0,
    })

    assert fallback["supports_packaging"] is False
    assert fallback["default_mode"] == "direct"
    assert fallback["internal_unit_code"] == "kg"
    assert fallback["current_balance"] == 23.0


def test_admin_adjustment_template_keeps_form_enabled_after_daily_limit() -> None:
    preview = {
        "codigo": "7896155116405",
        "descricao": "TEXTURA ACRILICA LISA 23KG",
        "categoria": "Mat. Pintura e Drywall",
        "marca": "Teste",
        "unidade": "Quilo",
        "classification_badge": "success",
        "classification_label": "Alinhado",
        "pre_cadastro_pendente": False,
        "daily_limit_exhausted": True,
        "daily_adjustments_remaining": 0,
        "daily_adjustments_used": 4,
        "daily_limit": 4,
        "daily_reference_date": None,
        "classification": "divergencia_zero",
        "saldo_exibido": 23.0,
        "saldo_display": "23.0 kg",
        "source": "stock_balance",
        "migrated": True,
        "legacy_balance": 23.0,
        "ledger_balance": 23.0,
        "stock_balance": 23.0,
        "divergence_legacy_vs_ledger": 0.0,
        "divergence_ledger_vs_cache": 0.0,
        "explicacao_saldo": "teste",
        "admin_balance_input": InventoryService.build_admin_balance_input_fallback({
            "unidade": "Quilo",
            "saldo_exibido": 23.0,
        }),
    }

    app = create_app()
    with app.app_context():
        with app.test_request_context("/configuracoes/estoque/ajuste-admin?codigo=7896155116405"):
            html = render_template(
                "config/estoque_admin.html",
                preview=preview,
                preview_code=preview["codigo"],
                adjustment_form={},
                recent_adjustments=[],
            )

    assert "Limite diário esgotado" not in html
    assert "Essa contagem agora é apenas informativa" in html
    assert 'name="admin_balance_mode" value="direct" checked' in html
    assert 'name="admin_balance_mode" value="direct" checked disabled' not in html