import React from 'react';
import ReactDOM from 'react-dom/client';
import axios from 'axios';
import './index.css';
import App from './App';

import { BACKEND_URL } from './config';

// Ensure REST calls hit the backend even when the frontend is not using CRA proxy.
axios.defaults.baseURL = BACKEND_URL;

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
