#!/usr/bin/env python3
"""Generate runtime optimization profiles for stable validation/demo runs."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_ENV = REPO / 'docs' / 'validation' / 'runtime_optimization_profile.env'
OUT_JSON = REPO / 'docs' / 'validation' / 'runtime_optimization_profile.json'

PROFILE = {
    'backend_env_overrides': {
        'LESNAR_EXTERNAL_TELEMETRY_STALE_AFTER_S': '3.5',
        'LESNAR_COMMAND_CONFIRM_TIMEOUT_S': '3.5',
        'LESNAR_TELEMETRY_HISTORY_INTERVAL_TICKS': '3',
        'LESNAR_CORS_ORIGINS': 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001',
    },
    'frontend_env_overrides': {
        'REACT_APP_TELEMETRY_STALE_MS': '2500',
        'REACT_APP_DEGRADED_LATENCY_MS': '900',
        'REACT_APP_DEGRADED_TELEMETRY_MS': '3000',
    },
    'teacher_bridge_recommended_args': [
        '--duration 0',
        '--safe_presentation_profile',
        '--max-end-to-end-drift-m 3.0',
    ],
    'host_runtime_recommendations': [
        'Run only one frontend dev server instance.',
        'Close non-essential GPU/CPU-heavy applications before simulation runs.',
        'Keep PX4 + Gazebo + teacher on dedicated terminals and avoid concurrent builds/tests.',
        'Use fixed test durations (e.g., 120s) for comparable quantitative validation.',
    ],
}


def write_env(path: Path, profile: dict) -> None:
    lines = [
        '# Runtime optimization profile (generated)',
        '# Apply manually to .env.secure / frontend/.env.local as needed.',
        '',
        '# Backend overrides',
    ]
    for key, value in profile['backend_env_overrides'].items():
        lines.append(f'{key}={value}')

    lines.extend(['', '# Frontend overrides'])
    for key, value in profile['frontend_env_overrides'].items():
        lines.append(f'{key}={value}')

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    OUT_ENV.parent.mkdir(parents=True, exist_ok=True)
    write_env(OUT_ENV, PROFILE)
    OUT_JSON.write_text(json.dumps(PROFILE, indent=2), encoding='utf-8')
    print(f'Created: {OUT_ENV}')
    print(f'Created: {OUT_JSON}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
