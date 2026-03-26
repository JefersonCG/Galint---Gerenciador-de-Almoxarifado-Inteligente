"""Rotas de lançamentos de estoque (entradas e saídas)."""
from __future__ import annotations

import unicodedata
import re
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for, send_file
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Item, Saida, RetiradaFerramenta
from ..services.inventory import MovimentoPayload, inventory_service
from ..services.users import user_service
from ..services.entrada_service import entrada_service
from ..services.telegram_service import TelegramService
from ..mako_renderer import render_mako_template

blueprint = Blueprint("movements", __name__, url_prefix="/movimentos")


@blueprint.get("/api/buscar-item")
@login_required
def buscar_item():
    """API: Busca itens por código ou nome (parcial)."""
    query = (request.args.get("q") or "").strip()
    
    if not query or len(query) < 1:
        return jsonify({"items": [], "itens": []})
    
    resultados = inventory_service.search_items_for_autocomplete(query, limit=20)
    return jsonify({"items": resultados, "itens": resultados})


@blueprint.after_request
def flush_withdrawal_notifications(response):
    """Finaliza e envia notificações agrupadas de saídas após cada requisição."""
    try:
        # Apenas processar em requisições POST bem-sucedidas (status 2xx ou 3xx redirect)
        if request.method == 'POST' and 200 <= response.status_code < 400:
            TelegramService.flush_pending_withdrawals()
    except Exception:
        # Não bloquear a resposta por erro nas notificações
        pass
    return response


LIQUID_PRODUCT_TYPES: list[dict[str, Any]] = [
    {
        "id": "massa_acrilica",
        "label": "Massa Acrílica / Massa Corrida",
        "default_unit": "quilo",
        "keywords": ["massa acrilica", "massa corrida"],
    },
    {
        "id": "tinta_piso_base_agua",
        "label": "Tinta para Piso (base água / acrílica)",
        "default_unit": "litro",
        "keywords": ["tinta piso", "piso acrilica", "piso base agua"],
    },
    {
        "id": "tinta_asfaltica",
        "label": "Tinta Asfáltica",
        "default_unit": "litro",
        "keywords": ["tinta asfaltica", "asfaltica"],
    },
    {
        "id": "tinta_epoxi_piso",
        "label": "Tinta Epóxi para Piso (bicomp / industrial)",
        "default_unit": "litro",
        "keywords": ["epoxi", "epóxi", "bicomp", "epoxi piso"],
    },
    {
        "id": "tinta_acrilica",
        "label": "Tinta Acrílica (padrão, PVA, semi-brilho, fosca)",
        "default_unit": "litro",
        "keywords": ["tinta acrilica", "tinta pva", "tinta fosca", "tinta semi"],
    },
    {
        "id": "resina_multuso",
        "label": "Resina Multiuso (base água)",
        "default_unit": "litro",
        "keywords": ["resina", "multiuso"],
    },
    {
        "id": "tinta_esmalte",
        "label": "Tinta Esmalte (base solvente)",
        "default_unit": "litro",
        "keywords": ["tinta esmalte", "esmalte"],
    },
    {
        "id": "impermeabilizante",
        "label": "Impermeabilizante (acrílico / borracha líquida)",
        "default_unit": "litro",
        "keywords": ["impermeabilizante", "borracha liquida", "acrilico"],
    },
    {
        "id": "cloro_granulado",
        "label": "Cloro Granulado HTH (hipoclorito de cálcio 65%)",
        "default_unit": "quilo",
        "keywords": ["cloro", "cloro granulado", "hipoclorito", "hth"],
    },
]

