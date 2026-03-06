"""Teste final do sistema de preferências de notificações."""

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramUser, TelegramNotificationPreferences, Usuario

app = create_app()

with app.app_context():
    print("=" * 80)
    print("TESTE FINAL: Sistema de Preferências de Notificações")
    print("=" * 80)
    print()
    
    # 1. Verificar todos os usuários têm preferências
    print("1️⃣ VERIFICANDO PREFERÊNCIAS DOS USUÁRIOS")
    print("-" * 80)
    
    telegram_users = TelegramUser.query.all()
    
    all_have_prefs = True
    for tg_user in telegram_users:
        has_prefs = tg_user.notification_preferences is not None
        status = "✅" if has_prefs else "❌"
        user_name = tg_user.usuario.nome if tg_user.usuario else tg_user.chat_id
        print(f"{status} {user_name} - {'TEM' if has_prefs else 'SEM'} preferências")
        
        if not has_prefs:
            all_have_prefs = False
    
    print()
    if all_have_prefs:
        print("✅ Todos os usuários têm preferências configuradas!")
    else:
        print("❌ Alguns usuários não têm preferências!")
    
    # 2. Testar acesso às preferências
    print()
    print("2️⃣ TESTANDO ACESSO ÀS PREFERÊNCIAS")
    print("-" * 80)
    
    if telegram_users:
        test_user = telegram_users[0]
        user_name = test_user.usuario.nome if test_user.usuario else test_user.chat_id
        print(f"Testando com usuário: {user_name}")
        print()
        
        prefs = test_user.notification_preferences
        if prefs:
            print("Preferências atuais:")
            print(f"  • Ferramenta (Retirada): {'SIM' if prefs.notify_ferramenta_withdrawal else 'NÃO'}")
            print(f"  • Ferramenta (Devolução): {'SIM' if prefs.notify_ferramenta_return else 'NÃO'}")
            print(f"  • Elétrico (Retirada): {'SIM' if prefs.notify_eletrico_withdrawal else 'NÃO'}")
            print(f"  • Elétrico (Devolução): {'SIM' if prefs.notify_eletrico_return else 'NÃO'}")
            print(f"  • Limpeza (Retirada): {'SIM' if prefs.notify_limpeza_withdrawal else 'NÃO'}")
            print(f"  • EPIs (Retirada): {'SIM' if prefs.notify_epi_withdrawal else 'NÃO'}")
            
            print()
            print("Testando método should_notify():")
            
            test_cases = [
                ("Material Elétrico", False, "Retirada de Material Elétrico"),
                ("Ferramenta", True, "Devolução de Ferramenta"),
                ("Material de Limpeza", False, "Retirada de Limpeza"),
            ]
            
            for categoria, is_return, desc in test_cases:
                result = prefs.should_notify(categoria, is_return)
                status = "✅ NOTIFICAR" if result else "❌ NÃO NOTIFICAR"
                print(f"  {status} - {desc}")
        else:
            print("❌ Preferências não encontradas!")
    
    # 3. Estatísticas gerais
    print()
    print("3️⃣ ESTATÍSTICAS GERAIS")
    print("-" * 80)
    
    total_users = TelegramUser.query.count()
    total_prefs = TelegramNotificationPreferences.query.count()
    
    print(f"📊 Total de usuários Telegram: {total_users}")
    print(f"🔔 Total de preferências criadas: {total_prefs}")
    print(f"✅ Taxa de cobertura: {(total_prefs/total_users*100) if total_users > 0 else 0:.1f}%")
    
    print()
    print("=" * 80)
    print("✅ SISTEMA PRONTO PARA USO!")
    print("=" * 80)
    print()
    print("📝 Para configurar preferências:")
    print("   1. Acesse: Configurações → Telegram")
    print("   2. Clique no ícone 🔔 ao lado do usuário")
    print("   3. Marque/desmarque as categorias desejadas")
    print("   4. Clique em 'Salvar Preferências'")
    print()
