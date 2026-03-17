import os
import json
from datetime import datetime
from sqlalchemy.engine import URL

from flask_sqlalchemy import SQLAlchemy
from audit_chain import append_signed_audit

db = SQLAlchemy()
ENFORCE_AUDIT_CHAIN = os.environ.get('LESNAR_ENFORCE_AUDIT_CHAIN', '1').strip() == '1'


def get_database_url() -> str:
    # Prefer discrete Postgres env vars when available (safe for special chars in password).
    pg_user = (os.environ.get('POSTGRES_USER') or '').strip()
    pg_password = os.environ.get('POSTGRES_PASSWORD')
    pg_db = (os.environ.get('POSTGRES_DB') or '').strip()
    pg_host = (os.environ.get('POSTGRES_HOST') or 'timescaledb').strip()
    pg_port = (os.environ.get('POSTGRES_PORT') or '5432').strip()
    if pg_user and pg_password is not None and pg_db:
        return URL.create(
            drivername='postgresql+psycopg2',
            username=pg_user,
            password=pg_password,
            host=pg_host,
            port=int(pg_port),
            database=pg_db,
        ).render_as_string(hide_password=False)

    # Fallback to DATABASE_URL (Docker/12factor).
    url = (os.environ.get('DATABASE_URL') or '').strip()
    if url:
        return url

    # Final fallback to a local SQLite file.
    return 'sqlite:///lesnar.db'


class CommandLog(db.Model):
    __tablename__ = 'command_logs'

    id = db.Column(db.Integer, primary_key=True)
    drone_id = db.Column(db.String(128), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    success = db.Column(db.Boolean, nullable=True)
    payload_json = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    operator_id = db.Column(db.String(128), nullable=True, index=True)
    operator_role = db.Column(db.String(32), nullable=True)
    session_id = db.Column(db.String(128), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class Drone(db.Model):
    __tablename__ = 'drones'

    id = db.Column(db.Integer, primary_key=True)
    drone_id = db.Column(db.String(128), nullable=False, unique=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    home_position_json = db.Column(db.Text, nullable=True)
    config_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Mission(db.Model):
    __tablename__ = 'missions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=True)
    mission_type = db.Column(db.String(64), nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MissionRun(db.Model):
    __tablename__ = 'mission_runs'

    id = db.Column(db.Integer, primary_key=True)
    mission_id = db.Column(db.Integer, db.ForeignKey('missions.id'), nullable=False, index=True)
    drone_id = db.Column(db.String(128), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(64), nullable=False, index=True)
    drone_id = db.Column(db.String(128), nullable=True, index=True)
    mission_run_id = db.Column(db.Integer, db.ForeignKey('mission_runs.id'), nullable=True, index=True)
    payload_json = db.Column(db.Text, nullable=True)
    operator_id = db.Column(db.String(128), nullable=True, index=True)
    operator_role = db.Column(db.String(32), nullable=True)
    session_id = db.Column(db.String(128), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class AuthSession(db.Model):
    __tablename__ = 'auth_sessions'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(128), nullable=False, unique=True, index=True)
    username = db.Column(db.String(128), nullable=False, index=True)
    role = db.Column(db.String(32), nullable=False, index=True)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True, index=True)
    metadata_json = db.Column(db.Text, nullable=True)


class AuthUser(db.Model):
    __tablename__ = 'auth_users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), nullable=False, unique=True, index=True)
    role = db.Column(db.String(32), nullable=False, index=True)
    display_name = db.Column(db.String(128), nullable=True)
    password_hash = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_password_change_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class TelemetrySample(db.Model):
    __tablename__ = 'telemetry_samples'

    id = db.Column(db.Integer, primary_key=True)
    drone_id = db.Column(db.String(128), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    altitude = db.Column(db.Float, nullable=False)
    heading = db.Column(db.Float, nullable=True)
    speed = db.Column(db.Float, nullable=True)
    battery = db.Column(db.Float, nullable=True)
    armed = db.Column(db.Boolean, nullable=True)
    mode = db.Column(db.String(64), nullable=True, index=True)
    source_timestamp = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


def safe_log_command(drone_id: str | None, action: str, payload_json: str | None, success: bool | None, error: str | None,
                     operator_id: str | None = None, operator_role: str | None = None, session_id: str | None = None):
    try:
        db.session.add(CommandLog(
            drone_id=drone_id,
            action=action,
            payload_json=payload_json,
            success=success,
            error=error,
            operator_id=operator_id,
            operator_role=operator_role,
            session_id=session_id,
        ))
        db.session.commit()
        try:
            append_signed_audit('command_log', {
                'drone_id': drone_id,
                'action': action,
                'payload_json': payload_json,
                'success': success,
                'error': error,
                'operator_id': operator_id,
                'operator_role': operator_role,
                'session_id': session_id,
                'created_at': datetime.utcnow().isoformat(),
            })
        except Exception:
            if ENFORCE_AUDIT_CHAIN:
                raise
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        if ENFORCE_AUDIT_CHAIN:
            raise


def safe_log_event(event_type: str, drone_id: str | None = None, mission_run_id: int | None = None, payload: dict | None = None,
                   operator_id: str | None = None, operator_role: str | None = None, session_id: str | None = None):
    try:
        db.session.add(Event(
            event_type=event_type,
            drone_id=drone_id,
            mission_run_id=mission_run_id,
            payload_json=json.dumps(payload) if payload is not None else None,
            operator_id=operator_id,
            operator_role=operator_role,
            session_id=session_id,
        ))
        db.session.commit()
        try:
            append_signed_audit('event_log', {
                'event_type': event_type,
                'drone_id': drone_id,
                'mission_run_id': mission_run_id,
                'payload': payload,
                'operator_id': operator_id,
                'operator_role': operator_role,
                'session_id': session_id,
                'created_at': datetime.utcnow().isoformat(),
            })
        except Exception:
            if ENFORCE_AUDIT_CHAIN:
                raise
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        if ENFORCE_AUDIT_CHAIN:
            raise
