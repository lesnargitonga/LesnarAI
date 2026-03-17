"""
Lesnar AI Backend API Server
Flask-based REST API for drone control and monitoring
"""

import os
import re
import sys
import json
import time as _time
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
# Force engineio to use threading driver to avoid importing Tornado
os.environ.setdefault('ENGINEIO_ASYNC_MODE', 'threading')
from flask_socketio import SocketIO, emit
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import threading
import time
import socket
import math
from pathlib import Path
import logging
import urllib.parse
import urllib.request
import redis
import uuid
import hashlib
import hmac

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
try:
    from werkzeug.security import check_password_hash as _werkzeug_check_password_hash
except Exception:
    _werkzeug_check_password_hash = None

from db import (
    db,
    get_database_url,
    safe_log_command,
    Drone,
    Mission as MissionModel,
    MissionRun,
    safe_log_event,
    AuthSession,
    AuthUser,
    TelemetrySample,
    Event as AuditEvent,
)

# Add drone_simulation to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'drone_simulation'))
from simulator import DroneFleet, Mission

# Legacy legacy path removed; PX4/Gazebo external bridge is canonical.
LegacyAdapter = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _env_str(name: str, default: str = '') -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name, str(default))
    try:
        return int(raw)
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name, str(default))
    try:
        return float(raw)
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env_str(name, '1' if default else '0').lower()
    return raw in ('1', 'true', 'yes', 'on')


def _parse_cors_origins() -> str | list[str]:
    raw = _env_str('LESNAR_CORS_ORIGINS', '*')
    if raw == '*':
        return '*'
    origins = [origin.strip() for origin in raw.split(',') if origin.strip()]
    return origins or '*'

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = _env_str('FLASK_SECRET_KEY', 'dev-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
_CORS_ORIGINS = _parse_cors_origins()
CORS(
    app,
    resources={
        r"/api/.*": {
            "origins": _CORS_ORIGINS,
            "allow_headers": [
                "Content-Type",
                "Authorization",
                "X-API-Key",
                "X-Operator-Id",
                "X-Operator-Role",
                "X-Session-Id",
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        }
    },
)
socketio = SocketIO(app, cors_allowed_origins=_CORS_ORIGINS, async_mode='threading')
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per minute"],
                  storage_uri="memory://")

# --- Security response headers ---
@app.after_request
def _add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
    response.headers['Cache-Control'] = 'no-store'
    # Only add HSTS if already on HTTPS
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

db.init_app(app)

# --- Constants ---
TELEMETRY_RATE_HZ = 5
TELEMETRY_SLEEP_S = 1.0 / TELEMETRY_RATE_HZ
DB_SYNC_INTERVAL = 3
WAYPOINT_DURATION_ESTIMATE_S = 60.0
SEG_LOG_MAX_ROWS = 500
REDIS_RETRY_DELAY_S = 5
DEFAULT_TAKEOFF_ALT = 10.0
FLYING_ALTITUDE_THRESHOLD = 1.0
LOW_BATTERY_THRESHOLD = 20.0
EXTERNAL_TELEMETRY_STALE_AFTER_S = _env_float('LESNAR_EXTERNAL_TELEMETRY_STALE_AFTER_S', 5.0)
COMMAND_CONFIRM_TIMEOUT_S = _env_float('LESNAR_COMMAND_CONFIRM_TIMEOUT_S', 2.5)
SESSION_TTL_S = _env_int('LESNAR_SESSION_TTL_S', 1800)
TELEMETRY_HISTORY_INTERVAL_TICKS = _env_int('LESNAR_TELEMETRY_HISTORY_INTERVAL_TICKS', 5)
MAX_DRONE_ID_LENGTH = 128
DRONE_ID_PATTERN = re.compile(r'^[A-Za-z0-9_\-\.]+$')
LAT_MIN, LAT_MAX = -90.0, 90.0
LON_MIN, LON_MAX = -180.0, 180.0
ALT_MIN, ALT_MAX = 0.0, 10000.0
CONFIG_ALLOWED_KEYS = {
    'drone_settings',
    'api_settings',
    'ai_settings',
    'logging',
    'data_pipeline',
    'simulation_settings',
}

_external_drone_ids: set[str] = set()
_external_drone_last_seen_monotonic: dict[str, float] = {}
_external_drone_prev_samples: dict[str, dict] = {}
_auth_serializer: URLSafeTimedSerializer | None = None


def _maybe_run_db_migrations():
    """Best-effort Alembic upgrade on startup (safe no-op after first run)."""
    if not _env_bool('AUTO_MIGRATE', True):
        return
    try:
        from alembic import command
        from alembic.config import Config

        backend_dir = os.path.dirname(__file__)
        cfg_path = os.path.join(backend_dir, 'alembic.ini')
        cfg = Config(cfg_path)
        cfg.set_main_option('script_location', os.path.join(backend_dir, 'migrations'))
        # URL comes from migrations/env.py (DATABASE_URL)
        command.upgrade(cfg, 'head')
        logger.info('DB migrations: up-to-date')
    except Exception as e:
        logger.warning(f"DB migrations failed (falling back to create_all): {e}")
        try:
            db.create_all()
        except Exception as e2:
            logger.warning(f"DB init failed (continuing without persistence): {e2}")


with app.app_context():
    _maybe_run_db_migrations()

USE_LEGACY_ADAPTER = False
fleet = DroneFleet()
legacy_adapter = None
if USE_LEGACY_ADAPTER and LegacyAdapter is not None:
    try:
        legacy_adapter = LegacyAdapter()
        logger.info("Legacy adapter enabled: serving live states from Legacy")
    except Exception as e:
        logger.warning(f"Failed to initialize Legacy adapter: {e}. Falling back to simulator.")
        legacy_adapter = None
telemetry_thread = None
_telemetry_stop = threading.Event()
_START_TIME = _time.time()


# --- Simple API-key auth (role-based) ---
# Security default is fail-closed: protected APIs require configured keys unless explicitly disabled.
_REQUIRE_AUTH = _env_bool('LESNAR_REQUIRE_AUTH', True)
_ADMIN_KEY = _env_str('LESNAR_ADMIN_API_KEY')
_OPERATOR_KEY = _env_str('LESNAR_OPERATOR_API_KEY')
_AUDIT_CHAIN_KEY = _env_str('LESNAR_AUDIT_CHAIN_KEY')

_WEAK_SECRET_VALUES = {
    'example-password',
    'example-admin-key',
    'example-operator-key',
    'replace-with-strong-random-secret',
    'changeme',
    'password',
    'dev-secret',
}

_REDIS_HOST = _env_str('REDIS_HOST', '127.0.0.1')
_REDIS_PORT = _env_int('REDIS_PORT', 6379)
_ENABLE_DEMO_FLEET = _env_bool('LESNAR_ENABLE_DEMO_FLEET', False)
_LOAD_PERSISTED_FLEET = _env_bool('LESNAR_LOAD_PERSISTED_FLEET', False)
_EXTERNAL_ONLY = _env_bool('LESNAR_EXTERNAL_ONLY', False)

# --- Brute-force / lockout state (in-memory, per IP+username) ---
_FAILED_LOGINS: dict = {}  # key: "ip:username" → {'count': int, 'locked_until': float}
_LOGIN_MAX_ATTEMPTS = _env_int('LESNAR_LOGIN_MAX_ATTEMPTS', 5)
_LOGIN_LOCKOUT_S = _env_int('LESNAR_LOGIN_LOCKOUT_S', 300)   # 5-minute lockout
_LOGIN_WINDOW_S  = _env_int('LESNAR_LOGIN_WINDOW_S', 60)
_failed_logins_lock = threading.Lock()

def _brute_check(ip: str, username: str) -> tuple[bool, float]:
    """Return (is_locked, seconds_remaining)."""
    key = f"{ip}:{username}"
    with _failed_logins_lock:
        rec = _FAILED_LOGINS.get(key)
        if not rec:
            return False, 0.0
        now = time.time()
        if rec.get('locked_until', 0) > now:
            return True, round(rec['locked_until'] - now, 1)
        return False, 0.0

def _brute_record_failure(ip: str, username: str) -> None:
    key = f"{ip}:{username}"
    now = time.time()
    with _failed_logins_lock:
        rec = _FAILED_LOGINS.setdefault(key, {'count': 0, 'window_start': now, 'locked_until': 0.0})
        if now - rec['window_start'] > _LOGIN_WINDOW_S:
            rec['count'] = 0
            rec['window_start'] = now
        rec['count'] += 1
        if rec['count'] >= _LOGIN_MAX_ATTEMPTS:
            rec['locked_until'] = now + _LOGIN_LOCKOUT_S
            logger.warning(f"SECURITY: Login lockout triggered for {key} after {rec['count']} attempts")

def _brute_clear(ip: str, username: str) -> None:
    key = f"{ip}:{username}"
    with _failed_logins_lock:
        _FAILED_LOGINS.pop(key, None)


# --- Password hashing utility ---
import os as _os
import secrets as _secrets

def _hash_password_pbkdf2(password: str, iterations: int = 390000) -> str:
    """Hash a password with pbkdf2_sha256. Returns a portable hash string."""
    salt = _secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


# --- Auth user helpers ---
def _normalize_role(raw_role: str | None) -> str:
    role = str(raw_role or 'viewer').strip().lower()
    return role if role in {'viewer', 'operator', 'admin'} else 'viewer'


def _auth_user_public_dict(row: AuthUser) -> dict:
    return {
        'username': row.username,
        'role': _normalize_role(row.role),
        'display_name': row.display_name or row.username,
    }


def _get_auth_user(username: str | None) -> AuthUser | None:
    normalized = str(username or '').strip().lower()
    if not normalized:
        return None
    return AuthUser.query.filter_by(username=normalized).one_or_none()


def _auth_user_count() -> int:
    return int(AuthUser.query.count())


def _auth_role_counts() -> dict:
    counts: dict[str, int] = {role: 0 for role in ('viewer', 'operator', 'admin')}
    for role, total in db.session.query(AuthUser.role, db.func.count(AuthUser.id)).group_by(AuthUser.role).all():
        counts[_normalize_role(role)] = int(total)
    return {role: total for role, total in counts.items() if total > 0}




def _is_demo_drone_id(drone_id: str | None) -> bool:
    value = (drone_id or '').strip().upper()
    return value.startswith('LESNAR-DEMO-')


def _auth_enabled() -> bool:
    return _REQUIRE_AUTH


def _get_auth_serializer() -> URLSafeTimedSerializer:
    global _auth_serializer
    if _auth_serializer is None:
        _auth_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='lesnar-session-v1')
    return _auth_serializer


def _check_password_hash(password_hash: str, password: str) -> bool:
    if not password_hash:
        return False
    value = str(password_hash).strip()
    if value.startswith('pbkdf2_sha256$'):
        try:
            _, iterations_raw, salt_hex, digest_hex = value.split('$', 3)
            iterations = int(iterations_raw)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False
    if _werkzeug_check_password_hash is None:
        return False
    try:
        return bool(_werkzeug_check_password_hash(value, password))
    except Exception:
        return False


def _authenticate_user(username: str, password: str):
    row = _get_auth_user(username)
    if row is None:
        return None
    password_hash = str(row.password_hash or '').strip()
    ok = _check_password_hash(password_hash, password)
    if not ok:
        return None
    return {
        'username': row.username,
        'role': _normalize_role(row.role),
        'display_name': str(row.display_name or row.username).strip(),
    }


