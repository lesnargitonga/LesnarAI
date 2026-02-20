"""
Lesnar AI Backend API Server
Flask-based REST API for drone control and monitoring
"""

import os
import sys
import json
import time as _time
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
# Force engineio to use threading driver to avoid importing Tornado
os.environ.setdefault('ENGINEIO_ASYNC_MODE', 'threading')
from flask_socketio import SocketIO, emit
import threading
import time
import socket
from pathlib import Path
import logging
import urllib.parse
import urllib.request
import redis

from db import db, get_database_url, safe_log_command, Drone, Mission as MissionModel, MissionRun, safe_log_event

# Add drone_simulation to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'drone_simulation'))
from simulator import DroneFleet, Mission
try:
    from airsim_adapter import AirSimAdapter
except Exception:
    AirSimAdapter = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = (os.environ.get('FLASK_SECRET_KEY') or 'dev-secret').strip()
app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

db.init_app(app)


def _maybe_run_db_migrations():
    """Best-effort Alembic upgrade on startup (safe no-op after first run)."""
    if os.environ.get('AUTO_MIGRATE', '1') != '1':
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

USE_AIRSIM = bool(int(os.environ.get('LESNAR_USE_AIRSIM', '0')))
fleet = DroneFleet()
airsim_adapter = None
if USE_AIRSIM and AirSimAdapter is not None:
    try:
        airsim_adapter = AirSimAdapter()
        logger.info("AirSim adapter enabled: serving live states from AirSim")
    except Exception as e:
        logger.warning(f"Failed to initialize AirSim adapter: {e}. Falling back to simulator.")
        airsim_adapter = None
telemetry_thread = None
telemetry_running = False
_START_TIME = _time.time()


# --- Simple API-key auth (role-based) ---
# If keys are unset, auth is disabled (keeps local non-docker usage working).
_ADMIN_KEY = (os.environ.get('LESNAR_ADMIN_API_KEY') or '').strip()
_OPERATOR_KEY = (os.environ.get('LESNAR_OPERATOR_API_KEY') or '').strip()

_REDIS_HOST = (os.environ.get('REDIS_HOST') or '127.0.0.1').strip()
_REDIS_PORT = int(os.environ.get('REDIS_PORT') or 6379)


def _auth_enabled() -> bool:
    return bool(_ADMIN_KEY or _OPERATOR_KEY)


def _get_role_from_request() -> str | None:
    key = (request.headers.get('X-API-Key') or '').strip()
    if not key:
        return None
    if _ADMIN_KEY and key == _ADMIN_KEY:
        return 'admin'
    if _OPERATOR_KEY and key == _OPERATOR_KEY:
        return 'operator'
    return None


def require_role(required: str):
    order = {'operator': 1, 'admin': 2}

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not _auth_enabled():
                return fn(*args, **kwargs)

            role = _get_role_from_request()
            if role is None:
                return jsonify({'success': False, 'error': 'Unauthorized (missing/invalid X-API-Key)'}), 401

            if order.get(role, 0) < order.get(required, 999):
                return jsonify({'success': False, 'error': 'Forbidden'}), 403

            return fn(*args, **kwargs)

        return wrapper

    return decorator

# API Routes

def _try_audit(drone_id, action, payload, success, error):
    try:
        safe_log_command(
            drone_id=drone_id,
            action=action,
            payload_json=json.dumps(payload) if payload is not None else None,
            success=success,
            error=error,
        )
    except Exception:
        pass


def _db_upsert_drone(drone_id: str, position_tuple: tuple | None):
    row = Drone.query.filter_by(drone_id=drone_id).one_or_none()
    now = datetime.utcnow()
    home_position_json = json.dumps(list(position_tuple)) if position_tuple is not None else None
    if row is None:
        row = Drone(
            drone_id=drone_id,
            enabled=True,
            home_position_json=home_position_json,
            config_json=None,
            created_at=now,
            updated_at=now,
        )
        db.session.add(row)
    else:
        row.enabled = True
        if home_position_json is not None:
            row.home_position_json = home_position_json
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
        return jsonify({'success': True, 'status': 'ok', 'database_url': app.config.get('SQLALCHEMY_DATABASE_URI')})
    except Exception as e:
        return jsonify({'success': False, 'status': 'error', 'error': str(e)}), 500

