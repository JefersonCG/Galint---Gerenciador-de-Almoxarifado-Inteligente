"""Add server_default to data_entrada field for immutability

Revision ID: 77f4bc1bda12
Revises: 616036e9b6f8
Create Date: 2026-02-02 11:52:26.085033

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '77f4bc1bda12'
down_revision = '616036e9b6f8'
branch_labels = None
depends_on = None


def upgrade():
    # Adicionar server_default=func.now() no campo data_entrada para blindagem
    # A mudança é apenas no código Python (models.py), sem SQL necessário
    pass


def downgrade():
    # Remover server_default (reverter para nullable sem default)
    pass
