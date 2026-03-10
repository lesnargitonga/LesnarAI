# Simulation Audit — 2026-03-06

## Scope
- Simulation stack was stopped before audit (teacher, PX4 SITL, Gazebo, MAVSDK bridge).
- Latest telemetry file audited: `dataset/px4_teacher/telemetry_god.csv`.
- Integrity snapshot created and verified.

## Integrity
- Manifest: `docs/security/telemetry_audit_manifest.json`
- Result: PASS (signature valid and files unchanged at verification time).

## Quality Metrics (latest telemetry run)
- Rows: 99,592
- Duration: 5,198.97 s
- Sample rate: 19.16 Hz
- Avg speed: 2.82 m/s
- Avg progress: 2.744 m/s
- Low speed: 10.75%
- Low progress: 11.98%
- Avg heading error: 22.87 deg
- Max heading error: 179.98 deg
- Avg cross-track: 1.51 m
- Max cross-track: 11.22 m
- Negative progress samples: 4.30%
- Heading error > 90 deg: 9.27%
- Heading error > 140 deg: 3.89%

## Runtime Indicators (last ONLINE session slice)
- FALCON metric rows: 3,386
- Heading-stall recoveries: 225

## Verdict
- The run is high-performing and stable enough for mission demo use.
- It is not mathematically perfect yet; rotation/deadlock episodes still occur and are recovered by replan logic.

## Recommended Modifications
1. Increase heading-stall trigger sensitivity to recover sooner:
   - Reduce `--heading_stall_err_deg` from 125 to 110.
   - Reduce `--heading_stall_strikes` from 18 to 12.
2. Reduce lateral overshoot in tight turns:
   - Reduce `--max_lateral_accel_mps2` from 2.4 to 2.0.
   - Reduce `--max_tilt_deg` from 14 to 12.
3. Reduce brief reverse-progress spikes during aggressive reorientation:
   - Increase `--goal_grace_sec` from 7.0 to 9.0.
   - Increase `--replan_strikes` from 4 to 5.
