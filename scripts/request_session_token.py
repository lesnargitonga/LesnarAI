#!/usr/bin/env python3
"""Request a LesnarAI session token for CLI smoke tests and operator tooling."""

from __future__ import annotations

import argparse
import json
import sys
from urllib import error, request


def login(base_url: str, username: str, password: str) -> dict:
    payload = json.dumps({'username': username, 'password': password}).encode('utf-8')
    req = request.Request(
        f'{base_url.rstrip("/")}/api/auth/login',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description='Request LesnarAI session token')
    parser.add_argument('--backend-url', default='http://localhost:5000', help='Backend base URL')
    parser.add_argument('--username', required=True, help='Operator username')
    parser.add_argument('--password', required=True, help='Operator password')
    parser.add_argument('--format', choices=['token', 'header', 'json'], default='header', help='Output format')
    args = parser.parse_args()

    try:
        data = login(args.backend_url, args.username, args.password)
    except error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        print(body or f'HTTP {exc.code}', file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    token = str(data.get('token') or '').strip()
    if not token:
        print(json.dumps(data), file=sys.stderr)
        return 1

    if args.format == 'token':
        print(token)
    elif args.format == 'header':
        print(f'Authorization: Bearer {token}')
    else:
        print(json.dumps(data, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())