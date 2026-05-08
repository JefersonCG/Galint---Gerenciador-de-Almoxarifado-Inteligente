# -*- coding: utf-8 -*-
"""Enviar notificações de teste de devolução para Jeferson."""

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import TelegramUser, Usuario
from galint_flask.services.telegram_service import TelegramService

app = create_app()
with app.app_context():
    jeferson = (
        db.session.query(TelegramUser)
        .join(Usuario, TelegramUser.matricula == Usuario.matricula)
        .filter(Usuario.nome.ilike('%jeferson%'))
        .first()
    )
    
    if not jeferson:
        print('Jeferson nao encontrado no Telegram')
    else:
        print(f'Encontrado: {jeferson.usuario.nome} - Chat ID: {jeferson.chat_id}')
        
        # Mensagem de teste de DEVOLUÇÃO DE FERRAMENTA
        msg1 = """✅ <b>DEVOLUÇÃO DE FERRAMENTA</b>

🔧 <b>FURADEIRA BOSCH 750W</b>
🏷️ Código: <code>7891024789456</code>
📂 Categoria: Ferramentas
🏭 Marca: Bosch

━━━━━━━━━━━━━━━━━

📤 <b>Retirado por:</b> Antonio Silva (Mat. 12345)
📥 <b>Devolvido por:</b> Antonio Silva (Mat. 12345)

📊 <b>Quantidade Devolvida:</b> +1
⏰ <b>Data:</b> 03/02/2026 12:15
💼 <b>Saldo Atual:</b> 5 un

💡 <i>Item disponível novamente para retirada</i>

<i>🔔 TESTE - Notificação de Devolução de Ferramenta</i>"""
        
        result1 = TelegramService.send_message(str(jeferson.chat_id), msg1)
        print(f'Devolucao Ferramenta: {result1}')
        
        # Mensagem de teste de DEVOLUÇÃO DE MATERIAL DE LIMPEZA
        msg2 = """✅ <b>DEVOLUÇÃO DE MATERIAL DE LIMPEZA</b>

🧹 <b>VASSOURA DE PELO 40CM</b>
🏷️ Código: <code>7891024111222</code>
📂 Categoria: Material de Limpeza
🏭 Marca: Condor

━━━━━━━━━━━━━━━━━

📤 <b>Retirado por:</b> Maria Santos (Mat. 67890)
📥 <b>Devolvido por:</b> Maria Santos (Mat. 67890)

📊 <b>Quantidade Devolvida:</b> +2
⏰ <b>Data:</b> 03/02/2026 12:15
💼 <b>Saldo Atual:</b> 10 un

💡 <i>Item disponível novamente para retirada</i>

<i>🔔 TESTE - Notificação de Devolução de Material de Limpeza</i>"""
        
        result2 = TelegramService.send_message(str(jeferson.chat_id), msg2)
        print(f'Devolucao Material Limpeza: {result2}')
        
        print("CONCLUIDO!")