LIQUID_PRODUCT_TYPES_BY_ID = {entry["id"]: entry for entry in LIQUID_PRODUCT_TYPES}
LIQUID_FRACTIONS: list[tuple[int, int]] = [(1, divisor) for divisor in range(2, 21)]
FRACTIONABLE_PACKAGING_TYPES = {"lata", "rolo", "pacote", "caixa", "litro", "balde", "bombona", "saco"}
FRACTIONABLE_LIQUID_HINTS = (
    "tinta",
    "resina",
    "verniz",
    "solvente",
    "thinner",
    "selador",
    "impermeabilizante",
    "esmalte",
)
FRACTIONABLE_WEIGHT_HINTS = (
    "massa",
    "argamassa",
    "rejunte",
    "cloro",
    "cimento",
    "gesso",
)


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


def _ensure_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_text(value: str | None) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _detect_liquid_type(*, categoria: str | None, descricao: str | None) -> dict[str, Any] | None:
    texto = f"{_normalize_text(categoria)} {_normalize_text(descricao)}"
    if not texto.strip():
        return None
    for entry in LIQUID_PRODUCT_TYPES:
        if any(keyword in texto for keyword in entry["keywords"]):
            return entry
    return None


def _infer_unidade(unidade: str | None) -> str:
    normalized = _normalize_text(unidade)
    if not normalized:
        return ""
    # Evita interpretar termos como "lata 18l" como litro
    if re.search(r"\b(litro|litros|lt|lts)\b", normalized):
        return "litro"
    if re.search(r"\b(kg|quilo|quilos)\b", normalized):
        return "quilo"
    return normalized


def _as_positive_float(value: Any) -> float:
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed > 0 else 0.0


def _extract_measurement_from_text(text: str, unit_pattern: str) -> float:
    if not text:
        return 0.0
    match = re.search(rf"(\d+(?:[.,]\d+)?)\s*({unit_pattern})\b", text)
    if not match:
        return 0.0
    raw_value = match.group(1).replace(",", ".")
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return 0.0


def _infer_package_name(item: dict[str, Any]) -> str:
    tipo_embalagem = _normalize_text(item.get("tipo_embalagem_novo"))
    unidade = _normalize_text(item.get("unidade"))
    descricao = _normalize_text(item.get("descricao"))
    if tipo_embalagem in FRACTIONABLE_PACKAGING_TYPES:
        return tipo_embalagem
    if unidade in FRACTIONABLE_PACKAGING_TYPES:
        return unidade
    for candidate in ("lata", "balde", "bombona", "rolo", "pacote", "caixa", "saco"):
        if candidate in descricao:
            return candidate
    if "tinta" in descricao or "resina" in descricao or "verniz" in descricao:
        return "lata"
    return "embalagem"


def _pluralize_package_name(package_name: str) -> str:
    package_name = _normalize_text(package_name)
    mapping = {
        "lata": "latas",
        "balde": "baldes",
        "bombona": "bombonas",
        "rolo": "rolos",
        "pacote": "pacotes",
        "caixa": "caixas",
        "saco": "sacos",
        "litro": "litros",
        "embalagem": "embalagens",
    }
    return mapping.get(package_name, f"{package_name}s" if package_name else "embalagens")


def _infer_package_capacity(item: dict[str, Any], *, fractional_info: dict[str, Any]) -> float:
    unidades_por_embalagem = _as_positive_float(item.get("unidades_por_embalagem"))
    if unidades_por_embalagem > 0:
        return unidades_por_embalagem

    litros_por_embalagem = _as_positive_float(item.get("litros_por_embalagem"))
    if litros_por_embalagem > 0:
        return litros_por_embalagem

    grandeza_referencia = _as_positive_float(item.get("grandeza_referencia"))
    if grandeza_referencia > 0:
        return grandeza_referencia

    texto = f"{_normalize_text(item.get('descricao'))} {_normalize_text(item.get('categoria'))}".strip()
    default_unit = _normalize_text(fractional_info.get("default_unit"))
    if default_unit == "litro":
        return _extract_measurement_from_text(texto, r"l|lt|lts|litro|litros")
    if default_unit == "quilo":
        return _extract_measurement_from_text(texto, r"kg|quilo|quilos")
    return 0.0


