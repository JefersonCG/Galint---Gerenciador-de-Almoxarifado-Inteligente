"""Script para adicionar tabela de conversações do Telegram.

Adiciona:
- Tabela telegram_conversations para rastrear cadastros automáticos
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
        print("🔄 Criando tabela de conversações do Telegram...")
        
        try:
            # Criar tabela telegram_conversations
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS telegram_conversations (
                    chat_id VARCHAR NOT NULL PRIMARY KEY,
                    state VARCHAR NOT NULL,
                    nome_informado VARCHAR,
                    cargo_informado VARCHAR,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.session.commit()
            print("  ✅ Tabela 'telegram_conversations' criada")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  ⚠️  Tabela 'telegram_conversations' já existe")
                db.session.rollback()
            else:
                print(f"  ❌ Erro: {e}")
                db.session.rollback()
                return False
        
        print("\n✅ Migração concluída com sucesso!")
        print("\n📝 Agora o bot pode cadastrar usuários automaticamente:")
        print("  1. Usuário envia /start para o bot")
        print("  2. Bot pergunta o nome completo")
        print("  3. Bot pergunta a função/cargo")
        print("  4. Sistema busca automaticamente no banco")
        print("  5. Se encontrar match único, vincula automaticamente!")
        
        return True


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
