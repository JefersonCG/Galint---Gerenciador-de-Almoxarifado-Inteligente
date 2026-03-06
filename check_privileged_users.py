"""Script para verificar quais usuários são considerados privilegiados."""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramUser, Usuario
from sqlalchemy import or_

app = create_app()

with app.app_context():
    print("\n" + "=" * 120)
    print("VERIFICAÇÃO DE USUÁRIOS PRIVILEGIADOS")
    print("=" * 120)
    
    # Query dos usuários privilegiados (mesma lógica do código)
    privileged = (
        db.session.query(TelegramUser, Usuario)
        .join(Usuario, TelegramUser.matricula == Usuario.matricula)
        .filter(TelegramUser.enabled.is_(True))
        .filter(
            or_(
                Usuario.is_admin == 1,
                Usuario.setor.ilike("%ZELADOR%"),
                Usuario.setor.ilike("%SUPERVISOR%"),
                Usuario.cargo.ilike("%ZELADOR%"),
                Usuario.cargo.ilike("%SUPERVISOR%"),
            )
        )
        .all()
    )
    
    print(f"\n📋 USUÁRIOS PRIVILEGIADOS (receberão notificações de supervisão): {len(privileged)}")
    print("-" * 120)
    
    for tg_user, usuario in privileged:
        is_admin = "✅ ADMIN" if usuario.is_admin == 1 else "❌ Not Admin"
        setor = usuario.setor or 'N/A'
        cargo = usuario.cargo or 'N/A'
        
        reasons = []
        if usuario.is_admin == 1:
            reasons.append("is_admin=1")
        if usuario.setor and ("ZELADOR" in usuario.setor.upper() or "SUPERVISOR" in usuario.setor.upper()):
            reasons.append(f"setor='{usuario.setor}'")
        if usuario.cargo and ("ZELADOR" in usuario.cargo.upper() or "SUPERVISOR" in usuario.cargo.upper()):
            reasons.append(f"cargo='{usuario.cargo}'")
        
        reason_str = " | ".join(reasons) if reasons else "NENHUMA RAZÃO (BUG?)"
        
        print(f"  {is_admin} | {usuario.nome:30} | Motivo: {reason_str}")
        print(f"         | chat_id={tg_user.chat_id:15} | matrícula={tg_user.matricula}")
    
    # Todos os usuários telegram
    all_users = db.session.query(TelegramUser).filter_by(enabled=True).all()
    
    print(f"\n📱 TOTAL DE USUÁRIOS TELEGRAM ATIVOS: {len(all_users)}")
    print(f"📋 TOTAL CONSIDERADOS PRIVILEGIADOS: {len(privileged)}")
    
    print("\n" + "=" * 120)
    print("ANÁLISE DO PROBLEMA")
    print("=" * 120)
    
    if len(privileged) >= len(all_users):
        print("\n❌ PROBLEMA CONFIRMADO:")
        print(f"   TODOS os {len(all_users)} usuários Telegram são considerados privilegiados!")
        print(f"   Isso significa que cada retirada está sendo enviada para TODOS eles.")
        print("\n💡 SOLUÇÕES POSSÍVEIS:")
        print("   1. Criar um GRUPO do Telegram e configurá-lo para receber notificações")
        print("      (assim, apenas 1 mensagem no grupo ao invés de 7 individuais)")
        print()
        print("   2. Remover a tag SUPERVISOR/ZELADOR de usuários que não precisam")
        print("      receber todas as notificações")
        print()
        print("   3. Desabilitar notify_supervisors na configuração do Telegram")
        print("      (mas isso pode não ser o ideal dependendo das suas necessidades)")
    elif len(privileged) > 3:
        print(f"\n⚠️  HÁ {len(privileged)} USUÁRIOS PRIVILEGIADOS:")
        print("   Isso significa que cada retirada está sendo enviada para todos eles.")
        print("   Considere criar um grupo do Telegram para reduzir o número de mensagens.")
    else:
        print(f"\n✅ Configuração normal: {len(privileged)} usuários privilegiados.")
    
    print("\n" + "=" * 120)
