"""add_retiradas_ferramentas_table

Revision ID: d4a8f2e5b1c3
Revises: c9f5e3b1a2d0
Create Date: 2026-01-20 14:30:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4a8f2e5b1c3"
down_revision = "c9f5e3b1a2d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "retiradas_ferramentas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo_item", sa.String(length=20), nullable=False),
        sa.Column("matricula", sa.String(length=20), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("local_servico", sa.String(length=200), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("data_retirada", sa.DateTime(), nullable=False),
        sa.Column("data_devolucao", sa.DateTime(), nullable=True),
        sa.Column("observacao_reparo", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="em_uso"),
        sa.CheckConstraint("quantidade > 0", name="ck_quantidade_positiva"),
        sa.CheckConstraint(
            "status IN ('em_uso', 'devolvida', 'atrasada', 'para_reparo')",
            name="ck_status_valido"
        ),
        sa.ForeignKeyConstraint(["codigo_item"], ["itens.codigo"], name="fk_retiradas_codigo_item"),
        sa.ForeignKeyConstraint(["matricula"], ["usuarios.matricula"], name="fk_retiradas_matricula"),
        sa.PrimaryKeyConstraint("id", name="pk_retiradas_ferramentas")
    )
    op.create_index(
        "ix_retiradas_status_data",
        "retiradas_ferramentas",
        ["status", "data_retirada"],
        unique=False
    )


def downgrade():
    op.drop_index("ix_retiradas_status_data", table_name="retiradas_ferramentas")
    op.drop_table("retiradas_ferramentas")
