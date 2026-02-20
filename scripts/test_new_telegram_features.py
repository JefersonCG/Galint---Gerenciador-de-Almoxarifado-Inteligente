"""Teste das novas funcionalidades do menu Telegram:
1. Planilha de estoque baixo em XLSX e PDF
2. Menu interativo por categorias com inline keyboards
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService

def main():
    app = create_app()
    
    with app.app_context():
        chat_id = "7855828574"  # Admin chat ID
        
        print("=" * 60)
        print("🧪 TESTE 1: Menu de Categorias Interativo")
        print("=" * 60)
        
        try:
            print("\n📤 Enviando menu de categorias com inline keyboard...")
            TelegramService._send_category_menu(chat_id)
            print("✅ Menu enviado! Verifique no Telegram para clicar em uma categoria.")
        except Exception as e:
            print(f"❌ Erro ao enviar menu: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("🧪 TESTE 2: Visualizar Itens de Categoria Específica")
        print("=" * 60)
        
        try:
            print("\n📤 Enviando itens da categoria 'PISCINA'...")
            TelegramService._send_category_items(chat_id, "PISCINA")
            print("✅ Itens enviados! Verifique no Telegram.")
        except Exception as e:
            print(f"❌ Erro ao enviar itens: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("🧪 TESTE 3: Gerar Planilhas (XLSX e PDF)")
        print("=" * 60)
        
        reports_dir = Path("instance") / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Teste XLSX
        try:
            xlsx_path = str(reports_dir / "test_estoque_baixo.xlsx")
            print(f"\n📊 Gerando XLSX em {xlsx_path}...")
            TelegramService.generate_estoque_baixo_xlsx(xlsx_path)
            print(f"✅ XLSX gerado com sucesso: {Path(xlsx_path).stat().st_size} bytes")
        except Exception as e:
            print(f"❌ Erro ao gerar XLSX: {e}")
            import traceback
            traceback.print_exc()
        
        # Teste PDF
        try:
            pdf_path = str(reports_dir / "test_estoque_baixo.pdf")
            print(f"\n📄 Gerando PDF em {pdf_path}...")
            TelegramService.generate_estoque_baixo_pdf(pdf_path)
            print(f"✅ PDF gerado com sucesso: {Path(pdf_path).stat().st_size} bytes")
        except Exception as e:
            print(f"❌ Erro ao gerar PDF: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("🧪 TESTE 4: Enviar Planilhas via Telegram")
        print("=" * 60)
        
        try:
            print("\n📤 Simulando comando 'Baixar Planilha Estoque Baixo'...")
            result = TelegramService.handle_menu_text(chat_id, "Baixar Planilha Estoque Baixo")
            if result:
                print("✅ Comando processado! Verifique o Telegram para ver XLSX e PDF.")
            else:
                print("⚠️ Comando retornou False")
        except Exception as e:
            print(f"❌ Erro ao processar comando: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 60)
        print("🧪 TESTE 5: Menus Principais (Textos com Emoji)")
        print("=" * 60)

        try:
            print("\n📤 Simulando botão '📊 Relatórios & Retiradas'...")
            result = TelegramService.handle_menu_text(chat_id, "📊 Relatórios & Retiradas")
            print("✅ OK" if result else "⚠️ Retornou False")

            print("\n📤 Simulando botão '📦 Itens & Estoque'...")
            result = TelegramService.handle_menu_text(chat_id, "📦 Itens & Estoque")
            print("✅ OK" if result else "⚠️ Retornou False")

            print("\n📤 Simulando botão '⬅️ Menu'...")
            result = TelegramService.handle_menu_text(chat_id, "⬅️ Menu")
            print("✅ OK" if result else "⚠️ Retornou False")

            print("\n📤 Simulando submenu '🛠️ Relatório de Ferramentas (1–6 meses)'...")
            result = TelegramService.handle_menu_text(chat_id, "🛠️ Relatório de Ferramentas (1–6 meses)")
            print("✅ OK" if result else "⚠️ Retornou False")

            print("\n📤 Simulando submenu '📦 Relatório de Materiais (1–6 meses)'...")
            result = TelegramService.handle_menu_text(chat_id, "📦 Relatório de Materiais (1–6 meses)")
            print("✅ OK" if result else "⚠️ Retornou False")

            print("\n📤 Simulando submenu '📊 Relatório Geral (por categoria)'...")
            result = TelegramService.handle_menu_text(chat_id, "📊 Relatório Geral (por categoria)")
            print("✅ OK" if result else "⚠️ Retornou False")

            print("\n📤 Simulando submenu '📄 Estoque Baixo (XLSX/PDF)'...")
            result = TelegramService.handle_menu_text(chat_id, "📄 Estoque Baixo (XLSX/PDF)")
            print("✅ OK" if result else "⚠️ Retornou False")

            print("\n📤 Simulando submenu '⬅️ Voltar ao Menu'...")
            result = TelegramService.handle_menu_text(chat_id, "⬅️ Voltar ao Menu")
            print("✅ OK" if result else "⚠️ Retornou False")

            print("\n📤 Simulando botão '❌ Cancelar'...")
            result = TelegramService.handle_menu_text(chat_id, "❌ Cancelar")
            print("✅ OK" if result else "⚠️ Retornou False")
        except Exception as e:
            print(f"❌ Erro ao testar menus principais: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("✅ TESTES CONCLUÍDOS")
        print("=" * 60)
        print("\n📱 Abra o Telegram e verifique:")
        print("  1. Menu interativo de categorias (botões clicáveis)")
        print("  2. Itens da categoria PISCINA formatados elegantemente")
        print("  3. Arquivos XLSX e PDF de estoque baixo")
        print("  4. Submenus de 'Relatórios & Retiradas' e 'Itens & Estoque'")

if __name__ == "__main__":
    main()
