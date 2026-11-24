"""Grupos de itens (produto genérico), 24/11/2026.

Pedido do usuário: "juntar produtos iguais (mesmo sendo marca diferente, código de barras diferente,
embalagem, NF diferente) como se fosse 1 para as retiradas" — ex.: JOELHO 25MM da Amanco (29) e da
Krona (38) viram um produto de 67. Decisões dele:
1. na retirada, sai primeiro o MAIS ANTIGO;
2. grupos sugeridos por nome igual, mas com um mecanismo de seleção — joelho tem de todo tipo (90°, 45°,
   soldável, rosqueável): a busca aceita várias palavras e "-palavra" para excluir ("joelho 25 -45");
3. relatórios por grupo, com o detalhe por marca.

Esta parte cuida dos grupos (sugestões, criação, membros, ordem de retirada). Regras:
- só materiais: ferramentas e equipamentos são controlados um a um (custódia) e ficam fora;
- todos os membros têm a mesma unidade base (somar unidades com metros não faz sentido);
- cada item fica em no máximo um grupo.
"Mais antigo" = membro cuja última entrada (recebimento da NF mais recente) é a mais antiga: o estoque
dele está parado há mais tempo. Membro sem saldo não entra na ordem.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date
from typing import Any, Iterable

from sqlalchemy import func

from ..extensions import db
from ..models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Item, ItemGrupo, ItemGrupoMembro
from ..utils.time_service import TimeService

SUGGESTION_LIMIT = 300
SEARCH_LIMIT = 60


def normalize_name(text: str | None) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(character for character in value if not unicodedata.combining(character)).upper()
    value = re.sub(r"[^A-Z0-9,./]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def unit_key(unit: str | None) -> str:
    return normalize_name(unit).lower()


def is_individual_control(item: Item) -> bool:
    """Ferramenta ou equipamento: controle um a um, fora dos grupos."""
    categoria = normalize_name(getattr(item, "categoria", "")).lower()
    return "ferrament" in categoria or "equipament" in categoria


def _last_entry_dates(codes: Iterable[str]) -> dict[str, date]:
    codes = [code for code in codes if code]
    if not codes:
        return {}
    data = func.coalesce(DocumentoEntradaEstoque.data_recebimento, DocumentoEntradaEstoque.data_emissao)
    rows = (
        db.session.query(DocumentoEntradaEstoqueItem.codigo_item, func.max(data))
        .join(DocumentoEntradaEstoque, DocumentoEntradaEstoque.id_documento == DocumentoEntradaEstoqueItem.documento_id)
        .filter(DocumentoEntradaEstoqueItem.codigo_item.in_(codes))
        .group_by(DocumentoEntradaEstoqueItem.codigo_item)
        .all()
    )
    return {codigo: value for codigo, value in rows if value is not None}


def _saldo(item: Item) -> float:
    try:
        return float(item.get_saldo_fisico_total() or 0.0)
    except Exception:
        return 0.0


def item_card(item: Item, *, last_entry: date | None = None, grupo: ItemGrupo | None = None) -> dict[str, Any]:
    try:
        saldo_display = item.get_saldo_fisico_display()
    except Exception:
        saldo_display = None
    return {
        "codigo": item.codigo_item,
        "descricao": item.descricao,
        "marca": item.marca or "",
        "unidade": item.unidade or "",
        "categoria": item.categoria or "",
        "saldo": _saldo(item),
        "saldo_display": saldo_display,
        "foto_path": (item.foto_path or "").strip() or None,
        "ultima_entrada": last_entry.isoformat() if last_entry else None,
        "grupo_id": grupo.id if grupo else None,
        "grupo_nome": grupo.nome if grupo else None,
    }


def _membership() -> dict[str, ItemGrupo]:
    rows = db.session.query(ItemGrupoMembro.codigo_item, ItemGrupo).join(ItemGrupo, ItemGrupo.id == ItemGrupoMembro.grupo_id).all()
    return {codigo: grupo for codigo, grupo in rows}


def suggestions(limit: int = SUGGESTION_LIMIT) -> list[dict[str, Any]]:
    """Materiais fora de grupo com o mesmo nome (sem acento/caixa) e a mesma unidade base.

    Material com o nome de um grupo que já existe (ex.: item novo cadastrado pelo nome padrão) vem como
    sugestão de entrar nesse grupo (grupo_id), mesmo sozinho.
    """
    grouped_codes = set(_membership())
    groups_by_name = {(normalize_name(grupo.nome), unit_key(grupo.unidade)): grupo for grupo in ItemGrupo.query.all()}
    buckets: dict[tuple[str, str], list[Item]] = defaultdict(list)
    for item in Item.query.all():
        if item.codigo_item in grouped_codes or is_individual_control(item):
            continue
        buckets[(normalize_name(item.descricao), unit_key(item.unidade))].append(item)
    candidates = [
        (key, items) for key, items in buckets.items()
        if key[0] and (len(items) >= 2 or key in groups_by_name)
    ]
    candidates.sort(key=lambda pair: (pair[0] not in groups_by_name, pair[0][0]))
    candidates = candidates[:limit]
    dates = _last_entry_dates(item.codigo_item for _key, items in candidates for item in items)
    result = []
    for key, items in candidates:
        grupo = groups_by_name.get(key)
        result.append({
            "nome": grupo.nome if grupo else items[0].descricao,
            "unidade": items[0].unidade or "",
            "grupo_id": grupo.id if grupo else None,
            "itens": [item_card(item, last_entry=dates.get(item.codigo_item)) for item in items],
        })
    return result


def search_items(query: str, *, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
    """Seleção de membros: todas as palavras precisam aparecer; "-palavra" exclui ("joelho 25 -45")."""
    raw_tokens = str(query or "").split()
    include = [normalize_name(token) for token in raw_tokens if not token.startswith("-") and normalize_name(token)]
    exclude = [normalize_name(token[1:]) for token in raw_tokens if token.startswith("-") and normalize_name(token[1:])]
    if not include:
        return []
    membership = _membership()
    found: list[Item] = []
    # Compara o começo das palavras da descrição e da marca: "25" pega "25MM" e não "125MM"; "-45" tira
    # "45GRAUS". O código de barras só serve para incluir (o "45" de 7899874560001 não pode excluir).
    for item in Item.query.order_by(Item.descricao).all():
        if is_individual_control(item):
            continue
        words = f"{normalize_name(item.descricao)} {normalize_name(item.marca)}".split()
        codigo = normalize_name(item.codigo_item)

        def has(token: str, *, with_code: bool) -> bool:
            return any(word.startswith(token) for word in words) or (with_code and codigo.startswith(token))

        if all(has(token, with_code=True) for token in include) and not any(has(token, with_code=False) for token in exclude):
            found.append(item)
            if len(found) >= limit:
                break
    dates = _last_entry_dates(item.codigo_item for item in found)
    return [item_card(item, last_entry=dates.get(item.codigo_item), grupo=membership.get(item.codigo_item)) for item in found]


def _word_prefix_match(text: str, tokens: list[str]) -> bool:
    words = normalize_name(text).split()
    return all(any(word.startswith(token) for word in words) for token in tokens)


def name_suggestions(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Nome padrão no cadastro (24/11/2026): enquanto se digita a descrição, sugere primeiro os nomes de
    grupo e depois os nomes de materiais já cadastrados (um por nome). Pedido do usuário: "quero que o
    grupo seja o nome padrão para cadastro; sempre que eu for digitando ele vai me sugerindo o nome".
    """
    tokens = [normalize_name(token) for token in str(query or "").split() if normalize_name(token)]
    if not tokens:
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for grupo in ItemGrupo.query.order_by(ItemGrupo.nome).all():
        if _word_prefix_match(grupo.nome, tokens):
            seen.add(normalize_name(grupo.nome))
            result.append({"nome": grupo.nome, "tipo": "grupo", "grupo_id": grupo.id, "unidade": grupo.unidade, "itens": len(grupo.membros)})
            if len(result) >= limit:
                return result
    for item in Item.query.order_by(Item.descricao).all():
        key = normalize_name(item.descricao)
        if not key or key in seen or is_individual_control(item) or not _word_prefix_match(item.descricao, tokens):
            continue
        seen.add(key)
        result.append({"nome": item.descricao, "tipo": "item", "unidade": item.unidade or ""})
        if len(result) >= limit:
            break
    return result


