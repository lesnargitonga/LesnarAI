#!/usr/bin/env python3
"""Interactive Postgres-backed auth user manager for LesnarAI."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from flask import Flask

from generate_auth_users_json import VALID_ROLES, generate_password_hash


REPO = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db import AuthUser, db, get_database_url  # noqa: E402


def prompt(text: str) -> str:
    return input(text).strip()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def list_users() -> list[AuthUser]:
    return AuthUser.query.order_by(AuthUser.username.asc()).all()


def upsert_user(username: str, role: str, password: str, display_name: str | None = None) -> tuple[AuthUser, bool]:
    normalized = username.strip().lower()
    row = AuthUser.query.filter_by(username=normalized).one_or_none()
    created = row is None
    if row is None:
        row = AuthUser(username=normalized)
        db.session.add(row)
    row.role = role
    row.display_name = (display_name or normalized).strip()[:128]
    row.password_hash = generate_password_hash(password)
    row.last_password_change_at = datetime.utcnow()
    db.session.commit()
    return row, created


def main() -> int:
    app = create_app()
    with app.app_context():
        db.create_all()

        print('LesnarAI user setup (Postgres-backed)')
        print('Roles: admin, operator, viewer')
        current = list_users()
        print(f'Existing users: {len(current)}')
        for row in current:
            print(f'  - {row.username} ({row.role})')
        print('Press Enter on username when finished.\n')

        while True:
            username = prompt('Username: ')
            if not username:
                break
            role = prompt('Role [admin/operator/viewer]: ').lower()
            if role not in VALID_ROLES:
                print('Invalid role. Use admin, operator, or viewer.\n')
                continue
            password = prompt('Password: ')
            if not password:
                print('Password cannot be empty.\n')
                continue
            display_name = prompt('Display name [optional]: ') or username
            row, created = upsert_user(username, role, password, display_name)
            action = 'created' if created else 'updated'
            print(f'[ok] {action} user {row.username} ({row.role})\n')

        print('\nCurrent users:')
        for row in list_users():
            print(f'  - {row.username} ({row.role})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())