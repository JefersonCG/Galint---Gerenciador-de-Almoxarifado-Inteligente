"""Script para testar retirada de ferramenta e verificar notificação."""
import os
import sys
from datetime import datetime

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, Categoria, Usuario, Saida, TelegramNotification
from galint_flask.services.telegram_service import TelegramService


def main():
    app = create_app()
    with app.app_context():
        # Buscar categoria Ferramentas
        cat = db.session.query(Categoria).filter(
            Categoria.nome.ilike('%ferramenta%')
        ).first()
        
        if not cat:
            print("❌ Categoria Ferramentas não encontrada")
            return
        
        print(f"✓ Categoria encontrada: {cat.nome}")
        
        # Buscar uma ferramenta em estoque
        item = db.session.query(Item).filter_by(
            categoria_id=cat.id_categoria
        ).filter(Item.quantidade > 0).first()
        
        if not item:
            print("❌ Nenhuma ferramenta em estoque")
            return
        
        print(f"✓ Ferramenta: {item.descricao} (Código: {item.codigo}, Qtd: {item.quantidade})")
        
        # Buscar um usuário administrador
        usuario = db.session.query(Usuario).filter_by(is_admin=1).first()
        
        if not usuario:
            print("❌ Nenhum usuário administrador encontrado")
            return
        
        print(f"✓ Usuário: {usuario.nome} (Mat: {usuario.matricula})")
        
        # Criar retirada de teste
        saida = Saida(
            codigo=item.codigo,
            quantidade=1,
            matricula=usuario.matricula,
            data_saida=datetime.now(),
            observacao="TESTE - Retirada de ferramenta para verificar notificação"
        )
        
        db.session.add(saida)
        
        # Atualizar estoque
        item.quantidade -= 1
        
        try:
            db.session.commit()
            print(f"✓ Retirada registrada! ID: {saida.id_saida}")
            
            # Enviar notificação
            print("\n📱 Enviando notificação Telegram...")
            result = TelegramService.notify_withdrawal(saida.id_saida)
            print(f"Resultado: {result}")
            
            # Buscar última notificação
            last_notif = db.session.query(TelegramNotification).order_by(
                TelegramNotification.sent_at.desc()
            ).first()
            
            if last_notif:
                print(f"\n📬 Última notificação:")
                print(f"   Tipo: {last_notif.message_type}")
                print(f"   Status: {last_notif.status}")
                print(f"   Chat ID: {last_notif.chat_id}")
                print(f"\n📝 Mensagem:")
                print("-" * 60)
                print(last_notif.message_text)
                print("-" * 60)
                
                if "RETIRADA DE FERRAMENTA" in last_notif.message_text:
                    print("\n✅ SUCESSO! Título correto: 'RETIRADA DE FERRAMENTA'")
                elif "RETIRADA DE MATERIAL" in last_notif.message_text:
                    print("\n⚠️ ATENÇÃO! Título ainda é: 'RETIRADA DE MATERIAL'")
                
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erro: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
