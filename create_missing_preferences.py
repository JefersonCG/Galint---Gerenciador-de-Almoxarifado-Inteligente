"""Script para criar preferências de notificações para usuários Telegram já cadastrados."""

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramUser, TelegramNotificationPreferences

app = create_app()

with app.app_context():
    print("=" * 70)
    print("CRIANDO PREFERÊNCIAS PARA USUÁRIOS JÁ CADASTRADOS")
    print("=" * 70)
    print()
    
    # Buscar todos os usuários do Telegram
    telegram_users = TelegramUser.query.all()
    
    print(f"📊 Total de usuários Telegram cadastrados: {len(telegram_users)}")
    print()
    
    created = 0
    already_exists = 0
    
    for tg_user in telegram_users:
        # Verificar se já tem preferências
        if tg_user.notification_preferences:
            already_exists += 1
            print(f"⏭️  {tg_user.usuario.nome if tg_user.usuario else tg_user.chat_id} - Já possui preferências")
        else:
            # Criar preferências padrão (todas ativas)
            preferences = TelegramNotificationPreferences(telegram_user_id=tg_user.id)
            db.session.add(preferences)
            created += 1
            print(f"✅ {tg_user.usuario.nome if tg_user.usuario else tg_user.chat_id} - Preferências criadas")
    
    # Salvar no banco
    if created > 0:
        try:
            db.session.commit()
            print()
            print("=" * 70)
            print(f"✅ SUCESSO! {created} preferências criadas")
            print(f"⏭️  {already_exists} usuários já tinham preferências")
            print("=" * 70)
            print()
            print("🔔 Agora todos os usuários podem configurar suas notificações em:")
            print("   Configurações → Telegram → Ícone 🔔 ao lado do usuário")
        except Exception as e:
            db.session.rollback()
            print()
            print(f"❌ ERRO ao salvar: {e}")
    else:
        print()
        print("=" * 70)
        print("✅ Nada a fazer - todos os usuários já possuem preferências!")
        print("=" * 70)
