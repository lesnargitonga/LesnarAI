# Lesnar AI Frontend Full Reference

## 1) Scope
This document covers the full frontend currently in `frontend/`, including app shell, routing, global state, telemetry/update flow, API binding, UI modules, styling system, and runtime behavior.

Included files:
- `frontend/src/App.js`
- `frontend/src/index.js`
- `frontend/src/index.css`
- `frontend/src/App.css`
- `frontend/src/config.js`
- `frontend/src/api.js`
- `frontend/src/context/DroneContext.js`
- `frontend/src/utils/droneState.js`
- `frontend/src/components/Header.js`
- `frontend/src/components/Sidebar.js`
- `frontend/src/components/Dashboard.js`
- `frontend/src/components/DroneMap.js`
- `frontend/src/components/DroneList.js`
- `frontend/src/components/MissionControl.js`
- `frontend/src/components/Analytics.js`
- `frontend/src/components/Settings.js`
- `frontend/src/components/DiagnosticTerminal.js`
- `frontend/src/components/HealthStatusIndicator.js`
- `frontend/src/components/ErrorBoundary.js`
- `frontend/src/components/LocationPicker.js`
- `frontend/tailwind.config.js`
- `frontend/package.json`

---

## 2) Runtime Architecture

### 2.1 App shell and wiring
- Entry point is `src/index.js`.
- `React.StrictMode` mounts `App`.
- Global axios defaults are set in `index.js` from `config.js`:
  - `axios.defaults.baseURL = BACKEND_URL`
  - session-auth is the default runtime path
  - browser-exposed `X-API-Key` fallback stays disabled unless `REACT_APP_ALLOW_LEGACY_API_KEY=1`
- `App.js` creates a Socket.IO client (`io(BACKEND_URL)`) and emits `subscribe_telemetry` on connect.
- `DroneProvider` wraps the app and exposes fleet state/actions to all routes.

### 2.2 Routes
`App.js` defines route mapping:
- `/` → `Dashboard`
- `/map` → `DroneMap`
- `/drones` → `DroneList`
- `/missions` → `MissionControl`
- `/analytics` → `Analytics`
- `/settings` → `Settings`

### 2.3 Persistent shell modules
Always mounted in `App.js`:
- `Header` (top bar, theme toggle, emergency action visibility)
- `Sidebar` (nav + system summary)
- `DiagnosticTerminal` (bottom panel, collapsible)
- `HealthStatusIndicator` (fixed status chip)

### 2.4 Error containment
- Routed content is wrapped by `ErrorBoundary`.
- Failure inside route content shows local recovery UI without killing the whole app shell.

---

## 3) Global State: DroneContext

File: `src/context/DroneContext.js`

### 3.1 State model
- `drones`: live fleet array
- `selectedDrone`: currently selected drone object
- `loading`, `error`
- `telemetry`: last socket telemetry payload
- `fleetStatus`: aggregate counters (`total`, `armed`, `flying`, `low_battery`)

### 3.2 Reducer actions
- `SET_LOADING`, `SET_ERROR`
- `SET_DRONES`, `ADD_DRONE`, `UPDATE_DRONE`, `REMOVE_DRONE`
- `SELECT_DRONE`
- `UPDATE_TELEMETRY`, `UPDATE_FLEET_STATUS`

### 3.3 Demo drone sanitization
- `isDemoDrone()` + `sanitizeDrones()` remove IDs prefixed with `LESNAR-DEMO-`.
- Applied on REST fetch and socket telemetry updates.

### 3.4 Polling and realtime strategy
- Polls `/api/drones` every 5s via `fetchDrones()`.
- Accepts socket push via `updateTelemetry()`.
- `updateTelemetry()` also updates `fleetStatus` when present.

### 3.5 Exposed action API
REST-backed actions:
- `createDrone`, `deleteDrone`
- `armDrone`, `disarmDrone`
- `takeoffDrone`, `landDrone`
- `gotoDrone`
- `executeMission`
- `emergencyLandAll`
- plus `fetchDrones`, `updateTelemetry`, `selectDrone`, `clearError`

---

