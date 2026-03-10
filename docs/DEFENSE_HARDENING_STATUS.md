# Defense Hardening Status

## Implemented

### Backend
- Short-lived signed session auth endpoints:
  - `/api/auth/login`
  - `/api/auth/me`
  - `/api/auth/logout`
- Persistent `auth_sessions` tracking with revocation support.
- Operator attribution persisted on command and event audit records:
  - `operator_id`
  - `operator_role`
  - `session_id`
- Telemetry history persistence in `telemetry_samples`.
- Replay/AAR APIs:
  - `/api/telemetry/history`
  - `/api/drones/:id/history`
- Server-side operational geofence enforcement on `goto` and mission waypoints.
- External telemetry freshness pruning and command confirmation logic.

### Frontend
- Session-aware request headers and operator context tagging.
- Optional session-auth gate for deployments that require login.
- RBAC scaffold for viewer/operator/admin behaviors.
- Stale telemetry command lockout.
- Typed confirmation for critical actions.
- Degraded-link mode with RTT/telemetry-age awareness.
- Local operator audit console entries.
- Tactical hotkeys.
- Offline/local tile configuration hooks.
- Geofence rendering and client-side waypoint rejection.
- Replay mode on tactical map using telemetry history.

## Required Environment for Full Session Auth
- `LESNAR_AUTH_USERS_JSON` on backend, e.g. JSON list of users with `username`, `role`, and `password_hash`.
- `REACT_APP_REQUIRE_SESSION_AUTH=1` on frontend if login should be mandatory.

## Recommended Next Infrastructure Steps
- Replace API-key fallback entirely once session auth is deployed.
- Stand up local tile service and set `REACT_APP_MAP_TILE_URL`.
- Add backend command endpoints for `hover/hold` and mission replay bookmarking.
- Add WebRTC video and sensor visualization pipeline.
- Add Timescale retention/compression policies for telemetry history.
