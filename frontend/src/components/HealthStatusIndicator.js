import React, { useState, useEffect } from 'react';
import api from '../api';
import {
  Wifi,
  WifiOff,
  Clock,
  Cpu,
  ShieldCheck,
  ShieldAlert,
  Activity,
  Shield,
  CheckCircle,
  AlertTriangle,
  AlertCircle
} from 'lucide-react';
import { BACKEND_URL } from '../config';

const HealthStatusIndicator = () => {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await api.get('/api/health');
        setHealth(response.data);
        setError(null);
      } catch (err) {
        setError(`Link_Severed`);
        setHealth(null);
      }
    };

    fetchHealth();
    const intervalId = setInterval(fetchHealth, 10000);
    return () => clearInterval(intervalId);
  }, []);

  const getStatusColor = () => {
    if (error || !health || health.status !== 'ok') return 'text-lesnar-danger border-lesnar-danger/30 bg-lesnar-danger/5';
    if (health.segmentation?.enabled && !health.segmentation?.model_exists) return 'text-lesnar-warning border-lesnar-warning/30 bg-lesnar-warning/5';
    return 'text-lesnar-success border-lesnar-success/30 bg-lesnar-success/5';
  };

  const getIndicatorColor = () => {
    if (error || !health || health.status !== 'ok') return 'bg-lesnar-danger shadow-[0_0_10px_rgba(255,0,85,0.8)]';
    if (health.segmentation?.enabled && !health.segmentation?.model_exists) return 'bg-lesnar-warning shadow-[0_0_10px_rgba(255,184,0,0.8)]';
    return 'bg-lesnar-success shadow-[0_0_10px_rgba(0,255,148,0.8)]';
  };

  const formatUptime = (seconds) => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    const hours = Math.floor(seconds / 3600);
    return `${hours}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  return (
    <div className={`glass-dark border px-4 py-2 rounded-full flex items-center space-x-4 transition-all duration-500 shadow-2xl ${getStatusColor()}`}>
      <div className={`h-2 w-2 rounded-full animate-pulse mr-1 ${getIndicatorColor()}`} />

      <div className="flex items-center space-x-3 divide-x divide-white/10 uppercase font-mono text-[9px] font-bold tracking-widest">
        <div className="flex items-center group cursor-help" title={`Backend: ${BACKEND_URL} | DB: ${health?.db_connected ? 'Connected' : 'Disconnected'}`}>
          {error ? <WifiOff className="h-3 w-3 mr-1.5" /> : <Wifi className="h-3 w-3 mr-1.5" />}
          {health ? 'Link_Active' : 'Offline'}
        </div>

        {health && (
          <>
            <div className="flex items-center pl-3" title="Operational Uptime">
              <Clock className="h-3 w-3 mr-1.5 opacity-50" />
              {formatUptime(health.uptime_seconds)}
            </div>

            <div className="flex items-center pl-3" title="ML Intelligence Layer">
              <Cpu className="h-3 w-3 mr-1.5 opacity-50" />
              {health.segmentation?.model_exists ?
                <span className="text-lesnar-success">Neural_Ok</span> :
                <span className="text-lesnar-warning">Neural_Fail</span>
              }
            </div>
          </>
        )}

        {!health && error && (
          <div className="pl-3 animate-pulse text-lesnar-danger">
            {error}
          </div>
        )}
      </div>

      <div className="pl-2 border-l border-white/10">
        {health?.status === 'ok' ? (
          <ShieldCheck className="h-3 w-3 text-lesnar-success" />
        ) : (
          <ShieldAlert className="h-3 w-3 text-lesnar-danger animate-bounce" />
        )}
      </div>
    </div>
  );
};

export default HealthStatusIndicator;
