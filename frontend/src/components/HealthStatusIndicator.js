import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Wifi, WifiOff, Server, Clock, Cpu, FileCheck, FileX } from 'lucide-react';
import { BACKEND_URL } from '../config';

const HealthStatusIndicator = () => {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await axios.get('/api/health');
        setHealth(response.data);
        setError(null);
      } catch (err) {
        setError(`Backend offline (${BACKEND_URL}). Run .\\start_everything.ps1`);
        setHealth(null);
      }
    };

    fetchHealth();
    const intervalId = setInterval(fetchHealth, 15000); // Poll every 15 seconds

    return () => clearInterval(intervalId);
  }, []);

  const getStatusColor = () => {
    if (error || !health || health.status !== 'ok') return 'bg-red-600';
    if (health.segmentation?.enabled && !health.segmentation?.model_exists) return 'bg-yellow-500';
    return 'bg-green-600';
  };

  const StatusIcon = () => {
    if (error || !health) return <WifiOff className="h-4 w-4" />;
    return <Wifi className="h-4 w-4" />;
  };

  const formatUptime = (seconds) => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  return (
    <div className={`fixed bottom-4 right-4 text-white text-xs p-2 rounded-lg shadow-lg flex items-center space-x-2 ${getStatusColor()}`}>
      <StatusIcon />
      {health && health.status === 'ok' ? (
        <div className="flex items-center space-x-2">
          <div className="flex items-center" title="Backend Status: OK">
            <Server className="h-3 w-3 mr-1" /> OK
          </div>
          <div className="flex items-center" title={`Uptime: ${formatUptime(health.uptime_seconds)}`}>
            <Clock className="h-3 w-3 mr-1" /> {formatUptime(health.uptime_seconds)}
          </div>
          {health.segmentation?.enabled && (
            <div className="flex items-center" title={`Segmentation Model: ${health.segmentation.model_path}`}>
              <Cpu className="h-3 w-3 mr-1" />
              {health.segmentation.model_exists ? <FileCheck className="h-3 w-3" /> : <FileX className="h-3 w-3" />}
            </div>
          )}
        </div>
      ) : (
        <span>{error || 'Connecting...'}</span>
      )}
    </div>
  );
};

export default HealthStatusIndicator;
