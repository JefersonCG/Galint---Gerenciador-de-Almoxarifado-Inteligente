"""add document illustration path

Revision ID: f2b3c4d5e6a7
Revises: f1a2b3c4d5e6
"""
from alembic import op

revision = "f2b3c4d5e6a7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE entrada_documentos ADD COLUMN IF NOT EXISTS imagem_secundaria_path varchar(255)")


def downgrade():
    op.execute("ALTER TABLE entrada_documentos DROP COLUMN IF EXISTS imagem_secundaria_path")