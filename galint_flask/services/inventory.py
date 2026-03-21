"""Inventory service bridging the legacy data model to Flask routes."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging
import math
from typing import Any

from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    DocumentoEntradaEstoque,
    DocumentoEntradaEstoqueItem,
    Entrada,
    EquipamentoReparo,
    FinanceLedgerEntry,
    FinanceSupplierPreference,
    InventarioEvento,
    Item,
    MaterialInventario,
    RetiradaFerramenta,
    Saida,
    TelegramOutbox,
)
from ..utils.lote_generator import generate_lote
from ..utils.barcode_generator import generate_barcode, get_barcode_path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MovimentoPayload:
    codigo: str
    quantidade: float
    matricula: str | None = None
    nota_fiscal: str | None = None
    observacao: str | None = None
    local_servico: str | None = None
    modo_fracionado: bool = False
    tipo_produto: str | None = None
    densidade_aplicada: float | None = None
    fracao_numerador: int | None = None
    fracao_denominador: int | None = None
    quantidade_total_embalagem: float | None = None
    quantidade_retirada_em_litros: float | None = None
    quantidade_retirada_em_quilos: float | None = None
    quantidade_restante: float | None = None
    is_devolucao: bool = False
    em_embalagens: bool | None = None  # True = embalagens, False = unidades, None = item sem embalagem
    tipo_custodia: str = "temporaria"


class InventoryService:
    """Facade responsável por CRUD de itens e lançamentos de estoque."""

    @staticmethod
    def _as_positive_float(value: object) -> float:
        try:
            f = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return f

    def get_material_return_pending(self, *, codigo: str, matricula: str) -> float:
        """Retorna quanto ainda pode ser devolvido (estornado) para um material.

        Regra:
        - Pendente = total_saidas(matricula,codigo) - total_devolucoes(matricula,codigo)
        - total_devolucoes considera:
          1) eventos tipo 'devolucao_material' (novo padrão)
          2) entradas legadas sem NF (rota antiga do mobile), para não permitir dupla devolução.
        """
        codigo_norm = (codigo or "").strip()
        matricula_norm = (matricula or "").strip()
        if not codigo_norm or not matricula_norm:
            return 0.0

        total_saidas = (
            db.session.query(func.coalesce(func.sum(Saida.quantidade), 0.0))
            .filter(Saida.codigo_item == codigo_norm, Saida.matricula == matricula_norm)
            .scalar()
        )
        total_eventos = (
            db.session.query(func.coalesce(func.sum(InventarioEvento.quantidade), 0.0))
            .filter(
                InventarioEvento.codigo_item == codigo_norm,
                InventarioEvento.matricula == matricula_norm,
                InventarioEvento.tipo == "devolucao_material",
            )
            .scalar()
        )
        # Legado: devoluções antigas do mobile geravam Entrada com NF = NULL.
        total_entradas_legado = (
            db.session.query(func.coalesce(func.sum(Entrada.quantidade), 0.0))
            .filter(
                Entrada.codigo_item == codigo_norm,
                Entrada.matricula == matricula_norm,
                Entrada.nota_fiscal.is_(None),
            )
            .scalar()
        )

        saidas_f = self._as_positive_float(total_saidas)
        devolucoes_f = self._as_positive_float(total_eventos) + self._as_positive_float(total_entradas_legado)
        pendente = saidas_f - devolucoes_f
        if pendente < 0:
            return 0.0
        return float(pendente)

    def registrar_devolucao_material(
        self,
        *,
        codigo: str,
        quantidade: float,
        matricula: str,
        observacao: str | None = None,
        commit: bool = True,
    ) -> InventarioEvento:
        """Registra devolução de material como um InventarioEvento.

        Importante:
        - Não cria Entrada (evita devolução virar 'adição' duplicada).
        - Bloqueia devolução acima do pendente por funcionário/item.
        """
        codigo_norm = (codigo or "").strip()
        matricula_norm = (matricula or "").strip()
        if not codigo_norm:
            raise ValueError("Código do item é obrigatório")
        if not matricula_norm:
            raise ValueError("Matrícula é obrigatória")

        quantidade_f = self._as_positive_float(quantidade)
        if quantidade_f <= 0:
            raise ValueError("Quantidade inválida")

        item = Item.query.get(codigo_norm)
        if not item:
            raise ValueError("Item não encontrado")

        categoria_text = (item.categoria or "").strip().lower()
        if "ferrament" in categoria_text:
            raise ValueError("Use a devolução de ferramentas para este item")

        pendente = self.get_material_return_pending(codigo=codigo_norm, matricula=matricula_norm)
        # Tolerância mínima para float.
        if pendente <= 1e-9:
            raise ValueError("Devolução não permitida: não há retirada pendente para este material.")
        if quantidade_f > pendente + 1e-9:
            raise ValueError(f"Devolução excede o pendente. Pendente: {pendente:g}")

        descricao_base = f"Devolução de Material: {item.descricao or 'Item'}"
        obs = (observacao or "").strip()
        descricao = f"{descricao_base} | {obs}" if obs else descricao_base

        evento = InventarioEvento(
            codigo_item=item.codigo_item,
            matricula=matricula_norm,
            tipo="devolucao_material",
            quantidade=float(quantidade_f),
            descricao=descricao,
            data_evento=datetime.utcnow(),
        )
        db.session.add(evento)
        db.session.flush()

        try:
            saldo_atualizado = float(item.get_saldo_atual() or 0.0)
        except Exception:
            saldo_atualizado = 0.0
        item.estoque_minimo = _calculate_min_stock(saldo_atualizado)

        if commit:
            db.session.commit()

        return evento

    @staticmethod
    def _normalize_tipo_custodia(value: str | None) -> str:
        raw = (value or "").strip().lower()
        if raw in {"permanente", "perm", "p"}:
            return "permanente"
        if raw in {"temporaria", "temporária", "diaria", "diária", "daily", "d"}:
            return "temporaria"
        return "temporaria"

    def _bulk_saldos(self, codigos: list[str] | None = None) -> dict[str, float]:
        # Importante: evitar IN com listas enormes (pode estourar limite de parâmetros
        # e/ou degradar performance). Só aplicamos filtro quando a lista é pequena.
        filtro_codigos: set[str] | None = None
        if codigos:
            candidatos = {c for c in codigos if c}
            if 0 < len(candidatos) <= 500:
                filtro_codigos = candidatos

        entradas_q = (
            db.session.query(
                Entrada.codigo_item,
                func.coalesce(func.sum(Entrada.quantidade), 0).label("total_entrada"),
            )
            .filter(Entrada.codigo_item.isnot(None))
            .group_by(Entrada.codigo_item)
        )
        saidas_q = (
            db.session.query(
                Saida.codigo_item,
                func.coalesce(func.sum(Saida.quantidade), 0).label("total_saida"),
            )
            .filter(Saida.codigo_item.isnot(None))
            .group_by(Saida.codigo_item)
        )
        ajustes_q = (
            db.session.query(
                InventarioEvento.codigo_item,
                func.coalesce(func.sum(InventarioEvento.quantidade), 0).label("total_ajuste"),
            )
            .filter(InventarioEvento.codigo_item.isnot(None))
            .group_by(InventarioEvento.codigo_item)
        )

        if filtro_codigos is not None:
            entradas_q = entradas_q.filter(Entrada.codigo_item.in_(filtro_codigos))
            saidas_q = saidas_q.filter(Saida.codigo_item.in_(filtro_codigos))
            ajustes_q = ajustes_q.filter(InventarioEvento.codigo_item.in_(filtro_codigos))

        entradas = {codigo: float(total or 0) for codigo, total in entradas_q.all() if codigo}
        saidas = {codigo: float(total or 0) for codigo, total in saidas_q.all() if codigo}
        ajustes = {codigo: float(total or 0) for codigo, total in ajustes_q.all() if codigo}

        saldos: dict[str, float] = {}
        for codigo in set(entradas) | set(saidas) | set(ajustes):
            saldos[codigo] = entradas.get(codigo, 0.0) - saidas.get(codigo, 0.0) + ajustes.get(codigo, 0.0)
        return saldos

    def search_items_for_autocomplete(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q or len(q) < 1:
            return []

        like = f"%{q}%"
        rows = (
            Item.query.filter(or_(Item.codigo_item.ilike(like), Item.descricao.ilike(like)))
            .order_by(Item.descricao)
            .limit(limit)
            .all()
        )

        saldo_map = self._bulk_saldos([item.codigo_item for item in rows])
        from ..services.embalagem_service import EmbalagemService
        results: list[dict[str, Any]] = []
        for item in rows:
            if EmbalagemService.tem_embalagem(item):
                try:
                    saldo = float(EmbalagemService.calcular_estoque_total(item) or 0)
                except Exception:
                    saldo = 0.0
            else:
                saldo = float(saldo_map.get(item.codigo_item, 0.0) or 0.0)
            results.append(
                {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "categoria": item.categoria,
                    "saldo": saldo,
                    "tipo_embalagem_novo": item.tipo_embalagem_novo,
                    "unidades_por_embalagem": item.unidades_por_embalagem,
                    "grandeza_referencia": item.grandeza_referencia,
                    "litros_por_embalagem": item.litros_por_embalagem,
                }
            )
        return results

    def _has_active_tool_withdrawal(self, codigo_item: str, matricula: str | None) -> bool:
        """Retorna True se a matrícula já possui retirada ativa da mesma ferramenta."""
        if not codigo_item or not matricula:
            return False

        saidas = (
            db.session.query(Saida.id_saida, Saida.data_saida)
            .filter(
                Saida.codigo_item == codigo_item,
                Saida.matricula == matricula,
            )
            .order_by(Saida.data_saida.desc())
            .limit(50)
            .all()
        )

        if not saidas:
            return False

        tipos_fechamento = [
            "devolucao_ferramenta",
            "devolucao_material",
            "quebra_ferramenta",
            "reparo_ferramenta",
            "devolucao",
        ]

        for _, data_saida in saidas:
            devolucao = (
                db.session.query(InventarioEvento.id_evento)
                .filter(
                    InventarioEvento.codigo_item == codigo_item,
                    InventarioEvento.matricula == matricula,
                    InventarioEvento.tipo.in_(tipos_fechamento),
                    InventarioEvento.data_evento >= data_saida,
                )
                .first()
            )
            if not devolucao:
                return True

        return False

    def ensure_barcodes_for_all(self) -> dict[str, int]:
        stats = {
            "total": 0,
            "generated": 0,
            "skipped": 0,
            "failed": 0,
        }
        itens = Item.query.order_by(Item.codigo_item).all()
        for item in itens:
            stats["total"] += 1
            codigo = (item.codigo_item or "").strip()
            if not codigo:
                stats["failed"] += 1
                continue

            existing_path = item.barcode_image_path or get_barcode_path(codigo)
            if existing_path:
                if item.barcode_image_path != existing_path:
                    item.barcode_image_path = existing_path
                stats["skipped"] += 1
                continue

            try:
                barcode_path = generate_barcode(codigo, item.descricao)
                item.barcode_image_path = barcode_path
                stats["generated"] += 1
            except Exception:
                stats["failed"] += 1

        db.session.commit()
        return stats

    def list_items(self) -> list[dict[str, Any]]:
        itens = Item.query.order_by(Item.descricao).all()
        saldo_map = self._bulk_saldos()
        resultado: list[dict[str, Any]] = []
        atualizado = False
        from ..services.embalagem_service import EmbalagemService

        def _safe_float_or_none(value: object) -> float | None:
            if value in ("", None):
                return None
            try:
                f = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
            if math.isnan(f) or math.isinf(f):
                return None
            return f

        def _calc_stock_total_value(item: Item, *, preco_unitario: float | None, saldo_total: float) -> float | None:
            if preco_unitario is None or preco_unitario <= 0:
                return None
            if EmbalagemService.tem_embalagem(item):
                emb = float(item.estoque_embalagens or 0.0)
                soltas = float(item.estoque_unidades_soltas or 0.0)
                try:
                    unidades_por = float(item.unidades_por_embalagem or 0.0)
                except (TypeError, ValueError):
                    unidades_por = 0.0
                if unidades_por > 0:
                    return (emb * preco_unitario) + (soltas * (preco_unitario / unidades_por))
                return emb * preco_unitario
            return float(saldo_total or 0.0) * preco_unitario

        for item in itens:
            if EmbalagemService.tem_embalagem(item):
                try:
                    saldo = float(EmbalagemService.calcular_estoque_total(item) or 0)
                except Exception:
                    saldo = 0.0
            else:
                saldo = saldo_map.get(item.codigo_item, 0.0)
            minimo = _calculate_min_stock(saldo)
            if item.estoque_minimo != minimo:
                item.estoque_minimo = minimo
                atualizado = True
            
            # Obter display formatado e explicação
            saldo_display = item.get_saldo_fisico_display()
            explicacao_saldo = item.get_explicacao_saldo()

            preco_compra = _safe_float_or_none(getattr(item, "preco_compra_unitario", None))
            preco_reposicao = _safe_float_or_none(getattr(item, "preco_reposicao_unitario", None))
            valor_total_compra = _calc_stock_total_value(item, preco_unitario=preco_compra, saldo_total=saldo)
            valor_total_reposicao = _calc_stock_total_value(item, preco_unitario=preco_reposicao, saldo_total=saldo)
            
            resultado.append(
                {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "unidade": item.unidade,
                    "marca": item.marca,
                    "localizacao": item.localizacao,
                    "setor": item.setor,
                    "estoque_minimo": minimo,
                    "nota_fiscal": item.nota_fiscal,
                    "categoria": item.categoria,
                    "ultima_edicao_em": item.ultima_edicao_em.isoformat() if item.ultima_edicao_em else None,
                    "ultima_edicao_por": item.ultima_edicao_por,
                    "saldo": saldo,
                    "saldo_display": saldo_display,
                    "explicacao_saldo": explicacao_saldo,
                    "saldo_unidades_total": saldo,
                    "saldo_embalagens": item.estoque_embalagens,
                    "saldo_unidades_soltas": item.estoque_unidades_soltas,
                    "foto_path": item.foto_path,
                    "tipo_embalagem_novo": item.tipo_embalagem_novo,
                    "unidades_por_embalagem": item.unidades_por_embalagem,
                    "grandeza_referencia": item.grandeza_referencia,
                    "litros_por_embalagem": item.litros_por_embalagem,
                    "preco_compra_unitario": preco_compra,
                    "preco_compra_fonte": getattr(item, "preco_compra_fonte", None),
                    "preco_compra_documento": getattr(item, "preco_compra_documento", None),
                    "preco_compra_atualizado_em": item.preco_compra_atualizado_em.isoformat() if getattr(item, "preco_compra_atualizado_em", None) else None,
                    "preco_compra_atualizado_por": getattr(item, "preco_compra_atualizado_por", None),
                    "preco_reposicao_unitario": preco_reposicao,
                    "preco_reposicao_fonte": getattr(item, "preco_reposicao_fonte", None),
                    "preco_reposicao_uf": getattr(item, "preco_reposicao_uf", None),
                    "preco_reposicao_query": getattr(item, "preco_reposicao_query", None),
                    "preco_reposicao_url": getattr(item, "preco_reposicao_url", None),
                    "preco_reposicao_atualizado_em": item.preco_reposicao_atualizado_em.isoformat() if getattr(item, "preco_reposicao_atualizado_em", None) else None,
                    "preco_reposicao_atualizado_por": getattr(item, "preco_reposicao_atualizado_por", None),
                    "valor_estoque_compra_total": valor_total_compra,
                    "valor_estoque_reposicao_total": valor_total_reposicao,
                }
            )
        if atualizado:
            db.session.commit()
        return resultado

    def get_item(self, codigo: str) -> dict[str, Any] | None:
        item = Item.query.get(codigo)
        if not item:
            return None
        from ..services.embalagem_service import EmbalagemService
        if EmbalagemService.tem_embalagem(item):
            try:
                saldo = float(EmbalagemService.calcular_estoque_total(item) or 0)
            except Exception:
                saldo = 0.0
        else:
            saldo = item.get_saldo_atual()
        minimo = _calculate_min_stock(saldo)
        if item.estoque_minimo != minimo:
            item.estoque_minimo = minimo
            db.session.commit()
        dados = item.to_dict(include_balance=True)
        latest_finance_entry = (
            FinanceLedgerEntry.query.filter(FinanceLedgerEntry.codigo_item == codigo)
            .order_by(FinanceLedgerEntry.data_lancamento.desc(), FinanceLedgerEntry.id.desc())
            .first()
        )
        if latest_finance_entry:
            dados.update(
                {
                    "finance_supplier_id": latest_finance_entry.fornecedor_id,
                    "finance_origem_valor": latest_finance_entry.origem_valor,
                    "finance_tipo_documento": latest_finance_entry.tipo_documento,
                    "finance_comprovacao_status": latest_finance_entry.comprovacao_status,
                    "finance_observacao": latest_finance_entry.observacao,
                }
            )
        dados["estoque_minimo"] = minimo
        dados["saldo"] = saldo
        return dados

    def create_item(self, payload: dict[str, Any]) -> str:
        codigo = _sanitize_codigo(payload.get("codigo") or payload.get("codigo_item"))
        if not codigo:
            raise ValueError("Código do item é obrigatório")

        # Verificar se item já existe
        item_existente = Item.query.get(codigo)
        
        # Processar data de entrada (blindada: sempre servidor)
        data_entrada = payload.get("data_entrada")
        if data_entrada:
            if isinstance(data_entrada, str):
                try:
                    data_entrada = datetime.strptime(data_entrada, '%Y-%m-%d').date()
                except ValueError:
                    data_entrada = None
        if not data_entrada:
            data_entrada = datetime.now().date()
        
        # Lote: manual quando informado, automático apenas quando solicitado
        auto_lote = bool(payload.get("gerar_lote_automatico"))
        lote = (payload.get("lote") or "").strip() or None
        if auto_lote:
            lote = generate_lote(datetime.combine(data_entrada, datetime.min.time()))
        
        # Se item existe, verificar se é o mesmo lote
        if item_existente:
            # Se o lote é igual (ou ambos vazios), é duplicata
            if (item_existente.lote or "") == (lote or ""):
                raise ValueError("Código já cadastrado com este lote. Use 'Registro de Entrada' para adicionar estoque.")
            else:
                # Lote diferente: registrar como nova entrada e atualizar dados do item
                # Campos estruturais de rastreabilidade são imutáveis após definidos.
                # Permitimos apenas o primeiro preenchimento (write-once) para manter
                # compatibilidade com bases antigas que tinham valores nulos.
                if not (item_existente.lote or "").strip() and lote:
                    item_existente.lote = lote
                item_existente.data_entrada = data_entrada
                
                # Atualizar datas de fabricação e validade se informadas
                data_fabricacao = payload.get("data_fabricacao")
                if data_fabricacao and isinstance(data_fabricacao, str):
                    try:
                        item_existente.data_fabricacao = datetime.strptime(data_fabricacao, '%Y-%m-%d').date()
                    except ValueError:
                        pass
                
                data_validade = payload.get("data_validade")
                if item_existente.data_validade is None and data_validade and isinstance(data_validade, str):
                    try:
                        item_existente.data_validade = datetime.strptime(data_validade, '%Y-%m-%d').date()
                    except ValueError:
                        pass

                # Foto: se foi enviada no formulário, persistir também.
                # (Antes, o fluxo de "lote diferente" ignorava foto_path.)
                if "foto_path" in payload:
                    nova_foto = payload.get("foto_path")
                    try:
                        if nova_foto and item_existente.foto_path and item_existente.foto_path != nova_foto:
                            from .item_foto_service import ItemFotoService

                            ItemFotoService.deletar_foto(item_existente.foto_path)
                    except Exception:
                        pass
                    item_existente.foto_path = nova_foto
                
                # Registrar entrada com a quantidade
                quantidade = payload.get("quantidade") or payload.get("saldo") or 0
                if quantidade and int(quantidade) > 0:
                    nota_fiscal = payload.get("nota_fiscal")

                    try:
                        from ..services.embalagem_service import embalagem_service

                        if embalagem_service.tem_embalagem(item_existente):
                            novas_emb, novas_soltas = embalagem_service.processar_entrada(
                                item_existente, float(quantidade), True
                            )
                            item_existente.estoque_embalagens = novas_emb
                            item_existente.estoque_unidades_soltas = novas_soltas
                    except Exception:
                        pass

                    entrada = Entrada(
                        codigo_item=codigo,
                        quantidade=int(quantidade),
                        nota_fiscal=nota_fiscal,
                        data_entrada=datetime.combine(data_entrada, datetime.min.time()),
                    )
                    db.session.add(entrada)
                
                db.session.commit()
                # Prefixo especial para indicar que foi atualização (entrada já registrada)
                return f"UPDATED:{codigo}"
        
        # Processar datas de fabricação e validade
        data_fabricacao = payload.get("data_fabricacao")
        if data_fabricacao and isinstance(data_fabricacao, str):
            try:
                data_fabricacao = datetime.strptime(data_fabricacao, '%Y-%m-%d').date()
            except ValueError:
                data_fabricacao = None
        
        data_validade = payload.get("data_validade")
        if data_validade and isinstance(data_validade, str):
            try:
                data_validade = datetime.strptime(data_validade, '%Y-%m-%d').date()
            except ValueError:
                data_validade = None

        data_emissao = payload.get("preco_compra_data_emissao")
        if data_emissao and isinstance(data_emissao, str):
            try:
                data_emissao = datetime.strptime(data_emissao, '%Y-%m-%d').date()
            except ValueError:
                data_emissao = None

        data_recebimento = payload.get("preco_compra_data_recebimento")
        if data_recebimento and isinstance(data_recebimento, str):
            try:
                data_recebimento = datetime.strptime(data_recebimento, '%Y-%m-%d').date()
            except ValueError:
                data_recebimento = None

        grandeza_referencia = payload.get("grandeza_referencia")
        if grandeza_referencia in ("", None):
            grandeza_referencia = None
        else:
            try:
                grandeza_referencia = float(grandeza_referencia)
            except (TypeError, ValueError):
                grandeza_referencia = None

        litros_por_embalagem = payload.get("litros_por_embalagem")
        if litros_por_embalagem in ("", None):
            litros_por_embalagem = None
        else:
            try:
                litros_por_embalagem = float(litros_por_embalagem)
            except (TypeError, ValueError):
                litros_por_embalagem = None

        # Novos campos de embalagem
        tipo_embalagem_novo = payload.get("tipo_embalagem_novo")
        if tipo_embalagem_novo in ("", None):
            tipo_embalagem_novo = None
        
        unidades_por_embalagem = payload.get("unidades_por_embalagem")
        if unidades_por_embalagem in ("", None):
            unidades_por_embalagem = None
        else:
            try:
                unidades_por_embalagem = float(unidades_por_embalagem)
            except (TypeError, ValueError):
                unidades_por_embalagem = None
        
        estoque_embalagens = payload.get("estoque_embalagens", 0)
        try:
            estoque_embalagens = float(estoque_embalagens)
        except (TypeError, ValueError):
            estoque_embalagens = 0
        
        estoque_unidades_soltas = payload.get("estoque_unidades_soltas", 0)
        try:
            estoque_unidades_soltas = float(estoque_unidades_soltas)
        except (TypeError, ValueError):
            estoque_unidades_soltas = 0

        def _coerce_price(value: object) -> float | None:
            if value in ("", None):
                return None
            try:
                f = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
            if math.isnan(f) or math.isinf(f):
                return None
            return f

        preco_compra_unitario = _coerce_price(payload.get("preco_compra_unitario"))
        preco_reposicao_unitario = _coerce_price(payload.get("preco_reposicao_unitario"))

        item = Item(
            codigo_item=codigo,
            descricao=payload.get("descricao", ""),
            unidade=(payload.get("unidade") or "Unidade"),
            localizacao=payload.get("localizacao"),
            marca=payload.get("marca"),
            nota_fiscal=payload.get("nota_fiscal"),
            categoria=payload.get("categoria", "Material Elétrico"),
            setor=payload.get("categoria", "Material Elétrico"),
            numero_serie=payload.get("numero_serie"),
            modelo=payload.get("modelo"),
            # Novos campos de rastreabilidade
            data_entrada=data_entrada,
            lote=lote,
            data_fabricacao=data_fabricacao,
            data_validade=data_validade,
            tipo_embalagem=payload.get("tipo_embalagem"),
            grandeza_referencia=grandeza_referencia,
            litros_por_embalagem=litros_por_embalagem,
            # Sistema de embalagens
            tipo_embalagem_novo=tipo_embalagem_novo,
            unidades_por_embalagem=unidades_por_embalagem,
            estoque_embalagens=estoque_embalagens,
            estoque_unidades_soltas=estoque_unidades_soltas,
            # Campos de Equipamento
            voltagem=payload.get("voltagem"),
            amperagem=payload.get("amperagem"),
            local_instalacao=payload.get("local_instalacao"),
            # Foto do item
            foto_path=payload.get("foto_path"),
            # Financeiro
            preco_compra_unitario=preco_compra_unitario,
            preco_compra_fonte=payload.get("preco_compra_fonte"),
            preco_compra_documento=payload.get("preco_compra_documento"),
            preco_compra_chave_acesso=payload.get("preco_compra_chave_acesso"),
            preco_compra_data_emissao=data_emissao if payload.get("preco_compra_data_emissao") else None,
            preco_compra_data_recebimento=data_recebimento if payload.get("preco_compra_data_recebimento") else None,
            preco_compra_atualizado_em=payload.get("preco_compra_atualizado_em"),
            preco_compra_atualizado_por=payload.get("preco_compra_atualizado_por"),
            preco_reposicao_unitario=preco_reposicao_unitario,
            preco_reposicao_fonte=payload.get("preco_reposicao_fonte"),
            preco_reposicao_uf=payload.get("preco_reposicao_uf"),
            preco_reposicao_query=payload.get("preco_reposicao_query"),
            preco_reposicao_url=payload.get("preco_reposicao_url"),
            preco_reposicao_atualizado_em=payload.get("preco_reposicao_atualizado_em"),
            preco_reposicao_atualizado_por=payload.get("preco_reposicao_atualizado_por"),
        )
        item.estoque_minimo = 0
        db.session.add(item)
        try:
            db.session.commit()
            
            # Gerar código de barras após salvar
            try:
                barcode_path = generate_barcode(codigo, item.descricao)
                item.barcode_image_path = barcode_path
                db.session.commit()
            except Exception as barcode_error:
                # Se falhar ao gerar barcode, apenas logar mas não reverter o item
                print(f"Aviso: Não foi possível gerar barcode para {codigo}: {barcode_error}")
                
        except IntegrityError as exc:
            db.session.rollback()
            raise ValueError("Não foi possível cadastrar o item") from exc
        return codigo

    def update_item(self, codigo: str, payload: dict[str, Any]) -> str:
        item = Item.query.get(codigo)
        if not item:
            raise ValueError("Item não encontrado")

        novo_codigo = _sanitize_codigo(payload.get("codigo") or codigo)
        if not novo_codigo:
            raise ValueError("Código do item é obrigatório")
        if novo_codigo != codigo and Item.query.get(novo_codigo):
            raise ValueError("Código já cadastrado")

        if novo_codigo != codigo:
            raise ValueError("Não é permitido alterar o código do item após criado. Crie um novo item.")

        item.descricao = payload.get("descricao", item.descricao)
        item.localizacao = payload.get("localizacao", item.localizacao)
        item.nota_fiscal = payload.get("nota_fiscal", item.nota_fiscal)
        categoria = payload.get("categoria")
        if categoria:
            item.categoria = categoria
            item.setor = categoria
        unidade = payload.get("unidade")
        if unidade:
            item.unidade = unidade
        marca = payload.get("marca")
        if marca is not None:
            item.marca = marca

        def _coerce_price(value: object) -> float | None:
            if value in ("", None):
                return None
            try:
                f = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        
        # Novos campos
        numero_serie = payload.get("numero_serie")
        if "numero_serie" in payload:  # Sempre atualizar se estiver no payload
            item.numero_serie = numero_serie
        modelo = payload.get("modelo")
        if "modelo" in payload:  # Sempre atualizar se estiver no payload
            item.modelo = modelo
        
        # Campos de rastreabilidade (data_entrada blindada; lote pode ser manual)
        data_entrada = payload.get("data_entrada")
        if data_entrada is not None:
            if isinstance(data_entrada, str):
                try:
                    item.data_entrada = datetime.strptime(data_entrada, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif isinstance(data_entrada, date):
                item.data_entrada = data_entrada
        elif item.data_entrada is None:
            item.data_entrada = datetime.now().date()

        auto_lote = bool(payload.get("gerar_lote_automatico"))
        lote_manual = (payload.get("lote") or "").strip() or None
        # Lote é write-once: só pode ser preenchido se estiver vazio.
        if not (item.lote or "").strip():
            if lote_manual:
                item.lote = lote_manual
            elif auto_lote and item.data_entrada:
                item.lote = generate_lote(datetime.combine(item.data_entrada, datetime.min.time()))
        
        data_fabricacao = payload.get("data_fabricacao")
        if data_fabricacao is not None:
            if isinstance(data_fabricacao, str):
                try:
                    item.data_fabricacao = datetime.strptime(data_fabricacao, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif isinstance(data_fabricacao, date):
                item.data_fabricacao = data_fabricacao
        
        data_validade = payload.get("data_validade")
        # data_validade é write-once: só pode ser preenchida se estiver nula.
        if item.data_validade is None and data_validade is not None:
            if isinstance(data_validade, str):
                try:
                    item.data_validade = datetime.strptime(data_validade, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif isinstance(data_validade, date):
                item.data_validade = data_validade
        
        tipo_embalagem = payload.get("tipo_embalagem")
        if tipo_embalagem is not None:
            item.tipo_embalagem = tipo_embalagem
        
        # Campos numéricos (suportar "limpar" quando o formulário troca de grandeza)
        if "grandeza_referencia" in payload:
            grandeza_referencia = payload.get("grandeza_referencia")
            if grandeza_referencia in (None, ""):
                item.grandeza_referencia = None
            else:
                try:
                    item.grandeza_referencia = float(grandeza_referencia)
                except (ValueError, TypeError):
                    pass

        if "litros_por_embalagem" in payload:
            litros_por_embalagem = payload.get("litros_por_embalagem")
            if litros_por_embalagem in (None, ""):
                item.litros_por_embalagem = None
            else:
                try:
                    item.litros_por_embalagem = float(litros_por_embalagem)
                except (ValueError, TypeError):
                    pass
        
        # Novos campos de embalagem
        tipo_embalagem_novo = payload.get("tipo_embalagem_novo")
        if tipo_embalagem_novo is not None:
            item.tipo_embalagem_novo = tipo_embalagem_novo if tipo_embalagem_novo else None
        
        if "unidades_por_embalagem" in payload:
            unidades_por_embalagem = payload.get("unidades_por_embalagem")
            if unidades_por_embalagem in (None, ""):
                item.unidades_por_embalagem = None
            else:
                try:
                    item.unidades_por_embalagem = float(unidades_por_embalagem)
                except (ValueError, TypeError):
                    item.unidades_por_embalagem = None
        
        estoque_embalagens = payload.get("estoque_embalagens")
        if estoque_embalagens is not None:
            try:
                item.estoque_embalagens = float(estoque_embalagens)
            except (ValueError, TypeError):
                item.estoque_embalagens = 0
        
        estoque_unidades_soltas = payload.get("estoque_unidades_soltas")
        if estoque_unidades_soltas is not None:
            try:
                item.estoque_unidades_soltas = float(estoque_unidades_soltas)
            except (ValueError, TypeError):
                item.estoque_unidades_soltas = 0
        
        # Histórico de Edição
        if "ultima_edicao_em" in payload:
            item.ultima_edicao_em = payload["ultima_edicao_em"]
        if "ultima_edicao_por" in payload:
            item.ultima_edicao_por = payload["ultima_edicao_por"]

        # Campos de Equipamento
        print(f"DEBUG - UPDATE SERVICE - Campos equipamento: voltagem={payload.get('voltagem')}, amperagem={payload.get('amperagem')}, local_instalacao={payload.get('local_instalacao')}")
        if "voltagem" in payload:
            item.voltagem = payload["voltagem"]
        if "amperagem" in payload:
            item.amperagem = payload["amperagem"]
        if "local_instalacao" in payload:
            item.local_instalacao = payload["local_instalacao"]

        # Foto do item
        if "foto_path" in payload:
            item.foto_path = payload["foto_path"]

        # Financeiro
        compra_keys = {
            "preco_compra_unitario",
            "preco_compra_fonte",
            "preco_compra_documento",
            "preco_compra_chave_acesso",
            "preco_compra_data_emissao",
            "preco_compra_data_recebimento",
        }
        if any(k in payload for k in compra_keys):
            if "preco_compra_unitario" in payload:
                item.preco_compra_unitario = _coerce_price(payload.get("preco_compra_unitario"))
            if "preco_compra_fonte" in payload:
                item.preco_compra_fonte = payload.get("preco_compra_fonte") or None
            if "preco_compra_documento" in payload:
                item.preco_compra_documento = payload.get("preco_compra_documento") or None
            if "preco_compra_chave_acesso" in payload:
                item.preco_compra_chave_acesso = payload.get("preco_compra_chave_acesso") or None
            if "preco_compra_data_emissao" in payload:
                raw_emissao = payload.get("preco_compra_data_emissao")
                if raw_emissao in (None, ""):
                    item.preco_compra_data_emissao = None
                elif isinstance(raw_emissao, str):
                    try:
                        item.preco_compra_data_emissao = datetime.strptime(raw_emissao, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                elif isinstance(raw_emissao, date):
                    item.preco_compra_data_emissao = raw_emissao
            if "preco_compra_data_recebimento" in payload:
                raw_recebimento = payload.get("preco_compra_data_recebimento")
                if raw_recebimento in (None, ""):
                    item.preco_compra_data_recebimento = None
                elif isinstance(raw_recebimento, str):
                    try:
                        item.preco_compra_data_recebimento = datetime.strptime(raw_recebimento, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                elif isinstance(raw_recebimento, date):
                    item.preco_compra_data_recebimento = raw_recebimento
            item.preco_compra_atualizado_em = payload.get("preco_compra_atualizado_em") or datetime.utcnow()
            item.preco_compra_atualizado_por = payload.get("preco_compra_atualizado_por") or payload.get("ultima_edicao_por")

        repos_keys = {
            "preco_reposicao_unitario",
            "preco_reposicao_fonte",
            "preco_reposicao_uf",
            "preco_reposicao_query",
            "preco_reposicao_url",
        }
        if any(k in payload for k in repos_keys):
            if "preco_reposicao_unitario" in payload:
                item.preco_reposicao_unitario = _coerce_price(payload.get("preco_reposicao_unitario"))
            if "preco_reposicao_fonte" in payload:
                item.preco_reposicao_fonte = payload.get("preco_reposicao_fonte") or None
            if "preco_reposicao_uf" in payload:
                item.preco_reposicao_uf = payload.get("preco_reposicao_uf") or None
            if "preco_reposicao_query" in payload:
                item.preco_reposicao_query = payload.get("preco_reposicao_query") or None
            if "preco_reposicao_url" in payload:
                item.preco_reposicao_url = payload.get("preco_reposicao_url") or None
            item.preco_reposicao_atualizado_em = payload.get("preco_reposicao_atualizado_em") or datetime.utcnow()
            item.preco_reposicao_atualizado_por = payload.get("preco_reposicao_atualizado_por") or payload.get("ultima_edicao_por")

        # Regenerar barcode se descrição mudou
        if payload.get("descricao") and item.descricao:
            try:
                barcode_path = generate_barcode(novo_codigo, item.descricao)
                item.barcode_image_path = barcode_path
            except Exception as barcode_error:
                print(f"Aviso: Não foi possível gerar barcode para {novo_codigo}: {barcode_error}")

        db.session.commit()
        return novo_codigo
        
    def delete_item(self, codigo: str) -> None:
        item = Item.query.get(codigo)
        if not item:
            raise ValueError("Item não encontrado")

        saidas_ids = [s.id_saida for s in Saida.query.filter_by(codigo_item=codigo).all()]
        entradas_ids = [e.id_entrada for e in Entrada.query.filter_by(codigo_item=codigo).all()]
        documento_ids = [
            row[0]
            for row in db.session.query(DocumentoEntradaEstoqueItem.documento_id)
            .filter(DocumentoEntradaEstoqueItem.codigo_item == codigo)
            .distinct()
            .all()
        ]

        if saidas_ids:
            TelegramOutbox.query.filter(TelegramOutbox.saida_id.in_(saidas_ids)).delete(
                synchronize_session=False
            )
            MaterialInventario.query.filter(MaterialInventario.saida_id.in_(saidas_ids)).delete(
                synchronize_session=False
            )

        if entradas_ids:
            TelegramOutbox.query.filter(TelegramOutbox.entrada_id.in_(entradas_ids)).delete(
                synchronize_session=False
            )

        FinanceSupplierPreference.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )
        FinanceLedgerEntry.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )
        DocumentoEntradaEstoqueItem.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )
        RetiradaFerramenta.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )
        EquipamentoReparo.query.filter_by(codigo_item=codigo).delete(
            synchronize_session=False
        )

        if documento_ids:
            documentos_vazios = [
                documento_id
                for documento_id in documento_ids
                if not db.session.query(DocumentoEntradaEstoqueItem.id_documento_item)
                .filter(DocumentoEntradaEstoqueItem.documento_id == documento_id)
                .first()
            ]
            if documentos_vazios:
                DocumentoEntradaEstoque.query.filter(
                    DocumentoEntradaEstoque.id_documento.in_(documentos_vazios)
                ).delete(synchronize_session=False)

        # Agora pode excluir o item (cascade vai excluir saídas e entradas)
        db.session.delete(item)
        db.session.commit()
        

    def registrar_entrada(self, payload: MovimentoPayload, skip_notification: bool = False) -> Any:
        """Registra uma entrada de estoque.
        
        Args:
            payload: Dados da movimentação
            skip_notification: Se True, não envia notificação de entrada (usado quando notificação unificada já foi enviada)
            
        Returns:
            Objeto Entrada criado
        """
        return self._registrar_movimento(payload, is_entrada=True, skip_notification=skip_notification)

    def registrar_saida(self, payload: MovimentoPayload, *, skip_notification: bool = False) -> int:
        """Registra uma saída de estoque.
        
        Returns:
            ID da saída criada
        """
        movimento = self._registrar_movimento(payload, is_entrada=False, skip_notification=skip_notification)
        return getattr(movimento, 'id_saida', 0)

    def resumo_estoque(self) -> list[dict[str, Any]]:
        itens = Item.query.order_by(Item.setor, Item.descricao).all()
        saldo_map = self._bulk_saldos()
        resumo: list[dict[str, Any]] = []
        atualizado = False
        from ..services.embalagem_service import EmbalagemService
        for item in itens:
            if EmbalagemService.tem_embalagem(item):
                try:
                    saldo = float(EmbalagemService.calcular_estoque_total(item) or 0)
                except Exception:
                    saldo = 0.0
            else:
                saldo = saldo_map.get(item.codigo_item, 0.0)
            minimo = _calculate_min_stock(saldo)
            if item.estoque_minimo != minimo:
                item.estoque_minimo = minimo
                atualizado = True
            resumo.append(
                {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "setor": item.setor,
                    "marca": item.marca,
                    "estoque_minimo": minimo,
                    "saldo": saldo,
                    "status": "OK" if saldo > minimo else "Estoque baixo",
                }
            )
        if atualizado:
            db.session.commit()
        return resumo

    def list_notas_fiscais(self, limit: int = 100) -> list[dict[str, Any]]:
        from .finance_service import finance_service

        documentos = finance_service.list_stock_documents(limit=limit)
        registros = (
            Entrada.query.filter(Entrada.nota_fiscal.isnot(None))
            .order_by(Entrada.data_entrada.desc())
            .limit(max(limit * 5, limit))
            .all()
        )
        agrupadas = _agrupar_notas(registros)
        notas_por_numero: dict[str, dict[str, Any]] = {}

        for documento in documentos:
            numero = str(documento.get("numero_documento") or documento.get("nota_fiscal") or "").strip()
            if numero:
                notas_por_numero[numero] = documento

        for numero, nota_legada in agrupadas.items():
            if numero not in notas_por_numero:
                notas_por_numero[numero] = nota_legada

        notas = sorted(
            notas_por_numero.values(),
            key=lambda nota: nota.get("data") or datetime.min,
            reverse=True,
        )
        return notas[:limit]

    def get_nota_fiscal(self, numero: str) -> dict[str, Any] | None:
        from .finance_service import finance_service

        numero = (numero or "").strip()
        if not numero:
            return None

        documento = finance_service.get_stock_document_by_number(numero)
        if documento:
            return documento

        registros = (
            Entrada.query.filter(Entrada.nota_fiscal == numero)
            .order_by(Entrada.data_entrada.desc())
            .all()
        )
        if not registros:
            return None
        notas = _agrupar_notas(registros)
        return notas.get(numero)

    def registrar_nota_fiscal(self, payload: MovimentoPayload) -> None:
        if not payload.nota_fiscal:
            raise ValueError("Informe a nota fiscal")
        self.registrar_entrada(payload)

    def list_entradas(self, limit: int = 100) -> list[dict[str, Any]]:
        registros = (
            Entrada.query.order_by(Entrada.data_entrada.desc()).limit(limit).all()
        )
        resultado: list[dict[str, Any]] = []
        for entrada in registros:
            resultado.append(
                {
                    "id": entrada.id_entrada,
                    "codigo": entrada.codigo_item,
                    "descricao": entrada.item.descricao if entrada.item else "",
                    "quantidade": entrada.quantidade,
                    "nota_fiscal": entrada.nota_fiscal,
                    "data": entrada.data_entrada,
                    "usuario": entrada.usuario.nome if entrada.usuario else entrada.matricula,
                    "matricula": entrada.usuario.matricula if entrada.usuario else entrada.matricula,
                    "categoria": entrada.item.categoria if entrada.item else None,
                }
            )
        return resultado

    def list_saidas(self, limit: int = 100) -> list[dict[str, Any]]:
        registros = Saida.query.order_by(Saida.data_saida.desc()).limit(limit).all()
        resultado: list[dict[str, Any]] = []
        for saida in registros:
            resultado.append(
                {
                    "id": saida.id_saida,
                    "codigo": saida.codigo_item,
                    "descricao": saida.item.descricao if saida.item else "",
                    "quantidade": saida.quantidade,
                    "data": saida.data_saida,
                    "observacao": saida.observacao,
                    "usuario": saida.usuario.nome if saida.usuario else saida.matricula,
                    "matricula": saida.usuario.matricula if saida.usuario else saida.matricula,
                    "tipo_produto": saida.tipo_produto,
                    "densidade_aplicada": saida.densidade_aplicada,
                    "fracao_numerador": saida.fracao_numerador,
                    "fracao_denominador": saida.fracao_denominador,
                    "quantidade_total_embalagem": saida.quantidade_total_embalagem,
                    "quantidade_retirada_em_litros": saida.quantidade_retirada_em_litros,
                    "quantidade_retirada_em_quilos": saida.quantidade_retirada_em_quilos,
                    "quantidade_restante": saida.quantidade_restante,
                    "usou_fracao": bool(saida.usou_fracao),
                }
            )
        return resultado

    def list_saidas_fracionadas(self, limit: int = 200) -> list[dict[str, Any]]:
        registros = (
            Saida.query.filter(
                or_(Saida.usou_fracao.is_(True), Saida.fracao_denominador.isnot(None))
            )
            .order_by(Saida.data_saida.desc())
            .limit(limit)
            .all()
        )
        resultado: list[dict[str, Any]] = []
        for saida in registros:
            resultado.append(
                {
                    "id": saida.id_saida,
                    "codigo": saida.codigo_item,
                    "descricao": saida.item.descricao if saida.item else "",
                    "quantidade": saida.quantidade,
                    "data": saida.data_saida,
                    "observacao": saida.observacao,
                    "usuario": saida.usuario.nome if saida.usuario else saida.matricula,
                    "matricula": saida.usuario.matricula if saida.usuario else saida.matricula,
                    "tipo_produto": saida.tipo_produto,
                    "densidade_aplicada": saida.densidade_aplicada,
                    "fracao_numerador": saida.fracao_numerador,
                    "fracao_denominador": saida.fracao_denominador,
                    "quantidade_total_embalagem": saida.quantidade_total_embalagem,
                    "quantidade_retirada_em_litros": saida.quantidade_retirada_em_litros,
                    "quantidade_retirada_em_quilos": saida.quantidade_retirada_em_quilos,
                    "quantidade_restante": saida.quantidade_restante,
                    "usou_fracao": bool(saida.usou_fracao),
                }
            )
        return resultado

    def list_saidas_por_usuario(
        self,
        matricula: str,
        *,
        limit: int | None = 200,
        data_inicial: datetime | None = None,
        data_final: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Retorna as saídas vinculadas a um usuário específico."""
        matricula = (matricula or "").strip()
        if not matricula:
            return []

        consulta = Saida.query.filter(Saida.matricula == matricula).order_by(Saida.data_saida.desc())
        if data_inicial:
            consulta = consulta.filter(Saida.data_saida >= data_inicial)
        if data_final:
            consulta = consulta.filter(Saida.data_saida <= data_final)
        if limit is not None:
            consulta = consulta.limit(limit)

        registros = consulta.all()
        historico: list[dict[str, Any]] = []
        for saida in registros:
            historico.append(
                {
                    "id": saida.id_saida,
                    "codigo": saida.codigo_item,
                    "descricao": saida.item.descricao if saida.item else "",
                    "quantidade": saida.quantidade,
                    "data": saida.data_saida,
                    "observacao": saida.observacao,
                    "usuario": saida.usuario.nome if saida.usuario else saida.matricula,
                    "matricula": saida.matricula,
                }
            )
        return historico

    def list_movements_feed(self, limit: int = 100) -> list[dict[str, Any]]:
        entradas = self.list_entradas(limit=limit)
        saidas = self.list_saidas(limit=limit)
        feed = [
            {
                "tipo": "Entrada",
                **entrada,
            }
            for entrada in entradas
        ]
        feed.extend(
            {
                "tipo": "Saída",
                **saida,
            }
            for saida in saidas
        )
        feed.sort(key=lambda registro: registro.get("data") or datetime.min, reverse=True)
        return feed[:limit]

    def list_item_movements(self, codigo: str, limit: int = 20) -> list[dict[str, Any]]:
        codigo_norm = (codigo or "").strip()
        if not codigo_norm:
            return []

        entradas = (
            Entrada.query
            .filter(Entrada.codigo_item == codigo_norm)
            .order_by(Entrada.data_entrada.desc())
            .limit(limit)
            .all()
        )
        saidas = (
            Saida.query
            .filter(Saida.codigo_item == codigo_norm)
            .order_by(Saida.data_saida.desc())
            .limit(limit)
            .all()
        )

        movimentos: list[dict[str, Any]] = []

        for entrada in entradas:
            movimentos.append(
                {
                    "id": entrada.id_entrada,
                    "tipo": "Entrada",
                    "quantidade": float(entrada.quantidade or 0),
                    "data": entrada.data_entrada,
                    "responsavel": entrada.usuario.nome if entrada.usuario else (entrada.matricula or "-"),
                }
            )

        for saida in saidas:
            movimentos.append(
                {
                    "id": saida.id_saida,
                    "tipo": "Saída",
                    "quantidade": float(saida.quantidade or 0),
                    "data": saida.data_saida,
                    "responsavel": saida.usuario.nome if saida.usuario else (saida.matricula or "-"),
                }
            )

        movimentos.sort(key=lambda registro: registro.get("data") or datetime.min, reverse=True)
        return movimentos[:limit]

    def total_quantity(self) -> int:
        from ..services.embalagem_service import EmbalagemService

        total = 0.0
        for item in Item.query.all():
            if EmbalagemService.tem_embalagem(item):
                total += float(item.estoque_embalagens or 0)
            else:
                total += float(item.get_saldo_atual() or 0)
        return int(round(total))

    def total_quantity_internal(self) -> int:
        from ..services.embalagem_service import EmbalagemService

        total = 0.0
        for item in Item.query.all():
            if EmbalagemService.tem_embalagem(item):
                total += float(item.get_saldo_fisico_total() or 0)
            else:
                total += float(item.get_saldo_atual() or 0)
        return int(round(total))

    def category_summary(self) -> list[dict[str, Any]]:
        from ..services.embalagem_service import EmbalagemService

        def _normalize_unidade(value: str | None) -> str:
            return (value or "").strip().lower()

        def _is_unit(unidade: str | None) -> bool:
            u = _normalize_unidade(unidade)
            return u in ("un", "und", "unid", "unidade", "unidades")

        categorias: dict[str, dict[str, Any]] = {}
        for item in Item.query.order_by(Item.categoria, Item.descricao).all():
            categoria = item.categoria or "Sem categoria"
            resumo = categorias.setdefault(
                categoria,
                {
                    "categoria": categoria,
                    "total_itens": 0,
                    "saldo_total": 0.0,
                },
            )
            resumo["total_itens"] += 1
            if EmbalagemService.tem_embalagem(item):
                saldo = float(item.estoque_embalagens or 0)
            else:
                saldo = float(item.get_saldo_atual() or 0)
            
            # Se for unidade, soma como inteiro; senão, soma normalmente mas arredonda
            if _is_unit(item.unidade):
                resumo["saldo_total"] += round(saldo)
            else:
                resumo["saldo_total"] += round(saldo, 1)
        
        # Arredondar todos os totais para eliminar problemas de float
        for resumo in categorias.values():
            resumo["saldo_total"] = round(resumo["saldo_total"], 1)
        
        return list(categorias.values())

    def adjust_item_balance(
        self,
        *,
        codigo: str,
        novo_saldo: float,
        matricula: str,
        nota_fiscal: str | None = None,
        tipo: str | None = None,
        descricao: str | None = None,
    ) -> None:
        if novo_saldo < 0:
            raise ValueError("Saldo não pode ser negativo")
        item = Item.query.get(codigo)
        if not item:
            raise ValueError("Item não encontrado")
        saldo_atual = item.get_saldo_atual()
        delta = novo_saldo - saldo_atual
        if delta == 0:
            return

        descricao_base = "Ajuste manual de estoque"
        if saldo_atual == 0:
            descricao_base = "Saldo inicial configurado"

        descricao_final = descricao or descricao_base
        tipo_final = tipo or "ajuste_estoque"

        descricao_evento = f"{descricao_final}: de {saldo_atual} para {novo_saldo}"
        if nota_fiscal:
            descricao_evento = f"{descricao_evento} (NF: {nota_fiscal})"

        # Evitar eventos duplicados na mesma janela de tempo.
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=60)
            existe_duplicado = (
                InventarioEvento.query
                .filter(InventarioEvento.codigo_item == codigo)
                .filter(InventarioEvento.matricula == matricula)
                .filter(InventarioEvento.tipo == tipo_final)
                .filter(InventarioEvento.descricao == descricao_evento)
                .filter(InventarioEvento.data_evento >= cutoff)
                .first()
            )
            if existe_duplicado:
                return
        except Exception:
            pass

        evento = InventarioEvento(
            codigo_item=codigo,
            matricula=matricula,
            tipo=tipo_final,
            quantidade=delta,
            descricao=descricao_evento,
        )

        db.session.add(evento)
        item.estoque_minimo = _calculate_min_stock(novo_saldo)
        
        db.session.commit()
        # Notificar administradores apenas quando houver AUMENTO de estoque (entrada)
        # para evitar ruído/confusão com ajustes negativos.
        if delta > 0:
            try:
                from ..services.notification_router import NotificationRouterService

                NotificationRouterService.route_inventory_event(evento.id_evento)
            except Exception:
                # Não bloquear o ajuste por falha no Telegram
                pass

    def report_low_stock(self) -> list[dict[str, Any]]:
        return [item for item in self.resumo_estoque() if item["saldo"] <= item["estoque_minimo"]]

    def report_inventory_events(self, tipo: str, limit: int = 500) -> list[dict[str, Any]]:
        tipo = (tipo or "").strip().lower()
        if not tipo:
            return []
        registros = (
            InventarioEvento.query.filter(InventarioEvento.tipo.ilike(f"%{tipo}%"))
            .order_by(InventarioEvento.data_evento.desc())
            .limit(limit)
            .all()
        )
        resultado: list[dict[str, Any]] = []
        for evento in registros:
            resultado.append(
                {
                    "data": evento.data_evento,
                    "codigo": evento.codigo_item,
                    "tipo": evento.tipo,
                    "quantidade": evento.quantidade,
                    "responsavel": evento.matricula,
                    "descricao": evento.descricao,
                }
            )
        return resultado

    def generate_report_csv(self, tipo: str) -> tuple[str, list[str], list[list[Any]]]:
        """Gera os dados para um relatório em formato CSV."""
        tipo = (tipo or "").strip().lower()
        if tipo == "falta":
            dados = self.report_low_stock()
            headers = ["codigo", "descricao", "setor", "saldo", "estoque_minimo"]
            rows = [[item.get(h, "") for h in headers] for item in dados]
            return "produtos-em-falta", headers, rows
        if tipo in {"perda", "perdas"}:
            dados = self.report_inventory_events("perda")
            headers = ["data", "codigo", "tipo", "quantidade", "responsavel", "descricao"]
            rows = [[
                registro["data"].isoformat() if registro.get("data") else "",
                registro.get("codigo", ""),
                registro.get("tipo", ""),
                registro.get("quantidade", 0),
                registro.get("responsavel", ""),
                registro.get("descricao", ""),
            ] for registro in dados]
            return "produtos-com-perda", headers, rows
        if tipo in {"avariado", "avariados", "avaria"}:
            dados = self.report_inventory_events("avari")
            headers = ["data", "codigo", "tipo", "quantidade", "responsavel", "descricao"]
            rows = [[
                registro["data"].isoformat() if registro.get("data") else "",
                registro.get("codigo", ""),
                registro.get("tipo", ""),
                registro.get("quantidade", 0),
                registro.get("responsavel", ""),
                registro.get("descricao", ""),
            ] for registro in dados]
            return "produtos-avariados", headers, rows
        raise ValueError("Tipo de relatório inválido")

    def _registrar_movimento(self, payload: MovimentoPayload, *, is_entrada: bool, skip_notification: bool = False) -> Any:
        """Registra uma movimentação de estoque (entrada ou saída).
        
        Returns:
            Objeto Entrada ou Saida criado
        """
        if payload.quantidade <= 0:
            raise ValueError("Quantidade precisa ser positiva")

        item = Item.query.get(payload.codigo)
        if not item:
            raise ValueError("Item não encontrado")

        categoria_text = (item.categoria or "").lower()
        if not is_entrada and "ferrament" in categoria_text:
            if self._has_active_tool_withdrawal(payload.codigo, payload.matricula):
                raise ValueError(
                    "Retirada bloqueada: este funcionário já possui esta ferramenta em aberto. "
                    "Faça a devolução antes de nova retirada."
                )

        # Verificar se o item usa sistema de embalagens
        from ..services.embalagem_service import EmbalagemService, embalagem_service
        tem_embalagem = embalagem_service.tem_embalagem(item)

        # Contexto de saldo para notificação (evita divergências de unidades no Telegram)
        telegram_balance_before: float | None = None
        telegram_balance_after: float | None = None
        telegram_balance_unit: str | None = None

        if not is_entrada:
            # Corrigir unidade quando confundida com tipo_embalagem_novo
            unidade_item = item.unidade or "un"
            tipo_emb = (item.tipo_embalagem_novo or "").lower().strip()
            
            # Se a unidade está igual ao tipo de embalagem, inferir a unidade correta
            if unidade_item.lower().strip() == tipo_emb:
                if tipo_emb == "rolo":
                    telegram_balance_unit = "metros"
                elif tipo_emb in ("lata", "balde"):
                    # Para lata/balde, usar a unidade de referência (L ou KG)
                    if item.litros_por_embalagem and float(item.litros_por_embalagem) > 0:
                        telegram_balance_unit = "L"
                    elif item.grandeza_referencia and float(item.grandeza_referencia) > 0:
                        telegram_balance_unit = "KG"
                    else:
                        telegram_balance_unit = "un"
                elif tipo_emb in ("pacote", "caixa"):
                    telegram_balance_unit = "un"
                elif tipo_emb == "litro":
                    telegram_balance_unit = "L"
                else:
                    telegram_balance_unit = "un"
            else:
                telegram_balance_unit = unidade_item
            
            if tem_embalagem and payload.em_embalagens is not None:
                try:
                    telegram_balance_before = float(EmbalagemService.calcular_estoque_total(item) or 0)
                except Exception:
                    telegram_balance_before = None
            else:
                try:
                    telegram_balance_before = float(item.get_saldo_atual() or 0)
                except Exception:
                    telegram_balance_before = None
        
        # Processar embalagens ANTES de verificar saldo ou criar movimento
        if tem_embalagem and payload.em_embalagens is not None:
            # Itens antigos podem ter saldo legado, mas estoque novo ainda não inicializado.
            # Sincroniza de forma conservadora antes de processar a operação.
            try:
                EmbalagemService.tentar_sincronizar_estoque_de_legacy(item)
            except Exception:
                pass

            if is_entrada:
                # Entrada/Devolução
                novas_emb, novas_soltas = embalagem_service.processar_entrada(
                    item, payload.quantidade, payload.em_embalagens
                )
                item.estoque_embalagens = novas_emb
                item.estoque_unidades_soltas = novas_soltas
            else:
                # Saída
                novas_emb, novas_soltas, sucesso = embalagem_service.processar_saida(
                    item, payload.quantidade, payload.em_embalagens
                )
                if not sucesso:
                    raise ValueError("Saldo insuficiente para a saída solicitada")
                item.estoque_embalagens = novas_emb
                item.estoque_unidades_soltas = novas_soltas

                # Saldo após a saída (em UNIDADES totais) para notificação
                try:
                    telegram_balance_after = float(EmbalagemService.calcular_estoque_total(item) or 0)
                except Exception:
                    telegram_balance_after = None

        # Validação de saldo para itens sem embalagem
        if not tem_embalagem and not is_entrada:
            saldo_atual = item.get_saldo_atual()
            if payload.quantidade > saldo_atual:
                raise ValueError("Saldo insuficiente para a saída solicitada")

        movimento_cls = Entrada if is_entrada else Saida
        movimento = movimento_cls(
            codigo_item=payload.codigo,
            matricula=payload.matricula,
            quantidade=payload.quantidade,
        )
        # Se o payload tiver observação e o modelo de movimento aceitar, persista-a
        if getattr(movimento.__class__, 'observacao', None) is not None and payload.observacao:
            try:
                movimento.observacao = payload.observacao
            except Exception:
                # Proteção genérica caso o mapeamento de coluna não exista em runtime
                pass
        if is_entrada:
            movimento.nota_fiscal = payload.nota_fiscal  # type: ignore[attr-defined]
        else:
            # Persistir metadados da operação fracionada quando aplicável
            if getattr(movimento.__class__, "usou_fracao", None) is not None:
                movimento.usou_fracao = bool(payload.modo_fracionado)
            if payload.modo_fracionado:
                for attr_name, value in (
                    ("tipo_produto", payload.tipo_produto),
                    ("densidade_aplicada", payload.densidade_aplicada),
                    ("fracao_numerador", payload.fracao_numerador),
                    ("fracao_denominador", payload.fracao_denominador),
                    ("quantidade_total_embalagem", payload.quantidade_total_embalagem),
                    ("quantidade_retirada_em_litros", payload.quantidade_retirada_em_litros),
                    ("quantidade_retirada_em_quilos", payload.quantidade_retirada_em_quilos),
                    ("quantidade_restante", payload.quantidade_restante),
                ):
                    if value is not None and hasattr(movimento, attr_name):
                        setattr(movimento, attr_name, value)
            
            # Persistir local_servico se for saída
            if not is_entrada and payload.local_servico and hasattr(movimento, "local_servico"):
                movimento.local_servico = payload.local_servico
            
            # Persistir tipo_custodia se for saída
            if not is_entrada and hasattr(movimento, "tipo_custodia"):
                movimento.tipo_custodia = self._normalize_tipo_custodia(getattr(payload, "tipo_custodia", None))

        db.session.add(movimento)
        db.session.flush()
        db.session.refresh(item)
        saldo_atualizado = item.get_saldo_atual()
        item.estoque_minimo = _calculate_min_stock(saldo_atualizado)
        db.session.commit()
        
        # Notificar via Telegram (não bloquear operação em caso de erro)
        # Se skip_notification=True, não envia notificação (usado quando já enviamos notificação unificada de item criado)
        if not skip_notification:
            try:
                from ..services.telegram_service import TelegramService
                
                if is_entrada:
                    # Notificar sobre nova entrada
                    entrada_id = getattr(movimento, "id_entrada", None)
                    if entrada_id:
                        TelegramService.notify_new_entry(entrada_id, is_devolucao=payload.is_devolucao)
                else:
                    # Notificar sobre saída
                    saida_id = getattr(movimento, "id_saida", None)
                    if saida_id:
                        tipo_custodia = (payload.tipo_custodia or "temporaria").strip().lower()
                        from ..services.notification_router import NotificationRouterService

                        if tipo_custodia == "permanente":
                            NotificationRouterService.route_permanent_custody(saida_id)
                        else:
                            NotificationRouterService.route_withdrawal(
                                saida_id,
                                force_single=True,
                                balance_before=telegram_balance_before,
                                balance_after=telegram_balance_after,
                                balance_unit=telegram_balance_unit,
                            )
            except Exception:
                # Não bloquear a operação por falha na notificação
                pass
        
        # Verificar e gerar relatório automático a cada 1000 entradas (apenas para entradas)
        if is_entrada:
            try:
                from ..services.entrada_report_service import entrada_report_service
                entrada_report_service.check_e_gerar_relatorio()
            except Exception as e:
                # Não bloquear a operação por falha no relatório automático
                logger.warning(f"Erro ao verificar relatório automático de entradas: {e}")

        # Retornar o objeto movimento criado
        return movimento