@app.route('/api/drones', methods=['GET'])
@require_role('operator')
def get_drones():
    """Get list of all drones"""
    try:
        if airsim_adapter is not None:
            states = airsim_adapter.get_all_states()
        else:
            states = fleet.get_all_states()
        return jsonify({
            'success': True,
            'drones': [state.to_dict() for state in states],
            'count': len(states)
        })
    except Exception as e:
        logger.error(f"Error getting drones: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/drones/<drone_id>', methods=['GET'])
@require_role('operator')
def get_drone(drone_id):
    """Get specific drone state"""
    try:
        if airsim_adapter is not None:
            state = airsim_adapter.get_state(drone_id)
            if state is None:
                return jsonify({'success': False, 'error': 'Drone not found'}), 404
            return jsonify({'success': True, 'drone': state.to_dict(), 'obstacles': []})
        else:
            drone = fleet.get_drone(drone_id)
            if not drone:
                return jsonify({'success': False, 'error': 'Drone not found'}), 404
            return jsonify({
                'success': True,
                'drone': drone.get_state().to_dict(),
                'obstacles': drone.obstacles_detected[-5:],
                'mission': drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None
            })
    except Exception as e:
        logger.error(f"Error getting drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/drones', methods=['POST'])
@require_role('operator')
def create_drone():
    """Create a new drone"""
    try:
        data = request.get_json()
        drone_id = data.get('drone_id')
        position = data.get('position')  # [lat, lon, alt]
        
        if not drone_id:
            return jsonify({'success': False, 'error': 'drone_id required'}), 400
        
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
                return jsonify({'success': False, 'error': f'Database error: {e}'}), 500

            _try_audit(drone_id, 'create_drone', {'position': list(position) if position else None}, True, None)
            safe_log_event('DRONE_CREATED', drone_id=drone_id, payload={'position': list(position) if position else None})
            return jsonify({'success': True, 'message': f'Drone {drone_id} created'})
        else:
            return jsonify({'success': False, 'error': 'Drone already exists'}), 409
    
    except Exception as e:
        logger.error(f"Error creating drone: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/drones/<drone_id>/arm', methods=['POST'])
@require_role('operator')
def arm_drone(drone_id):
    """Arm a drone"""
    try:
        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
        
        success = drone.arm()
        _try_audit(drone_id, 'arm', None, bool(success), None if success else 'arm_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"armed" if success else "failed to arm"}',
            'state': drone.get_state().to_dict()
        })
    
    except Exception as e:
        logger.error(f"Error arming drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/drones/<drone_id>/disarm', methods=['POST'])
@require_role('operator')
def disarm_drone(drone_id):
    """Disarm a drone"""
    try:
        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
        
        success = drone.disarm()
        _try_audit(drone_id, 'disarm', None, bool(success), None if success else 'disarm_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"disarmed" if success else "failed to disarm"}',
            'state': drone.get_state().to_dict()
        })
    
    except Exception as e:
        logger.error(f"Error disarming drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _publish_command(drone_id: str, action: str, params: dict | None = None) -> None:
    """Publish a command to Redis for external agents (Teacher/real drones)."""
    try:
        r = redis.Redis(host=_REDIS_HOST, port=_REDIS_PORT, db=0, socket_timeout=2)
        cmd = {
            'drone_id': drone_id,
            'action': action,
            'params': params or {},
            'timestamp': datetime.utcnow().isoformat(),
        }
        r.publish('commands', json.dumps(cmd))
    except Exception as e:
        logger.warning(f"Failed to publish Redis command ({action} -> {drone_id}): {e}")

@app.route('/api/drones/<drone_id>/takeoff', methods=['POST'])
@require_role('operator')
def takeoff_drone(drone_id):
    """Takeoff a drone"""
    try:
        data = request.get_json() or {}
        altitude = data.get('altitude', 10.0)

        # Always publish to Redis (Teacher/real drones).
        _publish_command(drone_id, 'takeoff', {'altitude': altitude})

        if airsim_adapter is not None:
            success = airsim_adapter.takeoff(drone_id, altitude)
            _try_audit(drone_id, 'takeoff', {'altitude': altitude}, success, None)
            return jsonify({
                'success': success,
                'message': f'Drone {drone_id} takeoff signal sent.',
                'target_altitude': altitude,
                'state': airsim_adapter.get_state(drone_id).to_dict() if airsim_adapter.get_state(drone_id) else {}
            })

        drone = fleet.get_drone(drone_id)
        if not drone:
            # Redis-only drone: acknowledge command.
            return jsonify({'success': True, 'message': f'Command published for {drone_id}', 'published': True})

        success = drone.takeoff(altitude)
        _try_audit(drone_id, 'takeoff', {'altitude': altitude}, bool(success), None if success else 'takeoff_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"taking off" if success else "failed to takeoff"}',
            'target_altitude': altitude,
            'state': drone.get_state().to_dict()
        })

    except Exception as e:
        logger.error(f"Error takeoff drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/drones/<drone_id>/land', methods=['POST'])
@require_role('operator')
def land_drone(drone_id):
    """Land a drone"""
    try:
        # Always publish to Redis (Teacher/real drones).
        _publish_command(drone_id, 'land')

        if airsim_adapter is not None:
            success = airsim_adapter.land(drone_id)
            _try_audit(drone_id, 'land', None, success, None)
            return jsonify({
                'success': success,
                'message': f'Drone {drone_id} land signal sent.',
                'state': airsim_adapter.get_state(drone_id).to_dict() if airsim_adapter.get_state(drone_id) else {}
            })

        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': True, 'message': f'Command published for {drone_id}', 'published': True})

        success = drone.land()
        _try_audit(drone_id, 'land', None, bool(success), None if success else 'land_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"landing" if success else "failed to land"}',
            'state': drone.get_state().to_dict()
        })

    except Exception as e:
        logger.error(f"Error landing drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/drones/<drone_id>/goto', methods=['POST'])
@require_role('operator')
def goto_drone(drone_id):
    """Navigate drone to coordinates"""
    try:
        data = request.get_json() or {}
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        altitude = data.get('altitude', 10.0)

        if latitude is None or longitude is None:
            return jsonify({'success': False, 'error': 'latitude and longitude required'}), 400

        # Always publish to Redis (Teacher/real drones).
        _publish_command(drone_id, 'goto', {'latitude': latitude, 'longitude': longitude, 'altitude': altitude})

        if airsim_adapter is not None:
            success = airsim_adapter.goto(drone_id, latitude, longitude, altitude)
            _try_audit(drone_id, 'goto', {'latitude': latitude, 'longitude': longitude, 'altitude': altitude}, success, None)
            return jsonify({
                'success': success,
                'message': f'Drone {drone_id} sent to ({latitude}, {longitude})',
                'target': {'latitude': latitude, 'longitude': longitude, 'altitude': altitude},
                'state': airsim_adapter.get_state(drone_id).to_dict() if airsim_adapter.get_state(drone_id) else {}
            })

        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': True, 'message': f'Command published for {drone_id}', 'published': True})
        
        success = drone.goto(latitude, longitude, altitude)
        _try_audit(drone_id, 'goto', {'latitude': latitude, 'longitude': longitude, 'altitude': altitude}, bool(success), None if success else 'goto_failed')
        return jsonify({
            'success': success,
            'message': f'Drone {drone_id} {"navigating" if success else "failed to navigate"}',
            'target': {'latitude': latitude, 'longitude': longitude, 'altitude': altitude},
            'state': drone.get_state().to_dict()
        })
    
    except Exception as e:
        logger.error(f"Error navigating drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/drones/<drone_id>/mission', methods=['POST'])
@require_role('operator')
def execute_mission(drone_id):
    """Execute a mission"""
    try:
        data = request.get_json()
        waypoints = data.get('waypoints', [])
        mission_type = data.get('mission_type', 'CUSTOM')
        
        if not waypoints:
            return jsonify({'success': False, 'error': 'waypoints required'}), 400
        
        drone = fleet.get_drone(drone_id)
        if not drone:
            return jsonify({'success': False, 'error': 'Drone not found'}), 404
        
        estimated_duration = len(waypoints) * 60.0  # Rough estimate
        mission = Mission(
            waypoints=[tuple(wp) for wp in waypoints],
            mission_type=mission_type,
        )

        mission_id = None
        run_id = None
        try:
            with app.app_context():
                mission_id, run_id = _db_create_mission_and_run(drone_id, mission_type, waypoints)
        except Exception as e:
            _try_audit(drone_id, 'mission_start', {'mission_type': mission_type, 'waypoints': waypoints}, False, f'db_error:{e}')
            return jsonify({'success': False, 'error': f'Database error: {e}'}), 500

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
            'state': drone.get_state().to_dict()
        })
    
    except Exception as e:
        logger.error(f"Error executing mission for drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/missions/active', methods=['GET'])
@require_role('operator')
def get_active_missions():
    """Get list of active/paused missions."""
    try:
        missions = []
        if airsim_adapter is not None:
            # AirSim adapter currently exposes only basic state.
            states = airsim_adapter.get_all_states() or []
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
                info = drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None
                if info:
                    missions.append(info)
        return jsonify({'success': True, 'missions': missions, 'count': len(missions)})
    except Exception as e:
        logger.error(f"Error getting active missions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/drones/<drone_id>/mission/pause', methods=['POST'])
@require_role('operator')
def pause_mission(drone_id):
    """Pause a mission (simulator mode only)."""
    try:
        if airsim_adapter is not None:
            return jsonify({'success': False, 'error': 'Mission pause not supported for AirSim adapter'}), 501
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
            'state': drone.get_state().to_dict(),
            'mission': drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None,
        })
    except Exception as e:
        logger.error(f"Error pausing mission for drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/drones/<drone_id>/mission/resume', methods=['POST'])
@require_role('operator')
def resume_mission(drone_id):
    """Resume a paused mission (simulator mode only)."""
    try:
        if airsim_adapter is not None:
            return jsonify({'success': False, 'error': 'Mission resume not supported for AirSim adapter'}), 501
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
            'state': drone.get_state().to_dict(),
            'mission': drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None,
        })
    except Exception as e:
        logger.error(f"Error resuming mission for drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/drones/<drone_id>/mission/stop', methods=['POST'])
@require_role('operator')
def stop_mission(drone_id):
    """Stop/cancel a mission (simulator mode only)."""
    try:
        if airsim_adapter is not None:
            return jsonify({'success': False, 'error': 'Mission stop not supported for AirSim adapter'}), 501
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
            'state': drone.get_state().to_dict(),
            'mission': drone.get_mission_info() if hasattr(drone, 'get_mission_info') else None,
        })
    except Exception as e:
        logger.error(f"Error stopping mission for drone {drone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/emergency', methods=['POST'])
@require_role('admin')
def emergency_land_all():
    """Emergency land all drones"""
    try:
        fleet.emergency_land_all()
        return jsonify({
            'success': True,
            'message': 'Emergency landing initiated for all drones',
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error during emergency landing: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/telemetry', methods=['GET'])
@require_role('operator')
def get_telemetry():
    """Get current telemetry data"""
    try:
        states = fleet.get_all_states()
        return jsonify({
            'success': True,
            'telemetry': [state.to_dict() for state in states],
            'timestamp': datetime.now().isoformat(),
            'fleet_status': {
                'total_drones': len(states),
                'armed_drones': len([s for s in states if s.armed]),
                'flying_drones': len([s for s in states if s.altitude > 1.0]),
                'low_battery_drones': len([s for s in states if s.battery < 20.0])
            }
        })
    
    except Exception as e:
        logger.error(f"Error getting telemetry: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/obstacles', methods=['GET'])
@require_role('operator')
def get_obstacles():
    """Get static obstacles GeoJSON"""
    try:
        data_path = os.path.join(os.path.dirname(__file__), '..', 'drone_simulation', 'data', 'obstacles.geojson')
        with open(data_path, 'r') as f:
            geojson = json.load(f)
        return jsonify(geojson)
    except Exception as e:
        logger.error(f"Error loading obstacles: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/geocode/suggest', methods=['GET'])
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
        return jsonify({'success': False, 'error': str(e)}), 500

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
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
@require_role('operator')
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

        # Probe AirSim RPC using mission.json
        mission_path = os.path.join(repo_root, 'airsim', 'mission.json')
        rpc_ok = None
        try:
            if os.path.exists(mission_path):
                with open(mission_path, 'r') as f:
                    mission_cfg = json.load(f)
                host = mission_cfg.get('rpc_host', '127.0.0.1')
                port = int(mission_cfg.get('rpc_port', 41451))
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                try:
                    s.connect((host, port))
                    rpc_ok = True
                except Exception:
                    rpc_ok = False
                finally:
                    s.close()
        except Exception as _e:
            rpc_ok = None

        report = {
            'service': 'Lesnar AI Backend',
            'status': 'ok',
            'time': datetime.now().isoformat(),
            'uptime_seconds': round(uptime_s, 1),
            'versions': {
                'python': sys.version.split()[0],
                'flask': _ver('flask'),
                'flask_socketio': _ver('flask_socketio'),
                'socketio': _ver('socketio'),
            },
            'features': {
                'airsim_adapter_enabled': USE_AIRSIM and (airsim_adapter is not None),
            },
            'segmentation': seg_info,
            'airsim_rpc_ok': rpc_ok,
        }
        return jsonify(report)
    except Exception as e:
        logger.error(f"Error in /api/health: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
@require_role('admin')
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
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
@require_role('admin')
def update_config():
    """Update config.json safely with minimal validation."""
    try:
        data = request.get_json() or {}
        if 'config' not in data:
            return jsonify({'success': False, 'error': 'config field required'}), 400
        cfg = data['config']
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
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/logs/segmentation/latest', methods=['GET'])
def get_latest_segmentation_log():
    """Return latest segmentation diagnostics CSV as JSON rows (limited)."""
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        logs_dir = Path(os.path.join(repo_root, 'logs'))
        if not logs_dir.exists():
            return jsonify({'success': False, 'error': 'logs dir missing'}), 404
        candidates = sorted(logs_dir.glob('seg_diag_*.csv'), reverse=True)
        if not candidates:
            return jsonify({'success': False, 'error': 'no segmentation logs found'}), 404
        latest = candidates[0]
        rows = []
        import csv
        with open(latest, 'r', newline='') as f:
            rdr = csv.DictReader(f)
            for i, row in enumerate(rdr):
                rows.append(row)
                if i >= 500:
                    break
        return jsonify({'success': True, 'file': str(latest), 'rows': rows})
    except Exception as e:
        logger.error(f"Error reading latest segmentation log: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
    global telemetry_running
    sync_tick = 0
    while telemetry_running:
        try:
            states = fleet.get_all_states()
            telemetry_data = {
                'telemetry': [state.to_dict() for state in states],
                'timestamp': datetime.now().isoformat(),
                'fleet_status': {
                    'total_drones': len(states),
                    'armed_drones': len([s for s in states if s.armed]),
                    'flying_drones': len([s for s in states if s.altitude > 1.0]),
                    'low_battery_drones': len([s for s in states if s.battery < 20.0])
                }
            }
            
            socketio.emit('telemetry_update', telemetry_data)

            # Best-effort mission run status sync (keeps DB consistent without storing high-rate telemetry).
            sync_tick = (sync_tick + 1) % 3
            if sync_tick == 0:
                try:
                    if airsim_adapter is None:
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
            time.sleep(0.2)  # 5 Hz update rate
            
        except Exception as e:
            logger.error(f"Error broadcasting telemetry: {e}")
            time.sleep(0.2)

def start_telemetry_broadcast():
    """Start telemetry broadcasting thread"""
    global telemetry_thread, telemetry_running
    
    if telemetry_running:
        return
    
    telemetry_running = True
    telemetry_thread = threading.Thread(target=broadcast_telemetry)
    telemetry_thread.daemon = True
    telemetry_thread.start()
    logger.info("Telemetry broadcasting started")

def stop_telemetry_broadcast():
    """Stop telemetry broadcasting"""
    global telemetry_running
    telemetry_running = False
    logger.info("Telemetry broadcasting stopped")

# --- Redis Bridge ---
redis_bridge_thread = None
redis_bridge_running = False

def redis_bridge_loop():
    """Listen for telemetry from external agents (Teacher/Sentinel)."""
    global redis_bridge_running
    r = None
    pubsub = None

    while redis_bridge_running:
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
                         # Ensure drone exists
                        if not fleet.get_drone(drone_id):
                            logger.info(f"Discovered external drone via Redis: {drone_id}")
                            # Auto-add to DB so it persists
                            with app.app_context():
                                _db_upsert_drone(drone_id, (data.get('latitude',0), data.get('longitude',0), 0))
                            # Add to fleet but stop internal sim loop immediately.
                            fleet.add_drone(drone_id, (data.get('latitude', 0), data.get('longitude', 0), data.get('altitude', 0)))
                            try:
                                d = fleet.get_drone(drone_id)
                                if d is not None:
                                    d.stop_simulation()
                            except Exception:
                                pass
                    
                    drone = fleet.get_drone(drone_id)
                    if drone:
                        # Update state directly (Source of Truth is now Redis)
                        drone.position = [
                            float(data.get('latitude', drone.position[0])),
                            float(data.get('longitude', drone.position[1])),
                            float(data.get('altitude', drone.position[2]))
                        ]
                        drone.heading = float(data.get('heading', drone.heading))
                        drone.speed = float(data.get('speed', drone.speed))
                        if 'battery' in data: drone.battery = float(data['battery'])
                        if 'armed' in data: drone.armed = bool(data['armed'])
                        if 'mode' in data: drone.mode = str(data['mode'])
                        # Ensure internal sim loop stays stopped.
                        drone.running = False
                except Exception as e:
                    logger.debug(f"bad telemetry packet: {e}")
        except redis.ConnectionError:
            if r: logger.warning("Redis connection lost. Retrying...")
            r = None
            time.sleep(5)
        except Exception as e:
            logger.error(f"Redis Bridge error: {e}")
            time.sleep(1)

def start_redis_bridge():
    global redis_bridge_thread, redis_bridge_running
    if redis_bridge_running: return
    redis_bridge_running = True
    redis_bridge_thread = threading.Thread(target=redis_bridge_loop, daemon=True)
    redis_bridge_thread.start()

# Initialize some demo drones
def initialize_demo_fleet():
    """Initialize demo drones for testing"""
    logger.info("Initializing drone fleet...")
    try:
        with app.app_context():
            enabled = Drone.query.filter_by(enabled=True).all()
            if enabled:
                for row in enabled:
                    pos = None
                    try:
                        if row.home_position_json:
                            pos_list = json.loads(row.home_position_json)
                            if isinstance(pos_list, list) and len(pos_list) >= 2:
                                pos = tuple(pos_list)
                    except Exception:
                        pos = None
                    fleet.add_drone(row.drone_id, pos)
                logger.info(f"Loaded {len(enabled)} drones from DB")
                return
    except Exception as e:
        logger.warning(f"Failed loading drones from DB: {e}")

    # If DB is empty/unavailable, seed a demo fleet.
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
        redis_bridge_running = False

        # Clean up drones
        for drone_id in list(fleet.drones.keys()):
            fleet.remove_drone(drone_id)
        
        print("Server stopped")
