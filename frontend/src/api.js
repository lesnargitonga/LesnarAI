import axios from 'axios';
import { API_BASE_URL, API_KEY } from './config';
import { getOperatorIdentity } from './utils/operatorAudit';

export function getApiErrorMessage(error, fallback = 'Request failed.') {
    const status = error?.response?.status;
    const payload = error?.response?.data;
    const serverMessage = payload?.message || payload?.error;

    if (serverMessage) {
        return String(serverMessage);
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
        error.message = getApiErrorMessage(error, error.message || 'Request failed.');
        console.error(`[API_ERROR] ${error.config?.url}:`, error.response?.data || error.message);
        return Promise.reject(error);
    }
);

export default api;