if _REQUIRE_AUTH:
    if not _ADMIN_KEY or not _OPERATOR_KEY:
        raise RuntimeError(
            'Auth is required but LESNAR_ADMIN_API_KEY and LESNAR_OPERATOR_API_KEY are not both set. '
            'Set both keys or explicitly set LESNAR_REQUIRE_AUTH=0 for local-only development.'
        )

    weak_keys = []
    for env_key, value in {
        'LESNAR_ADMIN_API_KEY': _ADMIN_KEY,
        'LESNAR_OPERATOR_API_KEY': _OPERATOR_KEY,
        'FLASK_SECRET_KEY': (app.config.get('SECRET_KEY') or '').strip(),
        'LESNAR_AUDIT_CHAIN_KEY': _AUDIT_CHAIN_KEY,
    }.items():
        if not value:
            weak_keys.append(env_key)
        elif value.strip().lower() in _WEAK_SECRET_VALUES:
            weak_keys.append(env_key)

    if weak_keys:
        raise RuntimeError(
            'Weak or missing secret values detected for: '
            f'{weak_keys}. Replace placeholders with strong random secrets before startup.'
        )
else:
    logger.warning(
        'API authentication is explicitly DISABLED (LESNAR_REQUIRE_AUTH=0). '
        'Only use this mode in isolated local development.'
    )


def _get_role_from_request() -> str | None:
    bearer = (request.headers.get('Authorization') or '').strip()
    if bearer.lower().startswith('bearer '):
        token = bearer[7:].strip()
        session_payload = _validate_session_token(token)
        if session_payload:
            request._lesnar_session = session_payload
            return session_payload.get('role')
    key = (request.headers.get('X-API-Key') or '').strip()
    if not key:
        return None
    if _ADMIN_KEY and key == _ADMIN_KEY:
        return 'admin'
    if _OPERATOR_KEY and key == _OPERATOR_KEY:
        return 'operator'
    return None


def _get_request_actor() -> dict:
    session = getattr(request, '_lesnar_session', None)
    header_operator_id = (request.headers.get('X-Operator-Id') or '').strip() or None
    header_role = (request.headers.get('X-Operator-Role') or '').strip().lower() or None
    header_session_id = (request.headers.get('X-Session-Id') or '').strip() or None
    if session:
        return {
            'operator_id': session.get('username') or header_operator_id,
            'operator_role': session.get('role') or header_role,
            'session_id': session.get('session_id') or header_session_id,
            'auth_type': 'session',
        }
    key = (request.headers.get('X-API-Key') or '').strip()
    if key == _ADMIN_KEY:
        return {'operator_id': header_operator_id or 'api-admin', 'operator_role': 'admin', 'session_id': header_session_id, 'auth_type': 'api-key'}
    if key == _OPERATOR_KEY:
        return {'operator_id': header_operator_id or 'api-operator', 'operator_role': 'operator', 'session_id': header_session_id, 'auth_type': 'api-key'}
    return {'operator_id': header_operator_id, 'operator_role': header_role, 'session_id': header_session_id, 'auth_type': 'anonymous'}


def _issue_session_token(username: str, role: str, session_id: str) -> str:
    serializer = _get_auth_serializer()
    return serializer.dumps({'username': username, 'role': role, 'session_id': session_id})


def _validate_session_token(token: str) -> dict | None:
    if not token:
        return None
    serializer = _get_auth_serializer()
    try:
        payload = serializer.loads(token, max_age=SESSION_TTL_S)
    except (BadSignature, SignatureExpired):
        return None
    session_id = str(payload.get('session_id') or '').strip()
    if not session_id:
        return None
    try:
        row = AuthSession.query.filter_by(session_id=session_id).one_or_none()
        if row is None:
            return None
        now = datetime.utcnow()
        if row.revoked_at is not None or row.expires_at <= now:
            return None
        row.last_seen_at = now
        db.session.commit()
        payload['username'] = row.username
        payload['role'] = row.role
        return payload
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def require_role(required: str):
    order = {'viewer': 0, 'operator': 1, 'admin': 2}

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not _auth_enabled():
                return fn(*args, **kwargs)

            role = _get_role_from_request()
            if role is None:
                return jsonify({'success': False, 'error': 'Unauthorized (missing/invalid credentials)'}), 401

            if order.get(role, 0) < order.get(required, 999):
                return jsonify({'success': False, 'error': 'Forbidden'}), 403

            return fn(*args, **kwargs)

        return wrapper

    return decorator

# API Routes

def _safe_error(msg: str, e: Exception, status: int = 500):
    """Return a JSON error response without exposing internal exception details."""
    logger.error(f"{msg}: {e}")
    return jsonify({'success': False, 'error': msg}), status


def _validate_drone_id(drone_id: str) -> str | None:
    """Return an error message if drone_id is invalid, else None."""
    if not drone_id or len(drone_id) > MAX_DRONE_ID_LENGTH:
        return 'drone_id must be 1-128 characters'
    if not DRONE_ID_PATTERN.match(drone_id):
        return 'drone_id may only contain alphanumeric characters, hyphens, underscores, and dots'
    return None


