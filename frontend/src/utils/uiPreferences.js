const STORAGE_KEY = 'lesnar.ui.preferences';

export const DEFAULT_UI_PREFERENCES = {
  mapProvider: 'carto-dark',
  defaultZoom: 12,
  showFlightPaths: true,
  enableNotifications: true,
};

export function readUiPreferences() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return { ...DEFAULT_UI_PREFERENCES, ...(parsed || {}) };
  } catch {
    return { ...DEFAULT_UI_PREFERENCES };
  }
}

export function writeUiPreferences(next) {
  const merged = { ...DEFAULT_UI_PREFERENCES, ...(next || {}) };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  window.dispatchEvent(new CustomEvent('lesnar:ui-preferences', { detail: merged }));
  return merged;
}

export function getMapTileProfile(provider) {
  switch (provider) {
    case 'stamen-toner':
      return {
        url: 'https://stamen-tiles.a.ssl.fastly.net/toner/{z}/{x}/{y}.png',
        attribution: 'Stamen Toner',
      };
    case 'osm-standard':
      return {
        url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attribution: 'OpenStreetMap',
      };
    case 'carto-dark':
    default:
      return {
        url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        attribution: 'CARTO Dark',
      };
  }
}