"""add condominium operations tables

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a8
Create Date: 2026-05-18
"""

from alembic import op


revision = "c4d5e6f7a8b9"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
CREATE TABLE IF NOT EXISTS condominium_maintenance_tickets (
  id serial PRIMARY KEY,
  opened_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now(),
  due_date date NULL,
  closed_at timestamp NULL,
  title varchar(180) NOT NULL,
  description text NULL,
  category varchar(40) NOT NULL DEFAULT 'manutencao',
  priority varchar(20) NOT NULL DEFAULT 'normal',
  status varchar(24) NOT NULL DEFAULT 'aberto',
  unit_id integer NULL REFERENCES condominium_units(id) ON DELETE SET NULL,
  building_id integer NULL REFERENCES condominium_buildings(id) ON DELETE SET NULL,
  owner_id integer NULL REFERENCES condominium_owners(id) ON DELETE SET NULL,
  service_company_id integer NULL REFERENCES service_companies(id) ON DELETE SET NULL,
  service_employee_id integer NULL REFERENCES service_provider_employees(id) ON DELETE SET NULL,
  notes text NULL,
  created_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  updated_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_opened_at ON condominium_maintenance_tickets(opened_at);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_due_date ON condominium_maintenance_tickets(due_date);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_title ON condominium_maintenance_tickets(title);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_category ON condominium_maintenance_tickets(category);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_priority ON condominium_maintenance_tickets(priority);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_status ON condominium_maintenance_tickets(status);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_unit_id ON condominium_maintenance_tickets(unit_id);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_building_id ON condominium_maintenance_tickets(building_id);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_owner_id ON condominium_maintenance_tickets(owner_id);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_service_company_id ON condominium_maintenance_tickets(service_company_id);
CREATE INDEX IF NOT EXISTS ix_condominium_maintenance_tickets_service_employee_id ON condominium_maintenance_tickets(service_employee_id);

CREATE TABLE IF NOT EXISTS condominium_package_logs (
  id serial PRIMARY KEY,
  received_at timestamp NOT NULL DEFAULT now(),
  delivered_at timestamp NULL,
  status varchar(24) NOT NULL DEFAULT 'recebido',
  recipient_name varchar(180) NOT NULL,
  tracking_code varchar(80) NULL,
  carrier varchar(80) NULL,
  package_type varchar(40) NOT NULL DEFAULT 'encomenda',
  unit_id integer NULL REFERENCES condominium_units(id) ON DELETE SET NULL,
  owner_id integer NULL REFERENCES condominium_owners(id) ON DELETE SET NULL,
  notes text NULL,
  created_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  delivered_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_condominium_package_logs_received_at ON condominium_package_logs(received_at);
CREATE INDEX IF NOT EXISTS ix_condominium_package_logs_status ON condominium_package_logs(status);
CREATE INDEX IF NOT EXISTS ix_condominium_package_logs_recipient_name ON condominium_package_logs(recipient_name);
CREATE INDEX IF NOT EXISTS ix_condominium_package_logs_tracking_code ON condominium_package_logs(tracking_code);
CREATE INDEX IF NOT EXISTS ix_condominium_package_logs_package_type ON condominium_package_logs(package_type);
CREATE INDEX IF NOT EXISTS ix_condominium_package_logs_unit_id ON condominium_package_logs(unit_id);
CREATE INDEX IF NOT EXISTS ix_condominium_package_logs_owner_id ON condominium_package_logs(owner_id);
"""
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS condominium_package_logs")
    op.execute("DROP TABLE IF EXISTS condominium_maintenance_tickets")