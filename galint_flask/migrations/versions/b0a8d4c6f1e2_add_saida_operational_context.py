"""add_saida_operational_context

Revision ID: b0a8d4c6f1e2
Revises: d4a8f2e5b1c3
Create Date: 2026-04-04 10:30:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b0a8d4c6f1e2"
down_revision = "d4a8f2e5b1c3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("saidas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("atividade_operacional", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("ordem_servico", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("centro_custo", sa.String(length=120), nullable=True))


def downgrade():
    with op.batch_alter_table("saidas", schema=None) as batch_op:
        batch_op.drop_column("centro_custo")
        batch_op.drop_column("ordem_servico")
        batch_op.drop_column("atividade_operacional")