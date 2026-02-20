"""Script para adicionar suporte ao sistema Telegram no banco de dados.

Adiciona:
- Campo local_servico na tabela saidas
- Tabelas telegram_config, telegram_users, telegram_groups, telegram_notifications
"""
from __future__ import annotations

import sys
from pathlib import Path

# Adicionar raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.extensions import db
from sqlalchemy import text


def run_migration():
    """Executa migração do banco de dados."""
    app = create_app()
    
    with app.app_context():
        print("🔄 Iniciando migração do banco de dados...")
        
        # 1. Adicionar campo local_servico na tabela saidas
        try:
            print("  → Adicionando campo 'local_servico' em 'saidas'...")
            db.session.execute(text(
                "ALTER TABLE saidas ADD COLUMN local_servico TEXT"
            ))
            db.session.commit()
            print("    ✅ Campo 'local_servico' adicionado")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("    ⚠️  Campo 'local_servico' já existe")
                db.session.rollback()
            else:
                print(f"    ❌ Erro: {e}")
                db.session.rollback()
                return False
        
        # 2. Criar tabelas do sistema Telegram
        print("  → Criando tabelas do sistema Telegram...")
        try:
            db.create_all()
            print("    ✅ Tabelas criadas com sucesso")
        except Exception as e:
            print(f"    ❌ Erro ao criar tabelas: {e}")
            return False
        
        # 3. Verificar se tabelas foram criadas
        inspector = db.inspect(db.engine)
        expected_tables = [
            "telegram_config",
            "telegram_users",
            "telegram_groups",
            "telegram_notifications",
        ]
        
        existing_tables = inspector.get_table_names()
        for table in expected_tables:
            if table in existing_tables:
                print(f"    ✅ Tabela '{table}' criada")
            else:
                print(f"    ⚠️  Tabela '{table}' não encontrada")
        
        # 4. Criar configuração inicial do Telegram (se não existir)
        from galint_flask.models import TelegramConfig
        
        config = TelegramConfig.query.first()
        if not config:
            print("  → Criando configuração inicial do Telegram...")
            config = TelegramConfig(
                enabled=False,
                notify_on_withdrawal=True,
                notify_supervisors=True,
                alert_weekday_time="16:20",
                alert_saturday_time="11:00",
                alert_enabled=True,
            )
            db.session.add(config)
            db.session.commit()
            print("    ✅ Configuração inicial criada")
        else:
            print("    ⚠️  Configuração já existe")
        
        print("\n✅ Migração concluída com sucesso!")
        print("\n📝 Próximos passos:")
        print("  1. Acesse: http://localhost:5000/configuracoes/telegram")
        print("  2. Configure o token do bot (obtenha com @BotFather no Telegram)")
        print("  3. Vincule usuários e grupos")
        print("  4. Teste o envio de mensagens")
        print("\n📖 Documentação completa: README.md (seção Telegram)")
        
        return True


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
