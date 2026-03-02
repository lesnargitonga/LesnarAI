import React from 'react';
import ReactDOM from 'react-dom/client';
import axios from 'axios';
import './index.css';
import App from './App';

import { BACKEND_URL, API_KEY } from './config';

// Ensure REST calls hit the backend even when the frontend is not using CRA proxy.
axios.defaults.baseURL = BACKEND_URL;
if (API_KEY) {
  axios.defaults.headers.common['X-API-Key'] = API_KEY;
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
