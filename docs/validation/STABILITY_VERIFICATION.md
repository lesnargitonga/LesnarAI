# Automated Stability Verification (Session Login + Drift Metrics)

This workflow automates session authentication, telemetry capture, and position-drift analysis for stability verification.

## Script

- `scripts/telemetry_stability_autologin.py`

## What it does

1. Logs in to backend using `/api/auth/login`.
2. Polls `/api/drones` with bearer auth for a configurable duration.
3. Computes quantitative stability metrics:
   - end-to-end drift (m)
   - RMS jitter from centroid (m)
   - p95 jitter (m)
   - altitude span (m)
   - telemetry availability ratio
   - telemetry age statistics
4. Writes:
   - JSON report: `docs/validation/stability_verification_latest.json`
   - sample CSV: `docs/validation/stability_verification_samples_latest.csv`
5. Returns exit code:
   - `0` = pass
   - `2` = fail thresholds
   - `1` = runtime/login error

## Example command

```bash
cd ~/workspace/LesnarAI
python3 scripts/telemetry_stability_autologin.py \
  --backend-url http://localhost:5000 \
  --username lesnar \
  --password lesnar1234 \
  --duration 120 \
  --interval 1.0 \
  --max-end-to-end-drift-m 3.0 \
  --max-rms-jitter-m 1.2 \
  --min-availability 0.90
```

## Supervisor-facing usage

- Use this script before and after each PID tuning change.
- Keep environment conditions fixed for A/B comparison.
- Require at least 3 consecutive PASS runs before promoting a tuning profile.