def withdrawal_order(grupo: ItemGrupo) -> list[dict[str, Any]]:
    """Membros na ordem de saída: o mais antigo (última entrada mais antiga) primeiro; sem saldo, fora."""
    codes = [membro.codigo_item for membro in grupo.membros]
    items = {item.codigo_item: item for item in Item.query.filter(Item.codigo_item.in_(codes)).all()} if codes else {}
    dates = _last_entry_dates(codes)
    cards = [item_card(items[code], last_entry=dates.get(code)) for code in codes if code in items]
    with_stock = [card for card in cards if card["saldo"] > 0]
    with_stock.sort(key=lambda card: (card["ultima_entrada"] or "0000-00-00", card["codigo"]))
    return with_stock


def list_groups() -> list[dict[str, Any]]:
    result = []
    for grupo in ItemGrupo.query.order_by(ItemGrupo.nome).all():
        codes = [membro.codigo_item for membro in grupo.membros]
        items = {item.codigo_item: item for item in Item.query.filter(Item.codigo_item.in_(codes)).all()} if codes else {}
        dates = _last_entry_dates(codes)
        cards = [item_card(items[code], last_entry=dates.get(code)) for code in codes if code in items]
        order = [card["codigo"] for card in withdrawal_order(grupo)]
        for card in cards:
            card["ordem"] = order.index(card["codigo"]) + 1 if card["codigo"] in order else None
        cards.sort(key=lambda card: (card["ordem"] is None, card["ordem"] or 0, card["descricao"] or ""))
        result.append({
            "id": grupo.id,
            "nome": grupo.nome,
            "unidade": grupo.unidade,
            "saldo_total": round(sum(card["saldo"] for card in cards if card["saldo"] > 0), 6),
            "itens": cards,
        })
    return result