def _validate_coordinates(lat, lon, alt=None) -> str | None:
    """Return an error message if coordinates are out of bounds, else None."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return 'latitude and longitude must be numeric'
    if not (LAT_MIN <= lat <= LAT_MAX):
        return f'latitude must be between {LAT_MIN} and {LAT_MAX}'
    if not (LON_MIN <= lon <= LON_MAX):
        return f'longitude must be between {LON_MIN} and {LON_MAX}'
    if alt is not None:
        try:
            alt = float(alt)
        except (TypeError, ValueError):
            return 'altitude must be numeric'
        if not (ALT_MIN <= alt <= ALT_MAX):
            return f'altitude must be between {ALT_MIN} and {ALT_MAX}'
    return None


def _try_audit(drone_id, action, payload, success, error):
    try:
        actor = _get_request_actor()
        safe_log_command(
            drone_id=drone_id,
            action=action,
            payload_json=json.dumps(payload) if payload is not None else None,
            success=success,
            error=error,
            operator_id=actor.get('operator_id'),
            operator_role=actor.get('operator_role'),
            session_id=actor.get('session_id'),
        )
    except Exception:
        pass


def _db_upsert_drone(drone_id: str, position_tuple: tuple | None, *, external: bool = False):
    row = Drone.query.filter_by(drone_id=drone_id).one_or_none()
    now = datetime.utcnow()
    home_position_json = json.dumps(list(position_tuple)) if position_tuple is not None else None
    config_json = json.dumps({'source': 'external'}) if external else None
    if row is None:
        row = Drone(
            drone_id=drone_id,
            enabled=True,
            home_position_json=home_position_json,
            config_json=config_json,
            created_at=now,
            updated_at=now,
        )
        db.session.add(row)
    else:
        row.enabled = True
        if home_position_json is not None:
            row.home_position_json = home_position_json
        if external:
            row.config_json = config_json
        row.updated_at = now
    db.session.commit()


def _db_disable_drone(drone_id: str):
    row = Drone.query.filter_by(drone_id=drone_id).one_or_none()
    if row is None:
        return
    row.enabled = False
    row.updated_at = datetime.utcnow()
    db.session.commit()


def _db_create_mission_and_run(drone_id: str, mission_type: str, waypoints: list):
    now = datetime.utcnow()
    mission = MissionModel(
        name=None,
        mission_type=mission_type,
        payload_json=json.dumps({'waypoints': waypoints, 'mission_type': mission_type}),
        created_at=now,
        updated_at=now,
    )
    db.session.add(mission)
    db.session.flush()  # mission.id
    run = MissionRun(
        mission_id=mission.id,
        drone_id=drone_id,
        status='CREATED',
        started_at=None,
        ended_at=None,
        error=None,
        created_at=now,
    )
    db.session.add(run)
    db.session.commit()
    return mission.id, run.id


def _db_update_latest_run_status(drone_id: str, status: str, *, ended: bool = False, error: str | None = None):
    run = (
        MissionRun.query
        .filter(MissionRun.drone_id == drone_id)
        .order_by(MissionRun.id.desc())
        .first()
    )
    if not run:
        return None
    run.status = status
    if status == 'RUNNING' and run.started_at is None:
        run.started_at = datetime.utcnow()
    if ended and run.ended_at is None:
        run.ended_at = datetime.utcnow()
    if error:
        run.error = error
    db.session.commit()
    return run


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_operational_boundary() -> list[list[float]]:
    raw = (os.environ.get('LESNAR_OPERATIONAL_BOUNDARY') or '').strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        out = []
        for row in data:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                lat = _safe_float(row[0], None)
                lon = _safe_float(row[1], None)
                if lat is not None and lon is not None:
                    out.append([lat, lon])
        return out
    except Exception as e:
        logger.warning(f"Invalid LESNAR_OPERATIONAL_BOUNDARY: {e}")
        return []


_OPERATIONAL_BOUNDARY = _load_operational_boundary()


def _point_in_polygon(lat: float, lon: float, polygon: list[list[float]]) -> bool:
    if len(polygon) < 3:
        return True
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        intersects = ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def _validate_operational_boundary(lat: float, lon: float) -> str | None:
    if not _OPERATIONAL_BOUNDARY:
        return None
    if not _point_in_polygon(float(lat), float(lon), _OPERATIONAL_BOUNDARY):
        return 'target lies outside the operational boundary'
    return None


def _state_is_flying(state) -> bool:
    altitude = _safe_float(getattr(state, 'altitude', 0.0))
    speed = _safe_float(getattr(state, 'speed', 0.0))
    armed = bool(getattr(state, 'armed', False))
    mode = str(getattr(state, 'mode', '') or '').upper()
    mode_tokens = ('TAKEOFF', 'OFFBOARD', 'MISSION', 'AUTO', 'LOITER', 'HOLD', 'RTL')
    return altitude > FLYING_ALTITUDE_THRESHOLD or speed > 0.8 or any(token in mode for token in mode_tokens) or (armed and speed > 0.1)


def _fleet_status_payload(states: list) -> dict:
    return {
        'total_drones': len(states),
        'armed_drones': len([s for s in states if bool(getattr(s, 'armed', False))]),
        'flying_drones': len([s for s in states if _state_is_flying(s)]),
        'low_battery_drones': len([s for s in states if _safe_float(getattr(s, 'battery', 0.0)) < LOW_BATTERY_THRESHOLD]),
    }


def _is_external_drone(drone_id: str | None) -> bool:
    return bool(drone_id) and drone_id in _external_drone_ids


def _prune_stale_external_drones() -> None:
    now = time.monotonic()
    for drone_id in list(_external_drone_ids):
        last_seen = _external_drone_last_seen_monotonic.get(drone_id)
        if last_seen is None or (now - last_seen) <= EXTERNAL_TELEMETRY_STALE_AFTER_S:
            continue
        logger.warning(f"Pruning stale external drone {drone_id}: no telemetry for {now - last_seen:.1f}s")
        try:
            fleet.remove_drone(drone_id)
        except Exception:
            pass
        _external_drone_ids.discard(drone_id)
        _external_drone_last_seen_monotonic.pop(drone_id, None)
        _external_drone_prev_samples.pop(drone_id, None)


def _get_live_states() -> list:
    _prune_stale_external_drones()
    if legacy_adapter is not None:
        adapter_states = legacy_adapter.get_all_states() or []
        if adapter_states:
            return adapter_states
    return fleet.get_all_states()


def _get_live_state(drone_id: str):
    for state in _get_live_states():
        if getattr(state, 'drone_id', None) == drone_id:
            return state
    return None


def _wait_for_state(drone_id: str, predicate, timeout_s: float):
    deadline = time.monotonic() + max(0.1, timeout_s)
    last_state = _get_live_state(drone_id)
    while time.monotonic() < deadline:
        state = _get_live_state(drone_id)
        if state is not None:
            last_state = state
            try:
                if predicate(state):
                    return True, state
            except Exception:
                pass
        time.sleep(0.2)
    return False, last_state


def _state_to_dict(state):
    if state is None:
        return {}
    payload = state.to_dict() if hasattr(state, 'to_dict') else dict(state)
    drone_id = payload.get('drone_id') or getattr(state, 'drone_id', None)
    payload['source'] = 'external' if _is_external_drone(drone_id) else 'simulated'
    return payload


def _command_result(drone_id: str, *, success: bool, message: str, state=None, accepted: bool = False, extra: dict | None = None, status_code: int | None = None):
    payload = {
        'success': bool(success),
        'accepted': bool(accepted),
        'confirmed': bool(success),
        'message': message,
        'state': _state_to_dict(state),
    }
    if extra:
        payload.update(extra)
    if status_code is None:
        status_code = 202 if accepted and not success else 200
    return jsonify(payload), status_code


def _persist_telemetry_history(states: list) -> None:
    if not states:
        return
    with app.app_context():
        now = datetime.utcnow()
        rows = []
        for state in states:
            source_ts = None
            raw_ts = getattr(state, 'timestamp', None)
            if raw_ts:
                try:
                    source_ts = datetime.fromisoformat(str(raw_ts).replace('Z', '+00:00')).replace(tzinfo=None)
                except Exception:
                    source_ts = None
            rows.append(TelemetrySample(
                drone_id=str(getattr(state, 'drone_id', '')),
                latitude=_safe_float(getattr(state, 'latitude', 0.0)),
                longitude=_safe_float(getattr(state, 'longitude', 0.0)),
                altitude=_safe_float(getattr(state, 'altitude', 0.0)),
                heading=_safe_float(getattr(state, 'heading', 0.0)),
                speed=_safe_float(getattr(state, 'speed', 0.0)),
                battery=_safe_float(getattr(state, 'battery', 0.0)),
                armed=bool(getattr(state, 'armed', False)),
                mode=str(getattr(state, 'mode', '') or ''),
                source_timestamp=source_ts,
                created_at=now,
            ))
        db.session.bulk_save_objects(rows)
        db.session.commit()

def _fetch_json(url, timeout_s=2.5):
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'LesnarAI/1.0 (local)',
            'Accept': 'application/json',
        },
        method='GET',
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read().decode('utf-8')
    return json.loads(data)

@app.route('/')
def home():
    """API home endpoint"""
    return jsonify({
        'message': 'Lesnar AI Drone Control API',
        'version': '1.0.0',
        'status': 'active',
        'endpoints': {
            'drones': '/api/drones',
            'telemetry': '/api/telemetry',
            'commands': '/api/commands',
            'missions': '/api/missions'
        }
    })


@app.route('/api/db/health', methods=['GET'])
def db_health():
    """Basic DB connectivity check."""
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'success': True, 'status': 'ok'})
    except Exception as e:
        return _safe_error('Database health check failed', e)


@app.route('/api/auth/login', methods=['POST'])
@limiter.limit('20 per minute')
def login():
    """Issue a short-lived session token for configured operators/viewers/admins."""
    try:
        if _auth_user_count() <= 0:
            return jsonify({'success': False, 'error': 'Session login is not configured on this deployment'}), 503
        data = request.get_json() or {}
        username = str(data.get('username') or '').strip()
        password = str(data.get('password') or '')
        if not username or not password:
            return jsonify({'success': False, 'error': 'username and password required'}), 400

        client_ip = request.remote_addr or '0.0.0.0'
        locked, remaining = _brute_check(client_ip, username)
        if locked:
            logger.warning(f"SECURITY: Blocked login attempt for '{username}' from {client_ip} (locked {remaining}s remaining)")
            return jsonify({'success': False, 'error': f'Account temporarily locked. Try again in {int(remaining)} seconds.'}), 429

        user = _authenticate_user(username, password)
        if user is None:
            _brute_record_failure(client_ip, username)
            # Constant-time response: do NOT reveal whether username exists
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

        _brute_clear(client_ip, username)
        session_id = uuid.uuid4().hex
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=SESSION_TTL_S)
        db.session.add(AuthSession(
            session_id=session_id,
            username=user['username'],
            role=user['role'],
            issued_at=now,
            expires_at=expires_at,
            last_seen_at=now,
            metadata_json=json.dumps({
                'display_name': user.get('display_name'),
                'remote_addr': client_ip,
                'user_agent': request.headers.get('User-Agent'),
            }),
        ))
        db.session.commit()
        token = _issue_session_token(user['username'], user['role'], session_id)
        safe_log_event('AUTH_LOGIN', payload={'username': user['username'], 'role': user['role']}, operator_id=user['username'], operator_role=user['role'], session_id=session_id)
        return jsonify({
            'success': True,
            'token': token,
            'session': {
                'sessionId': session_id,
                'userId': user['username'],
                'role': user['role'],
                'displayName': user.get('display_name') or user['username'],
                'expiresAt': expires_at.isoformat(),
            }
        })
    except Exception as e:
        return _safe_error('Login failed', e)


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    session = None
    bearer = (request.headers.get('Authorization') or '').strip()
    if bearer.lower().startswith('bearer '):
        session = _validate_session_token(bearer[7:].strip())
    if not session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    row = AuthSession.query.filter_by(session_id=session.get('session_id')).one_or_none()
    metadata = {}
    try:
        metadata = json.loads(row.metadata_json) if row and row.metadata_json else {}
    except Exception:
        metadata = {}
    return jsonify({'success': True, 'session': {
        'sessionId': session.get('session_id'),
        'userId': session.get('username'),
        'role': session.get('role'),
        'displayName': metadata.get('display_name') or session.get('username'),
        'expiresAt': row.expires_at.isoformat() if row else None,
    }})


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session = None
    bearer = (request.headers.get('Authorization') or '').strip()
    if bearer.lower().startswith('bearer '):
        session = _validate_session_token(bearer[7:].strip())
    if not session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    row = AuthSession.query.filter_by(session_id=session.get('session_id')).one_or_none()
    if row is None:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    row.revoked_at = datetime.utcnow()
    db.session.commit()
    safe_log_event('AUTH_LOGOUT', payload={'username': row.username, 'role': row.role}, operator_id=row.username, operator_role=row.role, session_id=row.session_id)
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# User Management CRUD (admin only)
# ---------------------------------------------------------------------------

_ROLE_HIERARCHY = {'viewer': 0, 'operator': 1, 'admin': 2}
_VALID_ROLES = set(_ROLE_HIERARCHY.keys())


@app.route('/api/auth/users', methods=['GET'])
@require_role('admin')
def list_users():
    """List all users (admin only). Passwords are never returned."""
    try:
        result = [_auth_user_public_dict(row) for row in AuthUser.query.all()]
        result.sort(key=lambda x: (-_ROLE_HIERARCHY.get(x['role'], 0), x['username']))
        return jsonify({'success': True, 'users': result, 'count': len(result)})
    except Exception as e:
        return _safe_error('Failed to list users', e)


@app.route('/api/auth/users', methods=['POST'])
@require_role('admin')
def create_user():
    """Create a new user (admin only)."""
    try:
        data = request.get_json() or {}
        username = str(data.get('username') or '').strip().lower()
        password = str(data.get('password') or '')
        role = str(data.get('role') or 'viewer').strip().lower()
        display_name = str(data.get('display_name') or username).strip()

        if not username or len(username) < 3 or len(username) > 64:
            return jsonify({'success': False, 'error': 'Username must be 3–64 characters'}), 400
        if not re.match(r'^[a-z0-9_\-]+$', username):
            return jsonify({'success': False, 'error': 'Username may only contain a-z, 0-9, _ or -'}), 400
        if len(password) < 8:
            return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400
        if role not in _VALID_ROLES:
            return jsonify({'success': False, 'error': f'Role must be one of: {", ".join(sorted(_VALID_ROLES))}'}), 400

        if _get_auth_user(username) is not None:
            return jsonify({'success': False, 'error': 'Username already exists'}), 409

        db.session.add(AuthUser(
            username=username,
            role=role,
            display_name=display_name[:128],
            password_hash=_hash_password_pbkdf2(password),
            last_password_change_at=datetime.utcnow(),
        ))
        db.session.commit()
        session_ctx = _validate_session_token((request.headers.get('Authorization') or '').replace('Bearer ', '').strip())
        safe_log_event('USER_CREATED', payload={'target_user': username, 'role': role}, operator_id=session_ctx.get('username') if session_ctx else 'admin', operator_role='admin')
        return jsonify({'success': True, 'user': {'username': username, 'role': role, 'display_name': display_name}}), 201
    except Exception as e:
        return _safe_error('Failed to create user', e)


@app.route('/api/auth/users/<target_username>', methods=['PUT'])
@require_role('admin')
def update_user(target_username):
    """Update an existing user's role, display name, or password (admin only)."""
    try:
        target_username = target_username.strip().lower()
        row = _get_auth_user(target_username)
        if row is None:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        data = request.get_json() or {}
        if 'role' in data:
            role = str(data['role']).strip().lower()
            if role not in _VALID_ROLES:
                return jsonify({'success': False, 'error': f'Role must be one of: {", ".join(sorted(_VALID_ROLES))}'}), 400
            # Prevent an admin from demoting themselves
            session_ctx = _validate_session_token((request.headers.get('Authorization') or '').replace('Bearer ', '').strip())
            if session_ctx and session_ctx.get('username') == target_username and role != 'admin':
                return jsonify({'success': False, 'error': 'Admins cannot demote themselves'}), 403
            row.role = role

        if 'display_name' in data:
            row.display_name = str(data['display_name']).strip()[:128]

        if 'password' in data:
            new_pw = str(data['password'])
            if len(new_pw) < 8:
                return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400
            row.password_hash = _hash_password_pbkdf2(new_pw)
            row.last_password_change_at = datetime.utcnow()
            # Revoke all existing sessions for this user for security
            now = datetime.utcnow()
            AuthSession.query.filter_by(username=target_username).filter(AuthSession.revoked_at.is_(None)).update({'revoked_at': now})
        db.session.commit()
        session_ctx = _validate_session_token((request.headers.get('Authorization') or '').replace('Bearer ', '').strip())
        safe_log_event('USER_UPDATED', payload={'target_user': target_username, 'fields': list(data.keys())}, operator_id=session_ctx.get('username') if session_ctx else 'admin', operator_role='admin')
        return jsonify({'success': True, 'user': _auth_user_public_dict(row)})
    except Exception as e:
        return _safe_error('Failed to update user', e)


