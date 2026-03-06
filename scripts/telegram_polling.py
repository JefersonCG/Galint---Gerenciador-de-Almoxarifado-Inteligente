"""Script para rodar bot Telegram em modo polling (sem webhook).

Execute este script em paralelo ao Flask para processar mensagens do Telegram.

Observação importante:
- Polling e Webhook NÃO podem ficar ativos ao mesmo tempo no Telegram.
- Por padrão, este script remove o webhook ao iniciar para evitar conflito.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramConfig, TelegramConversation, TelegramUser, Usuario
from galint_flask.services.telegram_service import TelegramService
from galint_flask.models import Item
from pathlib import Path


def _load_last_update_id(offset_file: Path) -> int:
    try:
        if not offset_file.exists():
            return 0
        content = offset_file.read_text(encoding="utf-8").strip()
        return int(content) if content else 0
    except Exception:
        return 0


def _save_last_update_id(offset_file: Path, last_update_id: int) -> None:
    try:
        offset_file.parent.mkdir(parents=True, exist_ok=True)
        offset_file.write_text(str(int(last_update_id)), encoding="utf-8")
    except Exception:
        # Evita derrubar o polling por falha de IO
        pass

def process_message(message):
    """Processa uma mensagem do Telegram."""
    chat_id = message.get("chat", {}).get("id")
    first_name = message.get("from", {}).get("first_name", "Usuário")
    
    if not chat_id:
        return
    
    chat_id_str = str(chat_id)

    photo_sizes = message.get("photo") or []
    if photo_sizes:
        TelegramService.handle_photo(chat_id_str, photo_sizes)
        return

    text = message.get("text", "").strip()
    if not text:
        return
    
    print(f"📩 Mensagem de {first_name} (chat_id={chat_id_str}): {text}")

    # Se estiver em cadastro de item, priorizar fluxo de conversação
    try:
        if TelegramService.is_item_create_active(chat_id_str):
            TelegramService.handle_menu_text(chat_id_str, text)
            return
    except Exception:
        pass
    
    # Verificar se usuário já está vinculado
    existing_user = TelegramUser.query.filter_by(chat_id=chat_id_str).first()
    if existing_user:
        # Usuário já vinculado — permitir comandos e opções de menu.
        user = None
        try:
            user = existing_user.usuario
        except Exception:
            user = None

        lower_text = text.lower().strip()

        # Para usuários vinculados, /start e "menu" apenas reexibem o menu.
        if lower_text.startswith("/start") or lower_text in ("menu", "/menu", "/inicio"):
            try:
                if user and getattr(user, "is_admin", 0) == 1:
                    TelegramService.send_admin_menu(chat_id_str)
                elif user and user.setor and user.setor.upper() in ("ZELADORES", "SUPERVISORES", "ENCARREGADOS"):
                    TelegramService.send_sector_menu(chat_id_str, setor=user.setor)
                elif user:
                        TelegramService.send_user_menu(chat_id_str)
                else:
                    TelegramService.send_message(chat_id_str, "✅ Você já está cadastrado!")
                print(f"✅ Menu reenviado para usuário já cadastrado: {existing_user.matricula}")
            except Exception:
                TelegramService.send_message(chat_id_str, "✅ Você já está cadastrado!")
            return

        # Comandos rápidos continuam disponíveis para usuários vinculados.
        if lower_text in ["/ajuda", "/help"]:
            response_text = (
                f"📚 <b>Ajuda - GALINT Bot</b>\n\n"
                f"<b>Comandos disponíveis:</b>\n"
                f"/start - Mostrar menu\n"
                f"/ajuda - Mostrar esta mensagem\n"
                f"/meuid - Ver seu Chat ID\n\n"
                f"💡 Dica: use os botões do menu para acessar relatórios/planilhas." 
            )
            TelegramService.send_message(chat_id_str, response_text)
            return

        if lower_text.startswith("/scanear") or text.strip() == "📸 Escanear Código":
            TelegramService.handle_command_scanear(chat_id_str)
            return

        if lower_text == "/meuid":
            response_text = (
                f"🆔 <b>Seu Chat ID:</b> <code>{chat_id}</code>\n\n"
                f"Copie este código e envie ao administrador para vincular sua conta manualmente."
            )
            TelegramService.send_message(chat_id_str, response_text)
            return

        if lower_text.startswith(("/estoque", "/stock")):
            parts = text.split(maxsplit=1)
            if len(parts) == 1:
                TelegramService.send_message(chat_id_str, "Use: /estoque <codigo ou parte da descrição>")
                return
            term = parts[1].strip()
            itens = Item.query.filter(
                (Item.codigo_item == term) | (Item.descricao.ilike(f"%{term}%"))
            ).limit(10).all()
            if not itens:
                TelegramService.send_message(chat_id_str, f"❌ Nenhum item encontrado para: {term}")
                return
            msgs = []
            for it in itens:
                try:
                    saldo = it.get_saldo_atual()
                except Exception:
                    saldo = "N/A"
                msgs.append(f"• {it.codigo_item} — {it.descricao} — Saldo: {saldo}")
            TelegramService.send_message(chat_id_str, "\n".join(msgs))
            return

        if lower_text.startswith("/relatorios"):
            reports_dir = Path("instance") / "reports"
            if not reports_dir.exists():
                TelegramService.send_message(chat_id_str, "Nenhum relatório disponível no servidor.")
                return
            files = [p.name for p in reports_dir.iterdir() if p.is_file()]
            if not files:
                TelegramService.send_message(chat_id_str, "Nenhum relatório encontrado em instance/reports.")
                return
            msg = "📄 Relatórios disponíveis:\n" + "\n".join(files[:50])
            TelegramService.send_message(chat_id_str, msg)
            return
        
        # Tentar interpretar como código de barras digitado manualmente
        # Se for curto (ex: até 20 chars) e não começar com barra /
        if len(text) <= 20 and not text.startswith("/"):
            # Verificar se parece código (letras e números apenas)
            if not any(c in text for c in "<>[]{}") and len(text) > 2:
                TelegramService.handle_barcode_text(chat_id_str, text)
                return

        # Delegar opções de menu/teclado ao TelegramService (ex.: ReplyKeyboard).
        try:
            handled = TelegramService.handle_menu_text(chat_id_str, text)
            if handled:
                return
        except Exception as e:
            print(f"❌ Erro ao processar menu (chat_id={chat_id_str}): {e}")
            try:
                TelegramService.send_message(chat_id_str, "❌ Ocorreu um erro ao processar sua solicitação. Tente novamente.")
            except Exception:
                pass
            return

        # Fallback: não exibir "comando não reconhecido".
        # Para usuários vinculados, apenas reenvia o menu adequado.
        try:
            if user and getattr(user, "is_admin", 0) == 1:
                TelegramService.send_admin_menu(chat_id_str)
            elif user and user.setor and str(user.setor).upper() in ("ZELADORES", "SUPERVISORES", "ENCARREGADOS"):
                TelegramService.send_sector_menu(chat_id_str, setor=user.setor)
            elif user:
                TelegramService.send_user_menu(chat_id_str)
            else:
                TelegramService.send_message(chat_id_str, "Envie /start para ver o menu.", parse_mode=None)
        except Exception:
            pass
        return
    
    # Processar comando /start - inicia conversa
    # Deep link do Telegram vira: "/start <payload>" (ex: /start ALMOXARIFADO)
    if text.lower().startswith("/start"):
        parts = text.split(maxsplit=1)
        start_payload = parts[1].strip() if len(parts) > 1 else None

        # Criar ou resetar conversa
        conversation = TelegramConversation.query.get(chat_id_str)
        if conversation:
            db.session.delete(conversation)

        conversation = TelegramConversation()
        conversation.chat_id = chat_id_str
        conversation.state = "awaiting_name"
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
        print(f"✅ Resposta enviada: aguardando nome")
        # Notificar administradores sobre novo cadastro em andamento
        try:
            admins = (
                TelegramUser.query.join(Usuario)
                .filter(Usuario.is_admin == 1, TelegramUser.enabled == True)
                .all()
            )
            for adm in admins:
                TelegramService.send_message(
                    adm.chat_id,
                    f"🔔 Novo cadastro iniciado:\n👤 Nome: {first_name} (chat_id: {chat_id_str})\nOrigem: {start_payload or '-'}",
                )
        except Exception:
            pass
        return
    
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
            f"• Lembretes diários para devolução de ferramentas\n"
            f"• Seg-Sex às 16:20 / Sáb às 11:00\n\n"
            f"💡 Dúvidas? Contate o administrador do sistema."
        )
        TelegramService.send_message(chat_id_str, response_text)
        print(f"✅ Resposta enviada: ajuda")
        return

    if text.lower().startswith("/scanear"):
        TelegramService.handle_command_scanear(chat_id_str)
        return
    
    # Processar comando /meuid
    if text.lower() == "/meuid":
        response_text = (
            f"🆔 <b>Seu Chat ID:</b> <code>{chat_id}</code>\n\n"
            f"Copie este código e envie ao administrador para vincular sua conta manualmente."
        )
        TelegramService.send_message(chat_id_str, response_text)
        print(f"✅ Resposta enviada: chat ID")
        return

    # Comandos utilitários: /estoque <codigo|descricao>
    if text.lower().startswith(('/estoque', '/stock')):
        parts = text.split(maxsplit=1)
        if len(parts) == 1:
            TelegramService.send_message(chat_id_str, "Use: /estoque <codigo ou parte da descrição>")
            return
        term = parts[1].strip()
        # buscar por codigo exato ou descricao parcial
        itens = Item.query.filter(
            (Item.codigo_item == term) | (Item.descricao.ilike(f"%{term}%"))
        ).limit(10).all()
        if not itens:
            TelegramService.send_message(chat_id_str, f"❌ Nenhum item encontrado para: {term}")
            return
        msgs = []
        for it in itens:
            try:
                saldo = it.get_saldo_atual()
            except Exception:
                saldo = 'N/A'
            msgs.append(f"• {it.codigo_item} — {it.descricao} — Saldo: {saldo}")
        TelegramService.send_message(chat_id_str, "\n".join(msgs))
        return

    # Comandos de relatórios: /relatorios (lista) e /relatorio <nome>
    if text.lower().startswith('/relatorios'):
        reports_dir = Path('instance') / 'reports'
        if not reports_dir.exists():
            TelegramService.send_message(chat_id_str, "Nenhum relatório disponível no servidor.")
            return
        files = [p.name for p in reports_dir.iterdir() if p.is_file()]
        if not files:
            TelegramService.send_message(chat_id_str, "Nenhum relatório encontrado em instance/reports.")
            return
        msg = "📄 Relatórios disponíveis:\n" + "\n".join(files[:50])
        TelegramService.send_message(chat_id_str, msg)
        return

    if text.lower().startswith('/relatorio'):
        parts = text.split(maxsplit=1)
        if len(parts) == 1:
            TelegramService.send_message(chat_id_str, "Use: /relatorio <nome_arquivo>")
            return
        name = parts[1].strip()
        reports_dir = Path('instance') / 'reports'
        target = reports_dir / name
        if not target.exists() or not target.is_file():
            TelegramService.send_message(chat_id_str, f"Relatório não encontrado: {name}")
            return
        # enviar documento via API
        res = TelegramService.send_document(chat_id_str, str(target), caption=f"Relatório: {name}")
        if not res.get('success'):
            TelegramService.send_message(chat_id_str, f"Erro ao enviar relatório: {res.get('error')}")
        return
    # Delegar opções de menu/teclado ao TelegramService (ex.: opções enviadas via ReplyKeyboard)
    try:
        handled = TelegramService.handle_menu_text(chat_id_str, text)
        if handled:
            return
    except Exception:
        pass
    
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
            print(f"✅ Resposta enviada: aguardando cargo")
            return
        
        elif conversation.state == "awaiting_cargo":
            # Salvar cargo e buscar no banco
            conversation.cargo_informado = text
            conversation.state = "awaiting_celular"
            db.session.commit()
            
            response_text = (
                f"✅ Cargo registrado: <b>{text}</b>\n\n"
                f"📱 <b>Por favor, digite seu número de celular (ex: +5511999998888):</b>"
            )
            TelegramService.send_message(chat_id_str, response_text)
            print(f"✅ Resposta enviada: aguardando celular")
            return

        elif conversation.state == "awaiting_celular":
            # Salvar celular e tentar vincular
            celular_val = text.strip()
            # validação simples: pelo menos 8 dígitos
            digits = "".join(ch for ch in celular_val if ch.isdigit())
            if len(digits) < 8:
                response_text = (
                    f"❌ Número de celular inválido. Digite novamente no formato: +5511999998888"
                )
                TelegramService.send_message(chat_id_str, response_text)
                print(f"⚠️ Recebido celular inválido: {celular_val}")
                return

            conversation.celular_informado = celular_val
            conversation.state = "completed"
            db.session.commit()

            nome_busca = conversation.nome_informado.strip()
            cargo_busca = conversation.cargo_informado.strip() if conversation.cargo_informado else ""
            celular_informado = conversation.celular_informado.strip()

            # Busca flexível: nome parcial (case insensitive)
            candidatos = Usuario.query.filter(
                Usuario.nome.ilike(f"%{nome_busca}%")
            ).all()
            
            # Se informou cargo, filtrar por ele também (se houver no banco)
            if candidatos and cargo_busca:
                candidatos_com_cargo = [
                    u for u in candidatos 
                    if u.cargo and cargo_busca.lower() in u.cargo.lower()
                ]
                if candidatos_com_cargo:
                    candidatos = candidatos_com_cargo
            
            if len(candidatos) == 1:
                # Match único! Vincular automaticamente
                usuario = candidatos[0]
                
                # Criar vinculação
                telegram_user = TelegramUser()
                telegram_user.matricula = usuario.matricula
                telegram_user.chat_id = chat_id_str
                telegram_user.celular = celular_informado
                telegram_user.enabled = True
                db.session.add(telegram_user)
                db.session.delete(conversation)
                db.session.commit()
                
                response_text = (
                    f"🎉 <b>Cadastro realizado com sucesso!</b>\n\n"
                    f"✅ Você foi vinculado automaticamente:\n\n"
                    f"👤 Nome: <b>{usuario.nome}</b>\n"
                    f"🆔 Matrícula: <code>{usuario.matricula}</code>\n"
                    f"💼 Cargo informado: {cargo_busca}\n"
                    f"📱 Celular informado: {celular_informado}\n"
                    f"🏢 Setor: {usuario.setor or 'Não informado'}\n\n"
                    f"🔔 A partir de agora você receberá:\n"
                    f"• Notificações de retirada de materiais\n"
                    f"• Lembretes de devolução de ferramentas\n\n"
                    f"✨ Tudo pronto! Não precisa fazer mais nada."
                )
                TelegramService.send_message(chat_id_str, response_text)
                print(f"✅ VINCULADO: {usuario.nome} ({usuario.matricula})")
                # Enviar menu apropriado após vinculação
                try:
                    if getattr(usuario, 'is_admin', 0) == 1:
                        TelegramService.send_admin_menu(chat_id_str)
                    elif usuario.setor and usuario.setor.upper() in ('ZELADORES', 'SUPERVISORES', 'ENCARREGADOS'):
                        TelegramService.send_sector_menu(chat_id_str, setor=usuario.setor)
                except Exception:
                    pass
                
            elif len(candidatos) > 1:
                # Múltiplos matches
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
                print(f"⚠️ Múltiplos cadastros encontrados")
                
            else:
                # Nenhum match
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
                print(f"❌ Nenhum cadastro encontrado")
            
            return


def main() -> int:
    """Loop principal de polling."""
    parser = argparse.ArgumentParser(description="GALINT Telegram Bot - Polling (sem webhook)")
    parser.add_argument(
        "--keep-webhook",
        action="store_true",
        help="NÃO remove o webhook ao iniciar (não recomendado; pode causar Conflict)",
    )
    parser.add_argument(
        "--offset-file",
        default=str(Path("instance") / "telegram_polling_offset.txt"),
        help="Arquivo para persistir o last_update_id (padrão: instance/telegram_polling_offset.txt)",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=25,
        help="Timeout do long polling (segundos). Padrão: 25",
    )
    args = parser.parse_args()

    app = create_app()
    
    with app.app_context():
        print("🤖 Bot Telegram em modo POLLING iniciado!")

        if not args.keep_webhook:
            res = TelegramService.delete_webhook()
            if res.get("success"):
                print("🧹 Webhook removido (ok). Polling liberado.")
            else:
                print(f"⚠️ Não foi possível remover webhook automaticamente: {res.get('error')}")
                print("Dica: remova o webhook no painel /configuracoes/telegram/.")
        else:
            print("ℹ️ keep-webhook ativo: webhook NÃO será removido.")

        offset_file = Path(args.offset_file)
        last_update_id = _load_last_update_id(offset_file)
        if last_update_id:
            print(f"↩️ Retomando do last_update_id={last_update_id} (arquivo: {offset_file.as_posix()})")

        print("📡 Aguardando mensagens...\n")

        last_error: str | None = None
        backoff_seconds = 2
        
        while True:
            try:
                # Buscar atualizações
                result = TelegramService.get_updates(offset=last_update_id + 1, timeout=args.poll_timeout)

                if not result.get("success"):
                    err = str(result.get("error") or "Erro desconhecido")
                    # Evita spam: só mostra se mudou
                    if err != last_error:
                        print(f"⚠️ getUpdates falhou: {err}")
                        print("Dica: se aparecer 'Conflict', remova o webhook no painel ou rode TelegramService.delete_webhook().")
                        last_error = err
                    time.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 30)
                    continue

                if result.get("updates"):
                    for update in result["updates"]:
                        update_id = update.get("update_id")
                        message = update.get("message")
                        callback_query = update.get("callback_query")
                        
                        if message:
                            process_message(message)
                        
                        if callback_query:
                            TelegramService.handle_callback_query(callback_query)
                        
                        last_update_id = max(last_update_id, update_id)
                        _save_last_update_id(offset_file, last_update_id)
                    backoff_seconds = 2
                else:
                    backoff_seconds = 2
                    time.sleep(1)
                
            except KeyboardInterrupt:
                print("\n\n⏹️ Bot encerrado pelo usuário.")
                break
            except Exception as e:
                print(f"❌ Erro: {e}")
                time.sleep(5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