inventory_service = InventoryService()


def _sanitize_codigo(codigo: str | None) -> str:
    if not codigo:
        return ""
    codigo = codigo.strip()
    if not codigo:
        return ""
    return codigo


def _calculate_min_stock(quantity: float) -> int:
    if quantity <= 0:
        return 0
    return max(1, math.ceil(quantity * 0.05))


def _append_usuario(nota: dict[str, Any], entrada: Entrada) -> None:
    usuarios: set[str] = nota.setdefault("usuarios", set())  # type: ignore[assignment]
    nome = (entrada.usuario.nome if entrada.usuario else entrada.matricula) or ""
    if nome:
        usuarios.add(nome)


def _normalizar_usuarios(nota: dict[str, Any]) -> None:
    raw = nota.get("usuarios")
    if isinstance(raw, set):
        nota["usuarios"] = sorted(raw)


def _agrupar_notas(registros: Iterable[Entrada]) -> dict[str, dict[str, Any]]:
    notas: dict[str, dict[str, Any]] = {}
    for entrada in registros:
        numero = (entrada.nota_fiscal or "").strip()
        if not numero:
            continue
        nota = notas.get(numero)
        if nota is None:
            nota = {
                "nota_fiscal": numero,
                "data": entrada.data_entrada,
                "itens": [],
                "total_itens": 0,
                "total_quantidade": 0,
                "usuarios": set(),
            }
            notas[numero] = nota
        else:
            data_atual = nota.get("data")
            if entrada.data_entrada and (data_atual is None or entrada.data_entrada > data_atual):
                nota["data"] = entrada.data_entrada
        item_info = {
            "id": entrada.id_entrada,
            "codigo": entrada.codigo_item,
            "descricao": entrada.item.descricao if entrada.item else "",
            "quantidade": entrada.quantidade,
        }
        nota["itens"].append(item_info)  # type: ignore[index]
        _append_usuario(nota, entrada)
    for nota in notas.values():
        nota["total_itens"] = len(nota["itens"])  # type: ignore[index]
        nota["total_quantidade"] = sum(item.get("quantidade", 0) for item in nota["itens"])  # type: ignore[index]
        _normalizar_usuarios(nota)
    return notas
