"""Add telegram notification preferences clean

Revision ID: notif_prefs_001
Revises: 
Create Date: 2026-01-30 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'notif_prefs_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Adicionar colunas de preferências de notificação
    with op.batch_alter_table('telegram_notification_preferences', schema=None) as batch_op:
        # Verificar e adicionar colunas se não existirem
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        existing_columns = [col['name'] for col in inspector.get_columns('telegram_notification_preferences')]
        
        # Ferramentas
        if 'notify_ferramenta_withdrawal' not in existing_columns:
            batch_op.add_column(sa.Column('notify_ferramenta_withdrawal', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de retirada de ferramentas'))
        if 'notify_ferramenta_return' not in existing_columns:
            batch_op.add_column(sa.Column('notify_ferramenta_return', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de devolução de ferramentas'))
        
        # Limpeza
        if 'notify_limpeza_withdrawal' not in existing_columns:
            batch_op.add_column(sa.Column('notify_limpeza_withdrawal', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de retirada de materiais de limpeza'))
        if 'notify_limpeza_return' not in existing_columns:
            batch_op.add_column(sa.Column('notify_limpeza_return', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de devolução de materiais de limpeza'))
        
        # Elétrico
        if 'notify_eletrico_withdrawal' not in existing_columns:
            batch_op.add_column(sa.Column('notify_eletrico_withdrawal', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de retirada de materiais elétricos'))
        if 'notify_eletrico_return' not in existing_columns:
            batch_op.add_column(sa.Column('notify_eletrico_return', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de devolução de materiais elétricos'))
        
        # Hidráulico
        if 'notify_hidraulico_withdrawal' not in existing_columns:
            batch_op.add_column(sa.Column('notify_hidraulico_withdrawal', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de retirada de materiais hidráulicos'))
        if 'notify_hidraulico_return' not in existing_columns:
            batch_op.add_column(sa.Column('notify_hidraulico_return', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de devolução de materiais hidráulicos'))
        
        # Construção
        if 'notify_construcao_withdrawal' not in existing_columns:
            batch_op.add_column(sa.Column('notify_construcao_withdrawal', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de retirada de materiais de construção'))
        if 'notify_construcao_return' not in existing_columns:
            batch_op.add_column(sa.Column('notify_construcao_return', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de devolução de materiais de construção'))
        
        # Pintura/Drywall
        if 'notify_pintura_withdrawal' not in existing_columns:
            batch_op.add_column(sa.Column('notify_pintura_withdrawal', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de retirada de materiais de pintura/drywall'))
        if 'notify_pintura_return' not in existing_columns:
            batch_op.add_column(sa.Column('notify_pintura_return', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de devolução de materiais de pintura/drywall'))
        
        # Piscina
        if 'notify_piscina_withdrawal' not in existing_columns:
            batch_op.add_column(sa.Column('notify_piscina_withdrawal', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de retirada de materiais de piscina'))
        if 'notify_piscina_return' not in existing_columns:
            batch_op.add_column(sa.Column('notify_piscina_return', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de devolução de materiais de piscina'))
        
        # EPIs
        if 'notify_epi_withdrawal' not in existing_columns:
            batch_op.add_column(sa.Column('notify_epi_withdrawal', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de retirada de EPIs'))
        if 'notify_epi_return' not in existing_columns:
            batch_op.add_column(sa.Column('notify_epi_return', sa.Boolean(), nullable=False, server_default='true', comment='Receber notificações de devolução de EPIs'))


def downgrade():
    # Remover colunas de preferências
    with op.batch_alter_table('telegram_notification_preferences', schema=None) as batch_op:
        batch_op.drop_column('notify_epi_return')
        batch_op.drop_column('notify_epi_withdrawal')
        batch_op.drop_column('notify_piscina_return')
        batch_op.drop_column('notify_piscina_withdrawal')
        batch_op.drop_column('notify_pintura_return')
        batch_op.drop_column('notify_pintura_withdrawal')
        batch_op.drop_column('notify_construcao_return')
        batch_op.drop_column('notify_construcao_withdrawal')
        batch_op.drop_column('notify_hidraulico_return')
        batch_op.drop_column('notify_hidraulico_withdrawal')
        batch_op.drop_column('notify_eletrico_return')
        batch_op.drop_column('notify_eletrico_withdrawal')
        batch_op.drop_column('notify_limpeza_return')
        batch_op.drop_column('notify_limpeza_withdrawal')
        batch_op.drop_column('notify_ferramenta_return')
        batch_op.drop_column('notify_ferramenta_withdrawal')