def _infer_fractional_item(item: dict[str, Any]) -> dict[str, Any]:
    tipo_embalagem = _normalize_text(item.get("tipo_embalagem_novo"))
    descricao = _normalize_text(item.get("descricao"))
    categoria = _normalize_text(item.get("categoria"))
    unidade = _infer_unidade(item.get("unidade"))
    grandeza_referencia = _as_positive_float(item.get("grandeza_referencia"))
    litros_por_embalagem = _as_positive_float(item.get("litros_por_embalagem"))
    texto = f"{categoria} {descricao}".strip()

    liquid_type = _detect_liquid_type(categoria=item.get("categoria"), descricao=item.get("descricao"))
    if liquid_type:
        return {
            "enabled": True,
            "default_unit": liquid_type.get("default_unit") or "litro",
            "source": "liquid_type",
        }

    if tipo_embalagem in FRACTIONABLE_PACKAGING_TYPES:
        if tipo_embalagem == "rolo":
            default_unit = "metro"
        elif tipo_embalagem == "caixa":
            default_unit = "unidade"
        elif tipo_embalagem in {"pacote", "saco"}:
            default_unit = "quilo" if grandeza_referencia > 0 else "unidade"
        elif tipo_embalagem == "litro" or litros_por_embalagem > 0:
            default_unit = "litro"
        elif tipo_embalagem in {"lata", "balde", "bombona"}:
            if unidade in {"litro", "quilo"}:
                default_unit = unidade
            elif grandeza_referencia > 0:
                default_unit = "quilo"
            else:
                default_unit = "unidade"
        else:
            default_unit = unidade or "unidade"
        return {
            "enabled": True,
            "default_unit": default_unit,
            "source": "tipo_embalagem_novo",
        }

    if litros_por_embalagem > 0:
        return {
            "enabled": True,
            "default_unit": "litro",
            "source": "litros_por_embalagem",
        }

    if grandeza_referencia > 0:
        return {
            "enabled": True,
            "default_unit": "quilo",
            "source": "grandeza_referencia",
        }

    if re.search(r"\b\d+(?:[.,]\d+)?\s*(l|lt|lts|litro|litros)\b", texto) and any(
        hint in texto for hint in FRACTIONABLE_LIQUID_HINTS
    ):
        return {
            "enabled": True,
            "default_unit": "litro",
            "source": "descricao_liquida",
        }

    if re.search(r"\b\d+(?:[.,]\d+)?\s*(kg|quilo|quilos)\b", texto) and any(
        hint in texto for hint in FRACTIONABLE_WEIGHT_HINTS
    ):
        return {
            "enabled": True,
            "default_unit": "quilo",
            "source": "descricao_pesavel",
        }

    return {
        "enabled": False,
        "default_unit": "quilo",
        "source": None,
    }


def _resolve_usuario(identificador: str | None):
    identificador = (identificador or "").strip()
    if identificador:
        # Aceita:
        # - matrícula (13 dígitos)
        # - barcode_token
        # - nome (com autocomplete)
        # - formato "Nome — 0000000000000" (extraímos a matrícula)
        candidato = identificador
        match = re.search(r"\b\d{13}\b", identificador)
        if match:
            candidato = match.group(0)

        usuario = user_service.find_by_identifier(candidato)
        if not usuario and not match:
            sugestoes = user_service.search_by_name(identificador, limit=6)
            if len(sugestoes) == 1:
                usuario = sugestoes[0]
            elif len(sugestoes) > 1:
                lista = ", ".join(f"{u.nome} ({u.matricula})" for u in sugestoes[:6])
                raise ValueError(
                    f"Múltiplos usuários encontrados. Seja mais específico ou use a matrícula. Sugestões: {lista}"
                )

        if not usuario:
            raise ValueError("Usuário não encontrado pelo identificador informado")

        # A matrícula/nome informado aqui é de quem está retirando/devolvendo.
        # (Não confundir com o usuário logado que está registrando.)
        return usuario
    if current_user.is_authenticated:
        return current_user
    raise ValueError("Sessão inválida")


