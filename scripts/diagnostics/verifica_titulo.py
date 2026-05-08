"""Verifica titulo da notificacao."""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramNotification

app = create_app()
with app.app_context():
    n = db.session.query(TelegramNotification).order_by(
        TelegramNotification.sent_at.desc()
    ).first()
    
    if n:
        texto = n.message_text
        if "RETIRADA DE FERRAMENTA" in texto:
            print("✅ SUCESSO! Titulo correto: RETIRADA DE FERRAMENTA")
        elif "RETIRADA DE MATERIAL" in texto:
            print("❌ FALHOU! Titulo ainda e: RETIRADA DE MATERIAL")
        else:
            print("⚠️ Titulo nao encontrado no texto")
        
        # Mostrar ID da notificacao
        print(f"ID Notificacao: {n.id}")
        print(f"Chat ID: {n.chat_id}")
        print(f"Enviado em: {n.sent_at}")