@app.route('/api/auth/users/<target_username>', methods=['DELETE'])
@require_role('admin')
def delete_user(target_username):
    """Delete a user (admin only; cannot delete own account)."""
    try:
        target_username = target_username.strip().lower()
        session_ctx = _validate_session_token((request.headers.get('Authorization') or '').replace('Bearer ', '').strip())
        if session_ctx and session_ctx.get('username') == target_username:
            return jsonify({'success': False, 'error': 'You cannot delete your own account'}), 403

        row = _get_auth_user(target_username)
        if row is None:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Count admins — must keep at least one
        if _normalize_role(row.role) == 'admin':
            admin_count = AuthUser.query.filter_by(role='admin').count()
            if admin_count <= 1:
                return jsonify({'success': False, 'error': 'Cannot delete the last admin account'}), 409

        db.session.delete(row)
        # Revoke all sessions for deleted user
        now = datetime.utcnow()
        AuthSession.query.filter_by(username=target_username).filter(AuthSession.revoked_at.is_(None)).update({'revoked_at': now})
        db.session.commit()
        safe_log_event('USER_DELETED', payload={'target_user': target_username}, operator_id=session_ctx.get('username') if session_ctx else 'admin', operator_role='admin')
        return jsonify({'success': True})
    except Exception as e:
        return _safe_error('Failed to delete user', e)


# ---------------------------------------------------------------------------
# Security Status Endpoint (for presentation / audit)
# ---------------------------------------------------------------------------

@app.route('/api/security/status', methods=['GET'])
@require_role('admin')
def security_status():
    """Return a summary of the active security configuration (admin only)."""
    try:
        import hashlib as _hl
        role_counts = _auth_role_counts()

        # Audit chain health — count recent events
        audit_health = 'ok'
        try:
            event_count = AuditEvent.query.count()
            audit_health = f'ok ({event_count} events)'
        except Exception:
            audit_health = 'unavailable'

        cors_origins = os.environ.get('LESNAR_CORS_ORIGINS', '*')

        status = {
            'auth': {
                'method': 'PBKDF2-SHA256 (390000 iterations)',
                'session_mechanism': 'itsdangerous TimestampSigner + Postgres-backed users and session revocation',
                'session_ttl_seconds': SESSION_TTL_S,
                'roles': sorted(_VALID_ROLES, key=lambda r: _ROLE_HIERARCHY[r]),
                'role_counts': role_counts,
                'total_users': sum(role_counts.values()),
            },
            'brute_force_protection': {
                'enabled': True,
                'max_attempts': _LOGIN_MAX_ATTEMPTS,
                'window_seconds': _LOGIN_WINDOW_S,
                'lockout_seconds': _LOGIN_LOCKOUT_S,
                'currently_locked_ips': len(_FAILED_LOGINS),
            },
            'security_headers': [
                'X-Content-Type-Options: nosniff',
                'X-Frame-Options: DENY',
                'X-XSS-Protection: 1; mode=block',
                'Referrer-Policy: strict-origin-when-cross-origin',
                'Permissions-Policy: geolocation=(), camera=(), microphone=()',
                'Cache-Control: no-store',
                'Strict-Transport-Security (HTTPS only)',
            ],
            'rate_limiting': {
                'login': '20 per minute (flask-limiter)',
            },
            'cors': {
                'allowed_origins': cors_origins,
            },
            'audit_log': {
                'chain_status': audit_health,
                'storage': 'TimescaleDB AuditEvent table',
            },
            'weak_secret_detection': 'enabled (startup check)',
            'error_messages': 'sanitised — raw exceptions never exposed to client',
        }
        return jsonify({'success': True, 'security': status})
    except Exception as e:
        return _safe_error('Failed to retrieve security status', e)


@app.route('/api/drones', methods=['GET'])
@require_role('viewer')
def get_drones():
    """Get list of all drones"""
    try:
        states = _get_live_states()
        return jsonify({
            'success': True,
            'drones': [_state_to_dict(state) for state in states],
            'count': len(states)
        })
    except Exception as e:
        logger.error(f"Error getting drones: {e}")
        return _safe_error('Failed to retrieve drones', e)

@app.route('/api/drones/<drone_id>', methods=['GET'])
@require_role('viewer')
def get_drone(drone_id):
    """Get specific drone state"""
    try:
        id_err = _validate_drone_id(drone_id)
        if id_err:
            return jsonify({'success': False, 'error': id_err}), 400
        if legacy_adapter is not None:
            state = legacy_adapter.get_state(drone_id)
            if state is None:
                return jsonify({'success': False, 'error': 'Drone not found'}), 404
            return jsonify({'success': True, 'drone': _state_to_dict(state), 'obstacles': []})
        else:
            drone = fleet.get_drone(drone_id)
            if not drone:
                return jsonify({'success': False, 'error': 'Drone not found'}), 404
            return jsonify({
                'success': True,
                'drone': _state_to_dict(drone.get_state()),
                'obstacles': drone.obstacles_detected[-5:],
                'mission': drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None
            })
    except Exception as e:
        logger.error(f"Error getting drone {drone_id}: {e}")
        return _safe_error('Failed to retrieve drone', e)

@app.route('/api/drones', methods=['POST'])
@require_role('operator')
def create_drone():
    """Create a new drone"""
    try:
        if _EXTERNAL_ONLY:
            return jsonify({
                'success': False,
                'error': 'External-only mode enabled (LESNAR_EXTERNAL_ONLY=1). Drones must come from real telemetry.'
            }), 400
        data = request.get_json()
        drone_id = data.get('drone_id')
        position = data.get('position')  # [lat, lon, alt]

        if not drone_id:
            return jsonify({'success': False, 'error': 'drone_id required'}), 400

        id_err = _validate_drone_id(drone_id)
        if id_err:
            return jsonify({'success': False, 'error': id_err}), 400

        if position:
            position = tuple(position)

        success = fleet.add_drone(drone_id, position)
        if success:
            try:
                with app.app_context():
                    _db_upsert_drone(drone_id, position)
            except Exception as e:
                # Keep DB as source of truth: revert in-memory add if persistence fails.
                try:
                    fleet.remove_drone(drone_id)
                except Exception:
                    pass
                _try_audit(drone_id, 'create_drone', {'position': list(position) if position else None}, False, f'db_error:{e}')
                return _safe_error('Failed to persist drone', e)

            _try_audit(drone_id, 'create_drone', {'position': list(position) if position else None}, True, None)
            safe_log_event('DRONE_CREATED', drone_id=drone_id, payload={'position': list(position) if position else None})
            return jsonify({'success': True, 'message': f'Drone {drone_id} created'})
        else:
            return jsonify({'success': False, 'error': 'Drone already exists'}), 409

    except Exception as e:
        return _safe_error('Failed to create drone', e)

@app.route('/api/drones/<drone_id>', methods=['DELETE'])
@require_role('operator')
def delete_drone(drone_id):
    """Delete a drone"""
    try:
        success = fleet.remove_drone(drone_id)
        if success:
            try:
                with app.app_context():
                    _db_disable_drone(drone_id)
                    safe_log_event('DRONE_DISABLED', drone_id=drone_id)
            except Exception:
                pass
        _try_audit(drone_id, 'delete_drone', None, bool(success), None if success else 'not_found')
        if success:
            return jsonify({'success': True, 'message': f'Drone {drone_id} removed'})
        else:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
    
    except Exception as e:
        logger.error(f"Error deleting drone {drone_id}: {e}")
        return _safe_error('Failed to delete drone', e)

@app.route('/api/drones/<drone_id>/arm', methods=['POST'])
@require_role('operator')
def arm_drone(drone_id):
    """Arm a drone"""
    try:
        live_state = _get_live_state(drone_id)
        if _is_external_drone(drone_id):
            if live_state is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            published = _publish_command(drone_id, 'arm')
            if not published:
                return jsonify({'success': False, 'error': 'No active external control subscriber for arm command'}), 503
            success, state = _wait_for_state(drone_id, lambda s: bool(getattr(s, 'armed', False)), max(COMMAND_CONFIRM_TIMEOUT_S, 8.0))
            _try_audit(drone_id, 'arm', None, bool(success), None if success else 'not_confirmed')
            if success:
                return _command_result(drone_id, success=True, message=f'Drone {drone_id} arm confirmed.', state=state)
            return _command_result(
                drone_id,
                success=False,
                accepted=True,
                message=f'Arm command accepted for {drone_id}, but telemetry did not confirm arming.',
                state=state,
            )

        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
        
        success = drone.arm()
        _try_audit(drone_id, 'arm', None, bool(success), None if success else 'arm_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"armed" if success else "failed to arm"}',
            'state': _state_to_dict(drone.get_state())
        })
    
    except Exception as e:
        logger.error(f"Error arming drone {drone_id}: {e}")
        return _safe_error('Failed to arm drone', e)

@app.route('/api/drones/<drone_id>/disarm', methods=['POST'])
@require_role('operator')
def disarm_drone(drone_id):
    """Disarm a drone"""
    try:
        live_state = _get_live_state(drone_id)
        if _is_external_drone(drone_id):
            if live_state is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            published = _publish_command(drone_id, 'disarm')
            if not published:
                return jsonify({'success': False, 'error': 'No active external control subscriber for disarm command'}), 503
            success, state = _wait_for_state(drone_id, lambda s: not bool(getattr(s, 'armed', False)), max(COMMAND_CONFIRM_TIMEOUT_S, 8.0))
            _try_audit(drone_id, 'disarm', None, bool(success), None if success else 'not_confirmed')
            if success:
                return _command_result(drone_id, success=True, message=f'Drone {drone_id} disarm confirmed.', state=state)
            return _command_result(
                drone_id,
                success=False,
                accepted=True,
                message=f'Disarm command accepted for {drone_id}, but telemetry did not confirm disarming.',
                state=state,
            )

        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
        
        success = drone.disarm()
        _try_audit(drone_id, 'disarm', None, bool(success), None if success else 'disarm_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"disarmed" if success else "failed to disarm"}',
            'state': _state_to_dict(drone.get_state())
        })
    
    except Exception as e:
        logger.error(f"Error disarming drone {drone_id}: {e}")
        return _safe_error('Failed to disarm drone', e)


def _publish_command(drone_id: str, action: str, params: dict | None = None) -> bool:
    """Publish a command to Redis for external agents (Teacher/real drones)."""
    try:
        r = redis.Redis(host=_REDIS_HOST, port=_REDIS_PORT, db=0, socket_timeout=2)
        cmd = {
            'drone_id': drone_id,
            'action': action,
            'params': params or {},
            'timestamp': datetime.utcnow().isoformat(),
        }
        subscriber_count = int(r.publish('commands', json.dumps(cmd)))
        return subscriber_count > 0
    except Exception as e:
        logger.warning(f"Failed to publish Redis command ({action} -> {drone_id}): {e}")
        return False