## 4) Shared Drone State Semantics

File: `src/utils/droneState.js`

### 4.1 `getDroneFlags(drone)`
Normalizes and infers:
- `altitude`, `speed`, `battery`, `armed`, `mode`
- `flying` inferred from:
  - altitude > 1.0 OR
  - mode implies flight (`TAKEOFF`, `OFFBOARD`, `MISSION`, `AUTO`, `LOITER`, `HOLD`, `RTL`) OR
  - armed + moving (speed > 0.8)

### 4.2 `getDroneStatus(drone)`
Returns standardized UI status object:
- `LOW POWER`, `AIRBORNE`, `ARMED`, or `STANDBY`
- includes tokenized dot/text classes used by list/map/dashboard cards.

### 4.3 Adoption
Used in:
- `Header`
- `Sidebar`
- `Dashboard`
- `DroneList`
- `DroneMap`
- `MissionControl`
- `Analytics`

---

## 5) Component Reference

## 5.1 `Header.js`
Responsibilities:
- Top nav branding + connection status.
- Alert button routes to analytics.
- Theme toggle (light/dark).
- Global emergency kill button shown only when at least one drone is armed/flying.

Inputs:
- `onMenuClick`, `connected`, `themeMode`, `onThemeToggle`.

Data dependencies:
- `useDrones()` for `drones` and low battery count.

Behavior:
- `actionableCount` computed from `getDroneFlags`.
- Emergency POST to `/api/emergency` only if user confirms.

## 5.2 `Sidebar.js`
Responsibilities:
- Route navigation.
- Health heartbeat from `/api/health` every 10s.
- Fleet load meter using flying/total ratio.

Data dependencies:
- `useDrones()` for drones.
- `getDroneFlags()` for flying count.

## 5.3 `Dashboard.js`
Responsibilities:
- Fleet KPI overview and tactical cards.
- Recharts propulsion trend panel.
- Integrity/readiness visual bars.
- Priority alerts from low battery drones.

Realtime:
- listens to `telemetry_update` socket event and calls `updateTelemetry`.

Notes:
- Drone card status and metrics use `getDroneFlags` for consistency.

## 5.4 `DroneMap.js`
Responsibilities:
- Main tactical map with drone markers and obstacle overlays.
- Auto-follow bounds or manual selected drone focus.
- Right-side HUD list with per-drone quick status.

Data:
- `useDrones()` for drones + telemetry update.
- loads obstacles from `/api/obstacles`.

Map details:
- Uses Leaflet + Carto dark tiles.
- Marker icon is custom SVG via `L.divIcon` with heading rotation and critical pulse.

## 5.5 `DroneList.js`
Responsibilities:
- Fleet list, search/filter, per-drone command center, telemetry panel.

Key UX logic:
- Control buttons are contextual:
  - show `ARM` only when not armed
  - show `TAKEOFF` only when armed + not flying
  - show `LAND` only when flying
  - show `DISARM` only when armed + not flying
- `INITIATE GOTO` only shows when selected drone is armed or flying.
- Emergency recall button shows only when actionable drones exist.
- Uses shared `getDroneFlags`/`getDroneStatus` everywhere possible.

## 5.6 `MissionControl.js`
Responsibilities:
- Mission planning map (click-to-add waypoints).
- Pattern generation (`ORBIT`, `SWEEP`).
- Mission execute and auto-launch flow.
- Active missions polling (`/api/missions/active` every 10s).

Key UX gating:
- Mission deployment button appears only when waypoints exist.
- Auto-launch + mission button appears only when:
  - waypoints exist,
  - a drone is selected,
  - selected drone is armed,
  - selected drone is not already flying.

## 5.7 `Analytics.js`
Responsibilities:
- Telemetry history chart.
- Readiness matrix.
- Segmentation log table from `/api/logs/segmentation/latest`.

Realtime:
- listens to `telemetry_update`; stores rolling window of last 40 points.

Flight logic:
- Active sortie metrics now use `getDroneFlags(...).flying`.

## 5.8 `Settings.js`
Responsibilities:
- Read/write backend config via:
  - GET `/api/config`
  - POST `/api/config`
