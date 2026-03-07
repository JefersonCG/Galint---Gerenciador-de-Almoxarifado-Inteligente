"""Views para configuração do sistema Telegram."""
from __future__ import annotations

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for, jsonify
from flask_login import login_required

from ..extensions import db
from sqlalchemy import exc as sa_exc
from ..models import (
    TelegramConfig,
    TelegramConversation,
    TelegramGroup,
    TelegramNotification,
    TelegramNotificationPreferences,
    TelegramUser,
    Usuario,
    Saida,
    Item,
)
from ..services.telegram_service import TelegramService

logger = logging.getLogger(__name__)

bp = Blueprint("telegram_config", __name__, url_prefix="/configuracoes/telegram")


@bp.route("/")
@login_required
def index():
    """Página principal de configuração do Telegram."""
    try:
        telegram_config = TelegramConfig.query.first()
        if not telegram_config:
            telegram_config = TelegramConfig()
            db.session.add(telegram_config)
            db.session.commit()
    except sa_exc.ProgrammingError:
        # Banco de dados sem as colunas novas (migração pendente).
        db.session.rollback()
        telegram_config = TelegramConfig()
        flash(
            "AVISO: o esquema do banco de dados parece desatualizado. Execute as migrações.",
            "warning",
        )

    telegram_users = TelegramUser.query.join(Usuario).all()
    groups = TelegramGroup.query.all()
    
    # Usuários sem Telegram vinculado
    usuarios_sem_telegram = (
        Usuario.query.outerjoin(TelegramUser, Usuario.matricula == TelegramUser.matricula)
        .filter(TelegramUser.id.is_(None))
        .all()
    )

    return render_template(
        "telegram/config.html",
        telegram_config=telegram_config,
        telegram_users=telegram_users,
        groups=groups,
        usuarios_sem_telegram=usuarios_sem_telegram,
    )


