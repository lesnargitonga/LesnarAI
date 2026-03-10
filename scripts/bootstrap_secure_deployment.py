#!/usr/bin/env python3
"""Bootstrap secure deployment artifacts for LesnarAI.

What this script does automatically:
- Generates `.env.secure` from `.env.example` with strong secrets if missing.
- Generates `frontend/.env.local.secure` and `frontend/.env.local` from `frontend/.env.example`.
- Optionally injects `LESNAR_AUTH_USERS_JSON` from a file.
- Mirrors backend operational boundary into frontend visualization config.

What still requires human input:
- Real usernames/passwords before generating auth users JSON.
- Real operational boundary coordinates.
- Real offline/local tile server URL.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT_ENV_EXAMPLE = REPO / '.env.example'
ROOT_ENV_SECURE = REPO / '.env.secure'
FRONTEND_ENV_EXAMPLE = REPO / 'frontend' / '.env.example'
FRONTEND_ENV_SECURE = REPO / 'frontend' / '.env.local.secure'
FRONTEND_ENV_RUNTIME = REPO / 'frontend' / '.env.local'


def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in raw:
            continue
        key, value = raw.split('=', 1)
        data[key.strip()] = value.strip()
    return data


def render_env(template_path: Path, values: dict[str, str]) -> str:
    out: list[str] = []
    for raw in template_path.read_text(encoding='utf-8').splitlines(keepends=True):
        stripped = raw.strip()
        if not stripped or stripped.startswith('#') or '=' not in raw:
            out.append(raw)
            continue
        key, _ = raw.split('=', 1)
        key = key.strip()
        out.append(f'{key}={values.get(key, "")}\n')
    return ''.join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description='Bootstrap secure deployment files for LesnarAI')
    parser.add_argument('--auth-users-json-file', help='Path to file containing LESNAR_AUTH_USERS_JSON payload')
    parser.add_argument('--boundary-json-file', help='Path to file containing JSON array of [lat, lng] boundary points')
    parser.add_argument('--tile-url', help='Offline/local tile URL for frontend, e.g. http://localhost:8081/tiles/{z}/{x}/{y}.png')
    parser.add_argument('--force', action='store_true', help='Overwrite existing secure env files')
    args = parser.parse_args()

    from generate_secure_env import build_secure_env  # local helper already in repo

    if args.force or not ROOT_ENV_SECURE.exists():
        build_secure_env(ROOT_ENV_EXAMPLE, ROOT_ENV_SECURE, force=args.force)
        print(f'[ok] wrote {ROOT_ENV_SECURE}')
    else:
        print(f'[skip] using existing {ROOT_ENV_SECURE}')

    root_values = parse_env(ROOT_ENV_SECURE)

    if args.auth_users_json_file:
        auth_json = Path(args.auth_users_json_file).read_text(encoding='utf-8').strip()
        json.loads(auth_json)
        root_values['LESNAR_AUTH_USERS_JSON'] = auth_json
        print('[ok] injected LESNAR_AUTH_USERS_JSON from file')

    if args.boundary_json_file:
        boundary_json = Path(args.boundary_json_file).read_text(encoding='utf-8').strip()
        json.loads(boundary_json)
        root_values['LESNAR_OPERATIONAL_BOUNDARY'] = boundary_json
        print('[ok] injected LESNAR_OPERATIONAL_BOUNDARY from file')

    ROOT_ENV_SECURE.write_text(render_env(ROOT_ENV_EXAMPLE, root_values), encoding='utf-8')

    frontend_values = parse_env(FRONTEND_ENV_EXAMPLE)
    frontend_values['REACT_APP_REQUIRE_SESSION_AUTH'] = '1'
    frontend_values['REACT_APP_ALLOW_LEGACY_API_KEY'] = '0'
    frontend_values['REACT_APP_OPERATIONAL_BOUNDARY'] = root_values.get('LESNAR_OPERATIONAL_BOUNDARY', '[]')
    if args.tile_url:
        frontend_values['REACT_APP_MAP_TILE_URL'] = args.tile_url

    frontend_rendered = render_env(FRONTEND_ENV_EXAMPLE, frontend_values)
    if args.force or not FRONTEND_ENV_SECURE.exists():
        FRONTEND_ENV_SECURE.write_text(frontend_rendered, encoding='utf-8')
        print(f'[ok] wrote {FRONTEND_ENV_SECURE}')
    else:
        print(f'[skip] using existing {FRONTEND_ENV_SECURE}')

    if args.force or not FRONTEND_ENV_RUNTIME.exists():
        FRONTEND_ENV_RUNTIME.write_text(frontend_rendered, encoding='utf-8')
        print(f'[ok] wrote {FRONTEND_ENV_RUNTIME}')
    else:
        print(f'[skip] using existing {FRONTEND_ENV_RUNTIME}')

    print('\nRemaining human-required inputs:')
    if root_values.get('LESNAR_AUTH_USERS_JSON', '[]').strip() == '[]':
        print(' - Generate real operator accounts and inject LESNAR_AUTH_USERS_JSON')
    if root_values.get('LESNAR_OPERATIONAL_BOUNDARY', '[]').strip() == '[]':
        print(' - Set a real LESNAR_OPERATIONAL_BOUNDARY')
    if not args.tile_url and not frontend_values.get('REACT_APP_MAP_TILE_URL', '').strip():
        print(' - Set REACT_APP_MAP_TILE_URL to a real offline/local tile source')
    print(' - Run docker compose with --env-file .env.secure')
    print(' - Apply migrations and perform live operator acceptance checks')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
