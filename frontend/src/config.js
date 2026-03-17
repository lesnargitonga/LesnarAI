const ENV_BACKEND_URL = String(process.env.REACT_APP_BACKEND_URL || '').trim();
const ENV_API_BASE_URL = String(process.env.REACT_APP_API_BASE_URL || '').trim();
const runtimeHost = window.location.hostname;
const runtimeProtocol = window.location.protocol;
const runtimePort = window.location.port;
const backendPort = String(process.env.REACT_APP_BACKEND_PORT || '5000').trim();
const isDev = process.env.NODE_ENV === 'development';
const useDevProxy = isDev && !ENV_BACKEND_URL && !ENV_API_BASE_URL;

const inferredBackendUrl = `${runtimeProtocol}//${runtimeHost}${backendPort ? `:${backendPort}` : ''}`;
const sameOriginIsBackend = runtimePort === backendPort;

export const BACKEND_URL = String(
  ENV_BACKEND_URL || (useDevProxy ? window.location.origin : (sameOriginIsBackend ? window.location.origin : inferredBackendUrl))
).replace(/\/$/, '');

export const API_BASE_URL = String(
  ENV_API_BASE_URL || (useDevProxy ? '' : BACKEND_URL)
).replace(/\/$/, '');

export const SESSION_AUTH_REQUIRED = process.env.REACT_APP_REQUIRE_SESSION_AUTH === '1';

export const ALLOW_LEGACY_API_KEY = process.env.REACT_APP_ALLOW_LEGACY_API_KEY === '1';

export const API_KEY = ALLOW_LEGACY_API_KEY ? (process.env.REACT_APP_API_KEY || '').trim() : '';

export const MAP_TILE_URL = String(
  process.env.REACT_APP_MAP_TILE_URL || ''
).trim();

export const MAP_TILE_ATTRIBUTION = String(
  process.env.REACT_APP_MAP_TILE_ATTRIBUTION || 'Local tactical tiles'
).trim();

export const MAP_TILE_FALLBACK_URL = String(
  process.env.REACT_APP_MAP_TILE_FALLBACK_URL || 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
).trim();

export const OPERATIONAL_BOUNDARY = (() => {
  try {
    const raw = process.env.REACT_APP_OPERATIONAL_BOUNDARY;
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
})();
