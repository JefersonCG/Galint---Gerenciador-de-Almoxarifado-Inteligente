"""add condominium schedule events

Revision ID: c4f8a2b1d906
Revises: b7c9d2e4f605
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "c4f8a2b1d906"
down_revision = "b7c9d2e4f605"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("condominium_schedule_events"):
        op.create_table(
            "condominium_schedule_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("event_date", sa.Date(), nullable=False),
            sa.Column("start_time", sa.Time(), nullable=True),
            sa.Column("end_time", sa.Time(), nullable=True),
            sa.Column("title", sa.String(length=180), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False, server_default="compromisso"),
            sa.Column("scope", sa.String(length=40), nullable=False, server_default="administracao"),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="agendado"),
            sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
            sa.Column("building_id", sa.Integer(), nullable=True),
            sa.Column("unit_id", sa.Integer(), nullable=True),
            sa.Column("owner_id", sa.Integer(), nullable=True),
            sa.Column("contact_name", sa.String(length=160), nullable=True),
            sa.Column("contact_phone", sa.String(length=40), nullable=True),
            sa.Column("location", sa.String(length=160), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("notify_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("reminder_minutes", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("notification_acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("created_by_matricula", sa.String(), nullable=True),
            sa.Column("updated_by_matricula", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["building_id"], ["condominium_buildings.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["unit_id"], ["condominium_units.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["owner_id"], ["condominium_owners.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_matricula"], ["usuarios.matricula"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_matricula"], ["usuarios.matricula"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_condominium_schedule_events_event_date"), "condominium_schedule_events", ["event_date"], unique=False)
        op.create_index(op.f("ix_condominium_schedule_events_event_type"), "condominium_schedule_events", ["event_type"], unique=False)
        op.create_index(op.f("ix_condominium_schedule_events_scope"), "condominium_schedule_events", ["scope"], unique=False)
        op.create_index(op.f("ix_condominium_schedule_events_status"), "condominium_schedule_events", ["status"], unique=False)
        op.create_index(op.f("ix_condominium_schedule_events_building_id"), "condominium_schedule_events", ["building_id"], unique=False)
        op.create_index(op.f("ix_condominium_schedule_events_unit_id"), "condominium_schedule_events", ["unit_id"], unique=False)
        op.create_index(op.f("ix_condominium_schedule_events_owner_id"), "condominium_schedule_events", ["owner_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("condominium_schedule_events"):
        op.drop_index(op.f("ix_condominium_schedule_events_owner_id"), table_name="condominium_schedule_events")
        op.drop_index(op.f("ix_condominium_schedule_events_unit_id"), table_name="condominium_schedule_events")
        op.drop_index(op.f("ix_condominium_schedule_events_building_id"), table_name="condominium_schedule_events")
        op.drop_index(op.f("ix_condominium_schedule_events_status"), table_name="condominium_schedule_events")
        op.drop_index(op.f("ix_condominium_schedule_events_scope"), table_name="condominium_schedule_events")
        op.drop_index(op.f("ix_condominium_schedule_events_event_type"), table_name="condominium_schedule_events")
        op.drop_index(op.f("ix_condominium_schedule_events_event_date"), table_name="condominium_schedule_events")
        op.drop_table("condominium_schedule_events")
