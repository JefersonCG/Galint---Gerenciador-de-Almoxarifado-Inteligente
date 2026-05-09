"""Views para configuração da empresa e relatórios."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from ..services.config_service import ConfigService
from ..services.finance_service import finance_service
from ..services.galint_notify_service import GalintNotifyService
from ..services.inventory import inventory_service
from ..services.notification_template_service import NotificationTemplateService
from ..services.notification_router import NotificationRouterService
from ..services.telegram_service import TelegramService
from ..extensions import db
from ..models import NotificationRouterConfig, TelegramConfig, TelegramUser, Usuario


bp = Blueprint("config", __name__, url_prefix="/configuracoes")


def _build_admin_adjustment_audit_context(*, codigo: str, novo_saldo: float | None, motivo: str | None) -> dict[str, object]:
    return {
        "codigo_item": str(codigo or "").strip() or None,
        "target_balance": novo_saldo,
        "reason": str(motivo or "").strip() or None,
        "user_id": str(getattr(current_user, "matricula", "") or getattr(current_user, "id", "")).strip() or None,
        "user_name": getattr(current_user, "nome", None),
        "route": request.path,
        "ip_address": request.remote_addr,
        "user_agent": request.user_agent.string if request.user_agent else None,
    }


@bp.route("/empresa", methods=["GET", "POST"])
@login_required
def empresa():
    """Configuração da empresa."""
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem alterar configurações.", "danger")
        return redirect(url_for("main.index"))
    
    empresa_config = ConfigService.get_empresa_config()
    login_branding = ConfigService.get_login_branding_config()
    
    if request.method == "POST":
        try:
            # Coletar dados do formulário
            data = {
                "nome_empresa": request.form.get("nome_empresa", "").strip(),
                "nome_fantasia": request.form.get("nome_fantasia", "").strip(),
                "cnpj": request.form.get("cnpj", "").strip(),
                "endereco_rua": request.form.get("endereco_rua", "").strip(),
                "endereco_numero": request.form.get("endereco_numero", "").strip(),
                "endereco_complemento": request.form.get("endereco_complemento", "").strip(),
                "endereco_bairro": request.form.get("endereco_bairro", "").strip(),
                "endereco_cidade": request.form.get("endereco_cidade", "").strip(),
                "endereco_estado": request.form.get("endereco_estado", "").strip(),
                "endereco_cep": request.form.get("endereco_cep", "").strip(),
                "telefone": request.form.get("telefone", "").strip(),
                "telefone_secundario": request.form.get("telefone_secundario", "").strip(),
                "email": request.form.get("email", "").strip(),
                "site": request.form.get("site", "").strip(),
            }
            
            # Validação básica
            if not data["nome_empresa"]:
                flash("Nome da empresa é obrigatório!", "danger")
                return render_template(
                    "config/empresa.html",
                    empresa_config=empresa_config,
                    login_branding=login_branding,
                )

            if request.form.get("remover_login_background") == "on":
                login_branding = ConfigService.clear_login_branding_asset("login_background_path")
                flash("Imagem de fundo do login removida. O sistema voltou para o fundo padrão.", "info")

            if request.form.get("remover_login_card_image") == "on":
                login_branding = ConfigService.clear_login_branding_asset("login_card_image_path")
                flash("Imagem do card do login removida. O sistema voltou para a imagem padrão.", "info")
            
            # Upload de logo (se houver)
            if "logo" in request.files:
                file = request.files["logo"]
                if file and file.filename:
                    try:
                        logo_path = ConfigService.upload_logo(file)
                        data["logo_path"] = logo_path
                        flash("Logo enviado com sucesso!", "success")
                    except ValueError as e:
                        flash(str(e), "danger")

            if "login_background" in request.files:
                file = request.files["login_background"]
                if file and file.filename:
                    try:
                        background_path = ConfigService.upload_login_background(file)
                        login_branding = ConfigService.update_login_branding_config(
                            {"login_background_path": background_path}
                        )
                        flash("Imagem de fundo do login atualizada com sucesso!", "success")
                    except ValueError as e:
                        flash(str(e), "danger")

            if "login_card_image" in request.files:
                file = request.files["login_card_image"]
                if file and file.filename:
                    try:
                        card_image_path = ConfigService.upload_login_card_image(file)
                        login_branding = ConfigService.update_login_branding_config(
                            {"login_card_image_path": card_image_path}
                        )
                        flash("Imagem do card do login atualizada com sucesso!", "success")
                    except ValueError as e:
                        flash(str(e), "danger")
            
            # Atualizar configuração
            ConfigService.update_empresa_config(data)
            flash("Configurações da empresa atualizadas com sucesso!", "success")
            
            return redirect(url_for("config.empresa"))
            
        except Exception as e:
            flash(f"Erro ao atualizar configurações: {str(e)}", "danger")
            empresa_config = ConfigService.get_empresa_config()
            login_branding = ConfigService.get_login_branding_config()
    
    return render_template(
        "config/empresa.html",
        empresa_config=empresa_config,
        login_branding=login_branding,
    )


@bp.route("/relatorios", methods=["GET", "POST"])
@login_required
def relatorios():
    """Configuração de relatórios."""
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem alterar configurações.", "danger")
        return redirect(url_for("main.index"))
    
    relatorio_config = ConfigService.get_relatorio_config()
    finance_config = finance_service.get_config()
    
    if request.method == "POST":
        try:
            # Coletar dados do formulário
            data = {
                "cabecalho_template": request.form.get("cabecalho_template", ""),
                "cabecalho_altura_mm": int(request.form.get("cabecalho_altura_mm", 40)),
                "cabecalho_mostrar_logo": request.form.get("cabecalho_mostrar_logo") == "on",
                "cabecalho_cor_texto": request.form.get("cabecalho_cor_texto", "#000000"),
                "cabecalho_fonte": request.form.get("cabecalho_fonte", "Helvetica"),
                "cabecalho_tamanho_fonte": int(request.form.get("cabecalho_tamanho_fonte", 10)),
                
                "rodape_template": request.form.get("rodape_template", ""),
                "rodape_altura_mm": int(request.form.get("rodape_altura_mm", 20)),
                "rodape_cor_texto": request.form.get("rodape_cor_texto", "#666666"),
                "rodape_tamanho_fonte": int(request.form.get("rodape_tamanho_fonte", 8)),
                "rodape_mostrar_data": request.form.get("rodape_mostrar_data") == "on",
                "rodape_mostrar_pagina": request.form.get("rodape_mostrar_pagina") == "on",
                
                "cor_primaria": request.form.get("cor_primaria", "#007bff"),
                "cor_secundaria": request.form.get("cor_secundaria", "#6c757d"),
                "fonte_principal": request.form.get("fonte_principal", "Helvetica"),
                "fonte_tabelas": request.form.get("fonte_tabelas", "Courier"),
            }

            finance_data = {
                "dia_fechamento": int(request.form.get("dia_fechamento", finance_config.dia_fechamento or 10)),
                "mes_fechamento": int(request.form.get("mes_fechamento", finance_config.mes_fechamento or 2)),
                "destacar_sem_comprovacao": request.form.get("destacar_sem_comprovacao") == "on",
                "permitir_fechamento_manual": request.form.get("permitir_fechamento_manual") == "on",
                "titulo_relatorio_anual": request.form.get("titulo_relatorio_anual", "").strip(),
            }
            
            # Atualizar configuração
            ConfigService.update_relatorio_config(data)
            finance_service.update_config(finance_data)
            flash("Configurações de relatórios atualizadas com sucesso!", "success")
            
            return redirect(url_for("config.relatorios"))
            
        except Exception as e:
            flash(f"Erro ao atualizar configurações: {str(e)}", "danger")
    
    return render_template(
        "config/relatorios.html",
        relatorio_config=relatorio_config,
        finance_config=finance_config,
    )


@bp.route("/fornecedores", methods=["GET", "POST"])
@login_required
def fornecedores():
    """Cadastro mestre de fornecedores financeiros."""
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem alterar configurações.", "danger")
        return redirect(url_for("dashboard.index"))

    supplier_edit = None
    if request.method == "POST":
        try:
            payload = {
                "id": request.form.get("id") or None,
                "razao_social": request.form.get("razao_social", "").strip(),
                "nome_fantasia": request.form.get("nome_fantasia", "").strip(),
                "cnpj": request.form.get("cnpj", "").strip(),
                "inscricao_estadual": request.form.get("inscricao_estadual", "").strip(),
                "endereco_rua": request.form.get("endereco_rua", "").strip(),
                "endereco_numero": request.form.get("endereco_numero", "").strip(),
                "endereco_complemento": request.form.get("endereco_complemento", "").strip(),
                "endereco_bairro": request.form.get("endereco_bairro", "").strip(),
                "endereco_cidade": request.form.get("endereco_cidade", "").strip(),
                "endereco_estado": request.form.get("endereco_estado", "").strip(),
                "endereco_cep": request.form.get("endereco_cep", "").strip(),
                "telefone": request.form.get("telefone", "").strip(),
                "email": request.form.get("email", "").strip(),
                "site": request.form.get("site", "").strip(),
                "situacao_cadastral": request.form.get("situacao_cadastral", "").strip(),
                "observacoes": request.form.get("observacoes", "").strip(),
                "api_origem": request.form.get("api_origem", "").strip(),
                "ativo": request.form.get("ativo") == "on",
            }
            supplier = finance_service.save_supplier(payload)
            flash(f"Fornecedor salvo com sucesso: {supplier.nome_exibicao()}", "success")
            return redirect(url_for("config.fornecedores", supplier_id=supplier.id))
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao salvar fornecedor: {exc}", "danger")

    supplier_id = request.args.get("supplier_id", type=int)
    if supplier_id:
        supplier = finance_service.get_supplier(supplier_id)
        supplier_edit = supplier.to_dict() if supplier else None

    return render_template(
        "config/fornecedores.html",
        fornecedores=finance_service.list_suppliers(),
        supplier_edit=supplier_edit,
    )


@bp.get("/api/fornecedores/autocomplete")
@login_required
def fornecedores_autocomplete():
    if not current_user.is_authenticated:
        return jsonify({"success": False, "message": "Não autenticado"}), 401
    term = request.args.get("q", "")
    return jsonify({"success": True, "results": finance_service.search_suppliers(term, limit=12)})


@bp.get("/api/fornecedores/cnpj/<cnpj>")
@login_required
def fornecedores_por_cnpj(cnpj: str):
    if not current_user.is_admin:
        return jsonify({"success": False, "message": "Acesso negado"}), 403
    try:
        existing = finance_service.get_supplier_by_cnpj(cnpj)
        if existing:
            supplier_data = existing.to_dict()
            supplier_data["source"] = "local"
            return jsonify({"success": True, "supplier": supplier_data})
        data = finance_service.fetch_supplier_by_cnpj(cnpj)
        data["source"] = "remote"
        return jsonify({"success": True, "supplier": data})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


@bp.route("/notificacoes", methods=["GET", "POST"])
@login_required
def notificacoes():
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem alterar configurações.", "danger")
        return redirect(url_for("dashboard.index"))

    router_config = NotificationRouterService.get_config()
    telegram_config = TelegramConfig.query.first() or TelegramConfig()

    if request.method == "POST":
        router_config.default_channel = (request.form.get("default_channel") or "telegram").strip().lower()
        router_config.telegram_enabled = request.form.get("telegram_enabled") == "on"
        router_config.notify_enabled = request.form.get("notify_enabled") == "on"
        router_config.push_enabled = request.form.get("push_enabled") == "on"
        router_config.push_provider = (request.form.get("push_provider") or "expo").strip().lower() or "expo"
        router_config.circuit_fail_threshold = max(1, int(request.form.get("circuit_fail_threshold") or 2))
        router_config.circuit_timeout_seconds = max(1, int(request.form.get("circuit_timeout_seconds") or 10))
        router_config.circuit_cooldown_seconds = max(60, int(request.form.get("circuit_cooldown_seconds") or 120))
        db.session.commit()
        flash("Painel de notificações atualizado com sucesso.", "success")
        return redirect(url_for("config.notificacoes"))

    router_status = NotificationRouterService.status_payload()
    telegram_users = TelegramUser.query.join(Usuario).all()
    groups = []
    usuarios = Usuario.query.order_by(Usuario.nome.asc()).all()

    return render_template(
        "config_notifications.html",
        router_config=router_config,
        router_status=router_status,
        telegram_config=telegram_config,
        telegram_users=telegram_users,
        groups=groups,
        usuarios=usuarios,
        notify_metrics=GalintNotifyService.metrics(),
    )


@bp.post("/notificacoes/testar")
@login_required
def notificacoes_testar():
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem testar notificações.", "danger")
        return redirect(url_for("dashboard.index"))

    matricula = (request.form.get("matricula") or "").strip()
    channel = (request.form.get("channel") or "router").strip().lower()
    message = (request.form.get("message") or "Teste manual do painel de notificações.").strip()
    title = (request.form.get("title") or "Teste GALINT").strip()

    if not matricula:
        flash("Selecione uma matrícula para o teste.", "warning")
        return redirect(url_for("config.notificacoes"))

    if channel == "telegram":
        telegram_user = TelegramUser.query.filter_by(matricula=matricula, enabled=True).first()
        if not telegram_user:
            flash("Usuário não possui vínculo Telegram ativo.", "warning")
            return redirect(url_for("config.notificacoes"))
        result = TelegramService.send_message(telegram_user.chat_id, f"<b>{title}</b>\n{message}")
        if result.get("success"):
            NotificationRouterService.record_telegram_success()
            flash("Teste Telegram enviado com sucesso.", "success")
        else:
            NotificationRouterService.record_telegram_failure(str(result.get("error") or "Falha no teste Telegram"), 0)
            flash(f"Falha no teste Telegram: {result.get('error')}", "danger")
        return redirect(url_for("config.notificacoes"))

    if channel == "notify":
        result = GalintNotifyService.deliver_message(
            recipient_ids=[matricula],
            title=title,
            body=message,
            category="manual_test",
            message_type="manual_test",
            payload={"kind": "manual_test"},
        )
        flash("Teste do inbox mobile enviado." if result.get("success") else f"Falha no teste: {result.get('error')}", "success" if result.get("success") else "danger")
        return redirect(url_for("config.notificacoes"))

    telegram_user = TelegramUser.query.filter_by(matricula=matricula, enabled=True).first()
    result = NotificationRouterService.route_event(
        event_name="manual_test",
        telegram_callable=(
            (lambda: TelegramService.send_message(telegram_user.chat_id, f"<b>{title}</b>\n{message}"))
            if telegram_user else (lambda: {"success": False, "error": "Usuário sem vínculo Telegram ativo"})
        ),
        notify_payload={
            "recipient_ids": [matricula],
            "title": title,
            "body": message,
            "category": "manual_test",
            "message_type": "manual_test",
            "payload": {"kind": "manual_test"},
        },
    )
    flash(
        f"Teste roteado via {result.get('channel')}" if result.get("success") else f"Falha no roteamento: {result.get('error')}",
        "success" if result.get("success") else "danger",
    )
    return redirect(url_for("config.notificacoes"))


@bp.route("/editor-notificacoes", methods=["GET", "POST"])
@login_required
def editor_notificacoes():
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem alterar modelos de notificação.", "danger")
        return redirect(url_for("dashboard.index"))

    models = NotificationTemplateService.list_models()
    if not models:
        flash("Nenhum modelo de notificação está disponível.", "warning")
        return redirect(url_for("config.notificacoes"))

    rotation = NotificationTemplateService.describe_current_rotation()
    selected_model_id = (request.values.get("model") or rotation.get("model_id") or models[0].get("id") or "").strip()
    if not NotificationTemplateService.get_model(selected_model_id):
        selected_model_id = str(models[0].get("id") or "")

    if request.method == "POST":
        action = (request.form.get("action") or "save").strip().lower()
        try:
            if action == "save":
                NotificationTemplateService.update_model(
                    selected_model_id,
                    {
                        "name": request.form.get("name") or "",
                        "description": request.form.get("description") or "",
                        "user_template": request.form.get("user_template") or "",
                        "supervisor_template": request.form.get("supervisor_template") or "",
                        "supervisor_batch_template": request.form.get("supervisor_batch_template") or "",
                    },
                )
                flash("Modelo salvo com sucesso.", "success")
            elif action == "preview_telegram":
                matricula = (request.form.get("matricula") or "").strip()
                template_kind = (request.form.get("template_kind") or "user").strip().lower()
                if not matricula:
                    raise ValueError("Selecione uma matrícula para enviar o preview.")
                telegram_user = TelegramUser.query.filter_by(matricula=matricula, enabled=True).first()
                if not telegram_user:
                    raise ValueError("Usuário não possui vínculo Telegram ativo.")
                usuario = Usuario.query.filter_by(matricula=matricula).first()
                preview_context = NotificationTemplateService.sample_context()
                if usuario:
                    preview_context["employee_name"] = usuario.nome or preview_context["employee_name"]
                    preview_context["employee_id"] = usuario.matricula or preview_context["employee_id"]
                preview_message = NotificationTemplateService.render(
                    template_kind,
                    preview_context,
                    model_id=selected_model_id,
                )
                result = TelegramService.send_message(str(telegram_user.chat_id), preview_message)
                if result.get("success"):
                    flash("Preview do modelo enviado ao Telegram.", "success")
                else:
                    flash(f"Falha ao enviar preview: {result.get('error')}", "danger")
            else:
                flash("Ação de editor não reconhecida.", "warning")
        except ValueError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("config.editor_notificacoes", model=selected_model_id))

    selected_model = NotificationTemplateService.get_model(selected_model_id) or models[0]

    def _safe_preview(kind: str) -> str:
        try:
            return NotificationTemplateService.render(kind, NotificationTemplateService.sample_context(), model_id=selected_model_id)
        except Exception as exc:
            return f"Erro ao renderizar preview: {exc}"

    return render_template(
        "config_notification_editor.html",
        models=models,
        selected_model=selected_model,
        rotation=rotation,
        preview_user=_safe_preview("user"),
        preview_supervisor=_safe_preview("supervisor"),
        preview_supervisor_batch=_safe_preview("supervisor_batch"),
        usuarios=Usuario.query.order_by(Usuario.nome.asc()).all(),
    )


@bp.route("/preview-cabecalho")
@login_required
def preview_cabecalho():
    """Preview do cabeçalho do relatório."""
    if not current_user.is_admin:
        return jsonify({"error": "Acesso negado"}), 403
    
    try:
        cabecalho = ConfigService.render_cabecalho()
        return jsonify({"cabecalho": cabecalho})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/preview-rodape")
@login_required
def preview_rodape():
    """Preview do rodapé do relatório."""
    if not current_user.is_admin:
        return jsonify({"error": "Acesso negado"}), 403
    
    try:
        rodape = ConfigService.render_rodape(pagina=1)
        return jsonify({"rodape": rodape})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/resetar-templates", methods=["POST"])
@login_required
def resetar_templates():
    """Reseta templates para valores padrão."""
    if not current_user.is_admin:
        return jsonify({"error": "Acesso negado"}), 403
    
    try:
        data = {
            "cabecalho_template": ConfigService.CABECALHO_PADRAO,
            "rodape_template": ConfigService.RODAPE_PADRAO,
        }
        ConfigService.update_relatorio_config(data)
        
        return jsonify({
            "success": True,
            "message": "Templates resetados para valores padrão!"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/estoque/ajuste-admin", methods=["GET", "POST"])
@login_required
def estoque_ajuste_admin():
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem alterar saldos por esta porta administrativa.", "danger")
        return redirect(url_for("dashboard.index"))

    selected_code = (request.values.get("codigo") or "").strip()
    preview = None
    adjustment_form = request.form.to_dict() if request.method == "POST" else {}

    if request.method == "POST":
        motivo = (request.form.get("motivo") or "").strip()
        user_id = str(getattr(current_user, "matricula", "") or getattr(current_user, "id", ""))
        audit_context = _build_admin_adjustment_audit_context(
            codigo=selected_code,
            novo_saldo=None,
            motivo=motivo,
        )
        try:
            result = inventory_service.apply_admin_item_adjustments(
                codigo_atual=selected_code,
                novo_codigo=request.form.get("novo_codigo"),
                novo_saldo=request.form.get("novo_saldo"),
                adjustment_payload=adjustment_form,
                matricula=user_id,
                motivo=motivo,
                audit_context=audit_context,
            )
            flash(result.get("message") or "Ajustes administrativos aplicados.", "success" if result.get("changed") else "info")
            return redirect(url_for("config.estoque_ajuste_admin", codigo=result.get("codigo_atual") or selected_code))
        except ValueError as exc:
            flash(str(exc), "danger")
        except Exception as exc:
            flash("Erro interno ao aplicar os ajustes administrativos.", "danger")

    if selected_code:
        try:
            preview = inventory_service.get_admin_balance_snapshot(selected_code)
            if preview is not None and not preview.get("admin_balance_input"):
                preview["admin_balance_input"] = inventory_service.build_admin_balance_input_fallback(preview)
        except ValueError as exc:
            if request.method == "GET":
                flash(str(exc), "danger")

    return render_template(
        "config/estoque_admin.html",
        preview=preview,
        preview_code=selected_code,
        adjustment_form=adjustment_form,
        recent_adjustments=inventory_service.list_recent_admin_balance_adjustments(limit=12),
    )
