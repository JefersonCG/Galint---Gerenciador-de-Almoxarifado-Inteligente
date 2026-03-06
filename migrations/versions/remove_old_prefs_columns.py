"""Remove colunas antigas da tabela telegram_notification_preferences

Revision ID: remove_old_prefs_cols
Revises: notif_prefs_001
Create Date: 2026-01-30 12:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_old_prefs_cols'
down_revision = 'notif_prefs_001'
branch_labels = None
depends_on = None


def upgrade():
    # Remover colunas antigas que foram criadas anteriormente
    with op.batch_alter_table('telegram_notification_preferences', schema=None) as batch_op:
        # Verificar e remover se existirem
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        existing_columns = [col['name'] for col in inspector.get_columns('telegram_notification_preferences')]
        
        if 'notify_ferramentas_withdrawal' in existing_columns:
            batch_op.drop_column('notify_ferramentas_withdrawal')
        if 'notify_ferramentas_return' in existing_columns:
            batch_op.drop_column('notify_ferramentas_return')
        if 'notify_epis_withdrawal' in existing_columns:
            batch_op.drop_column('notify_epis_withdrawal')
        if 'notify_epis_return' in existing_columns:
            batch_op.drop_column('notify_epis_return')


def downgrade():
    # Adicionar colunas antigas de volta
    with op.batch_alter_table('telegram_notification_preferences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notify_epis_return', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('notify_epis_withdrawal', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('notify_ferramentas_return', sa.Boolean(), nullable=False, server_default='true'))
        batch_op.add_column(sa.Column('notify_ferramentas_withdrawal', sa.Boolean(), nullable=False, server_default='true'))
