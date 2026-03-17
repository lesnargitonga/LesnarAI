"""auth users table

Revision ID: 0003_auth_users_table
Revises: 0002_auth_sessions_telemetry
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0003_auth_users_table"
down_revision = "0002_auth_sessions_telemetry"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    insp = inspect(conn)
    return name in insp.get_table_names()


def _has_index(conn, table: str, index_name: str) -> bool:
    insp = inspect(conn)
    return any(idx["name"] == index_name for idx in insp.get_indexes(table))


def upgrade() -> None:
    conn = op.get_bind()
    if _has_table(conn, "auth_users"):
        return

    op.create_table(
        "auth_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_password_change_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("username", name="uq_auth_users_username"),
    )
    if not _has_index(conn, "auth_users", "ix_auth_users_username"):
        op.create_index("ix_auth_users_username", "auth_users", ["username"], unique=False)
    if not _has_index(conn, "auth_users", "ix_auth_users_role"):
        op.create_index("ix_auth_users_role", "auth_users", ["role"], unique=False)
    if not _has_index(conn, "auth_users", "ix_auth_users_created_at"):
        op.create_index("ix_auth_users_created_at", "auth_users", ["created_at"], unique=False)
    if not _has_index(conn, "auth_users", "ix_auth_users_last_password_change_at"):
        op.create_index("ix_auth_users_last_password_change_at", "auth_users", ["last_password_change_at"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    if _has_table(conn, "auth_users"):
        op.drop_table("auth_users")