@app.route('/api/drones/<drone_id>/takeoff', methods=['POST'])
@require_role('operator')
def takeoff_drone(drone_id):
    """Takeoff a drone"""
    try:
        data = request.get_json() or {}
        altitude = data.get('altitude', DEFAULT_TAKEOFF_ALT)
        live_before = _get_live_state(drone_id)

        if legacy_adapter is not None and live_before is None:
            return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404

        # Always publish to Redis (Teacher/real drones).
        published = _publish_command(drone_id, 'takeoff', {'altitude': altitude})

        if legacy_adapter is not None:
            accepted = legacy_adapter.takeoff(drone_id, altitude)
            success, state = _wait_for_state(
                drone_id,
                lambda s: _state_is_flying(s) and _safe_float(getattr(s, 'altitude', 0.0)) >= min(float(altitude), FLYING_ALTITUDE_THRESHOLD),
                max(COMMAND_CONFIRM_TIMEOUT_S, 45.0),
            )
            _try_audit(drone_id, 'takeoff', {'altitude': altitude}, bool(success), None if success else 'not_confirmed')
            if success:
                return _command_result(drone_id, success=True, message=f'Drone {drone_id} takeoff confirmed.', state=state, extra={'target_altitude': altitude})
            if accepted:
                return _command_result(
                    drone_id,
                    success=False,
                    accepted=True,
                    message=f'Takeoff command accepted for {drone_id}, but no verified takeoff was observed.',
                    state=state or live_before,
                    extra={'target_altitude': altitude, 'control_link_active': published},
                )
            return jsonify({'success': False, 'error': f'Failed to send takeoff command to {drone_id}'}), 503

        if _is_external_drone(drone_id):
            if live_before is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            if not published:
                return jsonify({'success': False, 'error': 'No active external control subscriber for takeoff command'}), 503
            success, state = _wait_for_state(
                drone_id,
                lambda s: _state_is_flying(s) and _safe_float(getattr(s, 'altitude', 0.0)) >= min(float(altitude), FLYING_ALTITUDE_THRESHOLD),
                max(COMMAND_CONFIRM_TIMEOUT_S, 45.0),
            )
            _try_audit(drone_id, 'takeoff', {'altitude': altitude}, bool(success), None if success else 'not_confirmed')
            if success:
                return _command_result(drone_id, success=True, message=f'Drone {drone_id} takeoff confirmed.', state=state, extra={'target_altitude': altitude})
            return _command_result(
                drone_id,
                success=False,
                accepted=True,
                message=f'Takeoff command accepted for {drone_id}, but no verified takeoff was observed.',
                state=state or live_before,
                extra={'target_altitude': altitude},
            )

        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404

        success = drone.takeoff(altitude)
        _try_audit(drone_id, 'takeoff', {'altitude': altitude}, bool(success), None if success else 'takeoff_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"taking off" if success else "failed to takeoff"}',
            'target_altitude': altitude,
            'state': _state_to_dict(drone.get_state())
        })

    except Exception as e:
        logger.error(f"Error takeoff drone {drone_id}: {e}")
        return _safe_error('Failed to execute takeoff', e)

@app.route('/api/drones/<drone_id>/land', methods=['POST'])
@require_role('operator')
def land_drone(drone_id):
    """Land a drone"""
    try:
        live_before = _get_live_state(drone_id)
        # Always publish to Redis (Teacher/real drones).
        published = _publish_command(drone_id, 'land')

        if legacy_adapter is not None:
            if live_before is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            accepted = legacy_adapter.land(drone_id)
            success, state = _wait_for_state(
                drone_id,
                lambda s: (
                    _safe_float(getattr(s, 'altitude', 0.0)) <= FLYING_ALTITUDE_THRESHOLD
                    or not bool(getattr(s, 'armed', True))
                ),
                max(COMMAND_CONFIRM_TIMEOUT_S, 20.0),
            )
            _try_audit(drone_id, 'land', None, bool(success), None if success else 'not_confirmed')
            if success:
                return _command_result(drone_id, success=True, message=f'Drone {drone_id} landing confirmed.', state=state)
            if accepted:
                return _command_result(
                    drone_id,
                    success=False,
                    accepted=True,
                    message=f'Land command accepted for {drone_id}, but landing was not verified.',
                    state=state or live_before,
                    extra={'control_link_active': published},
                )
            return jsonify({'success': False, 'error': f'Failed to send land command to {drone_id}'}), 503

        if _is_external_drone(drone_id):
            if live_before is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            if not published:
                return jsonify({'success': False, 'error': 'No active external control subscriber for land command'}), 503
            success, state = _wait_for_state(
                drone_id,
                lambda s: (
                    _safe_float(getattr(s, 'altitude', 0.0)) <= FLYING_ALTITUDE_THRESHOLD
                    or not bool(getattr(s, 'armed', True))
                ),
                max(COMMAND_CONFIRM_TIMEOUT_S, 20.0),
            )
            _try_audit(drone_id, 'land', None, bool(success), None if success else 'not_confirmed')
            if success:
                return _command_result(drone_id, success=True, message=f'Drone {drone_id} landing confirmed.', state=state)
            return _command_result(
                drone_id,
                success=False,
                accepted=True,
                message=f'Land command accepted for {drone_id}, but landing was not verified.',
                state=state or live_before,
            )

        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404

        success = drone.land()
        _try_audit(drone_id, 'land', None, bool(success), None if success else 'land_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"landing" if success else "failed to land"}',
            'state': _state_to_dict(drone.get_state())
        })

    except Exception as e:
        logger.error(f"Error landing drone {drone_id}: {e}")
        return _safe_error('Failed to execute landing', e)

@app.route('/api/drones/<drone_id>/goto', methods=['POST'])
@require_role('operator')
def goto_drone(drone_id):
    """Navigate drone to coordinates"""
    try:
        data = request.get_json() or {}
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        altitude = data.get('altitude', DEFAULT_TAKEOFF_ALT)

        if latitude is None or longitude is None:
            return jsonify({'success': False, 'error': 'latitude and longitude required'}), 400

        coord_err = _validate_coordinates(latitude, longitude, altitude)
        if coord_err:
            return jsonify({'success': False, 'error': coord_err}), 400
        boundary_err = _validate_operational_boundary(latitude, longitude)
        if boundary_err:
            return jsonify({'success': False, 'error': boundary_err}), 400

        # Always publish to Redis (Teacher/real drones).
        published = _publish_command(drone_id, 'goto', {'latitude': latitude, 'longitude': longitude, 'altitude': altitude})
        live_before = _get_live_state(drone_id)

        if legacy_adapter is not None:
            if live_before is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            accepted = legacy_adapter.goto(drone_id, latitude, longitude, altitude)
            success, state = _wait_for_state(
                drone_id,
                lambda s: abs(_safe_float(getattr(s, 'latitude', 0.0)) - float(latitude)) > 0.00001 or abs(_safe_float(getattr(s, 'longitude', 0.0)) - float(longitude)) > 0.00001 or _safe_float(getattr(s, 'speed', 0.0)) > 0.5 or 'AUTO' in str(getattr(s, 'mode', '')).upper(),
                COMMAND_CONFIRM_TIMEOUT_S,
            )
            _try_audit(drone_id, 'goto', {'latitude': latitude, 'longitude': longitude, 'altitude': altitude}, bool(success), None if success else 'not_confirmed')
            if success:
                return _command_result(
                    drone_id,
                    success=True,
                    message=f'Drone {drone_id} navigation confirmed.',
                    state=state,
                    extra={'target': {'latitude': latitude, 'longitude': longitude, 'altitude': altitude}},
                )
            if accepted:
                return _command_result(
                    drone_id,
                    success=False,
                    accepted=True,
                    message=f'Goto command accepted for {drone_id}, but movement was not confirmed.',
                    state=state or live_before,
                    extra={'target': {'latitude': latitude, 'longitude': longitude, 'altitude': altitude}, 'control_link_active': published},
                )
            return jsonify({'success': False, 'error': f'Failed to send goto command to {drone_id}'}), 503

        if _is_external_drone(drone_id):
            if live_before is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            if not published:
                return jsonify({'success': False, 'error': 'No active external control subscriber for goto command'}), 503
            success, state = _wait_for_state(
                drone_id,
                lambda s: abs(_safe_float(getattr(s, 'latitude', 0.0)) - float(latitude)) > 0.00001 or abs(_safe_float(getattr(s, 'longitude', 0.0)) - float(longitude)) > 0.00001 or _safe_float(getattr(s, 'speed', 0.0)) > 0.5 or 'AUTO' in str(getattr(s, 'mode', '')).upper(),
                COMMAND_CONFIRM_TIMEOUT_S,
            )
            _try_audit(drone_id, 'goto', {'latitude': latitude, 'longitude': longitude, 'altitude': altitude}, bool(success), None if success else 'not_confirmed')
            if success:
                return _command_result(
                    drone_id,
                    success=True,
                    message=f'Drone {drone_id} navigation confirmed.',
                    state=state,
                    extra={'target': {'latitude': latitude, 'longitude': longitude, 'altitude': altitude}},
                )
            return _command_result(
                drone_id,
                success=False,
                accepted=True,
                message=f'Goto command accepted for {drone_id}, but movement was not confirmed.',
                state=state or live_before,
                extra={'target': {'latitude': latitude, 'longitude': longitude, 'altitude': altitude}},
            )

        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
        
        success = drone.goto(latitude, longitude, altitude)
        _try_audit(drone_id, 'goto', {'latitude': latitude, 'longitude': longitude, 'altitude': altitude}, bool(success), None if success else 'goto_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"navigating" if success else "failed to navigate"}',
            'target': {'latitude': latitude, 'longitude': longitude, 'altitude': altitude},
            'state': _state_to_dict(drone.get_state())
        })
    
    except Exception as e:
        logger.error(f"Error navigating drone {drone_id}: {e}")
        return _safe_error('Failed to navigate drone', e)

