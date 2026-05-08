"""
Script de teste de notificações Telegram - SOMENTE PARA JEFERSON DOS SANTOS
Testa todos os tipos de notificação para cada categoria do sistema.
"""
import os
import sys
import time
from pathlib import Path

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

# Configurar ambiente
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('GALINT_TELEGRAM_OUTBOX_ENABLED', 'false')  # Enviar diretamente, sem fila

from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService
from galint_flask.extensions import db
from datetime import datetime

# Chat ID do Jeferson dos Santos
JEFERSON_CHAT_ID = "7855828574"

def criar_mensagem_retirada_teste(categoria: str, emoji: str) -> str:
    """Cria mensagem de teste de retirada."""
    categoria_titulo = categoria.upper()
    if "FERRAMENTA" in categoria_titulo:
        categoria_titulo = "FERRAMENTA"
    
    msg = f"⚠️ <b>RETIRADA DE {categoria_titulo}</b> [TESTE]\n\n"
    msg += f"👤 <b>Funcionário:</b> Teste Sistema (Mat. 00000)\n"
    msg += f"📦 <b>Item:</b> {emoji} Item de Teste - {categoria}\n"
    msg += f"🏷️ <b>Código:</b> <code>TESTE-{categoria[:3].upper()}</code>\n"
    msg += f"🏭 <b>Marca:</b> Teste Ltda\n"
    msg += f"📍 <b>Local/Uso:</b> Teste de Sistema\n\n"
    msg += f"━━━━━━━━━━━━━━━━━\n\n"
    msg += f"📊 <b>MOVIMENTAÇÃO</b>\n"
    msg += f"├─ Quantidade retirada: <b>1</b> un\n"
    msg += f"└─ Saldo restante: <b>99</b> un\n\n"
    msg += f"⏰ <b>Data/Hora:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    msg += f"<i>✅ Esta é uma mensagem de TESTE do sistema de notificações</i>"
    
    return msg

def criar_mensagem_devolucao_teste(categoria: str, emoji: str) -> str:
    """Cria mensagem de teste de devolução."""
    categoria_titulo = categoria.upper()
    if "FERRAMENTA" in categoria_titulo:
        categoria_titulo = "FERRAMENTA"
    
    msg = f"✅ <b>DEVOLUÇÃO DE {categoria_titulo}</b> [TESTE]\n\n"
    msg += f"📤 <b>Retirado por:</b> Teste Sistema (Mat. 00000)\n"
    msg += f"📥 <b>Devolvido por:</b> Teste Sistema (Mat. 00000)\n"
    msg += f"📦 <b>Total de itens:</b> 1\n"
    msg += f"⏰ <b>Horário:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    msg += f"━━━━━━━━━━━━━━━━━\n\n"
    msg += f"<b>1.</b> {emoji} <b>Item de Teste - {categoria}</b>\n"
    msg += f"   🏷️ {categoria}\n"
    msg += f"   📊 Qtd: <b>+1</b> un\n"
    msg += f"   💼 Novo Saldo: 100 un\n\n"
    msg += f"<i>✅ Esta é uma mensagem de TESTE do sistema de notificações</i>"
    
    return msg

def criar_mensagem_ajuste_teste(categoria: str, emoji: str) -> str:
    """Cria mensagem de teste de ajuste de inventário."""
    msg = f"📥 <b>AJUSTE DE ESTOQUE - ENTRADA MANUAL</b> [TESTE]\n\n"
    msg += f"{emoji} <b>Item de Teste - {categoria}</b>\n"
    msg += f"🏷️ Código: <code>TESTE-{categoria[:3].upper()}</code>\n"
    msg += f"📂 Categoria: {categoria}\n"
    msg += f"🏭 Marca: Teste Ltda\n"
    msg += f"\n━━━━━━━━━━━━━━━━━\n\n"
    msg += f"📊 <b>MOVIMENTAÇÃO</b>\n"
    msg += f"├─ Saldo anterior: <b>95</b> un\n"
    msg += f"├─ Variação: <b>+5</b> un 📈\n"
    msg += f"└─ Saldo atual: <b>100</b> un\n\n"
    msg += f"👤 <b>Responsável:</b> Teste Sistema (Mat. 00000)\n"
    msg += f"📝 <b>Motivo:</b> Ajuste de estoque - TESTE\n"
    msg += f"⏰ <b>Data/Hora:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    msg += f"<i>✅ Esta é uma mensagem de TESTE do sistema de notificações</i>"
    
    return msg