@bp.route("/update-config", methods=["POST"])
@login_required
def update_config():
    """Atualiza configurações gerais do Telegram."""
    telegram_config = TelegramConfig.query.first()
    if not telegram_config:
        telegram_config = TelegramConfig()
        db.session.add(telegram_config)

    telegram_config.bot_token = request.form.get("bot_token", "").strip() or None
    telegram_config.enabled = request.form.get("enabled") == "on"
    telegram_config.notify_on_withdrawal = request.form.get("notify_on_withdrawal") == "on"
    telegram_config.notify_supervisors = request.form.get("notify_supervisors") == "on"
    telegram_config.alert_weekday_time = request.form.get("alert_weekday_time", "16:20")
    telegram_config.alert_saturday_time = request.form.get("alert_saturday_time", "11:00")
    telegram_config.alert_enabled = request.form.get("alert_enabled") == "on"

    try:
        db.session.commit()
        flash("Configurações atualizadas com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao salvar configurações: {e}", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/test-connection")
@login_required
def test_connection():
    """Testa conexão com o bot do Telegram."""
    result = TelegramService.test_connection()
    
    if result["success"]:
        flash(
            f"✅ Bot conectado! Username: @{result['bot_username']}, Nome: {result['bot_name']}",
            "success",
        )
    else:
        flash(f"❌ Erro ao conectar: {result['error']}", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/configurar-webhook", methods=["POST"])
@login_required
def configurar_webhook():
    """Configura webhook para respostas em português."""
    webhook_url = request.form.get("webhook_url", "").strip()
    
    if not webhook_url:
        flash("URL do webhook é obrigatória!", "danger")
        return redirect(url_for("telegram_config.index"))
    
    # Adicionar /configuracoes/telegram/webhook ao final se não tiver
    if not webhook_url.endswith("/webhook"):
        webhook_url = webhook_url.rstrip("/") + "/configuracoes/telegram/webhook"
    
    result = TelegramService.set_webhook(webhook_url)
    
    if result["success"]:
        flash(f"✅ Webhook configurado! Bot agora responde em português.", "success")
    else:
        flash(f"❌ Erro ao configurar webhook: {result['error']}", "danger")
    
    return redirect(url_for("telegram_config.index"))


@bp.route("/remover-webhook")
@login_required
def remover_webhook():
    """Remove webhook do Telegram."""
    result = TelegramService.delete_webhook()
    
    if result["success"]:
        flash("✅ Webhook removido!", "success")
    else:
        flash(f"❌ Erro ao remover webhook: {result['error']}", "danger")
    
    return redirect(url_for("telegram_config.index"))


@bp.route("/vincular-usuario", methods=["POST"])
@login_required
def vincular_usuario():
    """Vincula chat_id do Telegram a um usuário."""
    matricula = request.form.get("matricula", "").strip()
    chat_id = request.form.get("chat_id", "").strip()
    celular = request.form.get("celular", "").strip() or None

    if not matricula or not chat_id or not celular:
        flash("Matrícula, Chat ID e Celular são obrigatórios!", "danger")
        return redirect(url_for("telegram_config.index"))

    # Verificar se usuário existe
    usuario = Usuario.query.get(matricula)
    if not usuario:
        flash(f"Usuário com matrícula {matricula} não encontrado!", "danger")
        return redirect(url_for("telegram_config.index"))

    # Verificar se já existe vinculação
    existing = TelegramUser.query.filter_by(matricula=matricula).first()
    if existing:
        existing.chat_id = chat_id
        existing.celular = celular
        existing.enabled = True
        flash(f"Vinculação atualizada para {usuario.nome}!", "success")
    else:
        telegram_user = TelegramUser(matricula=matricula, chat_id=chat_id, celular=celular, enabled=True)
        db.session.add(telegram_user)
        db.session.flush()  # Para obter o ID antes de criar preferências
        
        # Criar preferências padrão (todas ativas)
        preferences = TelegramNotificationPreferences(telegram_user_id=telegram_user.id)
        db.session.add(preferences)
        
        flash(f"Usuário {usuario.nome} vinculado com sucesso!", "success")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao vincular usuário: {e}", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/desvincular-usuario/<int:user_id>")
@login_required
def desvincular_usuario(user_id: int):
    """Desvincula usuário do Telegram."""
    telegram_user = TelegramUser.query.get(user_id)
    if telegram_user:
        db.session.delete(telegram_user)
        db.session.commit()
        flash("Usuário desvinculado!", "success")
    else:
        flash("Usuário não encontrado!", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/preferencias/<int:telegram_user_id>")
@login_required
def preferencias_notificacoes(telegram_user_id: int):
    """Página para configurar preferências de notificações por categoria."""
    telegram_user = TelegramUser.query.get_or_404(telegram_user_id)
    
    # Buscar ou criar preferências
    preferences = telegram_user.notification_preferences
    if not preferences:
        preferences = TelegramNotificationPreferences(telegram_user_id=telegram_user.id)
        db.session.add(preferences)
        db.session.commit()
    
    # Categorias disponíveis com seus nomes exibidos
    categorias = [
        {"key": "ferramenta", "label": "Ferramentas"},
        {"key": "limpeza", "label": "Limpeza"},
        {"key": "eletrico", "label": "Elétrico"},
        {"key": "hidraulico", "label": "Hidráulico"},
        {"key": "construcao", "label": "Construção"},
        {"key": "pintura", "label": "Mat. Pintura e Drywall"},
        {"key": "piscina", "label": "Piscina"},
        {"key": "epi", "label": "EPIs"},
    ]
    
    return render_template(
        "telegram/notification_preferences.html",
        telegram_user=telegram_user,
        preferences=preferences,
        categorias=categorias,
    )


@bp.route("/preferencias/<int:telegram_user_id>/salvar", methods=["POST"])
@login_required
def salvar_preferencias(telegram_user_id: int):
    """Salva preferências de notificações."""
    telegram_user = TelegramUser.query.get_or_404(telegram_user_id)
    
    # Buscar ou criar preferências
    preferences = telegram_user.notification_preferences
    if not preferences:
        preferences = TelegramNotificationPreferences(telegram_user_id=telegram_user.id)
        db.session.add(preferences)
    
    # Categorias a processar
    categorias = ["ferramenta", "limpeza", "eletrico", "hidraulico", "construcao", "pintura", "piscina", "epi"]
    
    # Atualizar preferências baseado nos checkboxes
    for categoria in categorias:
        # Retirada
        field_withdrawal = f"notify_{categoria}_withdrawal"
        value_withdrawal = request.form.get(f"{categoria}_withdrawal") == "on"
        setattr(preferences, field_withdrawal, value_withdrawal)
        
        # Devolução
        field_return = f"notify_{categoria}_return"
        value_return = request.form.get(f"{categoria}_return") == "on"
        setattr(preferences, field_return, value_return)
    
    try:
        db.session.commit()
        flash(f"✅ Preferências de {telegram_user.usuario.nome} atualizadas com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao salvar preferências: {e}")
        flash(f"❌ Erro ao salvar preferências: {e}", "danger")
    
    return redirect(url_for("telegram_config.preferencias_notificacoes", telegram_user_id=telegram_user_id))


@bp.route("/toggle-usuario/<int:user_id>")
@login_required
def toggle_usuario(user_id: int):
    """Ativa/desativa notificações para um usuário."""
    telegram_user = TelegramUser.query.get(user_id)
    if telegram_user:
        telegram_user.enabled = not telegram_user.enabled
        db.session.commit()
        status = "ativado" if telegram_user.enabled else "desativado"
        flash(f"Usuário {status}!", "success")
    else:
        flash("Usuário não encontrado!", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/usuario/<int:user_id>/toggle-withdrawal", methods=["POST"])
@login_required
def toggle_withdrawal_permission(user_id: int):
    """Ativa/desativa permissão de retirada via Telegram para um usuário (AJAX)."""
    try:
        telegram_user = TelegramUser.query.get(user_id)
        if not telegram_user:
            return jsonify({"success": False, "error": "Usuário não encontrado"}), 404
        
        # Obter valor do request JSON
        data = request.get_json()
        can_withdraw = data.get("can_withdraw", False)
        
        # Atualizar permissão
        telegram_user.can_withdraw_via_telegram = can_withdraw
        db.session.commit()
        
        usuario_nome = telegram_user.usuario.nome if telegram_user.usuario else "Usuário"
        status_msg = "habilitadas" if can_withdraw else "desabilitadas"
        
        return jsonify({
            "success": True,
            "message": f"Retiradas via Telegram {status_msg} para {usuario_nome}",
            "can_withdraw": can_withdraw
        })
        
    except Exception as e:
        db.session.rollback()
        logger.exception(f"Erro ao atualizar permissão de retirada: {e}")
        return jsonify({
            "success": False,
            "error": f"Erro ao atualizar permissão: {str(e)}"
        }), 500


@bp.route("/usuario/<int:user_id>/toggle-item-create", methods=["POST"])
@login_required
def toggle_item_create_permission(user_id: int):
    """Ativa/desativa permissão de cadastro de item via Telegram para um usuário (AJAX)."""
    try:
        telegram_user = TelegramUser.query.get(user_id)
        if not telegram_user:
            return jsonify({"success": False, "error": "Usuário não encontrado"}), 404

        data = request.get_json()
        can_create_item = data.get("can_create_item", False)

        telegram_user.can_create_item_via_telegram = can_create_item
        db.session.commit()

        usuario_nome = telegram_user.usuario.nome if telegram_user.usuario else "Usuário"
        status_msg = "habilitado" if can_create_item else "desabilitado"

        return jsonify({
            "success": True,
            "message": f"Cadastro via Telegram {status_msg} para {usuario_nome}",
            "can_create_item": can_create_item
        })

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Erro ao atualizar permissão de cadastro: {e}")
        return jsonify({
            "success": False,
            "error": f"Erro ao atualizar permissão: {str(e)}"
        }), 500


@bp.route("/adicionar-grupo", methods=["POST"])
@login_required
def adicionar_grupo():
    """Adiciona grupo do Telegram."""
    chat_id = request.form.get("chat_id", "").strip()
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None

    if not chat_id or not name:
        flash("Chat ID e Nome são obrigatórios!", "danger")
        return redirect(url_for("telegram_config.index"))

    # Verificar se já existe
    existing = TelegramGroup.query.filter_by(chat_id=chat_id).first()
    if existing:
        flash("Grupo já cadastrado!", "warning")
        return redirect(url_for("telegram_config.index"))

    group = TelegramGroup(
        chat_id=chat_id,
        name=name,
        description=description,
        enabled=True,
        receive_withdrawals=True,
        receive_alerts=True,
    )
    db.session.add(group)

    try:
        db.session.commit()
        flash(f"Grupo {name} adicionado com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao adicionar grupo: {e}", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/remover-grupo/<int:group_id>")
@login_required
def remover_grupo(group_id: int):
    """Remove grupo do Telegram."""
    group = TelegramGroup.query.get(group_id)
    if group:
        db.session.delete(group)
        db.session.commit()
        flash("Grupo removido!", "success")
    else:
        flash("Grupo não encontrado!", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/toggle-grupo/<int:group_id>")
@login_required
def toggle_grupo(group_id: int):
    """Ativa/desativa notificações para um grupo."""
    group = TelegramGroup.query.get(group_id)
    if group:
        group.enabled = not group.enabled
        db.session.commit()
        status = "ativado" if group.enabled else "desativado"
        flash(f"Grupo {status}!", "success")
    else:
        flash("Grupo não encontrado!", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/enviar-teste", methods=["POST"])
@login_required
def enviar_teste():
    """Envia mensagem de teste."""
    chat_id = request.form.get("chat_id", "").strip()
    message = request.form.get("message", "").strip()

    if not chat_id or not message:
        flash("Chat ID e mensagem são obrigatórios!", "danger")
        return redirect(url_for("telegram_config.index"))

    result = TelegramService.send_message(chat_id, message)

    # Registrar no histórico
    notification = TelegramNotification(
        chat_id=chat_id,
        recipient_name="Teste manual",
        message_type="test",
        message_text=message,
        status="sent" if result["success"] else "failed",
        error_message=result.get("error"),
    )
    db.session.add(notification)
    db.session.commit()

    if result["success"]:
        flash("Mensagem enviada com sucesso!", "success")
    else:
        flash(f"Erro ao enviar mensagem: {result['error']}", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/executar-alerta")
@login_required
def executar_alerta():
    """Executa alerta agendado manualmente."""
    result = TelegramService.send_scheduled_alerts()

    if result["success"]:
        flash(
            f"Alerta executado! {result['total_sent']} enviados, {result['total_failed']} falhas",
            "success",
        )
    else:
        flash(f"Erro ao executar alerta: {result['error']}", "danger")

    return redirect(url_for("telegram_config.index"))


@bp.route("/historico")
@login_required
def historico():
    """Exibe histórico de notificações."""
    page = request.args.get("page", 1, type=int)
    per_page = 50

    notifications = (
        TelegramNotification.query.order_by(TelegramNotification.sent_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template("telegram/historico.html", notifications=notifications)

@bp.route("/webhook", methods=["POST"])
def webhook():
    """Processa atualizações do Telegram (webhook)."""
    try:
        update = request.get_json()
        # Suporte básico a callback_query (inline buttons)
        callback = update.get("callback_query") if isinstance(update, dict) else None
        if callback:
            data = callback.get("data")
            chat_id = callback.get("message", {}).get("chat", {}).get("id")
            if not chat_id:
                return jsonify({"ok": True})
            chat_id_str = str(chat_id)

            try:
                # Respostas leves/confirmatórias para permitir que botões funcionem
                if data == "retiradas_ferramentas":
                    count = Saida.query.count()
                    TelegramService.send_message(chat_id_str, f"Resumo de retiradas (ferramentas): {count} registros (ver painel).")
                    return jsonify({"ok": True})

                if data == "retiradas_materiais":
                    count = Saida.query.count()
                    TelegramService.send_message(chat_id_str, f"Resumo de retiradas (materiais): {count} registros.")
                    return jsonify({"ok": True})

                if data == "baixar_estoque_baixo":
                    # Enviar resposta simples e instrução (geração de CSV disponível via painel)
                    low_count = 0
                    try:
                        items = Item.query.all()
                        for it in items:
                            try:
                                saldo = it.get_saldo_fisico_display()
                            except Exception:
                                saldo = 0
                            minimo = it.estoque_minimo or 0
                            if saldo <= minimo:
                                low_count += 1
                    except Exception:
                        low_count = 0

                    TelegramService.send_message(chat_id_str, f"Relatório de estoque baixo: {low_count} itens. Gere o relatório no painel de configurações se precisar do CSV.")
                    return jsonify({"ok": True})

                # Demais callbacks (período/categoria/formato/menus)
                TelegramService.handle_callback_query(callback)
                return jsonify({"ok": True})

            except Exception as e:
                logger.exception("Erro ao processar callback_query no webhook de config")
                return jsonify({"ok": False, "error": str(e)}), 500
        
        # Extrair mensagem
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        first_name = message.get("from", {}).get("first_name", "Usuário")
        
        if not chat_id or not text:
            return jsonify({"ok": True})
        
        chat_id_str = str(chat_id)

        # Processar textos do menu (relatórios e outros)
        try:
            if TelegramService.handle_menu_text(chat_id_str, text):
                return jsonify({"ok": True})
        except Exception:
            logger.exception("Erro ao processar menu do Telegram")
        
        # Verificar se usuário já está vinculado
        existing_user = TelegramUser.query.filter_by(chat_id=chat_id_str).first()
        if existing_user:
            response_text = (
                f"✅ <b>Você já está cadastrado!</b>\n\n"
                f"👤 Nome: <b>{existing_user.usuario.nome}</b>\n"
                f"🆔 Matrícula: <code>{existing_user.matricula}</code>\n"
                f"💼 Cargo: {existing_user.usuario.cargo or 'Não informado'}\n\n"
                f"🔔 Você já recebe notificações automáticas!"
            )
            TelegramService.send_message(chat_id_str, response_text)
            return jsonify({"ok": True})
        
        # Processar comando /start - inicia conversa
        # Deep link do Telegram vira: "/start <payload>" (ex: /start ALMOXARIFADO)
        if text.lower().startswith("/start"):
            parts = text.split(maxsplit=1)
            start_payload = parts[1].strip() if len(parts) > 1 else None

            # Criar ou resetar conversa
            conversation = TelegramConversation.query.get(chat_id_str)
            if conversation:
                db.session.delete(conversation)
            
            conversation = TelegramConversation(
                chat_id=chat_id_str,
                state="awaiting_name"
            )
            db.session.add(conversation)
            db.session.commit()
            
            origem = (
                f"\n\n🔗 <b>Origem do link:</b> <code>{start_payload}</code>"
                if start_payload
                else ""
            )

            response_text = (
                f"👋 <b>Olá, {first_name}!</b>\n\n"
                f"Sou o assistente do <b>GALINT - Sistema de Almoxarifado</b>.{origem}\n\n"
                f"Vou te ajudar a se cadastrar automaticamente! 🚀\n\n"
                f"📝 <b>Por favor, digite seu nome completo:</b>\n"
                f"<i>(exatamente como está cadastrado no sistema)</i>"
            )
            TelegramService.send_message(chat_id_str, response_text)
            return jsonify({"ok": True})
        
        # Processar comando /ajuda
        if text.lower() in ["/ajuda", "/help"]:
            response_text = (
                f"📚 <b>Ajuda - GALINT Bot</b>\n\n"
                f"<b>Comandos disponíveis:</b>\n"
                f"/start - Iniciar cadastro automático\n"
                f"/ajuda - Mostrar esta mensagem\n"
                f"/meuid - Ver seu Chat ID\n\n"
                f"<b>Sobre as notificações:</b>\n"
                f"• Você receberá alertas quando retirar materiais\n"
                f"• Alertas a cada 4h para devolução de ferramentas (custódia diária)\n\n"
                f"💡 Dúvidas? Contate o administrador do sistema."
            )
            TelegramService.send_message(chat_id_str, response_text)
            return jsonify({"ok": True})
        
        # Processar comando /meuid
        if text.lower() == "/meuid":
            response_text = (
                f"🆔 <b>Seu Chat ID:</b> <code>{chat_id}</code>\n\n"
                f"Copie este código e envie ao administrador para vincular sua conta manualmente."
            )
            TelegramService.send_message(chat_id_str, response_text)
            return jsonify({"ok": True})
        
        # Processar conversa em andamento
        conversation = TelegramConversation.query.get(chat_id_str)
        if conversation:
            if conversation.state == "awaiting_name":
                # Salvar nome e pedir cargo
                conversation.nome_informado = text
                conversation.state = "awaiting_cargo"
                db.session.commit()
                
                response_text = (
                    f"✅ Nome registrado: <b>{text}</b>\n\n"
                    f"💼 <b>Agora digite sua função/cargo:</b>\n"
                    f"<i>(ex: Eletricista, Pedreiro, Auxiliar, Supervisor, etc.)</i>"
                )
                TelegramService.send_message(chat_id_str, response_text)
                return jsonify({"ok": True})
            
            elif conversation.state == "awaiting_cargo":
                # Salvar cargo e buscar no banco
                conversation.cargo_informado = text
                conversation.state = "completed"
                db.session.commit()
                
                # Buscar usuário no banco de dados
                nome_busca = conversation.nome_informado.strip()
                cargo_busca = text.strip()
                
                # Busca flexível: nome parcial (case insensitive)
                candidatos = Usuario.query.filter(
                    Usuario.nome.ilike(f"%{nome_busca}%")
                ).all()
                
                # Se informou cargo, filtrar por ele também (se houver no banco)
                if candidatos and cargo_busca:
                    # Primeiro tenta filtrar por cargo exato
                    candidatos_com_cargo = [
                        u for u in candidatos 
                        if u.cargo and cargo_busca.lower() in u.cargo.lower()
                    ]
                    # Se não achar nenhum com cargo, mantém todos os candidatos
                    # (pode ser que o cargo não esteja preenchido no cadastro)
                    if candidatos_com_cargo:
                        candidatos = candidatos_com_cargo
                
                if len(candidatos) == 1:
                    # Match único! Vincular automaticamente
                    usuario = candidatos[0]
                    
                    # Criar vinculação
                    telegram_user = TelegramUser(
                        matricula=usuario.matricula,
                        chat_id=chat_id_str,
                        enabled=True
                    )
                    db.session.add(telegram_user)
                    db.session.flush()  # Para obter ID
                    
                    # Criar preferências padrão (todas ativas)
                    preferences = TelegramNotificationPreferences(telegram_user_id=telegram_user.id)
                    db.session.add(preferences)
                    
                    db.session.delete(conversation)
                    db.session.commit()
                    
                    response_text = (
                        f"🎉 <b>Cadastro realizado com sucesso!</b>\n\n"
                        f"✅ Você foi vinculado automaticamente:\n\n"
                        f"👤 Nome: <b>{usuario.nome}</b>\n"
                        f"🆔 Matrícula: <code>{usuario.matricula}</code>\n"
                        f"💼 Cargo informado: {cargo_busca}\n"
                        f"🏢 Setor: {usuario.setor or 'Não informado'}\n\n"
                        f"🔔 A partir de agora você receberá:\n"
                        f"• Notificações de retirada de materiais\n"
                        f"• Lembretes de devolução de ferramentas\n\n"
                        f"✨ Tudo pronto! Não precisa fazer mais nada."
                    )
                    TelegramService.send_message(chat_id_str, response_text)
                    
                elif len(candidatos) > 1:
                    # Múltiplos matches - pedir para administrador
                    lista_candidatos = "\n".join([
                        f"• {u.nome} - {u.cargo or 'Sem cargo'} (Mat: {u.matricula})"
                        for u in candidatos[:5]
                    ])
                    
                    response_text = (
                        f"⚠️ <b>Encontrei múltiplos cadastros similares:</b>\n\n"
                        f"{lista_candidatos}\n\n"
                        f"Por favor, entre em contato com o administrador do sistema "
                        f"e informe:\n\n"
                        f"🆔 <b>Seu Chat ID:</b> <code>{chat_id}</code>\n"
                        f"📝 Nome: {nome_busca}\n"
                        f"💼 Cargo: {cargo_busca}\n\n"
                        f"O administrador fará a vinculação manual."
                    )
                    TelegramService.send_message(chat_id_str, response_text)
                    db.session.delete(conversation)
                    db.session.commit()
                    
                else:
                    # Nenhum match - pedir para administrador
                    response_text = (
                        f"❌ <b>Não encontrei seu cadastro no sistema.</b>\n\n"
                        f"Verifique se digitou corretamente:\n"
                        f"📝 Nome: <b>{nome_busca}</b>\n"
                        f"💼 Cargo: <b>{cargo_busca}</b>\n\n"
                        f"Se os dados estão corretos, entre em contato com o "
                        f"administrador e informe:\n\n"
                        f"🆔 <b>Seu Chat ID:</b> <code>{chat_id}</code>\n\n"
                        f"💡 <i>Você pode tentar novamente enviando /start</i>"
                    )
                    TelegramService.send_message(chat_id_str, response_text)
                    db.session.delete(conversation)
                    db.session.commit()
                
                return jsonify({"ok": True})
        
        # Mensagem não reconhecida
        return jsonify({"ok": True})
    
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500