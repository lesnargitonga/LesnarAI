#!/usr/bin/env python3
"""Validate secure deployment readiness for LesnarAI."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT_ENV = REPO / '.env.secure'
FRONTEND_ENV = REPO / 'frontend' / '.env.local.secure'
FRONTEND_RUNTIME_ENV = REPO / 'frontend' / '.env.local'
COMPOSE = REPO / 'docker-compose.yml'

DEFAULT_WEAK = {
    '',
    'example-password',
    'example-admin-key',
    'example-operator-key',
    'replace-with-strong-random-secret',
    'changeme',
    'password',
    '[]',
}


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding='utf-8').splitlines():
        if not raw.strip() or raw.lstrip().startswith('#') or '=' not in raw:
            continue
        key, value = raw.split('=', 1)
        result[key.strip()] = value.strip()
    return result


def check(condition: bool, ok_msg: str, fail_msg: str, failures: list[str]) -> None:
    if condition:
        print(f'[ok] {ok_msg}')
    else:
        print(f'[fail] {fail_msg}')
        failures.append(fail_msg)


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    root_env = parse_env(ROOT_ENV)
    frontend_env = parse_env(FRONTEND_RUNTIME_ENV if FRONTEND_RUNTIME_ENV.exists() else FRONTEND_ENV)
    compose_text = COMPOSE.read_text(encoding='utf-8') if COMPOSE.exists() else ''

    check(ROOT_ENV.exists(), '.env.secure exists', 'Missing .env.secure', failures)
    check(FRONTEND_ENV.exists(), 'frontend/.env.local.secure exists', 'Missing frontend/.env.local.secure', failures)
    check(FRONTEND_RUNTIME_ENV.exists(), 'frontend/.env.local exists', 'Missing frontend/.env.local', failures)

    for key in [
        'POSTGRES_PASSWORD',
        'LESNAR_AUDIT_CHAIN_KEY',
        'LESNAR_DATASET_SIGN_KEY',
        'FLASK_SECRET_KEY',
    ]:
        value = root_env.get(key, '')
        check(value not in DEFAULT_WEAK and len(value) >= 24, f'{key} looks strong', f'{key} is missing or weak', failures)

    auth_users = root_env.get('LESNAR_AUTH_USERS_JSON', '')
    try:
        auth_users_json = json.loads(auth_users)
    except Exception:
        auth_users_json = None
    check(isinstance(auth_users_json, list) and len(auth_users_json) > 0, 'Auth users JSON present', 'LESNAR_AUTH_USERS_JSON is empty or invalid', failures)

    boundary = root_env.get('LESNAR_OPERATIONAL_BOUNDARY', '')
    try:
        boundary_json = json.loads(boundary)
    except Exception:
        boundary_json = None
    check(isinstance(boundary_json, list) and len(boundary_json) >= 3, 'Operational boundary configured', 'LESNAR_OPERATIONAL_BOUNDARY is empty or invalid', failures)

    check(root_env.get('LESNAR_REQUIRE_AUTH') == '1', 'Backend auth fail-closed enabled', 'LESNAR_REQUIRE_AUTH must be 1', failures)
    check(root_env.get('LESNAR_SESSION_TTL_S', '').isdigit(), 'Session TTL configured', 'LESNAR_SESSION_TTL_S must be an integer', failures)

    check(frontend_env.get('REACT_APP_REQUIRE_SESSION_AUTH') == '1', 'Frontend requires session auth', 'REACT_APP_REQUIRE_SESSION_AUTH must be 1', failures)
    check(frontend_env.get('REACT_APP_ALLOW_LEGACY_API_KEY', '0') != '1', 'Legacy browser API-key fallback disabled', 'REACT_APP_ALLOW_LEGACY_API_KEY must not be 1', failures)

    frontend_boundary = frontend_env.get('REACT_APP_OPERATIONAL_BOUNDARY', '')
    check(frontend_boundary == boundary, 'Frontend and backend boundaries match', 'Frontend boundary does not match backend boundary', failures)

    tile_url = frontend_env.get('REACT_APP_MAP_TILE_URL', '')
    if not tile_url:
        warnings.append('REACT_APP_MAP_TILE_URL not set; frontend will rely on fallback tiles')
    else:
        print('[ok] Offline/local tile URL configured')

    auth_passthrough_ok = ('LESNAR_AUTH_USERS_JSON' in compose_text) or ('LESNAR_AUTH_USERS_FILE' in compose_text)
    check(
        auth_passthrough_ok,
        'Auth users are passed through docker-compose',
        'Neither LESNAR_AUTH_USERS_JSON nor LESNAR_AUTH_USERS_FILE found in docker-compose environment passthrough',
        failures,
    )

    for key in [
        'LESNAR_SESSION_TTL_S',
        'LESNAR_OPERATIONAL_BOUNDARY',
        'LESNAR_EXTERNAL_TELEMETRY_STALE_AFTER_S',
        'LESNAR_COMMAND_CONFIRM_TIMEOUT_S',
        'LESNAR_TELEMETRY_HISTORY_INTERVAL_TICKS',
    ]:
        check(key in compose_text, f'{key} is passed through docker-compose', f'{key} not found in docker-compose environment passthrough', failures)

    print('\nWarnings:')
    if warnings:
        for item in warnings:
            print(f' - {item}')
    else:
        print(' - none')

    print(f'\nResult: {"PASS" if not failures else "FAIL"}')
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
