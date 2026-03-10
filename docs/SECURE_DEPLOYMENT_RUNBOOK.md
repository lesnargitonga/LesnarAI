# Secure Deployment Runbook

This runbook finishes the software-side hardening already added to LesnarAI and isolates the remaining human-only inputs.

## 1. Generate secure backend secrets

Create the secure backend env file:

- `python3 scripts/bootstrap_secure_deployment.py`

This generates:

- `.env.secure`
- `frontend/.env.local.secure`
- `frontend/.env.local`

## 2. Create real operator accounts

Simplest option for beginners:

- `python3 scripts/manage_auth_users.py`

This asks for usernames, roles, and passwords interactively, writes `auth_users.json`, and updates `.env.secure` if it already exists.

Runtime note: `docker compose` mounts `auth_users.json` into the backend (`LESNAR_AUTH_USERS_FILE=/app/backend/auth_users.json`) so hashed passwords are loaded reliably without shell/env interpolation issues.

Manual option:

Generate `LESNAR_AUTH_USERS_JSON` using real usernames, roles, and strong passwords:

- `python3 scripts/generate_auth_users_json.py --user commander:admin:STRONG_PASSWORD --user ops1:operator:STRONG_PASSWORD --user intel:viewer:STRONG_PASSWORD --pretty`

Save the JSON output to a file, for example `auth_users.json`.

Then re-run bootstrap with that file:

- `python3 scripts/bootstrap_secure_deployment.py --auth-users-json-file auth_users.json --force`

## 3. Set the real operational geofence

Create a JSON file containing the approved polygon as an array of `[lat, lng]` pairs, for example:

- `[[47.6419,-122.1402],[47.6427,-122.1360],[47.6394,-122.1348],[47.6386,-122.1391]]`

Re-run bootstrap with the boundary file:

- `python3 scripts/bootstrap_secure_deployment.py --boundary-json-file boundary.json --force`

## 4. Configure offline/local tiles

If you have a local tile service, inject it during bootstrap:

- `python3 scripts/bootstrap_secure_deployment.py --tile-url http://localhost:8081/tiles/{z}/{x}/{y}.png --force`

If you do not yet have offline tiles, deployment can still proceed, but map behavior will rely on fallback tiles until this is completed.

## 5. Validate deployment readiness

Run the validator:

- `python3 scripts/validate_secure_deployment.py`

Do not proceed until it returns `PASS`.

For CLI validation, obtain a bearer header with:

- `python3 scripts/request_session_token.py --username <user> --password <pass>`

## 6. Start the stack securely

Run the stack with the secure env file:

- `docker compose --env-file .env.secure up --build`

## 7. Post-start checks

Required checks:

1. Login is required before the UI is visible.
2. Browser-exposed API-key fallback remains disabled.
3. Operator roles behave correctly:
   - `viewer` cannot issue commands.
   - `operator` can execute mission controls but not admin-only settings.
   - `admin` can access full controls.
4. Drone commands fail closed when telemetry is stale.
5. Commands no longer show success unless state change is confirmed.
6. Geofence rejects out-of-bounds mission waypoints and `goto` targets.
7. Replay/history endpoints return recent telemetry.
8. Degraded-link banner appears when socket/telemetry thresholds are exceeded.
9. Audit logs contain operator/session attribution.

## 8. Remaining human-only tasks

These cannot be completed purely in code:

- Choose and protect real operator passwords.
- Approve and provide the real operational boundary coordinates.
- Stand up and verify the offline/local map tile source.
- Run live sim or hardware acceptance tests.
- Rotate secrets on an operational schedule.
- Put the stack behind your chosen TLS/reverse-proxy and identity perimeter if required by your environment.

## 9. Recommended acceptance sequence

1. Run validator until it passes.
2. Start backend, database, and frontend from `.env.secure`.
3. Log in as `viewer`, `operator`, and `admin` separately.
4. Verify stale-state lockout by stopping telemetry.
5. Verify geofence rejection with an intentionally invalid waypoint.
6. Verify replay mode after several minutes of telemetry.
7. Verify emergency flows with typed confirmation.
8. Capture screenshots and logs for operational sign-off.

## 10. Presentation profile (fast path)

Use this when preparing a hackathon demo run:

1. `python3 scripts/bootstrap_secure_deployment.py`
2. `python3 scripts/validate_secure_deployment.py`
3. `docker compose --env-file .env.secure up -d --build`
4. `cd frontend && npm start`
5. `export SESSION_HEADER="$(python3 scripts/request_session_token.py --username <operator-user> --password <operator-password>)"`
6. `curl -H "$SESSION_HEADER" http://localhost:5000/api/health`

Optional live simulation:

1. `gz sim -v4 -r obstacles.sdf &`
2. `cd ~/PX4-Autopilot && export PX4_GZ_MODEL="x500" && PX4_GZ_STANDALONE=1 make px4_sitl gz_x500`
3. `python3 training/px4_teacher_collect_gz.py --duration 0`
