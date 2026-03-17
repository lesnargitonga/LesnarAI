#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import sys
import urllib.error
import urllib.request


DEFAULT_FRONTEND_URL = 'http://127.0.0.1:3000'
DEFAULT_BACKEND_URL = 'http://127.0.0.1:5000'
DEFAULT_ADMINER_URL = 'http://127.0.0.1:8080'
DEFAULT_USERNAME = 'lesnar'
DEFAULT_PASSWORD = 'LesnarAdmin2026!'


def request_json(url: str, method: str = 'GET', data: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    body = None
    req_headers = {'Content-Type': 'application/json'}
    if headers:
        req_headers.update(headers)
    if data is not None:
        body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode('utf-8'))


def request_text(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, method='GET')
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, resp.read().decode('utf-8', errors='replace')


def run_checks(frontend_url: str, backend_url: str, adminer_url: str, username: str, password: str) -> list[str]:
    checks: list[str] = []

    status, html = request_text(frontend_url)
    if status != 200 or '<!DOCTYPE html>' not in html:
        raise RuntimeError('frontend root check failed')
    checks.append('frontend root ok')

    status, html = request_text(adminer_url)
    if status != 200 or 'Adminer' not in html:
        raise RuntimeError('adminer root check failed')
    checks.append('adminer root ok')

    status, payload = request_json(f'{backend_url}/')
    if status != 200 or payload.get('status') != 'active':
        raise RuntimeError('backend root check failed')
    checks.append('backend root ok')

    status, payload = request_json(f'{backend_url}/api/auth/login', method='POST', data={
        'username': username,
        'password': password,
    })
    if status != 200 or not payload.get('success') or not payload.get('token'):
        raise RuntimeError('login check failed')
    token = payload['token']
    checks.append('login ok')

    auth_headers = {'Authorization': f'Bearer {token}'}

    status, payload = request_json(f'{backend_url}/api/auth/me', headers=auth_headers)
    if status != 200 or payload.get('session', {}).get('userId') != username:
        raise RuntimeError('auth/me check failed')
    checks.append('auth/me ok')

    status, payload = request_json(f'{backend_url}/api/security/status', headers=auth_headers)
    mechanism = payload.get('security', {}).get('auth', {}).get('session_mechanism', '')
    if status != 200 or 'Postgres-backed users' not in mechanism:
        raise RuntimeError('security status auth backend check failed')
    checks.append('security status ok')

    status, payload = request_json(f'{backend_url}/api/drones', headers=auth_headers)
    if status != 200 or not payload.get('success'):
        raise RuntimeError('drones endpoint check failed')
    checks.append('drones endpoint ok')

    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='LesnarAI runtime smoke test')
    parser.add_argument('--frontend-url', default=DEFAULT_FRONTEND_URL)
    parser.add_argument('--backend-url', default=DEFAULT_BACKEND_URL)
    parser.add_argument('--adminer-url', default=DEFAULT_ADMINER_URL)
    parser.add_argument('--username', default=DEFAULT_USERNAME)
    parser.add_argument('--password', default=DEFAULT_PASSWORD)
    parser.add_argument('--retries', type=int, default=1)
    parser.add_argument('--delay', type=float, default=2.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    last_error: Exception | None = None
    for attempt in range(1, max(args.retries, 1) + 1):
        try:
            checks = run_checks(args.frontend_url, args.backend_url, args.adminer_url, args.username, args.password)
            print(json.dumps({'success': True, 'checks': checks, 'attempt': attempt}, indent=2))
            return 0
        except Exception as exc:
            last_error = exc
            if attempt >= max(args.retries, 1):
                break
            time.sleep(max(args.delay, 0.0))

    raise RuntimeError(str(last_error) if last_error else 'runtime smoke test failed')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f'HTTP error: {exc.code} {exc.reason}', file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
