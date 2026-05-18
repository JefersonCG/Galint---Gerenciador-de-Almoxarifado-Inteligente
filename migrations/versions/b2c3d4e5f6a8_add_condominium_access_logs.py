"""add condominium access logs

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e6f7
Create Date: 2026-05-18
"""

from alembic import op


revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
CREATE TABLE IF NOT EXISTS condominium_access_logs (
  id serial PRIMARY KEY,
  occurred_at timestamp NOT NULL DEFAULT now(),
  direction varchar(20) NOT NULL DEFAULT 'entrada',
  access_status varchar(24) NOT NULL DEFAULT 'liberado',
  person_type varchar(30) NOT NULL DEFAULT 'visitante',
  person_name varchar(180) NOT NULL,
  document_number varchar(32) NULL,
  vehicle_plate varchar(16) NULL,
  purpose varchar(160) NULL,
  notes text NULL,
  unit_id integer NULL REFERENCES condominium_units(id) ON DELETE SET NULL,
  owner_id integer NULL REFERENCES condominium_owners(id) ON DELETE SET NULL,
  service_company_id integer NULL REFERENCES service_companies(id) ON DELETE SET NULL,
  service_employee_id integer NULL REFERENCES service_provider_employees(id) ON DELETE SET NULL,
  authorized_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  created_at timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_occurred_at ON condominium_access_logs(occurred_at);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_direction ON condominium_access_logs(direction);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_access_status ON condominium_access_logs(access_status);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_person_type ON condominium_access_logs(person_type);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_person_name ON condominium_access_logs(person_name);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_document_number ON condominium_access_logs(document_number);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_vehicle_plate ON condominium_access_logs(vehicle_plate);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_unit_id ON condominium_access_logs(unit_id);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_owner_id ON condominium_access_logs(owner_id);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_service_company_id ON condominium_access_logs(service_company_id);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_service_employee_id ON condominium_access_logs(service_employee_id);
CREATE INDEX IF NOT EXISTS ix_condominium_access_logs_authorized_by_matricula ON condominium_access_logs(authorized_by_matricula);
"""
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS condominium_access_logs")