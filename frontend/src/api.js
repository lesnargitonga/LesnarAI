import axios from 'axios';
import { BACKEND_URL, API_KEY } from './config';

const api = axios.create({
    baseURL: BACKEND_URL,
    headers: {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json',
    },
});

// Response interceptor for global error handling
api.interceptors.response.use(
    (response) => response,
    (error) => {
        console.error(`[API_ERROR] ${error.config?.url}:`, error.response?.data || error.message);
        return Promise.reject(error);
    }
);

export default api;
