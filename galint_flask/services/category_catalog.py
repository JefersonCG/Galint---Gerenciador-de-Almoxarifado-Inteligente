from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import FinanceLedgerEntry, InventoryCategory, Item


@dataclass(frozen=True)
class DefaultInventoryCategory:
    nome: str
    descricao: str
    ordem: int


DEFAULT_INVENTORY_CATEGORIES: tuple[DefaultInventoryCategory, ...] = (
    DefaultInventoryCategory("Material Elétrico", "Infraestrutura elétrica e componentes de energia.", 10),
    DefaultInventoryCategory("Material Hidráulico", "Tubulações, conexões e manutenção hidráulica.", 20),
    DefaultInventoryCategory("Material Piscina", "Tratamento, manutenção e operação de piscina.", 30),
    DefaultInventoryCategory("Mat. Pintura e Drywall", "Tintas, massas, drywall e acabamento.", 40),
    DefaultInventoryCategory("Materiais de Limpeza", "Produtos e insumos de limpeza operacional.", 50),
    DefaultInventoryCategory("Material Construção", "Materiais estruturais e de obra civil.", 60),
    DefaultInventoryCategory("Ferramentas", "Ferramentas de uso manual e apoio técnico.", 70),
    DefaultInventoryCategory("Equipamento", "Equipamentos permanentes e itens eletrificados.", 80),
    DefaultInventoryCategory("Material de EP", "Equipamentos e materiais de proteção individual.", 90),
    DefaultInventoryCategory("Material/Uso geral", "Itens transversais de uso geral e apoio operacional.", 100),
)

DEFAULT_INVENTORY_CATEGORY_NAME = DEFAULT_INVENTORY_CATEGORIES[0].nome


def normalize_inventory_category_name(value: object) -> str:
    return " ".join(str(value or "").strip().split())


