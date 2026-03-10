const SESSION_KEY = 'lesnar.session';

export function getStoredSession() {
  try {
    return JSON.parse(window.sessionStorage.getItem(SESSION_KEY) || 'null');
  } catch {
    return null;
  }
}

export function storeSession(session) {
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  window.sessionStorage.removeItem(SESSION_KEY);
}

export function sessionAuthRequired() {
  return process.env.REACT_APP_REQUIRE_SESSION_AUTH !== '0';
}