def testar_notificacoes():
    """Testa todos os tipos de notificação para cada categoria."""
    
    # Mapeamento de categorias e emojis
    categorias = {
        "Ferramentas": "🔧",
        "Limpeza": "🧹",
        "Material Elétrico": "⚡",
        "Material Hidráulico": "🚰",
        "Construção": "🏗️",
        "Pintura/Drywall": "🎨",
        "Piscina": "🏊",
        "EPI": "🦺"
    }
    
    print("=" * 80)
    print("🔍 TESTE DE NOTIFICAÇÕES TELEGRAM - JEFERSON DOS SANTOS")
    print("=" * 80)
    print(f"\n📱 Chat ID: {JEFERSON_CHAT_ID}")
    print(f"📊 Categorias a testar: {len(categorias)}")
    print(f"🔔 Tipos de notificação: 3 (Retirada, Devolução, Ajuste)")
    print(f"📧 Total de mensagens: {len(categorias) * 3}")
    print("\n" + "=" * 80)
    
    # Verificar se Telegram está habilitado
    if not TelegramService.is_enabled():
        print("\n❌ ERRO: Telegram não está habilitado!")
        print("   Configure o bot na interface de Configurações do sistema.")
        return
    
    config = TelegramService.get_config()
    if not config:
        print("\n❌ ERRO: Configuração do Telegram não encontrada!")
        return
    
    print(f"\n✅ Telegram habilitado")
    print(f"🤖 Bot Token: {config.bot_token[:10]}...{config.bot_token[-5:]}")
    print("\n" + "-" * 80)
    
    # Contador de resultados
    resultados = {
        "enviados": [],
        "falhados": [],
        "total": 0
    }
    
    # Testar cada categoria
    for idx, (categoria, emoji) in enumerate(categorias.items(), 1):
        print(f"\n[{idx}/{len(categorias)}] {emoji} Testando categoria: {categoria.upper()}")
        print("-" * 80)
        
        # 1. TESTE DE RETIRADA
        print(f"  1️⃣ Enviando notificação de RETIRADA...", end=" ")
        msg_retirada = criar_mensagem_retirada_teste(categoria, emoji)
        resultado_retirada = TelegramService.send_message(
            chat_id=JEFERSON_CHAT_ID,
            text=msg_retirada,
            parse_mode="HTML"
        )
        
        if resultado_retirada.get("success"):
            print("✅ ENVIADO")
            resultados["enviados"].append(f"Retirada - {categoria}")
        else:
            print(f"❌ ERRO: {resultado_retirada.get('error', 'Desconhecido')}")
            resultados["falhados"].append(f"Retirada - {categoria}: {resultado_retirada.get('error')}")
        resultados["total"] += 1
        
        # Delay para evitar rate limiting
        time.sleep(0.5)
        
        # 2. TESTE DE DEVOLUÇÃO
        print(f"  2️⃣ Enviando notificação de DEVOLUÇÃO...", end=" ")
        msg_devolucao = criar_mensagem_devolucao_teste(categoria, emoji)
        resultado_devolucao = TelegramService.send_message(
            chat_id=JEFERSON_CHAT_ID,
            text=msg_devolucao,
            parse_mode="HTML"
        )
        
        if resultado_devolucao.get("success"):
            print("✅ ENVIADO")
            resultados["enviados"].append(f"Devolução - {categoria}")
        else:
            print(f"❌ ERRO: {resultado_devolucao.get('error', 'Desconhecido')}")
            resultados["falhados"].append(f"Devolução - {categoria}: {resultado_devolucao.get('error')}")
        resultados["total"] += 1
        
        # Delay para evitar rate limiting
        time.sleep(0.5)
        
        # 3. TESTE DE AJUSTE
        print(f"  3️⃣ Enviando notificação de AJUSTE...", end=" ")
        msg_ajuste = criar_mensagem_ajuste_teste(categoria, emoji)
        resultado_ajuste = TelegramService.send_message(
            chat_id=JEFERSON_CHAT_ID,
            text=msg_ajuste,
            parse_mode="HTML"
        )
        
        if resultado_ajuste.get("success"):
            print("✅ ENVIADO")
            resultados["enviados"].append(f"Ajuste - {categoria}")
        else:
            print(f"❌ ERRO: {resultado_ajuste.get('error', 'Desconhecido')}")
            resultados["falhados"].append(f"Ajuste - {categoria}: {resultado_ajuste.get('error')}")
        resultados["total"] += 1
        
        # Delay entre categorias
        if idx < len(categorias):
            time.sleep(1)
    
    # Relatório final
    print("\n" + "=" * 80)
    print("📊 RELATÓRIO FINAL")
    print("=" * 80)
    print(f"\n✅ Enviados com sucesso: {len(resultados['enviados'])}/{resultados['total']}")
    print(f"❌ Falhados: {len(resultados['falhados'])}/{resultados['total']}")
    
    if resultados["enviados"]:
        print("\n🎯 Mensagens enviadas:")
        for msg in resultados["enviados"]:
            print(f"   ✓ {msg}")
    
    if resultados["falhados"]:
        print("\n⚠️ Mensagens que falharam:")
        for msg in resultados["falhados"]:
            print(f"   ✗ {msg}")
    
    print("\n" + "=" * 80)
    print("✅ Teste concluído!")
    print("📱 Verifique o Telegram de Jeferson dos Santos para ver as mensagens")
    print("=" * 80)

if __name__ == "__main__":
    app = create_app()
    
    with app.app_context():
        try:
            print("\n🚀 Iniciando testes de notificação...\n")
            testar_notificacoes()
        except KeyboardInterrupt:
            print("\n\n⚠️ Teste interrompido pelo usuário")
        except Exception as e:
            print(f"\n\n❌ ERRO FATAL: {e}")
            import traceback
            traceback.print_exc()
