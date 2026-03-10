#!/usr/bin/env python3
"""Automated session login + telemetry drift measurement for stability verification."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request


@dataclass
class Sample:
    poll_ts: float
    drone_id: str
    latitude: float
    longitude: float
    altitude: float
    speed: float
    heading: float
    telemetry_age_s: float | None


class ApiClient:
    def __init__(self, backend_url: str, timeout_s: float = 8.0):
        self.backend_url = backend_url.rstrip('/')
        self.timeout_s = timeout_s
        self.token = ''

    def _post_json(self, path: str, payload: dict, auth: bool = False) -> dict:
        body = json.dumps(payload).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        if auth and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        req = request.Request(f"{self.backend_url}{path}", data=body, headers=headers, method='POST')
        with request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _get_json(self, path: str, auth: bool = True) -> dict:
        headers = {'Accept': 'application/json'}
        if auth and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        req = request.Request(f"{self.backend_url}{path}", headers=headers, method='GET')
        with request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def login(self, username: str, password: str) -> None:
        payload = {'username': username, 'password': password}
        data = self._post_json('/api/auth/login', payload)
        token = str(data.get('token') or '').strip()
        if not token:
            raise RuntimeError(f"Login failed: {data}")
        self.token = token

    def get_drones(self) -> list[dict]:
        data = self._get_json('/api/drones', auth=True)
        drones = data.get('drones')
        if not isinstance(drones, list):
            return []
        return drones


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_iso_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except Exception:
        return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))


def summarize(samples: list[Sample], total_polls: int, duration_s: float) -> dict:
    availability = (len(samples) / total_polls) if total_polls > 0 else 0.0
    out: dict = {
        'timestamp': now_iso(),
        'duration_s': round(duration_s, 3),
        'total_polls': total_polls,
        'valid_samples': len(samples),
        'telemetry_availability_ratio': round(availability, 4),
    }

    if len(samples) < 2:
        out['metrics'] = {
            'note': 'Insufficient samples for drift statistics',
        }
        return out

    first = samples[0]
    last = samples[-1]

    radial_from_start = [
        haversine_m(first.latitude, first.longitude, sample.latitude, sample.longitude)
        for sample in samples
    ]

    centroid_lat = statistics.mean(sample.latitude for sample in samples)
    centroid_lon = statistics.mean(sample.longitude for sample in samples)
    radial_from_centroid = [
        haversine_m(centroid_lat, centroid_lon, sample.latitude, sample.longitude)
        for sample in samples
    ]

    end_to_end = haversine_m(first.latitude, first.longitude, last.latitude, last.longitude)
    altitudes = [sample.altitude for sample in samples]
    speeds = [sample.speed for sample in samples]
    headings = [sample.heading for sample in samples]
    ages = [sample.telemetry_age_s for sample in samples if sample.telemetry_age_s is not None]

    out['metrics'] = {
        'drone_id': first.drone_id,
        'end_to_end_drift_m': round(end_to_end, 3),
        'max_radial_drift_from_start_m': round(max(radial_from_start), 3),
        'rms_jitter_from_centroid_m': round(math.sqrt(statistics.mean(r * r for r in radial_from_centroid)), 3),
        'p95_jitter_from_centroid_m': round(sorted(radial_from_centroid)[max(0, int(len(radial_from_centroid) * 0.95) - 1)], 3),
        'altitude_min_m': round(min(altitudes), 3),
        'altitude_max_m': round(max(altitudes), 3),
        'altitude_span_m': round(max(altitudes) - min(altitudes), 3),
        'speed_avg_mps': round(statistics.mean(speeds), 3),
        'speed_max_mps': round(max(speeds), 3),
        'heading_std_deg': round(statistics.pstdev(headings), 3) if len(headings) > 1 else 0.0,
        'avg_telemetry_age_s': round(statistics.mean(ages), 3) if ages else None,
        'max_telemetry_age_s': round(max(ages), 3) if ages else None,
        'capture_span_s': round(samples[-1].poll_ts - samples[0].poll_ts, 3),
    }
    return out


def evaluate(report: dict, max_end_to_end_drift_m: float, max_rms_jitter_m: float, min_availability: float) -> dict:
    metrics = report.get('metrics', {})
    availability = float(report.get('telemetry_availability_ratio') or 0.0)

    if 'end_to_end_drift_m' not in metrics:
        return {
            'pass': False,
            'reasons': ['insufficient_samples'],
            'thresholds': {
                'max_end_to_end_drift_m': max_end_to_end_drift_m,
                'max_rms_jitter_m': max_rms_jitter_m,
                'min_availability': min_availability,
            },
        }

    reasons: list[str] = []
    if metrics['end_to_end_drift_m'] > max_end_to_end_drift_m:
        reasons.append('end_to_end_drift_exceeded')
    if metrics['rms_jitter_from_centroid_m'] > max_rms_jitter_m:
        reasons.append('rms_jitter_exceeded')
    if availability < min_availability:
        reasons.append('telemetry_availability_low')

    return {
        'pass': len(reasons) == 0,
        'reasons': reasons,
        'thresholds': {
            'max_end_to_end_drift_m': max_end_to_end_drift_m,
            'max_rms_jitter_m': max_rms_jitter_m,
            'min_availability': min_availability,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Automated session login + telemetry drift verification')
    parser.add_argument('--backend-url', default='http://localhost:5000')
    parser.add_argument('--username', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--drone-id', default='', help='Optional drone id filter; if omitted, first drone is used')
    parser.add_argument('--duration', type=float, default=60.0, help='Sampling duration in seconds')
    parser.add_argument('--interval', type=float, default=1.0, help='Polling interval in seconds')
    parser.add_argument('--max-end-to-end-drift-m', type=float, default=3.0)
    parser.add_argument('--max-rms-jitter-m', type=float, default=1.2)
    parser.add_argument('--min-availability', type=float, default=0.9)
    parser.add_argument('--out-json', default='docs/validation/stability_verification_latest.json')
    parser.add_argument('--out-csv', default='docs/validation/stability_verification_samples_latest.csv')
    args = parser.parse_args()

    client = ApiClient(args.backend_url)
    try:
        client.login(args.username, args.password)
    except error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        print(f'[error] login failed: HTTP {exc.code} {body}')
        return 1
    except Exception as exc:
        print(f'[error] login failed: {exc}')
        return 1

    start = time.monotonic()
    next_poll = start
    polls = 0
    samples: list[Sample] = []

    while True:
        now = time.monotonic()
        if now >= start + max(0.1, args.duration):
            break
        if now < next_poll:
            time.sleep(min(0.05, next_poll - now))
            continue

        polls += 1
        next_poll += max(0.1, args.interval)

        try:
            drones = client.get_drones()
        except Exception:
            continue

        if not drones:
            continue

        target = None
        if args.drone_id:
            for row in drones:
                if str(row.get('drone_id') or '') == args.drone_id:
                    target = row
                    break
        else:
            target = drones[0]

        if target is None:
            continue

        sample_ts = time.time()
        telem_ts = parse_iso_ts(target.get('timestamp'))
        age = (sample_ts - telem_ts) if telem_ts is not None else None

        samples.append(
            Sample(
                poll_ts=sample_ts,
                drone_id=str(target.get('drone_id') or 'unknown'),
                latitude=to_float(target.get('latitude')),
                longitude=to_float(target.get('longitude')),
                altitude=to_float(target.get('altitude')),
                speed=to_float(target.get('speed')),
                heading=to_float(target.get('heading')),
                telemetry_age_s=age,
            )
        )

    duration_s = time.monotonic() - start
    report = summarize(samples, polls, duration_s)
    report['evaluation'] = evaluate(
        report,
        max_end_to_end_drift_m=args.max_end_to_end_drift_m,
        max_rms_jitter_m=args.max_rms_jitter_m,
        min_availability=args.min_availability,
    )

    out_json = Path(args.out_json)
    out_csv = Path(args.out_csv)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(report, indent=2), encoding='utf-8')

    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'poll_ts', 'drone_id', 'latitude', 'longitude', 'altitude', 'speed', 'heading', 'telemetry_age_s'
        ])
        for sample in samples:
            writer.writerow([
                sample.poll_ts,
                sample.drone_id,
                sample.latitude,
                sample.longitude,
                sample.altitude,
                sample.speed,
                sample.heading,
                sample.telemetry_age_s,
            ])

    print(f"[ok] wrote report: {out_json}")
    print(f"[ok] wrote samples: {out_csv}")
    print(json.dumps(report.get('evaluation', {}), indent=2))

    return 0 if report.get('evaluation', {}).get('pass') else 2


if __name__ == '__main__':
    raise SystemExit(main())
