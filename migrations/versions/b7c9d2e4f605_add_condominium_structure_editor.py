"""add condominium structure editor

Revision ID: b7c9d2e4f605
Revises: a9d4e6f2c1b8
Create Date: 2026-05-06
"""

from alembic import op


revision = "b7c9d2e4f605"
down_revision = "a9d4e6f2c1b8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
CREATE TABLE IF NOT EXISTS condominium_buildings (
  id serial PRIMARY KEY,
  code varchar(30) NOT NULL,
  name varchar(120) NOT NULL,
  display_order integer NOT NULL DEFAULT 0,
  floor_start integer NOT NULL DEFAULT 1,
  floor_count integer NOT NULL DEFAULT 1,
  units_per_floor integer NOT NULL DEFAULT 0,
  unit_suffix_start integer NOT NULL DEFAULT 0,
  suffix_width integer NOT NULL DEFAULT 2,
  numbering_mode varchar(30) NOT NULL DEFAULT 'floor_suffix',
  custom_units_text text NULL,
  notes text NULL,
  active boolean NOT NULL DEFAULT true,
  created_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  updated_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_condominium_buildings_code ON condominium_buildings(code);
CREATE INDEX IF NOT EXISTS ix_condominium_buildings_code ON condominium_buildings(code);
CREATE INDEX IF NOT EXISTS ix_condominium_buildings_active ON condominium_buildings(active);

CREATE TABLE IF NOT EXISTS condominium_units (
  id serial PRIMARY KEY,
  building_id integer NOT NULL REFERENCES condominium_buildings(id) ON DELETE CASCADE,
  number varchar(40) NOT NULL,
  floor_number integer NOT NULL DEFAULT 1,
  position integer NOT NULL DEFAULT 1,
  status varchar(20) NOT NULL DEFAULT 'vago',
  unit_type varchar(30) NOT NULL DEFAULT 'residencial',
  notes text NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_condominium_units_building_number ON condominium_units(building_id, number);
CREATE INDEX IF NOT EXISTS ix_condominium_units_building_id ON condominium_units(building_id);
CREATE INDEX IF NOT EXISTS ix_condominium_units_floor_number ON condominium_units(floor_number);
CREATE INDEX IF NOT EXISTS ix_condominium_units_status ON condominium_units(status);
CREATE INDEX IF NOT EXISTS ix_condominium_units_active ON condominium_units(active);

CREATE TABLE IF NOT EXISTS condominium_owners (
  id serial PRIMARY KEY,
  unit_id integer NULL REFERENCES condominium_units(id) ON DELETE SET NULL,
  relationship_type varchar(30) NOT NULL DEFAULT 'proprietario',
  person_type varchar(20) NOT NULL DEFAULT 'fisica',
  full_name varchar(180) NOT NULL,
  document_number varchar(32) NOT NULL,
  rg varchar(32) NULL,
  cnh varchar(32) NULL,
  phone varchar(40) NULL,
  email varchar(160) NULL,
  correspondence_address text NULL,
  emergency_contact varchar(160) NULL,
  occupancy_status varchar(30) NOT NULL DEFAULT 'nao_informado',
  photo_path varchar(255) NULL,
  lgpd_authorized boolean NOT NULL DEFAULT false,
  status varchar(20) NOT NULL DEFAULT 'ativo',
  notes text NULL,
  created_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  updated_by_matricula varchar NULL REFERENCES usuarios(matricula) ON DELETE SET NULL,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_condominium_owners_unit_id ON condominium_owners(unit_id);
CREATE INDEX IF NOT EXISTS ix_condominium_owners_relationship_type ON condominium_owners(relationship_type);
CREATE INDEX IF NOT EXISTS ix_condominium_owners_full_name ON condominium_owners(full_name);
CREATE INDEX IF NOT EXISTS ix_condominium_owners_document_number ON condominium_owners(document_number);
CREATE INDEX IF NOT EXISTS ix_condominium_owners_status ON condominium_owners(status);
"""
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS condominium_owners")
    op.execute("DROP TABLE IF EXISTS condominium_units")
    op.execute("DROP TABLE IF EXISTS condominium_buildings")