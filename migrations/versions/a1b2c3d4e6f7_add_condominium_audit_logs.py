"""add condominium audit logs

Revision ID: a1b2c3d4e6f7
Revises: f6a1b2c3d4e5
Create Date: 2026-05-18
"""

from alembic import op


revision = "a1b2c3d4e6f7"
down_revision = "f6a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
CREATE TABLE IF NOT EXISTS condominium_audit_logs (
  id serial PRIMARY KEY,
  occurred_at timestamp NOT NULL DEFAULT now(),
  actor_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  action varchar(80) NOT NULL,
  entity_type varchar(80) NOT NULL,
  entity_id integer NULL,
  title varchar(220) NOT NULL,
  details_json jsonb NULL,
  ip_address varchar(64) NULL,
  user_agent varchar(255) NULL
);
CREATE INDEX IF NOT EXISTS ix_condominium_audit_logs_occurred_at ON condominium_audit_logs(occurred_at);
CREATE INDEX IF NOT EXISTS ix_condominium_audit_logs_actor_matricula ON condominium_audit_logs(actor_matricula);
CREATE INDEX IF NOT EXISTS ix_condominium_audit_logs_action ON condominium_audit_logs(action);
CREATE INDEX IF NOT EXISTS ix_condominium_audit_logs_entity_type ON condominium_audit_logs(entity_type);
CREATE INDEX IF NOT EXISTS ix_condominium_audit_logs_entity_id ON condominium_audit_logs(entity_id);
"""
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS condominium_audit_logs")