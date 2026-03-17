import atexit
import threading

from app import (
    app,
    fleet,
    initialize_demo_fleet,
    logger,
    start_redis_bridge,
    start_telemetry_broadcast,
    stop_telemetry_broadcast,
    _redis_bridge_stop,
)


_runtime_lock = threading.Lock()
_runtime_started = False


def ensure_runtime_started() -> None:
    global _runtime_started
    with _runtime_lock:
        if _runtime_started:
            return
        initialize_demo_fleet()
        start_telemetry_broadcast()
        start_redis_bridge()
        _runtime_started = True
        logger.info('Backend runtime services initialized via Gunicorn entrypoint')


def shutdown_runtime() -> None:
    try:
        stop_telemetry_broadcast()
    except Exception:
        pass
    try:
        _redis_bridge_stop.set()
    except Exception:
        pass
    try:
        for drone_id in list(fleet.drones.keys()):
            fleet.remove_drone(drone_id)
    except Exception:
        pass


ensure_runtime_started()
atexit.register(shutdown_runtime)
