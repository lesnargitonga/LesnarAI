"""init core models

Revision ID: 0001_init_core_models
Revises: 
Create Date: 2026-01-04

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0001_init_core_models"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    insp = inspect(conn)
    return name in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    if not _has_table(conn, "command_logs"):
        op.create_table(
            "command_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("drone_id", sa.String(length=128), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("success", sa.Boolean(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_command_logs_drone_id", "command_logs", ["drone_id"], unique=False)
        op.create_index("ix_command_logs_action", "command_logs", ["action"], unique=False)
        op.create_index("ix_command_logs_created_at", "command_logs", ["created_at"], unique=False)

    if not _has_table(conn, "drones"):
        op.create_table(
            "drones",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("drone_id", sa.String(length=128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("home_position_json", sa.Text(), nullable=True),
            sa.Column("config_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("drone_id", name="uq_drones_drone_id"),
        )
        op.create_index("ix_drones_enabled", "drones", ["enabled"], unique=False)

    if not _has_table(conn, "missions"):
        op.create_table(
            "missions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=True),
            sa.Column("mission_type", sa.String(length=64), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_missions_mission_type", "missions", ["mission_type"], unique=False)
        op.create_index("ix_missions_created_at", "missions", ["created_at"], unique=False)

    if not _has_table(conn, "mission_runs"):
        op.create_table(
            "mission_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("mission_id", sa.Integer(), nullable=False),
            sa.Column("drone_id", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["mission_id"], ["missions.id"], name="fk_mission_runs_mission_id"),
        )
        op.create_index("ix_mission_runs_drone_id", "mission_runs", ["drone_id"], unique=False)
        op.create_index("ix_mission_runs_status", "mission_runs", ["status"], unique=False)
        op.create_index("ix_mission_runs_created_at", "mission_runs", ["created_at"], unique=False)

    if not _has_table(conn, "events"):
        op.create_table(
            "events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("drone_id", sa.String(length=128), nullable=True),
            sa.Column("mission_run_id", sa.Integer(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["mission_run_id"], ["mission_runs.id"], name="fk_events_mission_run_id"),
        )
        op.create_index("ix_events_event_type", "events", ["event_type"], unique=False)
        op.create_index("ix_events_created_at", "events", ["created_at"], unique=False)


def downgrade() -> None:
    # Conservative downgrade: drop only tables created by this migration.
    conn = op.get_bind()
    insp = inspect(conn)
    tables = set(insp.get_table_names())

    if "events" in tables:
        op.drop_table("events")
    if "mission_runs" in tables:
        op.drop_table("mission_runs")
    if "missions" in tables:
        op.drop_table("missions")
    if "drones" in tables:
        op.drop_table("drones")
    # Do not drop command_logs by default.