def _parse_quantidade(raw: str | None) -> int:
    try:
        quantidade = float(raw or 0)
    except (TypeError, ValueError):
        quantidade = 0.0
    return quantidade


@blueprint.get("/")
@login_required
def index():
    """Mantém compatibilidade com a raiz de movimentos."""
    return redirect(url_for("movements.saidas_hub"))


@blueprint.get("/registro-de-saidas")
@login_required
def saidas_hub():
    """Exibe o hub de registro de saídas com os fluxos disponíveis."""
    return render_mako_template("movements/saidas_hub.mako")


# Página antiga "Controle de Saídas e Devoluções" removida - era inútil
# @blueprint.get("/")
# @login_required
# def index_OLD():
#     itens = inventory_service.list_items()
#     entradas = inventory_service.list_entradas(limit=25)
#     saidas = inventory_service.list_saidas(limit=25)
#     usuarios = user_service.list_users()
#     can_manage = bool(getattr(current_user, "is_admin", False))
#     devolucoes = [
#         entrada
#         for entrada in entradas
#         if (entrada.get("categoria") or "").strip().lower() == "ferramentas"
#     ]
#     return render_mako_template(
#         "movements/index.mako",
#         itens=itens,
#         entradas=devolucoes,
#         saidas=saidas,
#         usuarios=usuarios,
#         can_manage=can_manage,
#         liquid_types=LIQUID_PRODUCT_TYPES,
#         liquid_fractions=LIQUID_FRACTIONS,
#     )


