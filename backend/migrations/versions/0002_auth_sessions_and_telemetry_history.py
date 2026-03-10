"""auth sessions telemetry history and actor attribution

Revision ID: 0002_auth_sessions_telemetry
Revises: 0001_init_core_models
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0002_auth_sessions_telemetry"
down_revision = "0001_init_core_models"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    insp = inspect(conn)
    return name in insp.get_table_names()


def _has_column(conn, table: str, column: str) -> bool:
    insp = inspect(conn)
    return any(col["name"] == column for col in insp.get_columns(table))


def _has_index(conn, table: str, index_name: str) -> bool:
    insp = inspect(conn)
    return any(idx["name"] == index_name for idx in insp.get_indexes(table))


def upgrade() -> None:
    conn = op.get_bind()

    if _has_table(conn, "command_logs"):
        for column_name, column_type in [
            ("operator_id", sa.String(length=128)),
            ("operator_role", sa.String(length=32)),
            ("session_id", sa.String(length=128)),
        ]:
            if not _has_column(conn, "command_logs", column_name):
                op.add_column("command_logs", sa.Column(column_name, column_type, nullable=True))
        if not _has_index(conn, "command_logs", "ix_command_logs_operator_id"):
            op.create_index("ix_command_logs_operator_id", "command_logs", ["operator_id"], unique=False)
        if not _has_index(conn, "command_logs", "ix_command_logs_session_id"):
            op.create_index("ix_command_logs_session_id", "command_logs", ["session_id"], unique=False)

    if _has_table(conn, "events"):
        for column_name, column_type in [
            ("operator_id", sa.String(length=128)),
            ("operator_role", sa.String(length=32)),
            ("session_id", sa.String(length=128)),
        ]:
            if not _has_column(conn, "events", column_name):
                op.add_column("events", sa.Column(column_name, column_type, nullable=True))
        if not _has_index(conn, "events", "ix_events_operator_id"):
            op.create_index("ix_events_operator_id", "events", ["operator_id"], unique=False)
        if not _has_index(conn, "events", "ix_events_session_id"):
            op.create_index("ix_events_session_id", "events", ["session_id"], unique=False)

    if not _has_table(conn, "auth_sessions"):
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.String(length=128), nullable=False),
            sa.Column("username", sa.String(length=128), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("issued_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.UniqueConstraint("session_id", name="uq_auth_sessions_session_id"),
        )
        op.create_index("ix_auth_sessions_session_id", "auth_sessions", ["session_id"], unique=False)
        op.create_index("ix_auth_sessions_username", "auth_sessions", ["username"], unique=False)
        op.create_index("ix_auth_sessions_role", "auth_sessions", ["role"], unique=False)
        op.create_index("ix_auth_sessions_issued_at", "auth_sessions", ["issued_at"], unique=False)
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], unique=False)
        op.create_index("ix_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"], unique=False)

    if not _has_table(conn, "telemetry_samples"):
        op.create_table(
            "telemetry_samples",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("drone_id", sa.String(length=128), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("altitude", sa.Float(), nullable=False),
            sa.Column("heading", sa.Float(), nullable=True),
            sa.Column("speed", sa.Float(), nullable=True),
            sa.Column("battery", sa.Float(), nullable=True),
            sa.Column("armed", sa.Boolean(), nullable=True),
            sa.Column("mode", sa.String(length=64), nullable=True),
            sa.Column("source_timestamp", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_telemetry_samples_drone_id", "telemetry_samples", ["drone_id"], unique=False)
        op.create_index("ix_telemetry_samples_mode", "telemetry_samples", ["mode"], unique=False)
        op.create_index("ix_telemetry_samples_source_timestamp", "telemetry_samples", ["source_timestamp"], unique=False)
        op.create_index("ix_telemetry_samples_created_at", "telemetry_samples", ["created_at"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    tables = set(insp.get_table_names())

    if "telemetry_samples" in tables:
        op.drop_table("telemetry_samples")
    if "auth_sessions" in tables:
        op.drop_table("auth_sessions")
