# Deployment Completion Checklist

This checklist separates what the codebase now supports from the inputs only you can provide.

## Already implemented in code
- Session auth endpoints and persistent session tracking
- Operator-attributed audit records
- Telemetry history + replay APIs
- Server-side geofence enforcement
- Frontend auth gate, RBAC scaffold, stale-state lockout, degraded-link mode
- Replay UI, offline tile hooks, tactical hotkeys, typed confirmations

---

## You must provide these inputs

### 1. Real operator identities
Generate backend user JSON:

```bash
cd ~/workspace/LesnarAI
python3 scripts/generate_auth_users_json.py \
  --user admin:admin:YOUR_STRONG_ADMIN_PASSWORD \
  --user ops:operator:YOUR_STRONG_OPERATOR_PASSWORD \
  --user viewer:viewer:YOUR_STRONG_VIEWER_PASSWORD \
  --pretty
```

Copy the resulting JSON into:
- `LESNAR_AUTH_USERS_JSON` in `.env.secure`

### 2. Real secrets
Create a secure env file:

```bash
cd ~/workspace/LesnarAI
python3 scripts/generate_secure_env.py --force
```

Then copy `.env.secure` to `.env` and replace placeholders as needed.
Use `.env.secure` directly for `docker compose --env-file .env.secure ...`.

### 3. Operational boundary
Set a real operational boundary in both places:
- backend: `LESNAR_OPERATIONAL_BOUNDARY` in `.env.secure`
- frontend: `REACT_APP_OPERATIONAL_BOUNDARY` in `frontend/.env.local`

Format:

```json
[[40.7128,-74.0060],[40.7180,-74.0020],[40.7160,-73.9950],[40.7100,-73.9980]]
```

### 4. Offline/local tiles
Deploy a local tile source and set:
- `REACT_APP_MAP_TILE_URL`
- optional `REACT_APP_MAP_TILE_ATTRIBUTION`

If this is not set, offline map readiness is not complete.

### 5. Frontend secure env
Bootstrap writes these automatically:
- `frontend/.env.local.secure`
- `frontend/.env.local`

Ensure they contain:
- `REACT_APP_REQUIRE_SESSION_AUTH=1`
- `REACT_APP_ALLOW_LEGACY_API_KEY=0`
- `REACT_APP_MAP_TILE_URL`
- `REACT_APP_OPERATIONAL_BOUNDARY`

### 6. Apply database migration
Start backend with migrations enabled or run with your normal deployment path so `0002_auth_sessions_and_telemetry_history` is applied.

---

## Validation steps you should run

### Backend/session validation
- Login via `/api/auth/login`
- Or use `python3 scripts/request_session_token.py --username <user> --password <pass>`
- Confirm `/api/auth/me` works with returned bearer token
- Confirm `/api/auth/logout` revokes the session

### Safety validation
- Disconnect telemetry and confirm command lockout appears
- Attempt waypoint outside geofence and confirm rejection
- Confirm critical actions require typed confirmation

### Replay validation
- Run telemetry for several minutes
- Open Tactical Map replay mode
- Confirm path history renders and scrubs correctly

### Audit validation
- Send commands as different users
- Verify `command_logs` / `events` contain `operator_id`, `operator_role`, `session_id`
- Run `python3 scripts/verify_audit_chain.py`

---

## Physical / infrastructure items only you can complete
- local/offline tile server or packaged MBTiles
- real camera / WebRTC feed integration source
- live PX4 / Gazebo / hardware mission validation
- network-jamming / degraded-link field test
- production secret storage and rotation
- TLS termination / reverse proxy hardening

---

## Definition of fully complete
It is fully complete only when:
- session auth is enabled
- static browser API keys are no longer relied on and browser fallback remains disabled
- operational boundary is configured and verified
- local tile source is live
- migrations are applied
- replay history is accumulating
- audit attribution is visible per action
- live operator acceptance tests pass on the real stack
