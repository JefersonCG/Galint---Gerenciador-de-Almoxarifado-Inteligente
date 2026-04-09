"""add inventory categories catalog

Revision ID: 4f1c9e2a7b6d
Revises: 6f4c2d1b9a7e
Create Date: 2026-04-08
"""

from alembic import op


revision = "4f1c9e2a7b6d"
down_revision = "6f4c2d1b9a7e"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_name = 'inventory_categories'
  ) THEN
    CREATE TABLE inventory_categories (
      id serial PRIMARY KEY,
      nome varchar(120) NOT NULL UNIQUE,
      descricao text NULL,
      ordem integer NOT NULL DEFAULT 0,
      ativa boolean NOT NULL DEFAULT true,
      sistema boolean NOT NULL DEFAULT false,
      criada_por varchar(100) NULL,
      atualizada_por varchar(100) NULL,
      criado_em timestamp NOT NULL DEFAULT now(),
      atualizado_em timestamp NOT NULL DEFAULT now()
    );
  END IF;

  CREATE INDEX IF NOT EXISTS ix_inventory_categories_ativa ON inventory_categories(ativa);
END $$;
"""
    )

    op.execute(
        """
INSERT INTO inventory_categories (nome, descricao, ordem, ativa, sistema)
VALUES
  ('Material Elétrico', 'Infraestrutura elétrica e componentes de energia.', 10, true, true),
  ('Material Hidráulico', 'Tubulações, conexões e manutenção hidráulica.', 20, true, true),
  ('Material Piscina', 'Tratamento, manutenção e operação de piscina.', 30, true, true),
  ('Mat. Pintura e Drywall', 'Tintas, massas, drywall e acabamento.', 40, true, true),
  ('Materiais de Limpeza', 'Produtos e insumos de limpeza operacional.', 50, true, true),
  ('Material Construção', 'Materiais estruturais e de obra civil.', 60, true, true),
  ('Ferramentas', 'Ferramentas de uso manual e apoio técnico.', 70, true, true),
  ('Equipamento', 'Equipamentos permanentes e itens eletrificados.', 80, true, true),
  ('Material de EP', 'Equipamentos e materiais de proteção individual.', 90, true, true),
  ('Material/Uso geral', 'Itens transversais de uso geral e apoio operacional.', 100, true, true)
ON CONFLICT (nome) DO UPDATE
SET
  sistema = EXCLUDED.sistema,
  ordem = EXCLUDED.ordem,
  ativa = true,
  descricao = COALESCE(inventory_categories.descricao, EXCLUDED.descricao);
"""
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS inventory_categories")