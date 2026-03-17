#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import hashlib
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

REPO_DIR = Path(__file__).resolve().parent.parent
PX4_DIR = Path(os.path.expanduser("~/PX4-Autopilot"))
HOST = os.environ.get("LESNAR_ORCH_HOST", "127.0.0.1")
PORT = int(os.environ.get("LESNAR_ORCH_PORT", "8765"))

# Guardrail: the runtime can spam logs (especially `make px4_sitl ...`) and fill disks.
_MAX_LOG_BYTES = int(float(os.environ.get("LESNAR_ORCH_MAX_LOG_MB", "200")) * 1024 * 1024)
_LOG_APPEND = os.environ.get("LESNAR_ORCH_LOG_APPEND", "0").strip() in {"1", "true", "TRUE", "yes", "YES"}

_ACTIVE_RUN_LOCK = threading.Lock()
_ACTIVE_RUN: dict[str, object] | None = None

_TRAINING_JOB_LOCK = threading.Lock()
_TRAINING_JOB: dict[str, object] | None = None


def _python_cmd() -> str:
    py_bin = REPO_DIR / ".venv-wsl" / "bin" / "python3"
    return str(py_bin) if py_bin.exists() else "python3"


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _data_root() -> Path:
    raw = (os.environ.get("LESNAR_DATA_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return REPO_DIR / "dataset"


def _archive_root() -> Path | None:
    raw = (os.environ.get("LESNAR_ARCHIVE_ROOT") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _copytree_best_effort(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        # Avoid partial overwrites; keep previous copy and create a new suffix.
        stamp = time.strftime("%Y%m%d_%H%M%S")
        dst = dst.with_name(f"{dst.name}.dup.{stamp}")
    shutil.copytree(src, dst, dirs_exist_ok=False)


def _kick_archive_async(run_dir: Path, run_meta: dict[str, object], manifest_path: Path) -> dict[str, object]:
    archive_root = _archive_root()
    if not archive_root:
        return {"enabled": False}

    archive_root.mkdir(parents=True, exist_ok=True)
    run_id = str(run_meta.get("run_id") or run_dir.name)
    dst = archive_root / run_id

    status: dict[str, object] = {
        "enabled": True,
        "source": str(run_dir),
        "destination": str(dst),
        "started_at": time.time(),
        "completed": False,
        "error": None,
    }

    def _worker() -> None:
        try:
            _copytree_best_effort(run_dir, dst)
            # Verify manifest integrity in the copied folder.
            copied_manifest = dst / manifest_path.name
            if copied_manifest.exists():
                status["copied_manifest_sha256"] = _sha256_file(copied_manifest)
            status["completed"] = True
            status["completed_at"] = time.time()
        except Exception as exc:
            status["error"] = str(exc)
            status["completed"] = True
            status["completed_at"] = time.time()

    threading.Thread(target=_worker, daemon=True).start()
    return status


def _sha256_file(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _safe_git_rev() -> str | None:
    code, out, _ = _run("git rev-parse HEAD 2>/dev/null", cwd=REPO_DIR, timeout=3.0)
    if code != 0:
        return None
    value = (out or "").strip()
    return value or None


def _finalize_run_manifest(run_dir: Path, run_meta: dict[str, object]) -> Path:
    files: list[dict[str, object]] = []
    # Include all relevant run artifacts, not just CSVs. This keeps the manifest meaningful
    # even if a run ended early and produced no telemetry.
    include_exts = {".csv", ".json", ".log", ".txt", ".pt"}
    for p in sorted(run_dir.iterdir()):
        try:
            if not p.is_file():
                continue
            if p.name == "MANIFEST.json":
                continue
            if p.suffix.lower() not in include_exts:
                continue
            st = p.stat()
            files.append(
                {
                    "path": str(p.relative_to(run_dir)),
                    "bytes": int(st.st_size),
                    "mtime": float(st.st_mtime),
                    "sha256": _sha256_file(p),
                }
            )
        except OSError:
            continue

    manifest = {
        "schema": 1,
        "run": run_meta,
        "generated_at": time.time(),
        "files": files,
    }

    manifest_path = run_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _maybe_append_audit_for_manifest(run_dir: Path, run_meta: dict[str, object], manifest_path: Path) -> dict[str, object] | None:
    # Optional: produce a signed, append-only audit record if configured.
    if not (os.environ.get("LESNAR_AUDIT_CHAIN_KEY") or "").strip():
        return None
    try:
        from backend.audit_chain import append_signed_audit  # type: ignore
    except Exception:
        return None

    try:
        manifest_sha = _sha256_file(manifest_path)
        payload = {
            "run_id": run_meta.get("run_id"),
            "run_dir": str(run_dir),
            "manifest": str(manifest_path),
            "manifest_sha256": manifest_sha,
            "repo_git_rev": run_meta.get("repo_git_rev"),
            "obstacles_sdf_sha256": run_meta.get("obstacles_sdf_sha256"),
            "effective_drones": run_meta.get("effective_drones"),
            "requested_drones": run_meta.get("requested_drones"),
        }
        record = append_signed_audit("dataset_manifest", payload)
        (run_dir / "AUDIT_CHAIN_ENTRY.json").write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return record
    except Exception as exc:
        return {"error": str(exc)}

_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_CACHE: dict[str, object] = {
    "checked_at": 0.0,
    "count": 0,
    "models": [],
    "present": False,
    "refreshing": False,
    "error": None,
}

# Dense worlds make `gz model --list` slow; keep `/status` fast by caching.
_MODEL_CACHE_MAX_AGE_S = float(os.environ.get("LESNAR_ORCH_MODEL_CACHE_MAX_AGE_S", "120"))
_MODEL_REFRESH_TIMEOUT_S = float(os.environ.get("LESNAR_ORCH_MODEL_REFRESH_TIMEOUT_S", "15"))


def _run(cmd: str, cwd: Path | None = None, timeout: float = 20.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd or REPO_DIR),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"command timed out after {timeout}s"


def _run_bg(cmd: str, log_file: Path, cwd: Path | None = None, env: dict | None = None) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log_if_large(log_file)
    mode = "a" if _LOG_APPEND else "w"
    with log_file.open(mode, encoding="utf-8") as handle:
        subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(cwd or REPO_DIR),
            env=env,
            stdout=handle,
            stderr=handle,
            start_new_session=True,
            close_fds=True,
        )


def _rotate_log_if_large(path: Path, max_bytes: int = _MAX_LOG_BYTES) -> None:
    try:
        if not path.exists():
            return
        size = path.stat().st_size
        if size <= max_bytes:
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        rotated = path.with_name(f"{path.name}.old.{stamp}")
        try:
            path.rename(rotated)
        except OSError:
            # If rename fails (e.g., locked), fall back to truncation.
            pass
        try:
            path.write_text("", encoding="utf-8")
        except OSError:
            # Best-effort; if we can't truncate, we still tried.
            pass
    except OSError:
        return


def _get_active_or_latest_run_dir() -> Path | None:
    with _ACTIVE_RUN_LOCK:
        active = dict(_ACTIVE_RUN) if isinstance(_ACTIVE_RUN, dict) else None
    if active and active.get("dir"):
        run_dir = Path(str(active["dir"]))
        if run_dir.exists():
            return run_dir

    base = _data_root() / "px4_teacher" / "runs"
    if not base.exists():
        return None
    dirs = [p for p in base.iterdir() if p.is_dir()]
    if not dirs:
        return None
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0]


def _training_status_payload() -> dict[str, object]:
    with _TRAINING_JOB_LOCK:
        job = dict(_TRAINING_JOB) if isinstance(_TRAINING_JOB, dict) else None
    if not job:
        return {"running": False, "job": None}

    pid = int(job.get("pid") or 0)
    running = bool(job.get("running")) and _pid_is_running(pid)
    job["running"] = running
    return {"running": running, "job": job}


def start_training(epochs: int = 20, batch_size: int = 128, csv_index: int = 0) -> dict[str, object]:
    with _TRAINING_JOB_LOCK:
        if isinstance(_TRAINING_JOB, dict) and _TRAINING_JOB.get("running"):
            pid = int(_TRAINING_JOB.get("pid") or 0)
            if _pid_is_running(pid):
                return {"success": False, "error": "training_already_running", "pid": pid}
            globals()["_TRAINING_JOB"] = None

    run_dir = _get_active_or_latest_run_dir()
    if run_dir is None:
        return {"success": False, "error": "no_run_dir"}

    csv_path = run_dir / f"telemetry_live_{int(csv_index)}.csv"
    if not csv_path.exists():
        return {"success": False, "error": "telemetry_csv_missing", "csv": str(csv_path), "run_dir": str(run_dir)}

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_model = run_dir / f"student_px4_{stamp}.pt"
    log_file = run_dir / f"training_{stamp}.log"

    cmd = (
        f"{_python_cmd()} training/train_student_px4.py "
        f"--data {sh_quote(str(csv_path))} "
        f"--epochs {int(epochs)} --bs {int(batch_size)} "
        f"--out {sh_quote(str(out_model))}"
    )

    log_file.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log_if_large(log_file)
    mode = "a" if _LOG_APPEND else "w"
    handle = log_file.open(mode, encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=str(REPO_DIR),
        env=os.environ.copy(),
        stdout=handle,
        stderr=handle,
        start_new_session=True,
        close_fds=True,
    )

    job: dict[str, object] = {
        "pid": proc.pid,
        "running": True,
        "started_at": time.time(),
        "run_dir": str(run_dir),
        "data_csv": str(csv_path),
        "out_model": str(out_model),
        "log": str(log_file),
        "epochs": int(epochs),
        "batch_size": int(batch_size),
        "csv_index": int(csv_index),
    }

    def _watch() -> None:
        try:
            rc = proc.wait()
        except Exception:
            rc = None
        finally:
            try:
                handle.flush()
                handle.close()
            except Exception:
                pass
            with _TRAINING_JOB_LOCK:
                if isinstance(_TRAINING_JOB, dict) and int(_TRAINING_JOB.get("pid") or 0) == int(proc.pid):
                    _TRAINING_JOB["running"] = False
                    _TRAINING_JOB["ended_at"] = time.time()
                    _TRAINING_JOB["exit_code"] = rc

    with _TRAINING_JOB_LOCK:
        globals()["_TRAINING_JOB"] = job

    threading.Thread(target=_watch, daemon=True).start()
    return {"success": True, "job": job}


def _count_x500_from_model_list(output: str) -> int:
    # Example lines:
    #   - x500_0
    # We count occurrences of "x500" in model names. This is intentionally simple and robust
    # to CLI formatting changes.
    count = 0
    for raw in (output or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # Match `x500` as a token or as a prefix like `x500_0`.
        if re.search(r"\bx500\b|\bx500_", line, flags=re.IGNORECASE):
            count += 1
    return count


def _extract_x500_models(output: str) -> list[str]:
    models: list[str] = []
    for raw in (output or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # Typical output is either `- name` or just `name`.
        if line.startswith("-"):
            line = line[1:].strip()
        if not line:
            continue
        if re.search(r"\bx500_", line, flags=re.IGNORECASE) or re.fullmatch(r"x500", line, flags=re.IGNORECASE):
            models.append(line)

    # Keep stable ordering for UI; de-dupe while preserving first-seen.
    seen: set[str] = set()
    unique: list[str] = []
    for model in models:
        if model in seen:
            continue
        seen.add(model)
        unique.append(model)
    unique.sort(key=lambda value: value.lower())
    return unique


def _refresh_model_cache_blocking(timeout_s: float | None = None) -> dict[str, object]:
    timeout = float(timeout_s if timeout_s is not None else _MODEL_REFRESH_TIMEOUT_S)
    checked_at = time.time()
    code, out, err = _run("gz model --list 2>/dev/null", timeout=timeout)
    if code == 0:
        models = _extract_x500_models(out)
        count = len(models) if models else _count_x500_from_model_list(out)
        with _MODEL_CACHE_LOCK:
            _MODEL_CACHE.update(
                {
                    "checked_at": checked_at,
                    "count": int(count),
                    "models": models,
                    "present": bool(count > 0),
                    "error": None,
                }
            )
    else:
        with _MODEL_CACHE_LOCK:
            # Preserve last known count/present; record the error for observability.
            _MODEL_CACHE.update({"checked_at": checked_at, "error": (err or f"gz model --list exit={code}").strip()})

    with _MODEL_CACHE_LOCK:
        return dict(_MODEL_CACHE)


def _kick_model_cache_refresh_async() -> None:
    with _MODEL_CACHE_LOCK:
        if _MODEL_CACHE.get("refreshing"):
            return
        _MODEL_CACHE["refreshing"] = True

    def _worker() -> None:
        try:
            _refresh_model_cache_blocking()
        finally:
            with _MODEL_CACHE_LOCK:
                _MODEL_CACHE["refreshing"] = False

    threading.Thread(target=_worker, daemon=True).start()


def _get_cached_model_count() -> int:
    with _MODEL_CACHE_LOCK:
        return int(_MODEL_CACHE.get("count") or 0)


def _get_cached_model_present(expected: int = 1) -> bool:
    return _get_cached_model_count() >= max(1, int(expected))


def _get_cached_models() -> list[str]:
    with _MODEL_CACHE_LOCK:
        value = _MODEL_CACHE.get("models")
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def instant_kill() -> None:
    # Kill all known runtime actors before a fresh launch.
    _run("pkill -9 -f 'gz sim|gz-server|/bin/px4|make px4|px4_sitl|px4_teacher_collect_gz.py' 2>/dev/null || true", timeout=10.0)
    # Also kill any stale MAVSDK server processes so they don't hold port 50051
    # and block the next teacher from connecting.
    _run("pkill -9 -f 'mavsdk_server' 2>/dev/null || true", timeout=5.0)
    time.sleep(3.0)


def runtime_status() -> dict:
    _, out, _ = _run("ps -eo args=", timeout=10.0)

    gz_running = ("gz sim" in out) or ("gz-server" in out)

    return {
        "gz_running": gz_running,
        "px4_running": ("/bin/px4" in out) or ("make px4_sitl gz_x500" in out),
        "teacher_running": "px4_teacher_collect_gz.py" in out,
        "drone_model_present": _get_cached_model_present(1),
        "drone_model_count": _get_cached_model_count(),
        "drone_models": _get_cached_models(),
    }


def _wait_for_world_ready(timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        code, out, _ = _run(
            "timeout 2 gz service -s /world/obstacles/control "
            "--reqtype gz.msgs.WorldControl "
            "--reptype gz.msgs.Boolean "
            "--req 'pause: false' 2>/dev/null",
            timeout=5.0,
        )
        if code == 0 and "data: true" in out:
            return
        time.sleep(1.0)
    raise RuntimeError("Gazebo world did not become responsive in time")


def _wait_for_model(expected: int, timeout_s: int = 45) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cache = _refresh_model_cache_blocking(timeout_s=min(_MODEL_REFRESH_TIMEOUT_S, 45.0))
        count = int(cache.get("count") or 0)
        if count >= max(1, int(expected)):
            return
        time.sleep(2.0)
    raise RuntimeError(
        f"PX4 started but expected {expected} x500 model(s) are not visible in Gazebo (last_count={_get_cached_model_count()})"
    )


def _ensure_px4_sitl_built() -> Path:
    build_path = PX4_DIR / "build" / "px4_sitl_default"
    px4_bin = build_path / "bin" / "px4"
    if px4_bin.exists():
        return build_path

    code, _, err = _run("make px4_sitl_default", cwd=PX4_DIR, timeout=1800.0)
    if code != 0:
        raise RuntimeError(f"Failed to build px4_sitl_default: {err.strip() or 'unknown error'}")
    if not px4_bin.exists():
        raise RuntimeError("PX4 build finished but px4 binary was not found")
    return build_path


def _format_extra_args(extra_args: list[object] | None) -> str:
    if not extra_args:
        return ""
    tokens: list[str] = []
    for token in extra_args:
        if token is None:
            continue
        text = str(token).strip()
        if not text:
            continue
        tokens.append(sh_quote(text))
    return (" " + " ".join(tokens)) if tokens else ""


def _args_contains_flag(extra_args: list[object] | None, flag: str) -> bool:
    if not extra_args:
        return False
    needle = flag.strip().lower()
    if not needle:
        return False
    for token in extra_args:
        if token is None:
            continue
        if str(token).strip().lower() == needle:
            return True
    return False


def launch_all(
    drone_count: int = 1,
    teacher_args: list[object] | None = None,
    gz_headless: bool | None = None,
) -> dict:
    requested = max(1, int(drone_count))
    effective = min(10, requested)

    # SOP mode is exact two-step process provided by user docs; it supports one x500 spawn reliably.
    instant_kill()
    (REPO_DIR / "logs").mkdir(parents=True, exist_ok=True)

    # Rotate/truncate oversized logs to prevent disk churn from breaking the sim.
    for log_name in (
        "gz_world.out",
        "px4_0.out",
        "px4_1.out",
        "px4_spawn.out",
        "px4_gz_live.out",
        "teacher_live.out",
        "teacher_live_0.out",
        "teacher_live_1.out",
    ):
        _rotate_log_if_large(REPO_DIR / "logs" / log_name)
    _run("docker compose up -d timescaledb redis backend adminer", cwd=REPO_DIR, timeout=90.0)

    # Dataset run directory (proof + isolation): write outputs to a unique folder.
    data_root = _data_root()
    run_stamp = time.strftime("%Y%m%d_%H%M%S")
    run_id = f"px4_teacher_{run_stamp}_d{effective}"
    run_dir = data_root / "px4_teacher" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_meta: dict[str, object] = {
        "run_id": run_id,
        "started_at": time.time(),
        "requested_drones": requested,
        "effective_drones": effective,
        "world": "obstacles",
        "repo_git_rev": _safe_git_rev(),
        "data_root": str(data_root),
    }
    try:
        run_meta["obstacles_sdf_sha256"] = _sha256_file(REPO_DIR / "obstacles.sdf")
    except OSError:
        run_meta["obstacles_sdf_sha256"] = None

    (run_dir / "RUN.json").write_text(json.dumps(run_meta, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    # Pre-create expected telemetry files so every run folder has stable, auditable artifacts
    # even if the sim fails before the teacher collector fully starts.
    for i in range(effective):
        try:
            out_csv = run_dir / f"telemetry_live_{i}.csv"
            out_csv.touch(exist_ok=True)
            # Ensure the placeholder isn't a 0-byte file (auditors hate empty artifacts).
            # The teacher collector later overwrites this with the real header + rows.
            if out_csv.stat().st_size == 0:
                out_csv.write_text("timestamp\n", encoding="utf-8")
        except Exception:
            pass

    with _ACTIVE_RUN_LOCK:
        global _ACTIVE_RUN
        _ACTIVE_RUN = {"dir": str(run_dir), "meta": run_meta}

    # Terminal 1 (exact README SOP): start Gazebo world.
    gz_env = os.environ.copy()
    if gz_headless is not None:
        gz_env["LESNAR_GZ_HEADLESS"] = "1" if gz_headless else "0"

    _run_bg(
        f"bash {sh_quote(str(REPO_DIR / 'scripts' / 'start_gz_world.sh'))}",
        REPO_DIR / "logs" / "gz_world.out",
        cwd=REPO_DIR,
        env=gz_env,
    )

    _wait_for_world_ready(timeout_s=120)

    _run("killall -9 px4 2>/dev/null || true", cwd=PX4_DIR, timeout=10.0)

    # Single-drone path: keep the exact, documented README SOP.
    if effective == 1:
        _run_bg(
            f"bash {sh_quote(str(REPO_DIR / 'scripts' / 'spawn_px4_drone.sh'))}",
            REPO_DIR / "logs" / "px4_0.out",
            cwd=REPO_DIR,
            env=os.environ.copy(),
        )
    else:
        # Multi-drone path: staged workflow as well (world already running), then spawn N PX4 instances.
        # This uses PX4's gz_bridge spawning via PX4_GZ_MODEL + PX4_GZ_MODEL_POSE.
        _run_bg(
            f"bash {sh_quote(str(REPO_DIR / 'scripts' / 'spawn_px4_drones.sh'))} {effective}",
            REPO_DIR / "logs" / "px4_spawn.out",
            cwd=REPO_DIR,
            env=os.environ.copy(),
        )

    _wait_for_model(expected=effective, timeout_s=90)

    # Bind teacher IDs to the actual Gazebo model names to prevent any UI/telemetry/control drift.
    # (UI is gated on /models, so telemetry must share those IDs.)
    model_names = _get_cached_models()
    if len(model_names) >= effective:
        model_names = model_names[:effective]
    else:
        model_names = [f"x500_{i}" for i in range(effective)]

    # Default to bridge-only (frontend-controlled) teacher unless explicitly overridden.
    wants_bridge = os.environ.get("LESNAR_TEACHER_BRIDGE_ONLY", "1").strip().lower() in {"1", "true", "yes"}
    caller_set_bridge_flag = _args_contains_flag(teacher_args, "--bridge_only") or _args_contains_flag(teacher_args, "--no_bridge_only")
    default_bridge_arg = " --bridge_only" if (wants_bridge and not caller_set_bridge_flag) else ""

    # Start teacher bridge(s) for MAVSDK collection.
    python_cmd = _python_cmd()
    extra_teacher_args = _format_extra_args(teacher_args)
    for i in range(effective):
        mavlink_port = 14540 + i
        out_csv = run_dir / f"telemetry_live_{i}.csv"
        # IMPORTANT: Drone ID must match Gazebo model name so the frontend (which is gated by /models)
        # can enrich state, and so backend commands route to the correct external subscriber.
        drone_id = model_names[i] if i < len(model_names) else f"x500_{i}"
        _run_bg(
            (
                f"{python_cmd} training/px4_teacher_collect_gz.py "
                f"--duration 0 --system 127.0.0.1:{mavlink_port} --mavsdk-server auto --hz 5 "
                f"--out {sh_quote(str(out_csv))} --drone-id {sh_quote(drone_id)}{default_bridge_arg}{extra_teacher_args}"
            ),
            REPO_DIR / "logs" / f"teacher_live_{i}.out",
            cwd=REPO_DIR,
        )

    actions = [
        "kill_all",
        "start_gazebo_sop",
        "start_px4",
        "start_teacher",
    ]
    if requested != effective:
        actions.append(f"requested_drones={requested};effective_drones={effective} (cap=10)")

    return {
        "actions": actions,
        "requested_drones": requested,
        "effective_drones": effective,
        "run_dir": str(run_dir),
        "status": runtime_status(),
    }


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected (e.g., curl timeout). Nothing to do.
            return

    def do_OPTIONS(self):
        self._send(200, {"success": True})

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"success": True, "service": "runtime-orchestrator"})
            return
        if self.path == "/status":
            self._send(200, {"success": True, "status": runtime_status()})
            return
        if self.path == "/models":
            status = runtime_status()
            if status.get("gz_running"):
                with _MODEL_CACHE_LOCK:
                    checked_at = float(_MODEL_CACHE.get("checked_at") or 0.0)
                    refreshing = bool(_MODEL_CACHE.get("refreshing"))
                    count = int(_MODEL_CACHE.get("count") or 0)
                # If cache is empty, do a one-time blocking refresh so UI gating is correct.
                if count <= 0 and not refreshing:
                    _refresh_model_cache_blocking(timeout_s=_MODEL_REFRESH_TIMEOUT_S)
                else:
                    if (time.time() - checked_at) > _MODEL_CACHE_MAX_AGE_S and not refreshing:
                        _kick_model_cache_refresh_async()
            payload = {
                "success": True,
                "gz_running": bool(status.get("gz_running")),
                "models": _get_cached_models(),
            }
            with _MODEL_CACHE_LOCK:
                payload.update(
                    {
                        "checked_at": float(_MODEL_CACHE.get("checked_at") or 0.0),
                        "refreshing": bool(_MODEL_CACHE.get("refreshing")),
                        "error": _MODEL_CACHE.get("error"),
                    }
                )
            self._send(200, payload)
            return

        if self.path == "/train/status":
            self._send(200, {"success": True, **_training_status_payload()})
            return
        self._send(404, {"success": False, "error": "not_found"})

    def do_POST(self):
        if self.path == "/kill-all":
            instant_kill()
            finalized = None
            try:
                with _ACTIVE_RUN_LOCK:
                    active = dict(_ACTIVE_RUN) if isinstance(_ACTIVE_RUN, dict) else None
                    # Clear active run so we don't finalize twice.
                    globals()["_ACTIVE_RUN"] = None
                if active and active.get("dir"):
                    run_dir = Path(str(active["dir"]))
                    run_meta = active.get("meta") if isinstance(active.get("meta"), dict) else {}
                    manifest_path = _finalize_run_manifest(run_dir, run_meta)
                    audit_record = _maybe_append_audit_for_manifest(run_dir, run_meta, manifest_path)
                    archive_status = _kick_archive_async(run_dir, run_meta, manifest_path)
                    finalized = {
                        "run_dir": str(run_dir),
                        "manifest": str(manifest_path),
                    }
                    if audit_record is not None:
                        finalized["audit_chain"] = audit_record
                    if archive_status.get("enabled"):
                        finalized["archive"] = archive_status
            except Exception as exc:
                finalized = {"error": str(exc)}

            payload = {"success": True, "message": "All runtime processes killed."}
            if finalized:
                payload["finalized"] = finalized
            self._send(200, payload)
            return

        if self.path == "/launch-all":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                drone_count = 1
                teacher_args = None
                gz_headless = None
                if content_length > 0:
                    payload = self.rfile.read(content_length)
                    body = json.loads(payload)
                    drone_count = int(body.get("drone_count", 1))
                    if isinstance(body.get("teacher_args"), list):
                        teacher_args = body.get("teacher_args")
                    if "gz_headless" in body:
                        gz_headless = bool(body.get("gz_headless"))
                result = launch_all(drone_count, teacher_args=teacher_args, gz_headless=gz_headless)
                self._send(200, {"success": True, **result})
            except Exception as exc:
                self._send(500, {"success": False, "error": str(exc)})
            return

        if self.path == "/train/start":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                epochs = 20
                batch_size = 128
                csv_index = 0
                if content_length > 0:
                    payload = self.rfile.read(content_length)
                    body = json.loads(payload)
                    if "epochs" in body:
                        epochs = int(body.get("epochs") or epochs)
                    if "batch_size" in body:
                        batch_size = int(body.get("batch_size") or batch_size)
                    if "csv_index" in body:
                        csv_index = int(body.get("csv_index") or 0)

                result = start_training(epochs=epochs, batch_size=batch_size, csv_index=csv_index)
                if not result.get("success"):
                    status = 409 if result.get("error") == "training_already_running" else 400
                    self._send(status, result)
                    return
                self._send(200, result)
            except Exception as exc:
                self._send(500, {"success": False, "error": str(exc)})
            return

        self._send(404, {"success": False, "error": "not_found"})


if __name__ == "__main__":
    def _is_existing_orchestrator_healthy() -> bool:
        try:
            with urlopen(f"http://{HOST}:{PORT}/health", timeout=1.5) as resp:
                if getattr(resp, "status", 200) != 200:
                    return False
                data = resp.read(4096) or b""
            return b"runtime-orchestrator" in data
        except Exception:
            return False

    force_restart = (os.environ.get("LESNAR_ORCH_FORCE_RESTART") or "").strip().lower() in {"1", "true", "yes"}

    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        # Common operator error: starting a second instance while one is already running.
        if getattr(exc, "errno", None) == 98:
            if _is_existing_orchestrator_healthy() and not force_restart:
                print(
                    f"runtime orchestrator already running on http://{HOST}:{PORT} (set LESNAR_ORCH_FORCE_RESTART=1 to restart)",
                    flush=True,
                )
                raise SystemExit(0)

            if force_restart:
                _run("pkill -f 'scripts/runtime_orchestrator.py' 2>/dev/null || true", timeout=5.0)
                time.sleep(1.0)
                server = ThreadingHTTPServer((HOST, PORT), Handler)
            else:
                print(
                    f"port {PORT} is already in use; an old orchestrator may be running. "
                    f"Run: pkill -f scripts/runtime_orchestrator.py  (or set LESNAR_ORCH_PORT)",
                    flush=True,
                )
                raise SystemExit(1)
        raise

    print(f"runtime orchestrator listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()
