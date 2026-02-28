"""Script para verificar configuração de destinatários Telegram."""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramUser, TelegramGroup

app = create_app()

with app.app_context():
    print("\n" + "=" * 120)
    print("CONFIGURAÇÃO DE DESTINATÁRIOS TELEGRAM")
    print("=" * 120)
    
    # Verificar usuários ativos
    users = db.session.query(TelegramUser).filter_by(enabled=True).all()
    
    print(f"\n📱 USUÁRIOS TELEGRAM ATIVOS: {len(users)}")
    print("-" * 120)
    for u in users:
        usuario = u.usuario if hasattr(u, 'usuario') else None
        nome = usuario.nome if usuario else 'N/A'
        cargo = usuario.cargo if usuario and hasattr(usuario, 'cargo') else 'N/A'
        print(f"  chat_id={u.chat_id:15} | matrícula={u.matricula:10} | nome={nome:30} | cargo={cargo}")
    
    # Verificar grupos ativos
    groups = db.session.query(TelegramGroup).filter_by(enabled=True).all()
    
    print(f"\n👥 GRUPOS TELEGRAM ATIVOS: {len(groups)}")
    print("-" * 120)
    for g in groups:
        recv_withdrawals = "✅" if g.receive_withdrawals else "❌"
        recv_alerts = "✅" if g.receive_alerts else "❌"
        print(f"  {g.name:30} | chat_id={g.chat_id:15} | Retiradas={recv_withdrawals} | Alertas={recv_alerts}")
        if g.description:
            print(f"    Descrição: {g.description}")
    
    print("\n" + "=" * 120)
    print("ANÁLISE DO PROBLEMA")
    print("=" * 120)
    
    # Contar quantos destinatários receberão notificações de retirada
    withdrawal_recipients = []
    
    # Grupos que recebem retiradas
    groups_withdrawal = [g for g in groups if g.receive_withdrawals]
    for g in groups_withdrawal:
        withdrawal_recipients.append(f"Grupo: {g.name}")
    
    # Usuários individuais (todos os ativos podem receber se preferências permitirem)
    for u in users:
        withdrawal_recipients.append(f"Usuário: {u.matricula}")
    
    print(f"\n⚠️  CADA RETIRADA ESTÁ SENDO ENVIADA PARA ATÉ {len(withdrawal_recipients)} DESTINO(S):")
    for dest in withdrawal_recipients:
        print(f"  - {dest}")
    
    print("\n" + "=" * 120)
    print("POSSÍVEL CAUSA DA DUPLICAÇÃO")
    print("=" * 120)
    
    if len(groups_withdrawal) > 0 and len(users) > 0:
        print("\n❌ PROBLEMA IDENTIFICADO:")
        print(f"   Há {len(groups_withdrawal)} grupo(s) configurado(s) E {len(users)} usuário(s) ativos.")
        print(f"   A lógica atual está enviando para AMBOS grupos E usuários individuais!")
        print("\n💡 SOLUÇÃO:")
        print("   Se houver grupos configurados, deve enviar APENAS para grupos.")
        print("   Usuários individuais devem receber apenas se NÃO houver grupos.")
    elif len(groups_withdrawal) > 1:
        print("\n⚠️  MÚLTIPLOS GRUPOS:")
        print(f"   Há {len(groups_withdrawal)} grupos configurados.")
        print("   Cada retirada será enviada para TODOS os grupos.")
        print("   Isso pode ser intencional se você quiser notificar múltiplos grupos.")
    elif len(users) > 5:
        print("\n⚠️  MUITOS USUÁRIOS:")
        print(f"   Há {len(users)} usuários ativos.")
        print("   Cada retirada será enviada para TODOS eles (se preferências permitirem).")
        print("   Considere usar grupos em vez de notificações individuais.")
    
    print("\n" + "=" * 120)
