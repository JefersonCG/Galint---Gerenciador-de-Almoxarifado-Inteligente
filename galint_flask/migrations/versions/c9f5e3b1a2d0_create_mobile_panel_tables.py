"""create_mobile_panel_tables

Revision ID: c9f5e3b1a2d0
Revises: 95c17ef714ba
Create Date: 2026-01-20 10:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c9f5e3b1a2d0"
down_revision = "95c17ef714ba"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE TYPE target_type_enum AS ENUM ('user', 'device', 'profile')")

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_uuid", postgresql.UUID(), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False, server_default="android"),
        sa.Column("manufacturer", sa.String(100)),
        sa.Column("model", sa.String(100)),
        sa.Column("os_version", sa.String(50)),
        sa.Column("apk_version", sa.String(20), nullable=False),
        sa.Column("apk_build_number", sa.Integer()),
        sa.Column("apk_channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("current_user_id", sa.String(), sa.ForeignKey("usuarios.matricula", ondelete="SET NULL")),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_heartbeat_at", sa.DateTime()),
        sa.Column("last_ip_address", postgresql.INET()),
        sa.Column("deleted_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("blocked_reason", sa.Text()),
        sa.Column("blocked_by", sa.String(), sa.ForeignKey("usuarios.matricula", ondelete="SET NULL")),
        sa.Column("blocked_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_uuid"),
    )

    op.create_index("idx_devices_uuid", "devices", ["device_uuid"])
    op.create_index(
        "idx_devices_status",
        "devices",
        ["status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_devices_user",
        "devices",
        ["current_user_id"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "idx_devices_heartbeat",
        "devices",
        [sa.text("last_heartbeat_at DESC")],
        postgresql_where=sa.text("status = 'active' AND deleted_at IS NULL"),
    )
    op.create_index("idx_devices_version", "devices", ["apk_version", "apk_channel"])

    op.create_table(
        "device_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_token_hash", sa.String(64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64)),
        sa.Column("logged_in_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("logged_out_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("revoked_by", sa.String(), sa.ForeignKey("usuarios.matricula", ondelete="SET NULL")),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("revoke_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.matricula"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token_hash"),
        sa.CheckConstraint(
            "logged_out_at IS NULL OR logged_out_at >= logged_in_at",
            name="chk_logout_after_login",
        ),
        sa.CheckConstraint(
            "expires_at >= logged_in_at",
            name="chk_expires_after_login",
        ),
    )

    op.create_index("idx_sessions_device", "device_sessions", ["device_id"])
    op.create_index("idx_sessions_user", "device_sessions", ["user_id"])
    op.create_index("idx_sessions_token", "device_sessions", ["session_token_hash"])
    op.create_index(
        "idx_sessions_active",
        "device_sessions",
        ["status", "expires_at"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "idx_sessions_active_device",
        "device_sessions",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND logged_out_at IS NULL"),
    )

    op.create_table(
        "apk_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_name", sa.String(20), nullable=False),
        sa.Column("version_code", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("release_date", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("release_notes", sa.Text()),
        sa.Column("download_url", sa.Text()),
        sa.Column("eas_build_id", sa.String(100)),
        sa.Column("eas_update_group_id", sa.String(100)),
        sa.Column("created_by", sa.String(), sa.ForeignKey("usuarios.matricula", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_name", "channel", name="uq_version_channel"),
        sa.CheckConstraint("version_code > 0", name="chk_version_positive"),
    )

    op.create_index("idx_apk_versions_channel", "apk_versions", ["channel", "is_blocked"])
    op.create_index(
        "idx_apk_versions_mandatory",
        "apk_versions",
        ["is_mandatory"],
        postgresql_where=sa.text("is_mandatory = TRUE"),
    )

    op.create_table(
        "feature_flags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("flag_key", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("flag_type", sa.String(50), nullable=False, server_default="boolean"),
        sa.Column("default_value", sa.Text()),
        sa.Column("requires_app_restart", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("min_app_version", sa.String(20)),
        sa.Column("created_by", sa.String(), sa.ForeignKey("usuarios.matricula", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("flag_key"),
    )

    op.create_index("idx_feature_flags_enabled", "feature_flags", ["is_enabled"])
    op.create_index("idx_feature_flags_key", "feature_flags", ["flag_key"])

    op.create_table(
        "feature_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "feature_flag_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "target_type",
            postgresql.ENUM("user", "device", "profile", name="target_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("override_value", sa.Text()),
        sa.Column("assigned_by", sa.String(), sa.ForeignKey("usuarios.matricula", ondelete="SET NULL")),
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("deleted_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["feature_flag_id"], ["feature_flags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_flag_id", "target_type", "target_id", name="uq_feature_assignment"),
    )

    op.create_index(
        "idx_feature_assignments_target",
        "feature_assignments",
        ["target_type", "target_id"],
    )
    op.create_index(
        "idx_feature_assignments_feature",
        "feature_assignments",
        ["feature_flag_id", "is_enabled"],
    )

    op.create_table(
        "apk_audit_logs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", sa.String(), sa.ForeignKey("usuarios.matricula", ondelete="SET NULL")),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("admin_id", sa.String(), sa.ForeignKey("usuarios.matricula", ondelete="SET NULL")),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("action_result", sa.String(20), nullable=False, server_default="success"),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("details", postgresql.JSONB()),
        sa.Column("apk_version", sa.String(20)),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("device_sessions.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_audit_occurred", "apk_audit_logs", [sa.text("occurred_at DESC")])
    op.create_index(
        "idx_audit_user",
        "apk_audit_logs",
        ["user_id"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "idx_audit_device",
        "apk_audit_logs",
        ["device_id"],
        postgresql_where=sa.text("device_id IS NOT NULL"),
    )
    op.create_index("idx_audit_action", "apk_audit_logs", ["action_type", "action_result"])
    op.create_index(
        "idx_audit_details",
        "apk_audit_logs",
        ["details"],
        postgresql_using="gin",
    )


def downgrade():
    op.drop_index("idx_audit_details", table_name="apk_audit_logs")
    op.drop_index("idx_audit_action", table_name="apk_audit_logs")
    op.drop_index("idx_audit_device", table_name="apk_audit_logs")
    op.drop_index("idx_audit_user", table_name="apk_audit_logs")
    op.drop_index("idx_audit_occurred", table_name="apk_audit_logs")
    op.drop_table("apk_audit_logs")

    op.drop_index("idx_feature_assignments_feature", table_name="feature_assignments")
    op.drop_index("idx_feature_assignments_target", table_name="feature_assignments")
    op.drop_table("feature_assignments")

    op.drop_index("idx_feature_flags_key", table_name="feature_flags")
    op.drop_index("idx_feature_flags_enabled", table_name="feature_flags")
    op.drop_table("feature_flags")

    op.drop_index("idx_apk_versions_mandatory", table_name="apk_versions")
    op.drop_index("idx_apk_versions_channel", table_name="apk_versions")
    op.drop_table("apk_versions")

    op.drop_index("idx_sessions_active_device", table_name="device_sessions")
    op.drop_index("idx_sessions_active", table_name="device_sessions")
    op.drop_index("idx_sessions_token", table_name="device_sessions")
    op.drop_index("idx_sessions_user", table_name="device_sessions")
    op.drop_index("idx_sessions_device", table_name="device_sessions")
    op.drop_table("device_sessions")

    op.drop_index("idx_devices_version", table_name="devices")
    op.drop_index("idx_devices_heartbeat", table_name="devices")
    op.drop_index("idx_devices_user", table_name="devices")
    op.drop_index("idx_devices_status", table_name="devices")
    op.drop_index("idx_devices_uuid", table_name="devices")
    op.drop_table("devices")

    op.execute("DROP TYPE IF EXISTS target_type_enum")
