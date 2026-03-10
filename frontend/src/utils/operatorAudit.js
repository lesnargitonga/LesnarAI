const STORAGE_KEY = 'lesnar.operator.audit';
const SESSION_KEY = 'lesnar.session';
const OPERATOR_ID_KEY = 'lesnar.operator.id';
const MAX_ENTRIES = 200;
const EVENT_NAME = 'lesnar:operator-audit';

function getSession() {
  try {
    return JSON.parse(window.sessionStorage.getItem(SESSION_KEY) || 'null');
  } catch {
    return null;
  }
}

export function getOperatorIdentity() {
  const session = getSession();
  let operatorId = session?.userId || window.localStorage.getItem(OPERATOR_ID_KEY);
  if (!operatorId) {
    operatorId = `LOCAL-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
    window.localStorage.setItem(OPERATOR_ID_KEY, operatorId);
  }
  return {
    operatorId,
    role: session?.role || 'operator',
    sessionId: session?.sessionId || 'local-session',
    token: session?.token || '',
  };
}

export function readOperatorAuditLog() {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    return [];
  }
}

export function appendOperatorAudit(entry) {
  const actor = getOperatorIdentity();
  const record = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: new Date().toISOString(),
    actor,
    ...entry,
  };
  const next = [...readOperatorAuditLog(), record].slice(-MAX_ENTRIES);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: record }));
  return record;
}

export function subscribeOperatorAudit(listener) {
  const handler = (event) => listener(event.detail);
  window.addEventListener(EVENT_NAME, handler);
  return () => window.removeEventListener(EVENT_NAME, handler);
}

export function requireTypedConfirmation(message, phrase = 'CONFIRM') {
  const value = window.prompt(`${message}\nType ${phrase} to continue.`);
  return value === phrase;
}