@blueprint.post("/saida-multipla")
@login_required
def registrar_saida_multipla():
    """Registra múltiplas saídas de uma vez com notificação agrupada no Telegram."""
    _require_admin()
    
    try:
        data = request.get_json() or {}
        itens = data.get("itens", [])
        
        if not itens or not isinstance(itens, list):
            return jsonify({"success": False, "message": "Lista de itens é obrigatória"}), 400
        
        # Validar usuário comum para todos os itens
        identificador = data.get("usuario")
        usuario = _resolve_usuario(identificador)
        local_servico_geral = data.get("local_servico", "")
        
        saidas_criadas = []
        ledger_results = []
        resultados = []
        
        # Processar cada item
        for idx, item_data in enumerate(itens, 1):
            codigo = (item_data.get("codigo") or "").strip()
            quantidade = _parse_quantidade(item_data.get("quantidade"))
            observacao = (item_data.get("observacao") or "").strip() or None
            em_embalagens_raw = item_data.get("em_embalagens")
            em_embalagens = None
            if em_embalagens_raw is not None:
                em_embalagens = em_embalagens_raw == "1" if isinstance(em_embalagens_raw, str) else bool(em_embalagens_raw)
            
            if not codigo:
                resultados.append({"index": idx, "success": False, "message": "Código não informado"})
                continue
            
            if quantidade <= 0:
                resultados.append({"index": idx, "codigo": codigo, "success": False, "message": "Quantidade inválida"})
                continue
            
            savepoint = None
            try:
                savepoint = db.session.begin_nested()

                item = Item.query.filter_by(codigo_item=codigo).first()
                if not item:
                    raise ValueError("Item não encontrado")
                
                # Verificar saldo considerando sistema de embalagens
                from galint_flask.services.embalagem_service import EmbalagemService, embalagem_service

                usa_embalagens = EmbalagemService.tem_embalagem(item) and em_embalagens is not None
                saldo_atual = 0.0
                saldo_atual_unidades = 0.0

                if usa_embalagens:
                    # Itens antigos podem ter saldo legado, mas estoque novo zerado.
                    try:
                        EmbalagemService.tentar_sincronizar_estoque_de_legacy(item)
                    except Exception:
                        pass

                    try:
                        saldo_atual_unidades = float(EmbalagemService.calcular_estoque_total(item) or 0)
                    except Exception:
                        saldo_atual_unidades = 0.0

                    quantidade_em_unidades = float(quantidade)
                    if em_embalagens:
                        quantidade_em_unidades = float(quantidade) * float(item.unidades_por_embalagem or 1)

                    if saldo_atual_unidades < quantidade_em_unidades:
                        raise ValueError(
                            f"Saldo insuficiente. Disponível: {int(saldo_atual_unidades)} unidades"
                        )
                else:
                    # Sistema tradicional (sem embalagens) OU saída sem informar em_embalagens
                    try:
                        saldo_atual = float(item.get_saldo_atual() or 0)
                    except Exception:
                        saldo_atual = 0.0

                    if saldo_atual < quantidade:
                        raise ValueError(f"Saldo insuficiente. Disponível: {int(saldo_atual)}")
                
                # Debitar estoque de embalagens/unidades soltas (quando aplicável)
                if usa_embalagens:
                    novas_emb, novas_soltas, sucesso = embalagem_service.processar_saida(
                        item, float(quantidade), bool(em_embalagens)
                    )
                    if not sucesso:
                        raise ValueError("Saldo insuficiente para a saída solicitada")
                    item.estoque_embalagens = novas_emb
                    item.estoque_unidades_soltas = novas_soltas

                ledger_result = inventory_service.mirror_legacy_movement(
                    product_id=item.codigo_item,
                    movement_type="saida",
                    quantity=float(quantidade),
                    payload=MovimentoPayload(
                        codigo=item.codigo_item,
                        quantidade=float(quantidade),
                        matricula=usuario.matricula,
                        observacao=str(observacao or "").upper() if observacao else None,
                        local_servico=str(local_servico_geral or "").upper() if local_servico_geral else None,
                        em_embalagens=em_embalagens,
                    ),
                    metadata={
                        "reference_type": "movements_saida_multipla",
                    },
                )

                # Criar saída diretamente
                saida = Saida()
                saida.codigo_item = item.codigo_item
                saida.quantidade = quantidade
                saida.matricula = usuario.matricula
                saida.data_saida = datetime.now(timezone.utc)
                saida.observacao = str(observacao or "").upper() if observacao else None
                saida.local_servico = str(local_servico_geral or "").upper() if local_servico_geral else None

                # Se tiver parâmetro de embalagem, adicionar (caso modelo suporte)
                if em_embalagens is not None and hasattr(saida, 'em_embalagens'):
                    saida.em_embalagens = em_embalagens

                db.session.add(saida)
                ledger_results.append((ledger_result, saida))
                
                # Se for ferramenta, criar registro em retiradas_ferramentas
                try:
                    categoria_text = (item.categoria or '').lower()
                    if 'ferrament' in categoria_text:
                        # VALIDAÇÃO CRÍTICA: Verificar se há saldo disponível para ferramentas
                        from sqlalchemy import func
                        quantidade_em_uso = db.session.query(
                            func.coalesce(func.sum(RetiradaFerramenta.quantidade), 0)
                        ).filter(
                            RetiradaFerramenta.codigo_item == item.codigo_item,
                            RetiradaFerramenta.status == 'em_uso'
                        ).scalar() or 0
                        
                        # Ferramentas usam controle tradicional (quantidade em uso vs saldo total)
                        try:
                            saldo_atual_ferramenta = float(item.get_saldo_atual() or 0)
                        except Exception:
                            saldo_atual_ferramenta = 0.0

                        saldo_disponivel_ferramenta = saldo_atual_ferramenta - quantidade_em_uso
                        
                        if saldo_disponivel_ferramenta < quantidade:
                            raise ValueError(
                                f"Ferramenta indisponível. {int(quantidade_em_uso)} em uso por outro(s) funcionário(s)"
                            )
                        
                        retirada = RetiradaFerramenta(
                            codigo_item=item.codigo_item,
                            matricula=usuario.matricula,
                            quantidade=int(quantidade or 1),
                            local_servico=str(local_servico_geral or '').upper() if local_servico_geral else None,
                            observacao=str(observacao or '').upper() if observacao else None,
                            status='em_uso',
                        )
                        db.session.add(retirada)
                except ValueError as ve:
                    # Exceção de validação deve retornar erro
                    raise ve
                except Exception as e:
                    # Outros erros apenas logam mas não interrompem
                    current_app.logger.warning(f"Erro ao criar RetiradaFerramenta para {item.codigo_item}: {e}")
                
                db.session.flush()

                # Confirma o savepoint deste item (outer commit acontece ao final)
                try:
                    savepoint.commit()
                except Exception:
                    # Se falhar aqui, cai no except geral abaixo
                    raise
                
                saida_id = saida.id_saida
                if saida_id:
                    saidas_criadas.append(saida_id)
                    resultados.append({
                        "index": idx,
                        "codigo": codigo,
                        "success": True,
                        "descricao": item.descricao,
                        "quantidade": quantidade
                    })
                else:
                    resultados.append({
                        "index": idx,
                        "codigo": codigo,
                        "success": False,
                        "message": "Erro ao criar saída"
                    })
            except Exception as e:
                if savepoint is not None:
                    try:
                        savepoint.rollback()
                    except Exception:
                        pass
                resultados.append({
                    "index": idx,
                    "codigo": codigo,
                    "success": False,
                    "message": str(e)
                })
        
        if not saidas_criadas:
            return jsonify({
                "success": False,
                "message": "Nenhum item foi processado com sucesso",
                "resultados": resultados
            }), 400
        
        # Commit das saídas
        db.session.commit()
        for ledger_result, saida in ledger_results:
            if ledger_result is not None:
                ledger_result.metadata["reference_id"] = str(saida.id_saida)
                inventory_service.finalize_ledger_mirror(ledger_result)
        
        # Enviar notificação via router (Telegram -> failover GalintNotify)
        try:
            from ..services.notification_router import NotificationRouterService

            if len(saidas_criadas) > 1:
                NotificationRouterService.route_multiple_withdrawal(saidas_criadas)
            elif len(saidas_criadas) == 1:
                NotificationRouterService.route_withdrawal(saidas_criadas[0], force_single=True)
        except Exception as e:
            # Não bloquear a operação por falha na notificação
            pass
        
        return jsonify({
            "success": True,
            "message": f"{len(saidas_criadas)} item(ns) registrado(s) com sucesso",
            "resultados": resultados
        }), 201
        
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Erro interno: {str(exc)}"}), 500