class CategoryCatalogService:
    def ensure_seeded(self) -> None:
        existing_rows = InventoryCategory.query.order_by(InventoryCategory.ordem.asc(), InventoryCategory.id.asc()).all()
        existing_map = {
            normalize_inventory_category_name(row.nome).casefold(): row
            for row in existing_rows
            if normalize_inventory_category_name(row.nome)
        }
        changed = False

        for default_row in DEFAULT_INVENTORY_CATEGORIES:
            normalized_name = normalize_inventory_category_name(default_row.nome)
            existing = existing_map.get(normalized_name.casefold())
            if existing is None:
                new_row = InventoryCategory(
                    nome=default_row.nome,
                    descricao=default_row.descricao,
                    ordem=default_row.ordem,
                    ativa=True,
                    sistema=True,
                )
                db.session.add(new_row)
                existing_map[normalized_name.casefold()] = new_row
                changed = True
                continue

            row_changed = False
            if not existing.sistema:
                existing.sistema = True
                row_changed = True
            if existing.ordem != default_row.ordem:
                existing.ordem = default_row.ordem
                row_changed = True
            if not (existing.descricao or "").strip():
                existing.descricao = default_row.descricao
                row_changed = True
            if row_changed:
                changed = True

        item_categories = {
            normalize_inventory_category_name(value)
            for (value,) in db.session.query(Item.categoria).distinct().all()
            if normalize_inventory_category_name(value)
        }
        if item_categories:
            max_order = max((int(row.ordem or 0) for row in existing_map.values()), default=0)
            for category_name in sorted(item_categories):
                normalized_key = category_name.casefold()
                if normalized_key in existing_map:
                    continue
                max_order += 10
                new_row = InventoryCategory(
                    nome=category_name,
                    ordem=max_order,
                    ativa=True,
                    sistema=False,
                )
                db.session.add(new_row)
                existing_map[normalized_key] = new_row
                changed = True

        if changed:
            db.session.flush()

    def list_categories(self, *, include_inactive: bool = False) -> list[InventoryCategory]:
        self.ensure_seeded()
        query = InventoryCategory.query
        if not include_inactive:
            query = query.filter(InventoryCategory.ativa.is_(True))
        return query.order_by(
            InventoryCategory.ordem.asc(),
            func.lower(InventoryCategory.nome).asc(),
            InventoryCategory.id.asc(),
        ).all()

    def list_form_choices(self, *, selected_name: str | None = None) -> list[str]:
        selected_normalized = normalize_inventory_category_name(selected_name)
        categories = self.list_categories(include_inactive=bool(selected_normalized))
        seen: set[str] = set()
        options: list[str] = []
        for category in categories:
            normalized_name = normalize_inventory_category_name(category.nome)
            if not normalized_name:
                continue
            if not category.ativa and normalized_name != selected_normalized:
                continue
            if normalized_name.casefold() in seen:
                continue
            seen.add(normalized_name.casefold())
            options.append(category.nome)
        if selected_normalized and selected_normalized.casefold() not in seen:
            options.append(selected_normalized)
        return options or [DEFAULT_INVENTORY_CATEGORY_NAME]

    def resolve_name(
        self,
        value: object,
        *,
        fallback: str = DEFAULT_INVENTORY_CATEGORY_NAME,
        actor: str | None = None,
        auto_create: bool = True,
    ) -> str:
        self.ensure_seeded()
        normalized_name = normalize_inventory_category_name(value)
        if not normalized_name:
            normalized_name = normalize_inventory_category_name(fallback) or DEFAULT_INVENTORY_CATEGORY_NAME

        existing = self._find_by_name(normalized_name)
        if existing is not None:
            if auto_create and not existing.ativa:
                existing.ativa = True
                if actor:
                    existing.atualizada_por = actor
                db.session.flush()
            return existing.nome

        if not auto_create:
            return normalized_name

        max_order = db.session.query(func.max(InventoryCategory.ordem)).scalar() or 0
        new_row = InventoryCategory(
            nome=normalized_name,
            ordem=int(max_order) + 10,
            ativa=True,
            sistema=False,
            criada_por=actor,
            atualizada_por=actor,
        )
        db.session.add(new_row)
        db.session.flush()
        return new_row.nome

    def create_category(
        self,
        *,
        nome: object,
        descricao: object | None = None,
        ordem: object | None = None,
        ativa: bool = True,
        actor: str | None = None,
    ) -> InventoryCategory:
        self.ensure_seeded()
        normalized_name = normalize_inventory_category_name(nome)
        if not normalized_name:
            raise ValueError("Informe um nome de categoria.")
        if self._find_by_name(normalized_name) is not None:
            raise ValueError("Já existe uma categoria com esse nome.")

        max_order = db.session.query(func.max(InventoryCategory.ordem)).scalar() or 0
        parsed_order = self._parse_order(ordem, fallback=int(max_order) + 10)
        row = InventoryCategory(
            nome=normalized_name,
            descricao=normalize_inventory_category_name(descricao) or None,
            ordem=parsed_order,
            ativa=bool(ativa),
            sistema=False,
            criada_por=actor,
            atualizada_por=actor,
        )
        db.session.add(row)
        db.session.commit()
        return row

    def update_category(
        self,
        category_id: int,
        *,
        nome: object,
        descricao: object | None = None,
        ordem: object | None = None,
        ativa: bool = True,
        actor: str | None = None,
    ) -> InventoryCategory:
        row = InventoryCategory.query.get(category_id)
        if row is None:
            raise ValueError("Categoria não encontrada.")

        normalized_name = normalize_inventory_category_name(nome)
        if not normalized_name:
            raise ValueError("Informe um nome de categoria.")
        if row.sistema and normalized_name.casefold() != row.nome.casefold():
            raise ValueError("Categorias-base do sistema não podem ser renomeadas. Crie uma categoria nova quando precisar de outro nome.")

        duplicate = self._find_by_name(normalized_name)
        if duplicate is not None and duplicate.id != row.id:
            raise ValueError("Já existe uma categoria com esse nome.")

        if row.sistema and not ativa:
            raise ValueError("Categorias-base do sistema não podem ser desativadas.")

        old_name = row.nome
        row.nome = normalized_name
        row.descricao = normalize_inventory_category_name(descricao) or None
        row.ordem = self._parse_order(ordem, fallback=int(row.ordem or 0))
        row.ativa = bool(ativa)
        row.atualizada_por = actor

        if old_name != normalized_name:
            (
                Item.query.filter(Item.categoria == old_name)
                .update({Item.categoria: normalized_name, Item.setor: normalized_name}, synchronize_session=False)
            )
            (
                FinanceLedgerEntry.query.filter(FinanceLedgerEntry.categoria_nome == old_name)
                .update({FinanceLedgerEntry.categoria_nome: normalized_name}, synchronize_session=False)
            )

        db.session.commit()
        return row

    def delete_category(self, category_id: int) -> None:
        row = InventoryCategory.query.get(category_id)
        if row is None:
            raise ValueError("Categoria não encontrada.")
        if row.sistema:
            raise ValueError("Categorias-base do sistema não podem ser excluídas.")

        linked_items = int(
            db.session.query(func.count(Item.codigo_item))
            .filter(Item.categoria == row.nome)
            .scalar()
            or 0
        )
        if linked_items > 0:
            raise ValueError("Remova ou reclassifique os itens dessa categoria antes de excluí-la do catálogo.")

        db.session.delete(row)
        db.session.commit()

    @staticmethod
    def _parse_order(value: object | None, *, fallback: int) -> int:
        try:
            return int(value) if value not in (None, "") else int(fallback)
        except (TypeError, ValueError):
            return int(fallback)

    @staticmethod
    def _find_by_name(nome: str) -> InventoryCategory | None:
        normalized_name = normalize_inventory_category_name(nome)
        if not normalized_name:
            return None
        return (
            InventoryCategory.query
            .filter(func.lower(InventoryCategory.nome) == normalized_name.casefold())
            .first()
        )


category_catalog_service = CategoryCatalogService()