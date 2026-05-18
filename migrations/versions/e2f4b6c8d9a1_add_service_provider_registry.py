"""add service provider registry

Revision ID: e2f4b6c8d9a1
Revises: d8f0c3a2b9e1
Create Date: 2026-05-18
"""

from alembic import op


revision = "e2f4b6c8d9a1"
down_revision = "d8f0c3a2b9e1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
CREATE TABLE IF NOT EXISTS service_companies (
  id serial PRIMARY KEY,
  corporate_name varchar(180) NOT NULL,
  trade_name varchar(180) NULL,
  cnpj varchar(18) NOT NULL,
  state_registration varchar(40) NULL,
  municipal_registration varchar(40) NULL,
  phone varchar(40) NULL,
  whatsapp varchar(40) NULL,
  email varchar(160) NULL,
  address text NULL,
  legal_representative_name varchar(180) NULL,
  legal_representative_cpf varchar(18) NULL,
  contract_start_date date NULL,
  contract_end_date date NULL,
  service_types_json jsonb NULL,
  monthly_contract_value double precision NULL,
  status varchar(20) NOT NULL DEFAULT 'ativo',
  notes text NULL,
  lgpd_authorized boolean NOT NULL DEFAULT false,
  created_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  updated_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_service_companies_cnpj ON service_companies(cnpj);
CREATE INDEX IF NOT EXISTS ix_service_companies_corporate_name ON service_companies(corporate_name);
CREATE INDEX IF NOT EXISTS ix_service_companies_trade_name ON service_companies(trade_name);
CREATE INDEX IF NOT EXISTS ix_service_companies_contract_end_date ON service_companies(contract_end_date);
CREATE INDEX IF NOT EXISTS ix_service_companies_status ON service_companies(status);

CREATE TABLE IF NOT EXISTS service_provider_employees (
  id serial PRIMARY KEY,
  company_id integer NOT NULL REFERENCES service_companies(id) ON DELETE CASCADE,
  full_name varchar(180) NOT NULL,
  cpf varchar(18) NOT NULL,
  rg varchar(32) NULL,
  role varchar(120) NULL,
  phone varchar(40) NULL,
  vehicle_plate varchar(16) NULL,
  recurring_days_json jsonb NULL,
  usual_schedule varchar(80) NULL,
  status varchar(20) NOT NULL DEFAULT 'ativo',
  notes text NULL,
  lgpd_authorized boolean NOT NULL DEFAULT false,
  created_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  updated_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_service_provider_employees_cpf ON service_provider_employees(cpf);
CREATE INDEX IF NOT EXISTS ix_service_provider_employees_company_id ON service_provider_employees(company_id);
CREATE INDEX IF NOT EXISTS ix_service_provider_employees_full_name ON service_provider_employees(full_name);
CREATE INDEX IF NOT EXISTS ix_service_provider_employees_vehicle_plate ON service_provider_employees(vehicle_plate);
CREATE INDEX IF NOT EXISTS ix_service_provider_employees_status ON service_provider_employees(status);
"""
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS service_provider_employees")
    op.execute("DROP TABLE IF EXISTS service_companies")