@blueprint.post("/saida")
@login_required
def registrar_saida():
    _require_admin()
    codigo_raw = request.form.get("codigo")
    codigo = (codigo_raw or "").strip() if codigo_raw is not None else ""
    identificador = request.form.get("usuario")
    quantidade = _parse_quantidade(request.form.get("quantidade"))
    obs_raw = request.form.get("observacao")
    observacao = (obs_raw or "").strip() if obs_raw is not None else None
    local_raw = request.form.get("local_servico")
    local_servico = (local_raw or "").strip() if local_raw is not None else None
    
    # Novo: processar sistema de embalagens
    em_embalagens_raw = request.form.get("em_embalagens")
    em_embalagens = None
    if em_embalagens_raw is not None:
        em_embalagens = em_embalagens_raw == "1"
    
    # Novo: processar unidade fracionada (kg ou litro)
    unidade_fracionada = request.form.get("unidade_fracionada")

    try:
        usuario = _resolve_usuario(identificador)
        item_info = inventory_service.get_item(codigo)
        if not item_info:
            raise ValueError("Item não encontrado")

        # Obter categoria para uso posterior (notificações e alertas)
        categoria = (item_info.get("categoria") or "").strip().lower()
        
        # Processar unidade fracionada (kg ou litro)
        # IMPORTANTE: Não converter para embalagens! O serviço de embalagens já faz isso automaticamente
        quantidade_convertida = quantidade
        if unidade_fracionada:
            # Para kg: enviar direto em kg (unidades base)
            if unidade_fracionada == 'kg':
                quantidade_convertida = quantidade  # Ex: 0.4 kg
                em_embalagens = False  # Indicar que é em unidades base (kg, não baldes)
                if not observacao:
                    observacao = f"Retirada fracionada: {quantidade} kg"
            # Para litros: enviar direto em litros (unidades base)
            elif unidade_fracionada == 'litro':
                quantidade_convertida = quantidade  # Ex: 2.5 litros
                em_embalagens = False  # Indicar que é em unidades base (litros, não latas)
                if not observacao:
                    observacao = f"Retirada fracionada: {quantidade} L"

        payload_kwargs: dict[str, Any] = {
            "codigo": codigo,
            "quantidade": quantidade_convertida,
            "matricula": usuario.id,
            "observacao": observacao,
            "local_servico": local_servico,
            "em_embalagens": em_embalagens,
        }

        payload = MovimentoPayload(**payload_kwargs)
        saida_id = inventory_service.registrar_saida(payload)
        
        # Notificação Telegram já é enviada automaticamente dentro de inventory_service.registrar_saida()
        
        # Se for requisição AJAX (feita pelo JavaScript), retornar JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
            return jsonify({"success": True, "message": "Saída registrada com sucesso."}), 200
        
        flash("Saída registrada com sucesso.", "success")
    except ValueError as exc:
        # Se for requisição AJAX, retornar erro em JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
            return jsonify({"success": False, "error": str(exc)}), 400
        
        flash(str(exc), "danger")
    # Não redirecionar mais - manter na mesma página (AJAX)
    # return redirect(url_for("movements.saida_fracionada_page"))
    return redirect(url_for("movements.saida_fracionada_page"))