@app.route('/api/drones/<drone_id>/mission', methods=['POST'])
@require_role('operator')
def execute_mission(drone_id):
    """Execute a mission"""
    try:
        data = request.get_json() or {}
        waypoints = data.get('waypoints', [])
        mission_type = data.get('mission_type', 'CUSTOM')

        if not waypoints:
            return jsonify({'success': False, 'error': 'waypoints required'}), 400

        # Validate each waypoint
        for i, wp in enumerate(waypoints):
            if not isinstance(wp, (list, tuple)) or len(wp) < 2:
                return jsonify({'success': False, 'error': f'waypoint {i} must be [lat, lon, alt]'}), 400
            alt = wp[2] if len(wp) > 2 else None
            coord_err = _validate_coordinates(wp[0], wp[1], alt)
            if coord_err:
                return jsonify({'success': False, 'error': f'waypoint {i}: {coord_err}'}), 400
            boundary_err = _validate_operational_boundary(wp[0], wp[1])
            if boundary_err:
                return jsonify({'success': False, 'error': f'waypoint {i}: {boundary_err}'}), 400

        estimated_duration = len(waypoints) * WAYPOINT_DURATION_ESTIMATE_S  # Rough estimate

        mission_id = None
        run_id = None
        try:
            with app.app_context():
                mission_id, run_id = _db_create_mission_and_run(drone_id, mission_type, waypoints)
        except Exception as e:
            _try_audit(drone_id, 'mission_start', {'mission_type': mission_type, 'waypoints': waypoints}, False, f'db_error:{e}')
            return _safe_error('Failed to persist mission', e)

        if _is_external_drone(drone_id):
            live_before = _get_live_state(drone_id)
            if live_before is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            published = _publish_command(drone_id, 'mission_start', {
                'waypoints': waypoints,
                'mission_type': mission_type,
                'mission_run_id': run_id,
            })
            if not published:
                try:
                    with app.app_context():
                        _db_update_latest_run_status(drone_id, 'FAILED', ended=True, error='no_external_subscriber')
                except Exception:
                    pass
                return jsonify({'success': False, 'error': 'No active external control subscriber for mission command'}), 503
            try:
                with app.app_context():
                    _db_update_latest_run_status(drone_id, 'RUNNING')
                    safe_log_event('MISSION_STARTED', drone_id=drone_id, mission_run_id=run_id, payload={'mission_type': mission_type})
            except Exception:
                pass
            _try_audit(drone_id, 'mission_start', {'mission_type': mission_type, 'waypoints': waypoints}, True, None)
            try:
                socketio.emit('mission_status', {'drone_id': drone_id, 'status': 'RUNNING'})
            except Exception:
                pass
            return jsonify({
                'success': True,
                'accepted': True,
                'confirmed': False,
                'message': f'Mission uplink accepted for {drone_id}.',
                'mission': {
                    'waypoints': waypoints,
                    'mission_type': mission_type,
                    'estimated_duration': estimated_duration
                },
                'mission_run_id': run_id,
                'state': _state_to_dict(live_before),
            })

        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404

        mission = Mission(
            waypoints=[tuple(wp) for wp in waypoints],
            mission_type=mission_type,
        )

        success = drone.execute_mission(mission)
        if success:
            try:
                with app.app_context():
                    _db_update_latest_run_status(drone_id, 'RUNNING')
                    safe_log_event('MISSION_STARTED', drone_id=drone_id, mission_run_id=run_id, payload={'mission_type': mission_type})
            except Exception:
                pass
        else:
            try:
                with app.app_context():
                    _db_update_latest_run_status(drone_id, 'FAILED', ended=True, error='mission_failed')
                    safe_log_event('MISSION_FAILED', drone_id=drone_id, mission_run_id=run_id)
            except Exception:
                pass

        _try_audit(drone_id, 'mission_start', {'mission_type': mission_type, 'waypoints': waypoints}, bool(success), None if success else 'mission_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"executing mission" if success else "failed to start mission"}',
            'mission': {
                'waypoints': waypoints,
                'mission_type': mission_type,
                'estimated_duration': estimated_duration
            },
            'mission_run_id': run_id,
            'state': _state_to_dict(drone.get_state())
        })
    
    except Exception as e:
        logger.error(f"Error executing mission for drone {drone_id}: {e}")
        return _safe_error('Failed to execute mission', e)


@app.route('/api/missions/active', methods=['GET'])
@require_role('viewer')
def get_active_missions():
    """Get list of active/paused missions."""
    try:
        missions = []
        if legacy_adapter is not None:
            # Legacy adapter currently exposes only basic state.
            states = legacy_adapter.get_all_states() or []
            for st in states:
                d = st.to_dict()
                if (d.get('mode') or '').upper() in ('MISSION', 'HOLD'):
                    missions.append({
                        'drone_id': d.get('drone_id'),
                        'mission_type': 'UNKNOWN',
                        'total_waypoints': None,
                        'current_waypoint_index': None,
                        'estimated_remaining_s': None,
                        'status': 'ACTIVE' if (d.get('mode') or '').upper() == 'MISSION' else 'PAUSED',
                        'started_at': None,
                    })
        else:
            # Simulator mode: pull mission details directly.
            for drone in list(getattr(fleet, 'drones', {}).values()):
                drone_id = getattr(drone, 'drone_id', None) or getattr(drone.get_state(), 'drone_id', None)
                if not drone_id:
                    continue
                info = drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None
                if info:
                    missions.append(info)
                    continue
                if _is_external_drone(drone_id):
                    latest = (
                        MissionRun.query
                        .filter(MissionRun.drone_id == drone_id, MissionRun.status.in_(['RUNNING', 'PAUSED']))
                        .order_by(MissionRun.id.desc())
                        .first()
                    )
                    if not latest:
                        continue
                    mission_row = MissionModel.query.filter(MissionModel.id == latest.mission_id).first()
                    payload = {}
                    try:
                        payload = json.loads(mission_row.payload_json) if mission_row and mission_row.payload_json else {}
                    except Exception:
                        payload = {}
                    waypoints = payload.get('waypoints') or []
                    missions.append({
                        'drone_id': drone_id,
                        'mission_type': payload.get('mission_type') or (mission_row.mission_type if mission_row else 'CUSTOM'),
                        'total_waypoints': len(waypoints),
                        'current_waypoint_index': None,
                        'estimated_remaining_s': max(0, len(waypoints) * int(WAYPOINT_DURATION_ESTIMATE_S)) if waypoints else None,
                        'status': 'PAUSED' if latest.status == 'PAUSED' else 'ACTIVE',
                        'started_at': latest.started_at.isoformat() if latest.started_at else latest.created_at.isoformat() if latest.created_at else None,
                    })
        return jsonify({'success': True, 'missions': missions, 'count': len(missions)})
    except Exception as e:
        logger.error(f"Error getting active missions: {e}")
        return _safe_error('Failed to retrieve active missions', e)


@app.route('/api/drones/<drone_id>/mission/pause', methods=['POST'])
@require_role('operator')
def pause_mission(drone_id):
    """Pause a mission."""
    try:
        if legacy_adapter is not None:
            return jsonify({'success': False, 'error': 'Mission pause not supported for Legacy adapter'}), 501
        if _is_external_drone(drone_id):
            live_before = _get_live_state(drone_id)
            if live_before is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            if not _publish_command(drone_id, 'mission_pause'):
                return jsonify({'success': False, 'error': 'No active external control subscriber for mission pause'}), 503
            run = None
            try:
                with app.app_context():
                    run = _db_update_latest_run_status(drone_id, 'PAUSED')
                    safe_log_event('MISSION_PAUSED', drone_id=drone_id, mission_run_id=run.id if run else None)
            except Exception:
                pass
            try:
                socketio.emit('mission_status', {'drone_id': drone_id, 'status': 'PAUSED'})
            except Exception:
                pass
            return jsonify({
                'success': True,
                'accepted': True,
                'message': f'Drone {drone_id} pause command uplinked.',
                'state': _state_to_dict(live_before),
                'mission': fleet.get_drone(drone_id).get_mission_info() if fleet.get_drone(drone_id) else None,
            })
        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
        ok = drone.pause_mission() if hasattr(drone, 'pause_mission') else False
        if ok:
            try:
                with app.app_context():
                    run = _db_update_latest_run_status(drone_id, 'PAUSED')
                    safe_log_event('MISSION_PAUSED', drone_id=drone_id, mission_run_id=run.id if run else None)
            except Exception:
                pass
        return jsonify({
            'success': bool(ok),
            'message': f'Drone {drone_id} {"paused" if ok else "failed to pause"} mission',
            'state': _state_to_dict(drone.get_state()),
            'mission': drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None,
        })
    except Exception as e:
        logger.error(f"Error pausing mission for drone {drone_id}: {e}")
        return _safe_error('Failed to pause mission', e)


@app.route('/api/drones/<drone_id>/mission/resume', methods=['POST'])
@require_role('operator')
def resume_mission(drone_id):
    """Resume a paused mission."""
    try:
        if legacy_adapter is not None:
            return jsonify({'success': False, 'error': 'Mission resume not supported for Legacy adapter'}), 501
        if _is_external_drone(drone_id):
            live_before = _get_live_state(drone_id)
            if live_before is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            if not _publish_command(drone_id, 'mission_resume'):
                return jsonify({'success': False, 'error': 'No active external control subscriber for mission resume'}), 503
            run = None
            try:
                with app.app_context():
                    run = _db_update_latest_run_status(drone_id, 'RUNNING')
                    safe_log_event('MISSION_RESUMED', drone_id=drone_id, mission_run_id=run.id if run else None)
            except Exception:
                pass
            try:
                socketio.emit('mission_status', {'drone_id': drone_id, 'status': 'RUNNING'})
            except Exception:
                pass
            return jsonify({
                'success': True,
                'accepted': True,
                'message': f'Drone {drone_id} resume command uplinked.',
                'state': _state_to_dict(live_before),
                'mission': fleet.get_drone(drone_id).get_mission_info() if fleet.get_drone(drone_id) else None,
            })
        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
        ok = drone.resume_mission() if hasattr(drone, 'resume_mission') else False
        if ok:
            try:
                with app.app_context():
                    run = _db_update_latest_run_status(drone_id, 'RUNNING')
                    safe_log_event('MISSION_RESUMED', drone_id=drone_id, mission_run_id=run.id if run else None)
            except Exception:
                pass
        return jsonify({
            'success': bool(ok),
            'message': f'Drone {drone_id} {"resumed" if ok else "failed to resume"} mission',
            'state': _state_to_dict(drone.get_state()),
            'mission': drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None,
        })
    except Exception as e:
        logger.error(f"Error resuming mission for drone {drone_id}: {e}")
        return _safe_error('Failed to resume mission', e)


@app.route('/api/drones/<drone_id>/mission/stop', methods=['POST'])
@require_role('operator')
def stop_mission(drone_id):
    """Stop/cancel a mission."""
    try:
        if legacy_adapter is not None:
            return jsonify({'success': False, 'error': 'Mission stop not supported for Legacy adapter'}), 501
        if _is_external_drone(drone_id):
            live_before = _get_live_state(drone_id)
            if live_before is None:
                return jsonify({'success': False, 'error': 'Live drone telemetry not found'}), 404
            if not _publish_command(drone_id, 'mission_stop'):
                return jsonify({'success': False, 'error': 'No active external control subscriber for mission stop'}), 503
            run = None
            try:
                with app.app_context():
                    run = _db_update_latest_run_status(drone_id, 'STOPPED', ended=True)
                    safe_log_event('MISSION_STOPPED', drone_id=drone_id, mission_run_id=run.id if run else None)
            except Exception:
                pass
            try:
                socketio.emit('mission_status', {'drone_id': drone_id, 'status': 'STOPPED'})
            except Exception:
                pass
            return jsonify({
                'success': True,
                'accepted': True,
                'message': f'Drone {drone_id} stop command uplinked.',
                'state': _state_to_dict(live_before),
                'mission': None,
            })
        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
        ok = drone.stop_mission() if hasattr(drone, 'stop_mission') else False
        if ok:
            try:
                with app.app_context():
                    run = _db_update_latest_run_status(drone_id, 'STOPPED', ended=True)
                    safe_log_event('MISSION_STOPPED', drone_id=drone_id, mission_run_id=run.id if run else None)
            except Exception:
                pass
        return jsonify({
            'success': bool(ok),
            'message': f'Drone {drone_id} {"stopped" if ok else "failed to stop"} mission',
            'state': _state_to_dict(drone.get_state()),
            'mission': drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None,
        })
    except Exception as e:
        logger.error(f"Error stopping mission for drone {drone_id}: {e}")
        return _safe_error('Failed to stop mission', e)

