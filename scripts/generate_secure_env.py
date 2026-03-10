#!/usr/bin/env python3
import argparse
import secrets
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / '.env.example'
DEFAULT_OUTPUT = REPO_ROOT / '.env.secure'


def strong_secret(length: int = 48) -> str:
    return secrets.token_urlsafe(length)[:length]


def generate_value(key: str, current: str) -> str:
    if key == 'POSTGRES_PASSWORD':
        return strong_secret(40)
    if key in {
        'LESNAR_ADMIN_API_KEY',
        'LESNAR_OPERATOR_API_KEY',
        'LESNAR_AUDIT_CHAIN_KEY',
        'LESNAR_DATASET_SIGN_KEY',
        'FLASK_SECRET_KEY',
    }:
        return strong_secret(56)
    if key == 'LESNAR_AUTH_USERS_JSON':
        return '[]'
    if key == 'LESNAR_OPERATIONAL_BOUNDARY':
        return '[]'
    return current


def parse_env_line(line: str):
    stripped = line.strip()
    if not stripped or stripped.startswith('#') or '=' not in line:
        return None, None
    key, value = line.split('=', 1)
    return key.strip(), value.rstrip('\n')


def build_secure_env(in_path: Path, out_path: Path, force: bool) -> Path:
    if not in_path.exists():
        raise RuntimeError(f'Input env file not found: {in_path}')

    if out_path.exists() and not force:
        raise RuntimeError(f'Output already exists: {out_path} (use --force to overwrite)')

    lines = in_path.read_text(encoding='utf-8').splitlines(keepends=True)
    output = []

    for line in lines:
        key, value = parse_env_line(line)
        if key is None:
            output.append(line)
            continue
        secure_value = generate_value(key, value)
        output.append(f'{key}={secure_value}\n')

    out_path.write_text(''.join(output), encoding='utf-8')
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate secure env file with strong random secrets')
    parser.add_argument('--input', default=str(DEFAULT_INPUT), help='Input env template path')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT), help='Output secure env path')
    parser.add_argument('--force', action='store_true', help='Overwrite output file if it already exists')
    args = parser.parse_args()

    out = build_secure_env(Path(args.input), Path(args.output), args.force)
    print(f'Wrote secure env file: {out}')
    print('Next: set -a; source .env.secure; set +a')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
