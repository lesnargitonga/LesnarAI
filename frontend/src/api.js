import axios from 'axios';
import { API_BASE_URL, API_KEY } from './config';
import { getOperatorIdentity } from './utils/operatorAudit';
import { clearSession } from './utils/sessionAuth';

export function getApiErrorMessage(error, fallback = 'Request failed.') {
    const status = error?.response?.status;
    const payload = error?.response?.data;
    const serverMessage = payload?.message || payload?.error;
    const plainMessage = typeof error?.message === 'string' ? error.message.trim() : '';

    if (serverMessage) {
        return String(serverMessage);
    }
    if (plainMessage && plainMessage !== 'Network Error') {
        return plainMessage;
    }
    if (status === 401) {
        return 'Your session has expired. Please sign in again.';
    }
    if (status === 403) {
        return 'You do not have permission to access this part of the system.';
    }
    if (status === 404) {
        return 'The requested service is currently unavailable.';
    }
    if (status === 503) {
        return 'The control service is not ready yet. Start the runtime and try again.';
    }
    if (!error?.response) {
        return 'Unable to reach the backend. Check that the backend and frontend are running.';
    }
    return fallback;
}

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

const ORCHESTRATOR_BASE_URL = process.env.REACT_APP_ORCHESTRATOR_URL || 'http://127.0.0.1:8765';

function orchFetch(url, options = {}, timeoutMs = 10000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer));
}

export async function orchestratorStatus() {
    const res = await orchFetch(`${ORCHESTRATOR_BASE_URL}/status`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
        throw new Error('Runtime orchestrator status check failed');
    }
    return res.json();
}

export async function orchestratorModels() {
    const res = await orchFetch(`${ORCHESTRATOR_BASE_URL}/models`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
        throw new Error('Runtime orchestrator model listing failed');
    }
    return res.json();
}

export async function orchestratorLaunchAll(droneCount = 1, teacherArgs = null, options = {}) {
    const { gzHeadless } = options;
    const res = await orchFetch(`${ORCHESTRATOR_BASE_URL}/launch-all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            drone_count: droneCount,
            ...(Array.isArray(teacherArgs) && teacherArgs.length ? { teacher_args: teacherArgs } : {}),
            ...(typeof gzHeadless === 'boolean' ? { gz_headless: gzHeadless } : {})
        })
    }, 30000);
    if (!res.ok) {
        throw new Error('Runtime orchestrator launch failed');
    }
    return res.json();
}

export async function orchestratorKillAll() {
    const res = await orchFetch(`${ORCHESTRATOR_BASE_URL}/kill-all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
        throw new Error('Runtime orchestrator kill failed');
    }
    return res.json();
}

export async function orchestratorStartTraining({ epochs = 20, batchSize = 128, csvIndex = 0 } = {}) {
    const res = await orchFetch(`${ORCHESTRATOR_BASE_URL}/train/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            epochs,
            batch_size: batchSize,
            csv_index: csvIndex,
        }),
    }, 30000);
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
        const msg = payload?.error || payload?.message || 'Runtime orchestrator training start failed';
        throw new Error(String(msg));
    }
    return payload;
}

api.interceptors.request.use((config) => {
    const actor = getOperatorIdentity();
    config.headers = config.headers || {};
    if (actor.token) {
        config.headers.Authorization = `Bearer ${actor.token}`;
    } else if (API_KEY) {
        config.headers['X-API-Key'] = API_KEY;
    }
    config.headers['X-Operator-Id'] = actor.operatorId;
    config.headers['X-Operator-Role'] = actor.role;
    config.headers['X-Session-Id'] = actor.sessionId;

    if (config.data && typeof config.data === 'object' && !Array.isArray(config.data)) {
        config.data = {
            ...config.data,
            operator_context: {
                operator_id: actor.operatorId,
                role: actor.role,
                session_id: actor.sessionId,
            },
        };
    }
    return config;
});

// Response interceptor for global error handling
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error?.response?.status === 401) {
            clearSession();
        }
        error.message = getApiErrorMessage(error, error.message || 'Request failed.');
        console.error(`[API_ERROR] ${error.config?.url}:`, error.response?.data || error.message);
        return Promise.reject(error);
    }
);

export default api;
