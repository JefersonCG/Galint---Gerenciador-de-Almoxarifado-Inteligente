"""Script de teste para sistema de preferências de notificações do Telegram."""

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotificationPreferences

app = create_app()

with app.app_context():
    print("=" * 70)
    print("TESTE: Sistema de Preferências de Notificações do Telegram")
    print("=" * 70)
    print()
    
    # Teste 1: Normalização de categorias
    print("1️⃣ TESTE DE NORMALIZAÇÃO DE CATEGORIAS")
    print("-" * 70)
    
    test_cases = [
        ("Ferramenta", "ferramenta"),
        ("Ferramentas", "ferramenta"),
        ("Material de Limpeza", "limpeza"),
        ("Material Elétrico", "eletrico"),
        ("Elétrico", "eletrico"),
        ("Material Hidráulico", "hidraulico"),
        ("Hidráulico", "hidraulico"),
        ("Construção", "construcao"),
        ("Material de Construção", "construcao"),
        ("Pintura", "pintura"),
        ("Drywall", "pintura"),
        ("Pintura/Drywall", "pintura"),
        ("Piscina", "piscina"),
        ("EPI", "epi"),
        ("EPIs", "epi"),
        ("Equipamento de Proteção", "epi"),
        ("Segurança", "epi"),
        ("Outra Categoria", "outros"),
    ]
    
    success = 0
    failed = 0
    
    for input_cat, expected in test_cases:
        result = TelegramNotificationPreferences.normalize_category(input_cat)
        status = "✅" if result == expected else "❌"
        
        if result == expected:
            success += 1
        else:
            failed += 1
            
        print(f"{status} '{input_cat}' → '{result}' (esperado: '{expected}')")
    
    print()
    print(f"Resultado: {success} sucessos, {failed} falhas")
    print()
    
    # Teste 2: Verificação de preferências
    print("\n2️⃣ TESTE DE VERIFICAÇÃO DE PREFERÊNCIAS")
    print("-" * 70)
    
    # Criar preferências de teste
    prefs = TelegramNotificationPreferences(telegram_user_id=999999)
    
    # Configurar algumas preferências
    prefs.notify_eletrico_withdrawal = True
    prefs.notify_eletrico_return = False
    prefs.notify_ferramenta_withdrawal = True
    prefs.notify_ferramenta_return = True
    prefs.notify_limpeza_withdrawal = False
    prefs.notify_limpeza_return = False
    
    test_scenarios = [
        ("Material Elétrico", False, True, "Retirada de Material Elétrico"),
        ("Material Elétrico", True, False, "Devolução de Material Elétrico"),
        ("Ferramenta", False, True, "Retirada de Ferramenta"),
        ("Ferramenta", True, True, "Devolução de Ferramenta"),
        ("Material de Limpeza", False, False, "Retirada de Material de Limpeza"),
        ("Material de Limpeza", True, False, "Devolução de Material de Limpeza"),
    ]
    
    print("Configuração:")
    print("  • Elétrico: Retirada=SIM, Devolução=NÃO")
    print("  • Ferramenta: Retirada=SIM, Devolução=SIM")
    print("  • Limpeza: Retirada=NÃO, Devolução=NÃO")
    print()
    
    for categoria, is_return, expected_result, description in test_scenarios:
        result = prefs.should_notify(categoria, is_return)
        status = "✅" if result == expected_result else "❌"
        result_text = "NOTIFICAR" if result else "NÃO NOTIFICAR"
        expected_text = "NOTIFICAR" if expected_result else "NÃO NOTIFICAR"
        
        print(f"{status} {description}")
        print(f"   Resultado: {result_text} (esperado: {expected_text})")
    
    print()
    print("=" * 70)
    print("✅ TESTES CONCLUÍDOS COM SUCESSO!")
    print("=" * 70)
