"""Inventory CRUD routes."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from io import BytesIO

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import login_required, current_user

from ..models import Item, Usuario
from ..services.inventory import MovimentoPayload, inventory_service
from ..services.telegram_service import TelegramService
from ..utils.barcode_generator import generate_barcode, get_barcode_path
from .movements import LIQUID_PRODUCT_TYPES

blueprint = Blueprint("inventory", __name__, url_prefix="/itens")


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


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


def _is_admin(user) -> bool:
    if not user:
        return False
    value = getattr(user, "is_admin", False)
    if isinstance(value, str):
        return value.strip() in ("1", "true", "True", "TRUE")
    return bool(value)


def _is_supervisor(user) -> bool:
    if not user:
        return False
    setor = (getattr(user, "setor", "") or "").strip().lower()
    cargo = (getattr(user, "cargo", "") or "").strip().lower()
    return "supervisor" in setor or "supervisor" in cargo


def _require_admin_or_supervisor() -> None:
    if not (_is_admin(current_user) or _is_supervisor(current_user)):
        abort(403)


def _safe_float(value: str | int | float | None) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@blueprint.get("/")
@login_required
def list_items():
    raw_itens = inventory_service.list_items()
    itens: list[dict] = []
    for raw in raw_itens:
        item = dict(raw)
        codigo = item.get("codigo")
        if codigo:
            item["edit_url"] = url_for("inventory.edit_item_form", codigo=codigo)
        itens.append(item)
    can_manage = _is_admin(current_user)
    can_create = can_manage or _is_supervisor(current_user)
    
    # Carregar lista de usuários para modal de atribuição (apenas se admin)
    users_list = []
    if can_manage:
        try:
            users_query = Usuario.query.order_by(Usuario.nome).all()
            users_list = [{"matricula": u.matricula, "nome": u.nome} for u in users_query]
        except Exception:
            pass

    category_groups: dict[str, list[dict]] = defaultdict(list)
    for item in itens:
        category = item.get("categoria") or "Sem categoria"
        category_groups[category].append(item)
    category_cards: list[dict] = []
    for category, items in sorted(category_groups.items()):
        saldo_total = sum(_safe_float(item.get("saldo")) for item in items)
        category_cards.append(
            {
                "categoria": category,
                "total": len(items),
                "saldo_total": saldo_total,
                "entries": items,
            }
        )
    return render_template(
        "inventory/list.html",
        itens=itens,
        can_manage=can_manage,
        can_create=can_create,
        category_cards=category_cards,
        selected_category=request.args.get("categoria", "").strip(),
        users_list=users_list,
    )


@blueprint.get("/novo")
@login_required
def new_item_form():
    _require_admin_or_supervisor()
    codigo_prefill = request.args.get("codigo", "").strip()
    form_data = {"codigo": codigo_prefill} if codigo_prefill else None
    
    # Se o código já existe, calcular saldo total para mostrar no form
    saldo_total_ean = None
    if codigo_prefill:
        try:
            saldo_total_ean = Item.get_saldo_total_by_codigo(codigo_prefill)
        except Exception:
            pass
    
    return render_template(
        "inventory/form.html",
        item=None,
        form_data=form_data,
        saldo_desejado=0,
        saldo_total_ean=saldo_total_ean,
        liquid_types=LIQUID_PRODUCT_TYPES,
    )


@blueprint.post("/novo")
@login_required
def create_item():
    _require_admin_or_supervisor()
    form = request.form
    saldo_raw = form.get("saldo_atual", "0").strip()
    try:
        saldo_desejado = int(saldo_raw or 0)
    except ValueError:
        saldo_desejado = -1
    tipo_novo = form.get("tipo_embalagem_novo") or None
    unidade_embalagem_novo = form.get("unidade_embalagem_novo")
    unidades_por_emb_raw = form.get("unidades_por_embalagem")

    litros_var = None
    grandeza_var = None
    unidades_var = None

    if tipo_novo in ["lata", "balde"]:
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        if unidade_embalagem_novo == "litro":
            litros_var = val
        elif unidade_embalagem_novo == "kg":
            grandeza_var = val
    elif tipo_novo in ["rolo", "pacote", "caixa"]:
        unidades_var = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
    elif tipo_novo == "litro":
        litros_var = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
    
    payload = {
        "codigo": form.get("codigo", "").strip(),
        "descricao": form.get("descricao", "").strip(),
        "nota_fiscal": form.get("nota_fiscal", "").strip() or None,
        "localizacao": form.get("localizacao", "").strip() or None,
        "categoria": form.get("categoria", "Material Elétrico"),
        "marca": form.get("marca", "").strip() or None,
        "unidade": form.get("unidade", "").strip(),
        "numero_serie": form.get("numero_serie", "").strip() or None,
        "modelo": form.get("modelo", "").strip() or None,
        "data_entrada": form.get("data_entrada") or None,
        "data_fabricacao": form.get("data_fabricacao") or None,
        "data_validade": form.get("data_validade") or None,
        "lote": (form.get("lote") or "").strip() or None,
        "gerar_lote_automatico": bool(form.get("gerar_lote_automatico")),
        "tipo_embalagem": form.get("tipo_embalagem"),
        "grandeza_referencia": form.get("grandeza_referencia") or None,
        "litros_por_embalagem": form.get("litros_por_embalagem") or None,
        "tipo_embalagem_novo": tipo_novo,
        "unidades_por_embalagem": unidades_var,
        "voltagem": form.get("voltagem", "").strip() or None,
        "amperagem": form.get("amperagem", "").strip() or None,
        "local_instalacao": form.get("local_instalacao", "").strip() or None,
        "quantidade": saldo_desejado,  # Para registrar entrada quando item existe com lote diferente
    }
    if tipo_novo:
        payload["litros_por_embalagem"] = litros_var
        payload["grandeza_referencia"] = grandeza_var
    try:
        if not payload["codigo"] or not payload["descricao"]:
            raise ValueError("Código e descrição são obrigatórios")
        if saldo_desejado < 0:
            raise ValueError("Informe uma quantidade inicial válida")
        resultado = inventory_service.create_item(payload)
        
        # Verificar se foi atualização de item existente (lote diferente)
        foi_atualizacao = resultado.startswith("UPDATED:")
        codigo = resultado.replace("UPDATED:", "") if foi_atualizacao else resultado
        
        # Registrar entrada apenas se foi criação nova (não atualização)
        # Para atualizações, a entrada já foi registrada no service
        entrada_inicial = None
        if not foi_atualizacao and saldo_desejado > 0:
            # Registrar entrada com skip_notification=True pois enviaremos notificação unificada
            entrada_inicial = inventory_service.registrar_entrada(
                MovimentoPayload(
                    codigo=codigo,
                    quantidade=saldo_desejado,
                    matricula=current_user.id,
                    nota_fiscal=payload["nota_fiscal"],
                ),
                skip_notification=True  # Não enviar notificação separada de entrada
            )
        
        # Notificar criação de item aos administradores (notificação UNIFICADA)
        try:
            TelegramService.notify_item_created(codigo, entrada_inicial=entrada_inicial)
        except Exception:
            pass
        
        if foi_atualizacao:
            flash(f"Nova entrada registrada para item existente (lote atualizado).", "success")
        else:
            flash("Item cadastrado com sucesso.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
        quantidade_context = saldo_desejado if saldo_desejado >= 0 else None
        if quantidade_context is not None:
            payload["saldo"] = quantidade_context
        saldo_total_ean = None
        if payload.get("codigo"):
            try:
                saldo_total_ean = Item.get_saldo_total_by_codigo(payload["codigo"])
            except Exception:
                saldo_total_ean = None
        return render_template(
            "inventory/form.html",
            item=None,
            form_data=payload,
            saldo_desejado=quantidade_context,
            saldo_total_ean=saldo_total_ean,
            liquid_types=LIQUID_PRODUCT_TYPES,
        ), 400
    return redirect(url_for("inventory.list_items"))


@blueprint.get("/<codigo>/editar")
@login_required
def edit_item_form(codigo: str):
    _require_admin()
    item = inventory_service.get_item(codigo)
    if not item:
        flash("Item não encontrado.", "danger")
        return redirect(url_for("inventory.list_items"))
    
    # Calcular saldo total de todos os lotes com o mesmo EAN
    saldo_total = Item.get_saldo_total_by_codigo(codigo)
    
    return render_template(
        "inventory/form.html",
        item=item,
        form_data=None,
        saldo_desejado=item.get("saldo", 0),
        saldo_total_ean=saldo_total,
        liquid_types=LIQUID_PRODUCT_TYPES,
    )


@blueprint.post("/<codigo>/editar")
@login_required
def update_item(codigo: str):
    _require_admin()
    form = request.form
    saldo_raw = form.get("saldo_atual", "0").strip()
    try:
        saldo_desejado = int(saldo_raw or 0)
    except ValueError:
        saldo_desejado = -1

    # Lógica de processamento de Unidades Dinâmicas
    tipo_novo = form.get("tipo_embalagem_novo") or None
    unidade_embalagem_novo = form.get("unidade_embalagem_novo") # 'litro' ou 'kg'
    unidades_por_emb_raw = form.get("unidades_por_embalagem")
    
    litros_var = None
    grandeza_var = None
    unidades_var = None
    
    if tipo_novo in ['lata', 'balde']:
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        if unidade_embalagem_novo == 'litro':
            litros_var = val
        elif unidade_embalagem_novo == 'kg':
            grandeza_var = val
            # Baldes/Latas em KG usam grandeza_referencia
    elif tipo_novo in ['rolo', 'pacote', 'caixa']:
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = val
        # Rolos também podem usar grandeza_referencia no legado, mas no novo sistema usamos unidades_por_embalagem (metros/unid)
    elif tipo_novo == 'litro':
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        litros_var = val
    
    # Se tipo_novo for None (Nenhum), limpa tudo
    
    payload = {
        "codigo": form.get("codigo", "").strip(),
        "descricao": form.get("descricao", "").strip(),
        "nota_fiscal": form.get("nota_fiscal", "").strip() or None,
        "localizacao": form.get("localizacao", "").strip() or None,
        "categoria": form.get("categoria", "Material Elétrico"),
        "marca": form.get("marca", "").strip() or None,
        "unidade": form.get("unidade", "").strip(),
        "numero_serie": form.get("numero_serie", "").strip() or None,
        "modelo": form.get("modelo", "").strip() or None,
        "data_entrada": form.get("data_entrada") or None,
        "data_fabricacao": form.get("data_fabricacao") or None,
        "data_validade": form.get("data_validade") or None,
        "lote": (form.get("lote") or "").strip() or None,
        "gerar_lote_automatico": bool(form.get("gerar_lote_automatico")),
        
        
        # Campos atualizados de Unidades Dinâmicas
        "tipo_embalagem_novo": tipo_novo,
        "litros_por_embalagem": litros_var,
        "grandeza_referencia": grandeza_var,
        "unidades_por_embalagem": unidades_var,
        
        # Histórico
        "ultima_edicao_em": datetime.now(),
        "ultima_edicao_por": current_user.nome if hasattr(current_user, 'nome') else current_user.id,
        # Campos de Equipamento
        "voltagem": form.get("voltagem", "").strip() or None,
        "amperagem": form.get("amperagem", "").strip() or None,
        "local_instalacao": form.get("local_instalacao", "").strip() or None,
    }

    # Preservar campos antigos se não forem substituídos pelo novo sistema?
    # Neste caso, estamos assumindo que o formulário é a fonte da verdade para a edição.
    
    try:
        # buscar estado anterior para notificação
        prev_item = inventory_service.get_item(codigo)
        prev_balance = None
        try:
            if prev_item:
                prev_balance = int(prev_item.get("saldo", 0))
        except Exception:
            prev_balance = None

        if saldo_desejado < 0:
            raise ValueError("Informe uma quantidade válida")

        updated_codigo = inventory_service.update_item(codigo, payload)

        if saldo_desejado >= 0:
            inventory_service.adjust_item_balance(
                codigo=updated_codigo,
                novo_saldo=saldo_desejado,
                matricula=current_user.id,
                nota_fiscal=payload.get("nota_fiscal"),
                descricao="Ajuste manual via edição do item",
            )
        
        # Notificar atualização: enviar resumo do que mudou
        try:
            TelegramService.notify_item_updated(updated_codigo, prev=prev_item, prev_balance=prev_balance)
        except Exception:
            pass
        flash("Item atualizado com sucesso.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("inventory.edit_item_form", codigo=codigo))
    return redirect(url_for("inventory.list_items"))


@blueprint.post("/<codigo>/excluir")
@login_required
def delete_item(codigo: str):
    _require_admin()
    try:
        inventory_service.delete_item(codigo)
        flash("Item excluído.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("inventory.list_items"))


@blueprint.post("/<codigo>/entrada")
@login_required
def registrar_entrada(codigo: str):
    _require_admin()
    quantidade = float(request.form.get("quantidade", "0") or 0)
    nota = request.form.get("nota_fiscal") or None
    
    # Capturar tipo de entrada para unidades dinâmicas
    tipo_entrada = request.form.get("tipo_entrada")  # "embalagem" ou "unidades"
    em_embalagens = None
    if tipo_entrada == "embalagem":
        em_embalagens = True
    elif tipo_entrada == "unidades":
        em_embalagens = False
    # Se tipo_entrada não foi enviado (item sem unidades dinâmicas), em_embalagens fica None
    
    try:
        inventory_service.registrar_entrada(
            MovimentoPayload(codigo=codigo, quantidade=quantidade, matricula=current_user.id, nota_fiscal=nota, em_embalagens=em_embalagens)
        )
        flash("Entrada registrada.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("inventory.list_items"))


@blueprint.post("/<codigo>/saida")
@login_required
def registrar_saida(codigo: str):
    _require_admin()
    quantidade = float(request.form.get("quantidade", "0") or 0)
    tipo_custodia = request.form.get("tipo_custodia", "temporaria")
    matricula = request.form.get("matricula") or current_user.id
    
    # Capturar tipo de saída para unidades dinâmicas
    tipo_saida = request.form.get("tipo_saida")  # "embalagem" ou "unidades"
    em_embalagens = None
    if tipo_saida == "embalagem":
        em_embalagens = True
    elif tipo_saida == "unidades":
        em_embalagens = False
    # Se tipo_saida não foi enviado (item sem unidades dinâmicas), em_embalagens fica None
    
    try:
        saida_id = inventory_service.registrar_saida(
            MovimentoPayload(
                codigo=codigo, 
                quantidade=quantidade, 
                matricula=matricula,
                tipo_custodia=tipo_custodia,
                em_embalagens=em_embalagens
            )
        )
        flash("Saída registrada.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("inventory.list_items"))


@blueprint.post('/<codigo>/notify')
@login_required
def notify_item(codigo: str):
    _require_admin()
    try:
        from ..services.telegram_service import TelegramService

        res = TelegramService.notify_item_now(codigo)
        if res.get('success'):
            flash('Notificação enviada para administradores vinculados.', 'success')
        else:
            flash(f"Falha ao enviar notificação: {res.get('error')}", 'warning')
    except Exception as exc:
        flash(f'Erro ao notificar: {exc}', 'danger')
    return redirect(url_for('inventory.list_items'))


@blueprint.post('/categoria/<categoria>/excluir')
@login_required
def delete_category(categoria: str):
    _require_admin()
    try:
        # Buscar todos os itens da categoria
        itens = inventory_service.list_items()
        itens_categoria = [item for item in itens if item.get("categoria") == categoria]
        
        if not itens_categoria:
            flash(f"Nenhum item encontrado na categoria '{categoria}'.", "warning")
            return redirect(url_for('inventory.list_items'))
        
        # Excluir cada item da categoria
        deleted_count = 0
        for item in itens_categoria:
            try:
                inventory_service.delete_item(item["codigo"])
                deleted_count += 1
            except Exception:
                pass
        
        if deleted_count > 0:
            flash(f"Categoria '{categoria}' excluída com sucesso ({deleted_count} itens removidos).", "success")
        else:
            flash(f"Não foi possível excluir itens da categoria '{categoria}'.", "danger")
    except Exception as exc:
        flash(f"Erro ao excluir categoria: {exc}", "danger")
    return redirect(url_for('inventory.list_items'))


@blueprint.post('/barcodes/gerar')
@login_required
def generate_all_barcodes():
    _require_admin()
    stats = inventory_service.ensure_barcodes_for_all()
    message = (
        f"Códigos de barras: {stats['generated']} gerados, "
        f"{stats['skipped']} já existiam, {stats['failed']} falharam."
    )
    category = "success" if stats["failed"] == 0 else "warning"
    flash(message, category)
    return redirect(url_for('inventory.list_items'))


@blueprint.get("/<codigo>/barcode.svg")
@login_required
def item_barcode_svg(codigo: str):
    _require_admin()
    item = Item.query.get(codigo)
    if not item:
        abort(404)

    payload = (item.codigo_item or "").strip()
    if not payload:
        abort(400)

    try:
        import barcode
        from barcode.writer import SVGWriter
    except Exception as exc:
        raise ValueError(
            "Biblioteca de código de barras não instalada. Instale 'python-barcode' (pip install python-barcode)."
        ) from exc

    code = barcode.get(
        "code128",
        payload,
        writer=SVGWriter(),
    )

    buffer = BytesIO()
    code.write(
        buffer,
        options={
            "write_text": False,
            "module_width": 0.4,
            "module_height": 24.0,
            "quiet_zone": 10.0,
            "background": "white",
            "foreground": "black",
        },
    )
    svg_bytes = buffer.getvalue()

    if not item.barcode_image_path:
        try:
            barcode_path = get_barcode_path(payload) or generate_barcode(payload, item.descricao)
            item.barcode_image_path = barcode_path
            from ..extensions import db
            db.session.commit()
        except Exception:
            pass

    resp = make_response(svg_bytes)
    resp.mimetype = "image/svg+xml"
    resp.headers["Content-Disposition"] = f'inline; filename="barcode_item_{payload}.svg"'
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@blueprint.get("/<codigo>/barcode.png")
@login_required
def item_barcode_png(codigo: str):
    _require_admin()
    item = Item.query.get(codigo)
    if not item:
        abort(404)

    payload = (item.codigo_item or "").strip()
    if not payload:
        abort(400)

    try:
        import barcode
        from barcode.writer import ImageWriter
    except Exception as exc:
        raise ValueError(
            "Biblioteca de código de barras não instalada. Instale 'python-barcode' (pip install python-barcode)."
        ) from exc

    code = barcode.get(
        "code128",
        payload,
        writer=ImageWriter(),
    )

    buffer = BytesIO()
    code.write(
        buffer,
        options={
            "write_text": False,
            "module_width": 0.4,
            "module_height": 28.0,
            "quiet_zone": 12.0,
            "background": "white",
            "foreground": "black",
        },
    )
    png_bytes = buffer.getvalue()

    if not item.barcode_image_path:
        try:
            barcode_path = get_barcode_path(payload) or generate_barcode(payload, item.descricao)
            item.barcode_image_path = barcode_path
            from ..extensions import db
            db.session.commit()
        except Exception:
            pass

    resp = make_response(png_bytes)
    resp.mimetype = "image/png"
    resp.headers["Content-Disposition"] = f'inline; filename="barcode_item_{payload}.png"'
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@blueprint.get("/api/<codigo>")
@login_required
def get_item_api(codigo: str):
    """API endpoint para buscar informações do item."""
    from flask import jsonify
    item = Item.query.get(codigo)
    if not item:
        return jsonify({"error": "Item não encontrado"}), 404
    
    return jsonify({
        "codigo": item.codigo,
        "descricao": item.descricao,
        "unidade": item.unidade,
        "tipo_embalagem_novo": item.tipo_embalagem_novo,
        "unidades_por_embalagem": item.unidades_por_embalagem,
        "saldo": item.saldo,
    })
