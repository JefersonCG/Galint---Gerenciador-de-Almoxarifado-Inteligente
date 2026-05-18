"""extend messenger package logs

Revision ID: d5e6f7a8b9c1
Revises: c4d5e6f7a8b9
Create Date: 2026-05-18
"""

from alembic import op


revision = "d5e6f7a8b9c1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
ALTER TABLE condominium_package_logs ADD COLUMN IF NOT EXISTS stored_at timestamp NULL;
ALTER TABLE condominium_package_logs ADD COLUMN IF NOT EXISTS notified_at timestamp NULL;
ALTER TABLE condominium_package_logs ADD COLUMN IF NOT EXISTS storage_location varchar(80) NULL;
ALTER TABLE condominium_package_logs ADD COLUMN IF NOT EXISTS delivered_to varchar(180) NULL;
ALTER TABLE condominium_package_logs ADD COLUMN IF NOT EXISTS stored_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL;
ALTER TABLE condominium_package_logs ADD COLUMN IF NOT EXISTS notified_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_condominium_package_logs_storage_location ON condominium_package_logs(storage_location);
"""
    )


def downgrade():
    op.execute(
        """
DROP INDEX IF EXISTS ix_condominium_package_logs_storage_location;
ALTER TABLE condominium_package_logs DROP COLUMN IF EXISTS notified_by_matricula;
ALTER TABLE condominium_package_logs DROP COLUMN IF EXISTS stored_by_matricula;
ALTER TABLE condominium_package_logs DROP COLUMN IF EXISTS delivered_to;
ALTER TABLE condominium_package_logs DROP COLUMN IF EXISTS storage_location;
ALTER TABLE condominium_package_logs DROP COLUMN IF EXISTS notified_at;
ALTER TABLE condominium_package_logs DROP COLUMN IF EXISTS stored_at;
"""
    )