@blueprint.get("/item-info/<codigo>")
@login_required
def item_info(codigo: str):
    """Retorna informações do item (para modal de embalagens e detalhes de líquidos)."""
    _require_admin()
    codigo = (codigo or "").strip()
    if not codigo:
        return jsonify({"found": False}), 400
    item = inventory_service.get_item(codigo)
    if not item:
        return jsonify({"found": False}), 404
    item_model = db.session.get(Item, codigo)
    
    liquid_type = _detect_liquid_type(categoria=item.get("categoria"), descricao=item.get("descricao"))
    fractional_info = _infer_fractional_item(item)
    package_name = _infer_package_name(item)
    package_capacity = _infer_package_capacity(item, fractional_info=fractional_info)
    package_name_plural = _pluralize_package_name(package_name)
    saldo_total = _as_positive_float(item.get("saldo"))
    foto_path = item.get("foto_path")
    response = {
        "found": True,
        "codigo": codigo,
        "descricao": item.get("descricao"),
        "categoria": item.get("categoria"),
        "unidade": item.get("unidade"),
        "saldo": item.get("saldo"),
        "saldo_display": item.get("saldo_display"),
        "saldo_total_fracionado": saldo_total,
        "tipo_embalagem_novo": item.get("tipo_embalagem_novo"),
        "unidades_por_embalagem": item.get("unidades_por_embalagem"),
        "grandeza_referencia": item.get("grandeza_referencia"),
        "litros_por_embalagem": item.get("litros_por_embalagem"),
        "saldo_embalagens": item.get("saldo_embalagens"),
        "saldo_unidades_soltas": item.get("saldo_unidades_soltas"),
        "permite_saida_fracionada": bool(fractional_info.get("enabled")),
        "fracao_unidade_padrao": fractional_info.get("default_unit"),
        "fracao_origem": fractional_info.get("source"),
        "nome_embalagem": item_model.get_nome_embalagem() if item_model and item_model.tipo_embalagem_novo else package_name,
        "nome_embalagem_plural": item_model.get_nome_embalagem_plural() if item_model and item_model.tipo_embalagem_novo else package_name_plural,
        "capacidade_embalagem": package_capacity,
        "unidade_exibicao_total": (
            "L"
            if _normalize_text(fractional_info.get("default_unit")) == "litro"
            else "kg"
            if _normalize_text(fractional_info.get("default_unit")) == "quilo"
            else "m"
            if _normalize_text(fractional_info.get("default_unit")) == "metro"
            else "un"
        ),
        "foto_path": foto_path,
        "foto_url": url_for("static", filename=foto_path) if foto_path else None,
    }
    if liquid_type:
        response.update(
            {
                "tipo_id": liquid_type["id"],
                "tipo_label": liquid_type["label"],
            }
        )
    return jsonify(response)


