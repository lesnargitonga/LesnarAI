const SESSION_KEY = 'lesnar.session';
const SESSION_EVENT = 'lesnar:session-changed';

function emitSessionChange(session) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: session || null }));
}

export function getStoredSession() {
  try {
    return JSON.parse(window.sessionStorage.getItem(SESSION_KEY) || 'null');
  } catch {
    return null;
  }
}

export function storeSession(session) {
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  emitSessionChange(session);
}

export function clearSession() {
  window.sessionStorage.removeItem(SESSION_KEY);
  emitSessionChange(null);
}

export function sessionAuthRequired() {
  return process.env.REACT_APP_REQUIRE_SESSION_AUTH !== '0';
}

export function subscribeSession(listener) {
  if (typeof window === 'undefined') return () => {};
  const handler = (event) => listener(event?.detail ?? getStoredSession());
  window.addEventListener(SESSION_EVENT, handler);
  return () => window.removeEventListener(SESSION_EVENT, handler);
}
