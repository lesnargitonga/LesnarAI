# LESNAR AI — Demo-Safe Mode

Runs the operator stack **without Docker, real Postgres, PX4, or Gazebo**, and
demonstrates a real runtime action (registering simulated drones) so the
dashboard, telemetry and audit reflect a genuine backend state change.

> This is **control/orchestration architecture in simulation**. No real drone,
> flight, or hardware is operated.

## What is real vs simulated/off

| Layer | Demo-safe behaviour |
|---|---|
| Frontend (React) `:3006` | **Real** operator dashboard |
| Backend (Flask + Socket.IO) `:5000` | **Real** API, **throwaway SQLite** DB (`/tmp/lesnar-demo.db`) |
| Runtime orchestrator `:8765` | **Real** control-plane process; Gazebo/PX4 launch stays **OFF** |
| Drones | **Simulated** records via `POST /api/drones`; no real telemetry source |
| Auth | Disabled for the demo (`LESNAR_REQUIRE_AUTH=0`) — do not show the login/users screens |

## Run

```bash
cd /home/lesnar/workspace/LesnarAI
./scripts/run_lesnarai_demo_safe.sh up      # start stack + seed simulated drones
./scripts/run_lesnarai_demo_safe.sh seed    # re-seed only
```

## Safe runtime action to show in the Loom

```bash
# before
curl -s http://127.0.0.1:5000/api/drones | python3 -c "import sys,json;print('drones',len(json.load(sys.stdin)['drones']))"
# action: register a simulated drone
curl -s -X POST http://127.0.0.1:5000/api/drones -H 'Content-Type: application/json' \
  -d '{"drone_id":"DEMO-SIM-03","position":[-1.2921,36.8219,0]}'
# after — telemetry + dashboard map now reflect it
curl -s http://127.0.0.1:5000/api/telemetry | python3 -c "import sys,json;print(json.load(sys.stdin)['fleet_status'])"
```

Health checks:

```bash
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool   # status: ok
curl -s http://127.0.0.1:8765/health                              # success: true
curl -s http://127.0.0.1:8765/status                              # gz_running: false (safe)
```

## Safety

- Gazebo/PX4 are never launched; `/status` shows `gz_running: false`.
- No real `.env`/Postgres; SQLite is wiped per run.
- Do **not** open the auth/users screens (auth is disabled for the demo).
- Files added: `demo/lesnarai_demo_seed.json`, `demo/README_DEMO.md`,
  `scripts/run_lesnarai_demo_safe.sh`. Reversible.