@blueprint.get('/saida/page')
@login_required
def saida_page():
    """Página separada para Registro de Saída (formulário com campo de observações)."""
    _require_admin()
    return render_mako_template(
        'movements/saida.mako',
        usuarios=user_service.list_users(),
        itens=[],
        liquid_types=LIQUID_PRODUCT_TYPES,
        liquid_fractions=LIQUID_FRACTIONS,
    )


@blueprint.get('/saida-fracionada/page')
@login_required
def saida_fracionada_page():
    """Página separada para Registro de Saída Fracionada (entrada manual via balança/pesagem)."""
    can_manage = bool(getattr(current_user, "is_admin", False))
    return render_mako_template(
        'movements/saida_fracionada.mako',
        usuarios=user_service.list_users(),
        itens=[],
        can_manage=can_manage,
    )


@blueprint.get('/saidas-fracionadas')
@login_required
def saidas_fracionadas_page():
    """Página com histórico de saídas fracionadas."""
    _require_admin()
    saidas = inventory_service.list_saidas_fracionadas(limit=200)
    return render_mako_template('movements/saidas_fracionadas.mako', saidas=saidas)


@blueprint.get('/entrada/page')
@login_required
def entrada_page():
    """Página separada para Registro de Devolução."""
    _require_admin()
    codigo_prefill = (request.args.get("codigo") or "").strip()
    return render_template(
        'movements/entrada.html',
        codigo_prefill=codigo_prefill,
        usuarios=user_service.list_users(),
        itens=[],
    )


@blueprint.post("/entrada")
@login_required
def registrar_entrada():
    """Registra entrada e garante atualização no histórico de entradas."""
    _require_admin()
    codigo = (request.form.get("codigo") or "").strip()
    identificador = request.form.get("usuario")
    quantidade = _parse_quantidade(request.form.get("quantidade"))
    nota_fiscal = (request.form.get("nota_fiscal") or "").strip() or None
    
    # Capturar tipo de entrada para unidades dinâmicas
    tipo_entrada = request.form.get("tipo_entrada")  # "embalagem" ou "unidades"
    em_embalagens = None
    if tipo_entrada == "embalagem":
        em_embalagens = True
    elif tipo_entrada == "unidades":
        em_embalagens = False
    # Se tipo_entrada não foi enviado (item sem unidades dinâmicas), em_embalagens fica None

    try:
        usuario = _resolve_usuario(identificador)
        inventory_service.registrar_entrada(
            MovimentoPayload(
                codigo=codigo,
                quantidade=quantidade,
                matricula=usuario.id,
                nota_fiscal=nota_fiscal,
                em_embalagens=em_embalagens,
            )
        )
        flash("Entrada registrada.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("movements.saida_fracionada_page"))  # Redirecionar para página principal





@blueprint.get('/alertas-estoque/pdf')
@login_required
def gerar_pdf_alertas_estoque():
    """Gera e faz download de PDF com alertas de estoque."""
    _require_admin()
    
    try:
        pdf_info = entrada_service.generate_alertas_estoque_pdf()
        
        return send_file(
            pdf_info['path'],
            as_attachment=True,
            download_name=pdf_info['filename']
        )
    
    except Exception as e:
        flash(f'Erro ao gerar PDF: {str(e)}', 'danger')
        return redirect(url_for('dashboard.index'))

