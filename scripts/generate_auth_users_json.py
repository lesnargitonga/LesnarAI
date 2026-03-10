#!/usr/bin/env python3
"""Generate LESNAR_AUTH_USERS_JSON from usernames, roles, and passwords.

Examples:
  python3 scripts/generate_auth_users_json.py \
    --user admin:admin:CorrectHorseBatteryStaple \
    --user ops:operator:AnotherStrongPassword \
    --user viewer:viewer:ReadOnlyPass
"""

import argparse
import hashlib
import hmac
import json
import secrets
import sys

VALID_ROLES = {'admin', 'operator', 'viewer'}


def generate_password_hash(password: str, *, iterations: int = 390000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f'pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}'


def parse_user(raw: str) -> dict:
    parts = raw.split(':', 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid user format: {raw}. Expected username:role:password")
    username, role, password = [p.strip() for p in parts]
    if not username or not role or not password:
        raise ValueError(f"Invalid user format: {raw}. Empty field found")
    role = role.lower()
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role for {username}: {role}. Use one of admin, operator, viewer")
    return {
        'username': username,
        'role': role,
        'display_name': username,
        'password_hash': generate_password_hash(password),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate LESNAR_AUTH_USERS_JSON payload')
    parser.add_argument('--user', action='append', required=True, help='username:role:password')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON')
    args = parser.parse_args()

    try:
        users = [parse_user(raw) for raw in args.user]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.pretty:
        print(json.dumps(users, indent=2))
    else:
        print(json.dumps(users))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