- Maps backend config schema into UI state and back.

Important mapping:
- Persists `autoLandBattery` to `drone_settings.auto_land_battery`.

## 5.9 `DiagnosticTerminal.js`
Responsibilities:
- Bottom live console panel with boot sequence + socket event logs.

Socket streams consumed:
- `telemetry_update`
- `drone_status`
- `mission_update`

Behavior:
- Keeps max 100 lines.
- Autoscroll to newest log.

## 5.10 `HealthStatusIndicator.js`
Responsibilities:
- Global compact health chip.
- Polls `/api/health` every 10s.
- Displays backend link state, uptime, ML model readiness, and shield state.

## 5.11 `ErrorBoundary.js`
Responsibilities:
- Catches runtime render errors in child tree.
- Displays recoverable fallback panel.

## 5.12 `LocationPicker.js`
Responsibilities:
- Generic geospatial picker component (currently utility-level, not primary route).
- Supports local presets and backend geocode suggestions (`/api/geocode/suggest`).
- Confirm callback returns `{ lat, lng, label }`.

---

## 6) Networking and API Layer

### 6.1 `config.js`
- Resolves backend URL from:
  1. `REACT_APP_BACKEND_URL`
  2. `REACT_APP_API_BASE_URL`
  3. fallback: `http://localhost:5000` on localhost, otherwise `/api`
- Exposes `SESSION_AUTH_REQUIRED` from env.
- Exposes `API_KEY` only when `REACT_APP_ALLOW_LEGACY_API_KEY=1`.

### 6.2 `api.js`
- Axios instance with JSON.
- Sends `Authorization: Bearer ...` when session login is active.
- Only falls back to `X-API-Key` if legacy fallback is explicitly enabled.
- Response interceptor logs API failures to console and rethrows.

### 6.3 APIs referenced in frontend
- `/api/drones`
- `/api/drones/:id` (delete)
- `/api/drones/:id/arm`
- `/api/drones/:id/disarm`
- `/api/drones/:id/takeoff`
- `/api/drones/:id/land`
- `/api/drones/:id/goto`
- `/api/drones/:id/mission`
- `/api/emergency`
- `/api/health`
- `/api/obstacles`
- `/api/missions/active`
- `/api/logs/segmentation/latest`
- `/api/config`
- `/api/geocode/suggest`

---

## 7) Styling and Theming

### 7.1 Tailwind config
File: `tailwind.config.js`
- Custom palette: `navy-black`, `lesnar-accent`, `lesnar-danger`, `lesnar-warning`, `lesnar-success`.
- Custom shadows, animations, and keyframes used across tactical UI.

### 7.2 Global CSS split
- `index.css`: Tailwind layers + base/body sizing + shared glass utility classes.
- `App.css`: tactical overlays, custom scrollbar, map filters, animations, readability hardening.

### 7.3 Theme mode
Implemented in `App.js` and `App.css`:
- persisted key: `lesnar.ui.theme` in local storage.
- root class toggles `theme-dark` or `theme-light`.
- light mode overrides tactical backgrounds, text contrast, borders, glass surfaces, and map filter.

---

## 8) UX Rules Implemented

- Demo placeholders are sanitized from frontend state.
- Emergency controls are contextual (only shown when actionable).
- Drone command controls are contextual by state.
- Mission controls hide until preconditions are valid.
- Small-text readability baseline increased (`8-10px` classes normalized to readable minimum).
- Gray contrast increased for low-visibility labels.

---

## 9) Build/Run

From `frontend/`:
- Dev: `npm start`
- Prod build: `npm run build`
- Test: `npm test`

Current dependency/runtime profile is CRA (`react-scripts@5`), React 18, Tailwind 3, Socket.IO client, Leaflet, Recharts.

---

## 10) Integration Notes

- Frontend expects backend socket and REST endpoints to be live and aligned.
- Fleet behavior is robust against stale socket state because of 5-second REST refresh in `DroneContext`.
- For operator realism, all status-driven UI should continue using `getDroneFlags/getDroneStatus` to avoid drift between pages.