def _load_items(codes: Iterable[str]) -> list[Item]:
    codes = list(dict.fromkeys(str(code or "").strip() for code in codes if str(code or "").strip()))
    items = Item.query.filter(Item.codigo_item.in_(codes)).all() if codes else []
    missing = sorted(set(codes) - {item.codigo_item for item in items})
    if missing:
        raise ValueError(f"Item não encontrado: {', '.join(missing)}")
    return items


def _validate_members(items: list[Item], *, unidade: str | None, grupo_id: int | None = None) -> str:
    if not items:
        raise ValueError("Marque os itens do grupo.")
    tools = [item.descricao for item in items if is_individual_control(item)]
    if tools:
        raise ValueError(f"Ferramenta e equipamento ficam fora dos grupos: {', '.join(tools)}")
    units = {unit_key(item.unidade) for item in items}
    if unidade:
        units.add(unit_key(unidade))
    if len(units) > 1:
        raise ValueError("Os itens do grupo precisam ter a mesma unidade base.")
    membership = _membership()
    taken = [f"{item.descricao} ({membership[item.codigo_item].nome})" for item in items
             if item.codigo_item in membership and membership[item.codigo_item].id != grupo_id]
    if taken:
        raise ValueError(f"Já está em outro grupo: {', '.join(taken)}")
    return unidade or (items[0].unidade or "")


def create_group(nome: str, codes: Iterable[str], *, usuario: str | None = None) -> ItemGrupo:
    nome = re.sub(r"\s+", " ", str(nome or "")).strip().upper()
    if not nome:
        raise ValueError("Informe o nome do grupo.")
    items = _load_items(codes)
    if len(items) < 2:
        raise ValueError("Marque pelo menos dois itens.")
    unidade = _validate_members(items, unidade=None)
    if ItemGrupo.query.filter(func.upper(ItemGrupo.nome) == nome).first():
        raise ValueError("Já existe um grupo com esse nome.")
    grupo = ItemGrupo(nome=nome, unidade=unidade, criado_por=usuario)
    grupo.membros = [ItemGrupoMembro(codigo_item=item.codigo_item) for item in items]
    db.session.add(grupo)
    db.session.commit()
    return grupo


def add_members(grupo: ItemGrupo, codes: Iterable[str]) -> int:
    current = {membro.codigo_item for membro in grupo.membros}
    items = [item for item in _load_items(codes) if item.codigo_item not in current]
    if not items:
        return 0
    _validate_members(items, unidade=grupo.unidade, grupo_id=grupo.id)
    for item in items:
        grupo.membros.append(ItemGrupoMembro(codigo_item=item.codigo_item))
    grupo.atualizado_em = TimeService.now_db()
    db.session.commit()
    return len(items)


def remove_member(grupo: ItemGrupo, codigo: str) -> None:
    for membro in list(grupo.membros):
        if membro.codigo_item == codigo:
            grupo.membros.remove(membro)
    grupo.atualizado_em = TimeService.now_db()
    db.session.commit()


def rename_group(grupo: ItemGrupo, nome: str) -> None:
    nome = re.sub(r"\s+", " ", str(nome or "")).strip().upper()
    if not nome:
        raise ValueError("Informe o nome do grupo.")
    other = ItemGrupo.query.filter(func.upper(ItemGrupo.nome) == nome, ItemGrupo.id != grupo.id).first()
    if other:
        raise ValueError("Já existe um grupo com esse nome.")
    grupo.nome = nome
    db.session.commit()


def delete_group(grupo: ItemGrupo) -> None:
    db.session.delete(grupo)
    db.session.commit()


def group_of(codigo: str) -> ItemGrupo | None:
    membro = ItemGrupoMembro.query.filter_by(codigo_item=str(codigo or "").strip()).first()
    return membro.grupo if membro else None