@app.route('/api/emergency', methods=['POST'])
@require_role('admin')
@limiter.limit("5 per minute")
def emergency_land_all():
    """Emergency land all drones"""
    try:
        fleet.emergency_land_all()
        # Ensure Gazebo/PX4 Bridge actually receives the emergency command via Redis publish
        _publish_command('SENTINEL-01', 'land')
        return jsonify({
            'success': True,
            'message': 'Emergency landing initiated for all drones',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error during emergency landing: {e}")
        return _safe_error('Emergency landing failed', e)

@app.route('/api/telemetry', methods=['GET'])
@require_role('viewer')
def get_telemetry():
    """Get current telemetry data"""
    try:
        states = _get_live_states()
        return jsonify({
            'success': True,
            'telemetry': [_state_to_dict(state) for state in states],
            'timestamp': datetime.now().isoformat(),
            'fleet_status': _fleet_status_payload(states)
        })
    
    except Exception as e:
        logger.error(f"Error getting telemetry: {e}")
        return _safe_error('Failed to retrieve telemetry', e)


@app.route('/api/telemetry/history', methods=['GET'])
@require_role('viewer')
def get_telemetry_history():
    """Return recent telemetry samples for replay/AAR."""
    try:
        drone_id = (request.args.get('drone_id') or '').strip() or None
        limit = max(1, min(int(request.args.get('limit') or 500), 5000))
        query = TelemetrySample.query
        if drone_id:
            query = query.filter(TelemetrySample.drone_id == drone_id)
        rows = query.order_by(TelemetrySample.created_at.desc()).limit(limit).all()
        rows.reverse()
        return jsonify({'success': True, 'samples': [
            {
                'drone_id': row.drone_id,
                'latitude': row.latitude,
                'longitude': row.longitude,
                'altitude': row.altitude,
                'heading': row.heading,
                'speed': row.speed,
                'battery': row.battery,
                'armed': row.armed,
                'mode': row.mode,
                'timestamp': (row.source_timestamp or row.created_at).isoformat(),
                'created_at': row.created_at.isoformat(),
            }
            for row in rows
        ]})
    except Exception as e:
        return _safe_error('Failed to retrieve telemetry history', e)


@app.route('/api/drones/<drone_id>/history', methods=['GET'])
@require_role('viewer')
def get_drone_history(drone_id):
    try:
        limit = max(1, min(int(request.args.get('limit') or 500), 5000))
        rows = (
            TelemetrySample.query
            .filter(TelemetrySample.drone_id == drone_id)
            .order_by(TelemetrySample.created_at.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        return jsonify({'success': True, 'drone_id': drone_id, 'samples': [
            {
                'latitude': row.latitude,
                'longitude': row.longitude,
                'altitude': row.altitude,
                'heading': row.heading,
                'speed': row.speed,
                'battery': row.battery,
                'armed': row.armed,
                'mode': row.mode,
                'timestamp': (row.source_timestamp or row.created_at).isoformat(),
                'created_at': row.created_at.isoformat(),
            }
            for row in rows
        ]})
    except Exception as e:
        return _safe_error('Failed to retrieve drone history', e)

@app.route('/api/obstacles', methods=['GET'])
@require_role('viewer')
def get_obstacles():
    """Get static obstacles GeoJSON"""
    try:
        data_path = os.path.join(os.path.dirname(__file__), '..', 'drone_simulation', 'data', 'obstacles.geojson')
        with open(data_path, 'r') as f:
            geojson = json.load(f)
        return jsonify(geojson)
    except Exception as e:
        logger.error(f"Error loading obstacles: {e}")
        return _safe_error('Failed to load obstacles', e)

@app.route('/api/geocode/suggest', methods=['GET'])
@limiter.limit("30 per minute")
def geocode_suggest():
    """Suggest locations for a query string via Nominatim (OpenStreetMap)."""
    try:
        q = (request.args.get('q') or '').strip()
        if not q:
            return jsonify({'success': False, 'error': 'q required'}), 400
        params = {
            'format': 'json',
            'limit': '6',
            'q': q,
        }
        url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(params)
        results = _fetch_json(url, timeout_s=3.0)
        out = []
        for r in (results or []):
            try:
                out.append({
                    'display_name': r.get('display_name'),
                    'lat': float(r.get('lat')),
                    'lng': float(r.get('lon')),
                })
            except Exception:
                continue
        return jsonify({'success': True, 'results': out})
    except Exception as e:
        logger.error(f"Error in geocode_suggest: {e}")
        return _safe_error('Geocoding failed', e)

@app.route('/api/geocode/reverse', methods=['GET'])
def geocode_reverse():
    """Reverse geocode lat/lng to a human label via Nominatim (OpenStreetMap)."""
    try:
        lat = request.args.get('lat')
        lng = request.args.get('lng')
        if lat is None or lng is None:
            return jsonify({'success': False, 'error': 'lat and lng required'}), 400
        params = {
            'format': 'json',
            'lat': str(lat),
            'lon': str(lng),
        }
        url = 'https://nominatim.openstreetmap.org/reverse?' + urllib.parse.urlencode(params)
        result = _fetch_json(url, timeout_s=3.0)
        return jsonify({
            'success': True,
            'display_name': (result or {}).get('display_name'),
        })
    except Exception as e:
        logger.error(f"Error in geocode_reverse: {e}")
        return _safe_error('Reverse geocoding failed', e)

@app.route('/api/health', methods=['GET'])
@require_role('viewer')
def health():
    """Return a minimal health report for the backend service."""
    try:
        uptime_s = _time.time() - _START_TIME
        # Optional package versions
        def _ver(mod_name):
            try:
                m = __import__(mod_name)
                return getattr(m, '__version__', 'unknown')
            except Exception:
                return None

        # Read repo root config.json and report segmentation settings
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        config_path = os.path.join(repo_root, 'config.json')
        cfg = None
        seg_info = {
            'enabled': None,
            'backend': None,
            'model_path': None,
            'model_exists': None,
        }
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    cfg = json.load(f)
                ai_cfg = (cfg or {}).get('ai_settings', {})
                seg_cfg = ai_cfg.get('segmentation', {})
                seg_info['enabled'] = seg_cfg.get('enabled')
                seg_info['backend'] = seg_cfg.get('backend')
                seg_info['model_path'] = seg_cfg.get('model_path')
                mpath = seg_cfg.get('model_path')
                if mpath:
                    mpath_full = mpath if os.path.isabs(mpath) else os.path.join(repo_root, mpath)
                    seg_info['model_exists'] = os.path.exists(mpath_full)
        except Exception as _e:
            seg_info['error'] = str(_e)

        # Database check
        db_ok = True
        try:
            db.session.execute(db.text('SELECT 1'))
        except Exception:
            db_ok = False

        report = {
            'service': 'Lesnar AI Backend',
            'status': 'ok' if db_ok else 'degraded',
            'db_connected': db_ok,
            'time': datetime.now().isoformat(),
            'uptime_seconds': round(uptime_s, 1),
            'versions': {
                'python': sys.version.split()[0],
                'flask': _ver('flask'),
                'flask_socketio': _ver('flask_socketio'),
                'socketio': _ver('socketio'),
            },
            'features': {
                'computer_vision': bool(((cfg or {}).get('ai_settings') or {}).get('computer_vision_enabled')),
                'obstacle_avoidance': bool(((cfg or {}).get('ai_settings') or {}).get('obstacle_avoidance_enabled')),
                'swarm_intelligence': bool(((cfg or {}).get('ai_settings') or {}).get('swarm_intelligence_enabled')),
                'segmentation_enabled': bool(seg_info.get('enabled')),
            },
            'segmentation': seg_info,
        }
        return jsonify(report)
    except Exception as e:
        logger.error(f"Error in /api/health: {e}")
        return _safe_error('Health check failed', e)

@app.route('/api/config', methods=['GET'])
@require_role('viewer')
def get_config():
    """Return current repo config.json contents."""
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        config_path = os.path.join(repo_root, 'config.json')
        if not os.path.exists(config_path):
            return jsonify({'success': False, 'error': 'config.json not found'}), 404
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        return jsonify({'success': True, 'config': cfg})
    except Exception as e:
        logger.error(f"Error reading config: {e}")
        return _safe_error('Failed to read configuration', e)

@app.route('/api/config', methods=['POST'])
@require_role('admin')
@limiter.limit("10 per minute")
def update_config():
    """Update config.json safely with schema validation."""
    try:
        data = request.get_json() or {}
        if 'config' not in data:
            return jsonify({'success': False, 'error': 'config field required'}), 400
        cfg = data['config']

        if not isinstance(cfg, dict):
            return jsonify({'success': False, 'error': 'config must be a JSON object'}), 400
        unknown_keys = set(cfg.keys()) - CONFIG_ALLOWED_KEYS
        if unknown_keys:
            return jsonify({'success': False, 'error': f'unknown config keys: {", ".join(sorted(unknown_keys))}'}), 400

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        config_path = os.path.join(repo_root, 'config.json')
        backup_path = config_path + ".bak"
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    old = f.read()
                with open(backup_path, 'w') as bf:
                    bf.write(old)
            except Exception:
                pass
        with open(config_path, 'w') as f:
            json.dump(cfg, f, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return _safe_error('Failed to update configuration', e)

@app.route('/api/logs/segmentation/latest', methods=['GET'])
@require_role('viewer')
def get_latest_segmentation_log():
    """Return latest segmentation diagnostics CSV as JSON rows (most recent SEG_LOG_MAX_ROWS)."""
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        logs_dir = Path(os.path.join(repo_root, 'logs'))
        if not logs_dir.exists():
            return jsonify({'success': False, 'error': 'logs dir missing'}), 404
        candidates = sorted(logs_dir.glob('seg_diag_*.csv'), reverse=True)
        if not candidates:
            return jsonify({'success': False, 'error': 'no segmentation logs found'}), 404
        latest = candidates[0]
        import csv as _csv_mod
        all_rows = []
        with open(latest, 'r', newline='') as f:
            rdr = _csv_mod.DictReader(f)
            for row in rdr:
                all_rows.append(row)
        # Return only the most recent rows so the UI shows live detections
        rows = all_rows[-SEG_LOG_MAX_ROWS:] if len(all_rows) > SEG_LOG_MAX_ROWS else all_rows
        return jsonify({'success': True, 'file': latest.name, 'rows': rows})
    except Exception as e:
        logger.error(f"Error reading latest segmentation log: {e}")
        return _safe_error('Failed to read segmentation logs', e)

# WebSocket Events for Real-time Communication

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info('Client connected to WebSocket')
    emit('connected', {'message': 'Connected to Lesnar AI Drone API'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info('Client disconnected from WebSocket')

@socketio.on('subscribe_telemetry')
def handle_subscribe_telemetry():
    """Subscribe to real-time telemetry"""
    logger.info('Client subscribed to telemetry updates')
    emit('telemetry_subscribed', {'message': 'Subscribed to telemetry updates'})

def broadcast_telemetry():
    """Broadcast telemetry data to all connected clients"""
    sync_tick = 0
    while not _telemetry_stop.is_set():
        try:
            states = _get_live_states()
            telemetry_data = {
                'telemetry': [_state_to_dict(state) for state in states],
                'timestamp': datetime.now().isoformat(),
                'fleet_status': _fleet_status_payload(states)
            }

            socketio.emit('telemetry_update', telemetry_data)

            # Best-effort mission run status sync (keeps DB consistent without storing high-rate telemetry).
            sync_tick = (sync_tick + 1) % DB_SYNC_INTERVAL
            if sync_tick == 0:
                try:
                    _persist_telemetry_history(states)
                    if legacy_adapter is None:
                        with app.app_context():
                            for drone in list(getattr(fleet, 'drones', {}).values()):
                                drone_id = getattr(drone, 'drone_id', None) or getattr(drone.get_state(), 'drone_id', None)
                                if not drone_id:
                                    continue
                                info = drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None
                                latest = (
                                    MissionRun.query
                                    .filter(MissionRun.drone_id == drone_id)
                                    .order_by(MissionRun.id.desc())
                                    .first()
                                )
                                if not latest:
                                    continue

                                if _is_external_drone(drone_id):
                                    continue

                                if info is None:
                                    if latest.status in ('RUNNING', 'PAUSED'):
                                        latest.status = 'COMPLETED'
                                        if latest.ended_at is None:
                                            latest.ended_at = datetime.utcnow()
                                        db.session.commit()
                                else:
                                    desired = 'RUNNING' if (info.get('status') == 'ACTIVE') else 'PAUSED'
                                    if latest.status != desired:
                                        latest.status = desired
                                        if desired == 'RUNNING' and latest.started_at is None:
                                            latest.started_at = datetime.utcnow()
                                        db.session.commit()
                except Exception:
                    # Never interrupt telemetry.
                    pass
            _telemetry_stop.wait(TELEMETRY_SLEEP_S)

        except Exception as e:
            logger.error(f"Error broadcasting telemetry: {e}")
            _telemetry_stop.wait(TELEMETRY_SLEEP_S)

def start_telemetry_broadcast():
    """Start telemetry broadcasting thread"""
    global telemetry_thread

    if not _telemetry_stop.is_set() and telemetry_thread is not None and telemetry_thread.is_alive():
        return

    _telemetry_stop.clear()
    telemetry_thread = threading.Thread(target=broadcast_telemetry)
    telemetry_thread.daemon = True
    telemetry_thread.start()
    logger.info("Telemetry broadcasting started")

def stop_telemetry_broadcast():
    """Stop telemetry broadcasting"""
    _telemetry_stop.set()
    logger.info("Telemetry broadcasting stopped")

# --- Redis Bridge ---
redis_bridge_thread = None
_redis_bridge_stop = threading.Event()

def redis_bridge_loop():
    """Listen for telemetry from external agents (Teacher/Sentinel)."""
    r = None
    pubsub = None

    while not _redis_bridge_stop.is_set():
        try:
            if r is None:
                r = redis.Redis(host=_REDIS_HOST, port=_REDIS_PORT, db=0, socket_timeout=5)
                pubsub = r.pubsub()
                pubsub.subscribe('telemetry')
                logger.info(f"Redis Bridge connected ({_REDIS_HOST}:{_REDIS_PORT}). Listening for telemetry...")
            
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message['type'] == 'message':
                try:
                    raw = message.get('data')
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode('utf-8', errors='replace')
                    data = json.loads(raw)
                    drone_id = data.get('drone_id')
                    if drone_id:
                        first_seen_external = drone_id not in _external_drone_ids
                        _external_drone_ids.add(drone_id)
                        _external_drone_last_seen_monotonic[drone_id] = time.monotonic()

                        # Ensure the DB + in-memory fleet treat this drone as EXTERNAL source-of-truth.
                        if first_seen_external:
                            logger.info(f"Discovered external drone via Redis: {drone_id}")
                            # Auto-mark as external so it doesn't get restored as a simulated drone.
                            try:
                                with app.app_context():
                                    _db_upsert_drone(drone_id, (data.get('latitude', 0), data.get('longitude', 0), 0), external=True)
                            except Exception:
                                pass

                        # Ensure drone exists in fleet.
                        if not fleet.get_drone(drone_id):
                            fleet.add_drone(
                                drone_id,
                                (data.get('latitude', 0), data.get('longitude', 0), data.get('altitude', 0)),
                                start_simulation=False,
                            )

                        # Stop internal sim loop (prevents competing updates causing jumps).
                        try:
                            d = fleet.get_drone(drone_id)
                            if d is not None:
                                d.stop_simulation()
                                d.running = False
                        except Exception:
                            pass
                    
                    drone = fleet.get_drone(drone_id)
                    if drone:
                        prev_lat = _safe_float(data.get('latitude', drone.position[0]), drone.position[0])
                        prev_lon = _safe_float(data.get('longitude', drone.position[1]), drone.position[1])
                        prev_alt = _safe_float(data.get('altitude', drone.position[2]), drone.position[2])
                        now_mono = time.monotonic()
                        prev_sample = _external_drone_prev_samples.get(drone_id)
                        derived_speed = None
                        if prev_sample is not None:
                            dt = max(0.001, now_mono - prev_sample['t'])
                            lat_m = (prev_lat - prev_sample['lat']) * 111000.0
                            lon_m = (prev_lon - prev_sample['lon']) * 111000.0 * max(0.1, abs(math.cos(math.radians(prev_lat))))
                            alt_m = prev_alt - prev_sample['alt']
                            derived_speed = math.sqrt(lat_m ** 2 + lon_m ** 2 + alt_m ** 2) / dt
                        _external_drone_prev_samples[drone_id] = {'lat': prev_lat, 'lon': prev_lon, 'alt': prev_alt, 't': now_mono}
                        # Update state directly (Source of Truth is now Redis)
                        drone.position = [
                            prev_lat,
                            prev_lon,
                            prev_alt
                        ]
                        drone.heading = float(data.get('heading', drone.heading))
                        reported_speed = data.get('speed', None)
                        if reported_speed is None:
                            drone.speed = float(derived_speed if derived_speed is not None else drone.speed)
                        else:
                            reported_speed = _safe_float(reported_speed, drone.speed)
                            drone.speed = float(derived_speed if reported_speed <= 0.05 and derived_speed is not None else reported_speed)
                        if 'battery' in data: drone.battery = float(data['battery'])
                        if 'armed' in data: drone.armed = bool(data['armed'])
                        if 'mode' in data: drone.mode = str(data['mode'])
                        drone.is_flying = bool(data.get('in_air', drone.is_flying or prev_alt > FLYING_ALTITUDE_THRESHOLD or drone.speed > 0.8))
                        mission_status = data.get('mission_status')
                        if mission_status in ('ACTIVE', 'PAUSED'):
                            drone.external_mission_info = {
                                'drone_id': drone_id,
                                'mission_type': data.get('mission_type') or 'CUSTOM',
                                'total_waypoints': int(data.get('total_waypoints') or 0),
                                'current_waypoint_index': int(data.get('current_waypoint_index') or 0),
                                'estimated_remaining_s': int(data.get('estimated_remaining_s') or 0),
                                'status': mission_status,
                                'started_at': data.get('started_at'),
                            }
                        else:
                            drone.external_mission_info = None
                        # Ensure internal sim loop stays stopped.
                        drone.running = False
                except Exception as e:
                    logger.debug(f"bad telemetry packet: {e}")
        except redis.ConnectionError:
            if r: logger.warning("Redis connection lost. Retrying...")
            r = None
            _redis_bridge_stop.wait(REDIS_RETRY_DELAY_S)
        except Exception as e:
            logger.error(f"Redis Bridge error: {e}")
            _redis_bridge_stop.wait(1)

def start_redis_bridge():
    global redis_bridge_thread
    if not _redis_bridge_stop.is_set() and redis_bridge_thread is not None and redis_bridge_thread.is_alive():
        return
    _redis_bridge_stop.clear()
    redis_bridge_thread = threading.Thread(target=redis_bridge_loop, daemon=True)
    redis_bridge_thread.start()

# Initialize some demo drones
def initialize_demo_fleet():
    """Initialize fleet from DB and optionally seed demo drones."""
    logger.info("Initializing drone fleet...")
    if _EXTERNAL_ONLY:
        logger.info("External-only mode enabled (LESNAR_EXTERNAL_ONLY=1). Starting with empty fleet and waiting for real telemetry.")
        return
    if not _LOAD_PERSISTED_FLEET:
        logger.info("Persisted fleet restore disabled (LESNAR_LOAD_PERSISTED_FLEET=0). Starting with empty fleet.")
    else:
        logger.info("Persisted fleet restore enabled (LESNAR_LOAD_PERSISTED_FLEET=1). Loading drones from DB.")
    try:
        with app.app_context():
            if not _LOAD_PERSISTED_FLEET:
                raise RuntimeError('persisted fleet restore disabled')
            enabled = Drone.query.filter_by(enabled=True).all()
            if enabled:
                loaded_count = 0
                for row in enabled:
                    if _is_demo_drone_id(row.drone_id) and not _ENABLE_DEMO_FLEET:
                        row.enabled = False
                        continue
                    try:
                        row_cfg = json.loads(row.config_json) if row.config_json else {}
                    except Exception:
                        row_cfg = {}
                    if row_cfg.get('source') == 'external':
                        logger.info(f"Skipping persisted external drone {row.drone_id} until live telemetry resumes")
                        continue
                    pos = None
                    try:
                        if row.home_position_json:
                            pos_list = json.loads(row.home_position_json)
                            if isinstance(pos_list, list) and len(pos_list) >= 2:
                                pos = tuple(pos_list)
                    except Exception:
                        pos = None
                    fleet.add_drone(row.drone_id, pos)
                    loaded_count += 1
                try:
                    db.session.commit()
                except Exception:
                    pass

                if loaded_count > 0:
                    logger.info(f"Loaded {loaded_count} drones from DB")
                    return
    except Exception as e:
        # Normal when restore is disabled.
        if _LOAD_PERSISTED_FLEET:
            logger.warning(f"Failed loading drones from DB: {e}")

    if not _ENABLE_DEMO_FLEET:
        logger.info("Demo fleet disabled (LESNAR_ENABLE_DEMO_FLEET=0). Waiting for real telemetry drones.")
        return

    # If DB is empty/unavailable and demo mode enabled, seed a demo fleet.
    fleet.add_drone("LESNAR-DEMO-01", (40.7128, -74.0060, 0))  # NYC
    fleet.add_drone("LESNAR-DEMO-02", (40.7589, -73.9851, 0))  # Times Square
    fleet.add_drone("LESNAR-DEMO-03", (40.6892, -74.0445, 0))  # Statue of Liberty
    try:
        with app.app_context():
            _db_upsert_drone("LESNAR-DEMO-01", (40.7128, -74.0060, 0))
            _db_upsert_drone("LESNAR-DEMO-02", (40.7589, -73.9851, 0))
            _db_upsert_drone("LESNAR-DEMO-03", (40.6892, -74.0445, 0))
    except Exception:
        pass
    logger.info("Seeded demo fleet with 3 drones")

if __name__ == '__main__':
    print("=== Lesnar AI Backend API Server ===")
    print("Advanced drone control and monitoring API")
    print("Copyright © 2025 Lesnar AI Ltd.")
    print("-" * 40)
    
    # Initialize demo fleet
    initialize_demo_fleet()

    # Start telemetry broadcasting
    start_telemetry_broadcast()
    
    # Start Redis Bridge (Input from Teacher)
    start_redis_bridge()

    try:
        # Run the Flask-SocketIO server
        allow_unsafe_werkzeug = os.environ.get("ALLOW_UNSAFE_WERKZEUG", "1") == "1"
        socketio.run(
            app,
            host='0.0.0.0',
            port=5000,
            debug=False,
            allow_unsafe_werkzeug=allow_unsafe_werkzeug,
        )
    
    except KeyboardInterrupt:
        print("\nShutting down server...")
        stop_telemetry_broadcast()
        _redis_bridge_stop.set()

        # Clean up drones
        for drone_id in list(fleet.drones.keys()):
            fleet.remove_drone(drone_id)
        
        print("Server stopped")
