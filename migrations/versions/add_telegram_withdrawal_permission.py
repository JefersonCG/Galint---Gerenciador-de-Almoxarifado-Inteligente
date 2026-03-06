"""add telegram withdrawal permission

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2026-02-09

Adiciona campo can_withdraw_via_telegram na tabela telegram_users para controlar
permissões de retiradas via Telegram (escaneamento de código de barras).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Verificar se a coluna já existe antes de adicionar
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('telegram_users')]
    
    if 'can_withdraw_via_telegram' not in columns:
        op.add_column('telegram_users', 
            sa.Column('can_withdraw_via_telegram', 
                     sa.Boolean(), 
                     nullable=False, 
                     server_default='false',
                     comment='Permite que o usuário faça retiradas via Telegram (escaneando código de barras)')
        )
        print("✅ Coluna 'can_withdraw_via_telegram' adicionada com sucesso")
    else:
        print("⚠️ Coluna 'can_withdraw_via_telegram' já existe, pulando...")


def downgrade():
    # Verificar se a coluna existe antes de remover
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('telegram_users')]
    
    if 'can_withdraw_via_telegram' in columns:
        op.drop_column('telegram_users', 'can_withdraw_via_telegram')
        print("✅ Coluna 'can_withdraw_via_telegram' removida")
    else:
        print("⚠️ Coluna 'can_withdraw_via_telegram' não existe, pulando...")
