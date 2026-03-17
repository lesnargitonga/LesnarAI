#!/usr/bin/env python3

"""LesnarAI Scenario Runner

Headless scenario executor for overnight ODD / stressor runs.

Core constraints:
- Uses the existing runtime orchestrator for launch/kill and audit manifest finalization.
- Never fabricates outcomes: pass/fail is derived only from real run artifacts (telemetry CSV).
- Writes `scenario.json` and `outcomes.json` into the orchestrator-provided run directory *before*
  triggering `/kill-all`, so they are included in `MANIFEST.json`.

Typical usage:
  python3 scripts/scenario_runner.py --count 100 --duration-s 120 \
    --teacher-args --no_safe_presentation_profile --base_speed 2.8 --max_speed 5.0

  python3 scripts/scenario_runner.py --scenarios scripts/scenarios.json

Scenario file format (JSON):
  {
    "scenarios": [
      {
        "scenario_id": "ODD_WIND_FAST_001",
        "drone_count": 1,
        "duration_s": 90,
        "teacher_args": ["--no_safe_presentation_profile", "--base_speed", "2.8", "--max_speed", "5.0"],
        "geofence": {"lat_min": 0, "lat_max": 0, "lon_min": 0, "lon_max": 0}
      }
    ]
  }
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def _utc_now_iso() -> str:
    # Avoid datetime import overhead; good enough for stamping.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class OrchestratorClient:
    def __init__(self, base_url: str, timeout_s: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = float(timeout_s)

    def get(self, path: str) -> dict[str, Any]:
        url = self.base_url + path
        with urlopen(url, timeout=self.timeout_s) as resp:
            data = resp.read() or b"{}"
        return json.loads(data.decode("utf-8"))

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.base_url + path
        raw = json.dumps(body or {}).encode("utf-8")
        req = Request(url, method="POST", data=raw, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=self.timeout_s) as resp:
            data = resp.read() or b"{}"
        return json.loads(data.decode("utf-8"))

    def launch_all(self, drone_count: int, teacher_args: list[str] | None) -> dict[str, Any]:
        body: dict[str, Any] = {"drone_count": int(drone_count)}
        if teacher_args:
            body["teacher_args"] = list(teacher_args)
        return self.post("/launch-all", body)

    def kill_all(self) -> dict[str, Any]:
        return self.post("/kill-all", {})


@dataclass
class Geofence:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def contains(self, lat: float, lon: float) -> bool:
        return (self.lat_min <= lat <= self.lat_max) and (self.lon_min <= lon <= self.lon_max)


@dataclass
class MonitorConfig:
    warmup_s: float = 15.0
    min_rows_after_warmup: int = 5
    stale_s: float = 10.0
    poll_s: float = 0.5

    # Collision-ish heuristic (derived only from telemetry CSV)
    collision_front_lidar_m: float = 0.05
    collision_speed_drop_mps: float = 2.0
    collision_dt_s: float = 1.0

    # Loss-of-control guardrails
    max_abs_roll_deg: float = 65.0
    max_abs_pitch_deg: float = 65.0
    attitude_persist_s: float = 0.5


class CsvTail:
    def __init__(self, path: Path):
        self.path = path
        self._fh = None
        self._reader: csv.DictReader[str] | None = None
        self.fieldnames: list[str] | None = None
        self.rows_read = 0
        self.last_row: dict[str, str] | None = None
        self.last_row_walltime = 0.0

    def open_if_ready(self) -> None:
        if self._fh is not None:
            return
        if not self.path.exists():
            return
        fh = self.path.open("r", newline="", encoding="utf-8", errors="replace")
        header_line = fh.readline()
        if not header_line:
            fh.close()
            return
        header = next(csv.reader([header_line]))
        self.fieldnames = [str(h).strip() for h in header if str(h).strip()]
        self._reader = csv.DictReader(fh, fieldnames=self.fieldnames)
        self._fh = fh

    def close(self) -> None:
        try:
            if self._fh is not None:
                self._fh.close()
        finally:
            self._fh = None
            self._reader = None

    def read_available(self, max_rows: int = 2000) -> int:
        self.open_if_ready()
        if self._fh is None or self._reader is None:
            return 0

        read_now = 0
        while read_now < max_rows:
            pos = self._fh.tell()
            line = self._fh.readline()
            if not line:
                # No more data available right now.
                self._fh.seek(pos)
                break
            try:
                row_values = next(csv.reader([line]))
            except csv.Error:
                continue
            if not row_values:
                continue
            # Expand / trim to header length.
            values = (row_values + [""] * (len(self.fieldnames or []) - len(row_values)))[: len(self.fieldnames or [])]
            row = dict(zip(self.fieldnames or [], values))
            self.last_row = row
            self.last_row_walltime = time.time()
            self.rows_read += 1
            read_now += 1

        return read_now


def _getf(row: dict[str, str] | None, key: str, default: float | None = None) -> float | None:
    if not row:
        return default
    raw = row.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _hardfail_reason(
    *,
    now: float,
    start_wall: float,
    cfg: MonitorConfig,
    tail: CsvTail,
    geofence: Geofence | None,
    state: dict[str, Any],
) -> str | None:
    # Warmup: require some real telemetry rows.
    if (now - start_wall) >= cfg.warmup_s and tail.rows_read < cfg.min_rows_after_warmup:
        return f"telemetry_insufficient_rows(rows={tail.rows_read}, warmup_s={cfg.warmup_s})"

    # Stale: if we had rows but they stopped arriving.
    if tail.rows_read >= 1:
        if (now - tail.last_row_walltime) > cfg.stale_s:
            return f"telemetry_stale(no_new_rows_s={now - tail.last_row_walltime:.1f}, stale_s={cfg.stale_s})"

    row = tail.last_row
    if not row:
        return None

    # Geofence (optional)
    if geofence is not None:
        lat = _getf(row, "lat")
        lon = _getf(row, "lon")
        if lat is not None and lon is not None:
            if not geofence.contains(lat, lon):
                return f"geofence_breach(lat={lat:.7f}, lon={lon:.7f})"

    # Attitude persist
    roll = _getf(row, "roll_deg")
    pitch = _getf(row, "pitch_deg")
    if roll is not None and abs(roll) > cfg.max_abs_roll_deg:
        bad_since = state.setdefault("roll_bad_since", now)
        if (now - bad_since) >= cfg.attitude_persist_s:
            return f"attitude_roll_exceeded(roll_deg={roll:.1f})"
    else:
        state.pop("roll_bad_since", None)

    if pitch is not None and abs(pitch) > cfg.max_abs_pitch_deg:
        bad_since = state.setdefault("pitch_bad_since", now)
        if (now - bad_since) >= cfg.attitude_persist_s:
            return f"attitude_pitch_exceeded(pitch_deg={pitch:.1f})"
    else:
        state.pop("pitch_bad_since", None)

    # Collision-ish: detect a sudden speed drop near zero clearance.
    # We need at least 2 samples; we approximate by comparing previous speed snapshot.
    speed = _getf(row, "ground_speed_mps")
    front = _getf(row, "front_lidar_min")
    ts = _getf(row, "timestamp")
    if speed is not None and ts is not None:
        prev = state.get("prev_sample")
        if isinstance(prev, dict):
            prev_speed = prev.get("speed")
            prev_ts = prev.get("ts")
            if isinstance(prev_speed, (int, float)) and isinstance(prev_ts, (int, float)):
                dt = float(ts) - float(prev_ts)
                if 0.0 < dt <= cfg.collision_dt_s:
                    if (prev_speed - speed) >= cfg.collision_speed_drop_mps:
                        if front is not None and front <= cfg.collision_front_lidar_m:
                            state["collision_events"] = int(state.get("collision_events") or 0) + 1
                            return (
                                "collision_heuristic(speed_drop_mps="
                                f"{prev_speed - speed:.2f}, front_lidar_min_m={front:.3f}, dt_s={dt:.2f})"
                            )
        state["prev_sample"] = {"ts": float(ts), "speed": float(speed)}

    return None


def _load_scenarios(path: Path) -> list[dict[str, Any]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, dict) and isinstance(obj.get("scenarios"), list):
        return [dict(item) for item in obj["scenarios"]]
    if isinstance(obj, list):
        return [dict(item) for item in obj]
    raise ValueError("Scenario file must be a JSON list or an object with a 'scenarios' array")


def _generate_fuzz_scenarios(count: int, seed: int, duration_s: int, drone_count: int) -> list[dict[str, Any]]:
    rng = random.Random(int(seed))
    scenarios: list[dict[str, Any]] = []
    for i in range(int(count)):
        base = rng.uniform(1.2, 3.8)
        max_speed = max(base + rng.uniform(0.8, 2.5), base)
        yaw_rate = rng.uniform(40.0, 110.0)
        max_tilt = rng.uniform(8.0, 22.0)
        args = [
            "--no_safe_presentation_profile",
            "--base_speed",
            f"{base:.2f}",
            "--max_speed",
            f"{max_speed:.2f}",
            "--yaw_rate_limit",
            f"{yaw_rate:.1f}",
            "--max_tilt_deg",
            f"{max_tilt:.1f}",
        ]
        scenarios.append(
            {
                "scenario_id": f"fuzz_{seed}_{i:05d}",
                "drone_count": int(drone_count),
                "duration_s": int(duration_s),
                "teacher_args": args,
                "seed": int(seed),
                "fuzz_index": i,
            }
        )
    return scenarios


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orchestrator", type=str, default=os.environ.get("LESNAR_ORCH_URL", "http://127.0.0.1:8765"))
    ap.add_argument("--scenarios", type=str, default="", help="Path to JSON scenarios file")
    ap.add_argument("--count", type=int, default=1, help="Number of runs (when not using --scenarios)")
    ap.add_argument("--seed", type=int, default=0, help="Seed for fuzz generation")
    ap.add_argument("--fuzz", action="store_true", help="Generate fuzz scenarios (varies controller aggressiveness)")
    ap.add_argument("--drone-count", type=int, default=1)
    ap.add_argument("--duration-s", type=int, default=90)
    ap.add_argument(
        "--teacher-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Extra args appended to training/px4_teacher_collect_gz.py (e.g., --no_safe_presentation_profile --base_speed 2.5)",
    )

    ap.add_argument("--warmup-s", type=float, default=15.0)
    ap.add_argument("--stale-s", type=float, default=10.0)
    ap.add_argument("--poll-s", type=float, default=0.5)
    ap.add_argument("--min-rows-after-warmup", type=int, default=5)

    ap.add_argument("--collision-front-lidar-m", type=float, default=0.05)
    ap.add_argument("--collision-speed-drop-mps", type=float, default=2.0)

    ap.add_argument("--max-abs-roll-deg", type=float, default=65.0)
    ap.add_argument("--max-abs-pitch-deg", type=float, default=65.0)
    ap.add_argument("--attitude-persist-s", type=float, default=0.5)

    ap.add_argument("--continue-on-fail", action="store_true", help="Keep running remaining scenarios after a failure")

    args = ap.parse_args()

    cfg = MonitorConfig(
        warmup_s=float(args.warmup_s),
        min_rows_after_warmup=int(args.min_rows_after_warmup),
        stale_s=float(args.stale_s),
        poll_s=float(args.poll_s),
        collision_front_lidar_m=float(args.collision_front_lidar_m),
        collision_speed_drop_mps=float(args.collision_speed_drop_mps),
        max_abs_roll_deg=float(args.max_abs_roll_deg),
        max_abs_pitch_deg=float(args.max_abs_pitch_deg),
        attitude_persist_s=float(args.attitude_persist_s),
    )

    orch = OrchestratorClient(args.orchestrator)

    scenarios: list[dict[str, Any]]
    if args.scenarios:
        scenarios = _load_scenarios(Path(args.scenarios))
    else:
        if args.fuzz:
            seed = int(args.seed or int(time.time()))
            scenarios = _generate_fuzz_scenarios(args.count, seed, args.duration_s, args.drone_count)
        else:
            scenarios = []
            for i in range(int(args.count)):
                scenarios.append(
                    {
                        "scenario_id": f"run_{i:05d}",
                        "drone_count": int(args.drone_count),
                        "duration_s": int(args.duration_s),
                        "teacher_args": list(args.teacher_args or []),
                    }
                )

    overall_fail = False

    for idx, scenario in enumerate(scenarios, start=1):
        scenario_id = str(scenario.get("scenario_id") or f"scenario_{idx:04d}")
        duration_s = int(scenario.get("duration_s") or args.duration_s)
        drone_count = int(scenario.get("drone_count") or args.drone_count)
        teacher_args = scenario.get("teacher_args")
        teacher_args_list = [str(x) for x in teacher_args] if isinstance(teacher_args, list) else list(args.teacher_args or [])

        geofence = None
        gf = scenario.get("geofence")
        if isinstance(gf, dict) and all(k in gf for k in ("lat_min", "lat_max", "lon_min", "lon_max")):
            try:
                geofence = Geofence(
                    lat_min=float(gf["lat_min"]),
                    lat_max=float(gf["lat_max"]),
                    lon_min=float(gf["lon_min"]),
                    lon_max=float(gf["lon_max"]),
                )
            except Exception:
                geofence = None

        print(f"[{_utc_now_iso()}] scenario {idx}/{len(scenarios)}: {scenario_id} (drones={drone_count}, duration_s={duration_s})", flush=True)

        start_wall = time.time()
        run_dir = None
        tails: list[CsvTail] = []
        state_by_drone: list[dict[str, Any]] = []
        fail_reason = None

        try:
            launch_resp = orch.launch_all(drone_count=drone_count, teacher_args=teacher_args_list)
            if not bool(launch_resp.get("success")):
                raise RuntimeError(f"/launch-all failed: {launch_resp}")
            run_dir_raw = str(launch_resp.get("run_dir") or "").strip()
            if not run_dir_raw:
                raise RuntimeError(f"orchestrator did not return run_dir: {launch_resp}")
            run_dir = Path(run_dir_raw).expanduser()

            effective_drones = int(launch_resp.get("effective_drones") or drone_count)
            effective_drones = max(1, effective_drones)

            scenario_stamp = {
                "scenario_id": scenario_id,
                "started_at_utc": _utc_now_iso(),
                "started_at_wall_s": start_wall,
                "duration_s": duration_s,
                "requested_drone_count": drone_count,
                "effective_drone_count": effective_drones,
                "teacher_args": teacher_args_list,
                "orchestrator": {"base_url": orch.base_url},
                "inputs": scenario,
                "monitor_config": cfg.__dict__,
            }
            _json_dump(run_dir / "scenario.json", scenario_stamp)

            tails = [CsvTail(run_dir / f"telemetry_live_{i}.csv") for i in range(effective_drones)]
            state_by_drone = [{} for _ in range(effective_drones)]

            deadline = start_wall + float(duration_s)
            while time.time() < deadline:
                now = time.time()
                for i, tail in enumerate(tails):
                    tail.read_available()
                    reason = _hardfail_reason(
                        now=now,
                        start_wall=start_wall,
                        cfg=cfg,
                        tail=tail,
                        geofence=geofence,
                        state=state_by_drone[i],
                    )
                    if reason:
                        fail_reason = f"drone_{i}:{reason}"
                        break
                if fail_reason:
                    break
                time.sleep(cfg.poll_s)

            # Compute outcomes strictly from artifacts observed so far.
            outcomes = {
                "scenario_id": scenario_id,
                "finished_at_utc": _utc_now_iso(),
                "duration_s": duration_s,
                "requested_drone_count": drone_count,
                "effective_drone_count": effective_drones,
                "pass": bool(fail_reason is None),
                "fail_reason": fail_reason,
                "telemetry": [
                    {
                        "file": str(t.path),
                        "rows_read": int(t.rows_read),
                        "last_timestamp": _getf(t.last_row, "timestamp"),
                        "collision_events": int(state_by_drone[i].get("collision_events") or 0),
                    }
                    for i, t in enumerate(tails)
                ],
            }
            _json_dump(run_dir / "outcomes.json", outcomes)

        except Exception as exc:
            fail_reason = fail_reason or f"exception:{exc}"
            overall_fail = True
            print(f"[{_utc_now_iso()}] scenario failed: {scenario_id} reason={fail_reason}", flush=True)
            if run_dir is not None:
                try:
                    _json_dump(
                        run_dir / "outcomes.json",
                        {
                            "scenario_id": scenario_id,
                            "finished_at_utc": _utc_now_iso(),
                            "pass": False,
                            "fail_reason": fail_reason,
                        },
                    )
                except Exception:
                    pass
        finally:
            for t in tails:
                t.close()
            try:
                kill_resp = orch.kill_all()
                if not bool(kill_resp.get("success")):
                    print(f"[{_utc_now_iso()}] warning: /kill-all did not return success: {kill_resp}", flush=True)
            except Exception as exc:
                print(f"[{_utc_now_iso()}] warning: /kill-all failed: {exc}", flush=True)

        if fail_reason is not None:
            overall_fail = True
            if not args.continue_on_fail:
                break

    return 1 if overall_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
