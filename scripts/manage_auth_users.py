#!/usr/bin/env python3
"""Beginner-friendly interactive auth user manager for LesnarAI."""

from __future__ import annotations

import json
from pathlib import Path

from generate_auth_users_json import VALID_ROLES, generate_password_hash


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / 'auth_users.json'
ENV_FILE = REPO / '.env.secure'


def prompt(text: str) -> str:
    return input(text).strip()


def load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def upsert_user(users: list[dict], username: str, role: str, password: str) -> list[dict]:
    hashed = generate_password_hash(password)
    out = [u for u in users if str(u.get('username') or '').strip() != username]
    out.append({
        'username': username,
        'role': role,
        'display_name': username,
        'password_hash': hashed,
    })
    out.sort(key=lambda item: str(item.get('username') or '').lower())
    return out


def update_env_secure(users: list[dict]) -> None:
    if not ENV_FILE.exists():
        print(f'[skip] {ENV_FILE} not found; not updating env file')
        return
    lines = ENV_FILE.read_text(encoding='utf-8').splitlines(keepends=True)
    payload = json.dumps(users, separators=(',', ':'))
    replaced = False
    updated: list[str] = []
    for raw in lines:
        if raw.startswith('LESNAR_AUTH_USERS_JSON='):
            updated.append(f'LESNAR_AUTH_USERS_JSON={payload}\n')
            replaced = True
        else:
            updated.append(raw)
    if not replaced:
        updated.append(f'LESNAR_AUTH_USERS_JSON={payload}\n')
    ENV_FILE.write_text(''.join(updated), encoding='utf-8')
    print(f'[ok] updated {ENV_FILE}')


def main() -> int:
    output = DEFAULT_OUTPUT
    users = load_existing(output)
    print('LesnarAI user setup')
    print('Roles: admin, operator, viewer')
    print('This file can be reused later when you need new users.')
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
        users = upsert_user(users, username, role, password)
        print(f'[ok] saved user {username} ({role})\n')

    output.write_text(json.dumps(users, indent=2) + '\n', encoding='utf-8')
    print(f'[ok] wrote {output}')
    update_env_secure(users)
    print('\nNext:')
    print('  python3 scripts/bootstrap_secure_deployment.py --auth-users-json-file auth_users.json --force')
    print('If .env.secure already exists, your users are also written there automatically.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())