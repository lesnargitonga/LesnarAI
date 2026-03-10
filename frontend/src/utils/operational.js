export const TELEMETRY_STALE_MS = Number(process.env.REACT_APP_TELEMETRY_STALE_MS || 7000);
export const DEGRADED_LATENCY_MS = Number(process.env.REACT_APP_DEGRADED_LATENCY_MS || 1200);
export const DEGRADED_TELEMETRY_MS = Number(process.env.REACT_APP_DEGRADED_TELEMETRY_MS || 4000);

function parseTimestamp(ts) {
  if (!ts) return null;
  const value = new Date(ts).getTime();
  return Number.isFinite(value) ? value : null;
}

export function getTelemetryAgeMs(drone, now = Date.now()) {
  const ts = parseTimestamp(drone?.timestamp);
  if (ts == null) return Number.POSITIVE_INFINITY;
  return Math.max(0, now - ts);
}

export function isTelemetryStale(drone, now = Date.now(), thresholdMs = TELEMETRY_STALE_MS) {
  return getTelemetryAgeMs(drone, now) > thresholdMs;
}

export function getTelemetryFreshness(drone, now = Date.now()) {
  const ageMs = getTelemetryAgeMs(drone, now);
  if (!Number.isFinite(ageMs)) return { ageMs, label: 'NO FEED', color: 'text-lesnar-danger' };
  if (ageMs > TELEMETRY_STALE_MS) return { ageMs, label: 'STALE', color: 'text-lesnar-danger' };
  if (ageMs > TELEMETRY_STALE_MS / 2) return { ageMs, label: 'AGING', color: 'text-lesnar-warning' };
  return { ageMs, label: 'FRESH', color: 'text-lesnar-success' };
}

export function getLinkMode({ connected, latencyMs, telemetryAgeMs }) {
  if (!connected) return { key: 'lost', label: 'LINK LOST', degraded: true };
  if ((latencyMs || 0) > DEGRADED_LATENCY_MS || (telemetryAgeMs || 0) > DEGRADED_TELEMETRY_MS) {
    return { key: 'degraded', label: 'DEGRADED', degraded: true };
  }
  return { key: 'nominal', label: 'NOMINAL', degraded: false };
}

export function safeJsonParse(raw, fallback) {
  try {
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

export function pointInPolygon(point, polygon) {
  const [x, y] = point;
  if (!Array.isArray(polygon) || polygon.length < 3) return true;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    const intersect = ((yi > y) !== (yj > y))
      && (x < ((xj - xi) * (y - yi)) / ((yj - yi) || Number.EPSILON) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

export function normalizeBoundary(boundary) {
  if (!Array.isArray(boundary)) return [];
  return boundary
    .filter((pair) => Array.isArray(pair) && pair.length >= 2)
    .map(([lat, lng]) => [Number(lat), Number(lng)])
    .filter(([lat, lng]) => Number.isFinite(lat) && Number.isFinite(lng));
}
