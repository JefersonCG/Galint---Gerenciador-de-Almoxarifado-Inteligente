"""
Script para testar os 3 novos formatos de notificação Telegram.
Exibe exemplos de cada formato sem enviar mensagens reais.
"""
import os
import sys
from datetime import datetime

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService
from galint_flask.models import Saida, Usuario, Item
from galint_flask.extensions import db


def print_separator(title: str):
    """Imprime separador visual."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def main():
    app = create_app()
    
    with app.app_context():
        # Buscar uma saída de exemplo (ferramentas de uso temporário)
        saida = (
            db.session.query(Saida)
            .filter(Saida.item.has(Item.categoria.ilike('%ferramentas%')))
            .filter(Saida.tipo_custodia == 'temporaria')  # Apenas uso temporário
            .first()
        )
        
        if not saida:
            print("❌ Nenhuma saída de ferramentas (uso temporário) encontrada no banco.")
            print("   Crie uma retirada primeiro para testar os formatos.")
            return
        
        usuario = saida.usuario
        item = saida.item
        
        if not usuario or not item:
            print("❌ Dados incompletos na saída.")
            return
        
        print("\n🎨 TESTANDO NOVOS FORMATOS DE NOTIFICAÇÃO TELEGRAM")
        print(f"\nDados de exemplo:")
        print(f"  • Material: {item.descricao}")
        print(f"  • Categoria: {item.categoria}")
        print(f"  • Funcionário: {usuario.nome}")
        print(f"  • Matrícula: {usuario.matricula}")
        print(f"  • Tipo Custódia: {saida.tipo_custodia}")
        
        # Teste 1: Formato COMPACTO
        print_separator("1️⃣  FORMATO COMPACTO (Compact)")
        print("👤 VERSÃO PARA FUNCIONÁRIO:")
        print("-" * 60)
        msg_compact_user = TelegramService.format_withdrawal_message_compact(
            saida, usuario, item, for_supervisor=False
        )
        print(msg_compact_user)
        
        print("\n👔 VERSÃO PARA SUPERVISOR:")
        print("-" * 60)
        msg_compact_sup = TelegramService.format_withdrawal_message_compact(
            saida, usuario, item, for_supervisor=True
        )
        print(msg_compact_sup)
        
        # Teste 2: Formato DETALHADO
        print_separator("2️⃣  FORMATO DETALHADO (Detailed)")
        print("👤 VERSÃO PARA FUNCIONÁRIO:")
        print("-" * 60)
        msg_detailed_user = TelegramService.format_withdrawal_message_detailed(
            saida, usuario, item, for_supervisor=False
        )
        print(msg_detailed_user)
        
        print("\n👔 VERSÃO PARA SUPERVISOR:")
        print("-" * 60)
        msg_detailed_sup = TelegramService.format_withdrawal_message_detailed(
            saida, usuario, item, for_supervisor=True
        )
        print(msg_detailed_sup)
        
        # Teste 3: Formato MODERNO
        print_separator("3️⃣  FORMATO MODERNO (Modern)")
        print("👤 VERSÃO PARA FUNCIONÁRIO:")
        print("-" * 60)
        msg_modern_user = TelegramService.format_withdrawal_message_modern(
            saida, usuario, item, for_supervisor=False
        )
        print(msg_modern_user)
        
        print("\n👔 VERSÃO PARA SUPERVISOR:")
        print("-" * 60)
        msg_modern_sup = TelegramService.format_withdrawal_message_modern(
            saida, usuario, item, for_supervisor=True
        )
        print(msg_modern_sup)
        
        # Comparação de tamanhos
        print_separator("📊 COMPARAÇÃO DE TAMANHOS")
        formats = [
            ("Compacto (Funcionário)", msg_compact_user),
            ("Compacto (Supervisor)", msg_compact_sup),
            ("Detalhado (Funcionário)", msg_detailed_user),
            ("Detalhado (Supervisor)", msg_detailed_sup),
            ("Moderno (Funcionário)", msg_modern_user),
            ("Moderno (Supervisor)", msg_modern_sup),
        ]
        
        for name, msg in formats:
            lines = msg.count('\n') + 1
            chars = len(msg)
            print(f"{name:30} → {lines:2} linhas, {chars:4} caracteres")
        
        print("\n" + "=" * 60)
        print("✅ Teste concluído!")
        print("=" * 60 + "\n")
        
        # Informações adicionais
        print("\n💡 COMO USAR:")
        print("   1. Escolha o formato que preferir")
        print("   2. Edite o arquivo galint_flask/services/telegram_service.py")
        print("   3. Na função notify_withdrawal(), substitua:")
        print("      format_withdrawal_message_user() por:")
        print("      • format_withdrawal_message_compact()")
        print("      • format_withdrawal_message_detailed()")
        print("      • format_withdrawal_message_modern()")
        print("\n   Consulte NOVOS_FORMATOS_NOTIFICACOES_TELEGRAM.md para detalhes.\n")


if __name__ == "__main__":
    main()
