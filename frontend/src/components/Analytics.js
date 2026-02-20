import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { TrendingUp, Activity, Clock, Shield, Compass, Radio } from 'lucide-react';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { useDrones } from '../context/DroneContext';

function Analytics({ socket }) {
  const { drones, updateTelemetry } = useDrones();
  const [segLog, setSegLog] = useState({ file: null, rows: [] });
  const [healthData, setHealthData] = useState(null);
  const [error, setError] = useState(null);
  const [telemetryHistory, setTelemetryHistory] = useState([]);
  const [sessionStart] = useState(Date.now());

  // Subscribe to live telemetry for the chart
  useEffect(() => {
    if (!socket) return;
    const handler = (data) => {
      updateTelemetry(data);
      const ts = new Date();
      setTelemetryHistory(prev => {
        const next = [
          ...prev,
          {
            time: ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            activeDrones: data.fleet_status?.flying_drones || 0,
            totalDrones: data.fleet_status?.total_drones || 0,
            avgBattery: data.telemetry?.length
              ? Math.round(data.telemetry.reduce((s, d) => s + (d.battery || 0), 0) / data.telemetry.length)
              : 0,
          },
        ];
        // Keep last 60 data points (~60 seconds at 1 update/sec visual throttle)
        return next.slice(-60);
      });
    };
    socket.on('telemetry_update', handler);
    return () => socket.off('telemetry_update', handler);
  }, [socket, updateTelemetry]);

  // Fetch backend health for uptime
  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await axios.get('/api/health');
        setHealthData(res.data);
      } catch {
        setHealthData(null);
      }
    };
    fetchHealth();
    const id = setInterval(fetchHealth, 15000);
    return () => clearInterval(id);
  }, []);

  // Load segmentation log
  useEffect(() => {
    const loadSegmentationLog = async () => {
      setError(null);
      try {
        const res = await axios.get('/api/logs/segmentation/latest');
        if (res.data?.success && Array.isArray(res.data.rows)) {
          setSegLog({ file: res.data.file, rows: res.data.rows });
        } else {
          setError(res.data?.error || 'No segmentation logs found');
        }
      } catch {
        setError('Segmentation log unavailable');
      }
    };
    loadSegmentationLog();
  }, []);

  // --- Derived live metrics ---
  const flyingDrones = drones.filter(d => d.altitude > 1.0);
  const armedDrones = drones.filter(d => d.armed);
  const avgBattery = drones.length
    ? Math.round(drones.reduce((s, d) => s + (d.battery || 0), 0) / drones.length)
    : 0;
  const lowBatteryCount = drones.filter(d => d.battery < 20).length;
  const avgSpeed = flyingDrones.length
    ? (flyingDrones.reduce((s, d) => s + (d.speed || 0), 0) / flyingDrones.length).toFixed(1)
    : '0.0';
  const sessionMinutes = Math.round((Date.now() - sessionStart) / 60000);
  const uptimeStr = healthData?.uptime_seconds
    ? formatUptime(healthData.uptime_seconds)
    : '--';

  // Sort drones by performance (battery + speed composite)
  const rankedDrones = [...drones]
    .map(d => ({
      ...d,
      score: Math.round(d.battery * 0.6 + Math.min(d.speed * 5, 40) * 0.4),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  // Live alerts from fleet state
  const alerts = generateAlerts(drones);

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
        <p className="mt-1 text-sm text-gray-600">
          Live fleet performance metrics and system insights
        </p>
      </div>

      {/* Key Metrics — Live */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <MetricCard
          title="Active Drones"
          value={`${flyingDrones.length} / ${drones.length}`}
          subtitle={`${armedDrones.length} armed`}
          icon={Compass}
          color="blue"
        />
        <MetricCard
          title="Avg Battery"
          value={`${avgBattery}%`}
          subtitle={lowBatteryCount > 0 ? `${lowBatteryCount} low` : 'All healthy'}
          icon={Activity}
          color={avgBattery > 50 ? 'green' : avgBattery > 20 ? 'yellow' : 'red'}
        />
        <MetricCard
          title="Avg Speed"
          value={`${avgSpeed} m/s`}
          subtitle={`${flyingDrones.length} in flight`}
          icon={TrendingUp}
          color="purple"
        />
        <MetricCard
          title="System Uptime"
          value={uptimeStr}
          subtitle={`Session: ${sessionMinutes}m`}
          icon={Clock}
          color="green"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Live Telemetry Chart */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-lg font-semibold mb-4">Live Fleet Activity</h2>
          {telemetryHistory.length > 2 ? (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={telemetryHistory}>
                <defs>
                  <linearGradient id="colorActive" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorBattery" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10B981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Area type="monotone" dataKey="activeDrones" name="Flying" stroke="#3B82F6" fill="url(#colorActive)" strokeWidth={2} />
                <Area type="monotone" dataKey="avgBattery" name="Avg Battery %" stroke="#10B981" fill="url(#colorBattery)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-400">
              <div className="text-center">
                <Radio className="h-8 w-8 mx-auto mb-2 animate-pulse" />
                <p className="text-sm">Collecting telemetry data...</p>
              </div>
            </div>
          )}
        </div>

        {/* Fleet Health — Live */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-lg font-semibold mb-4">Fleet Health Status</h2>
          <div className="space-y-4">
            <HealthItem
              label="Battery Health"
              value={avgBattery}
              color={avgBattery > 60 ? 'green' : avgBattery > 30 ? 'yellow' : 'red'}
            />
            <HealthItem
              label="Fleet Coverage"
              value={drones.length > 0 ? Math.round((flyingDrones.length / drones.length) * 100) : 0}
              color={flyingDrones.length > 0 ? 'green' : 'yellow'}
            />
            <HealthItem
              label="Communication Link"
              value={healthData?.status === 'ok' ? 100 : 0}
              color={healthData?.status === 'ok' ? 'green' : 'red'}
            />
            <HealthItem
              label="Armed Readiness"
              value={drones.length > 0 ? Math.round((armedDrones.length / drones.length) * 100) : 0}
              color={armedDrones.length > 0 ? 'green' : 'yellow'}
            />
            <HealthItem
              label="Sensor Systems"
              value={healthData?.features?.computer_vision ? 95 : 75}
              color="green"
            />
          </div>
        </div>
      </div>

      {/* Segmentation Logs Summary */}
      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <h3 className="text-lg font-semibold mb-2">Latest Segmentation Log</h3>
        {error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : segLog.file ? (
          <div>
            <p className="text-sm text-gray-600 mb-2">File: {segLog.file}</p>
            <p className="text-sm text-gray-600 mb-4">Entries: {segLog.rows.length}</p>
            <div className="overflow-auto max-h-64 border rounded">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="bg-gray-50">
                    {Object.keys(segLog.rows[0] || {}).slice(0, 6).map(k => (
                      <th key={k} className="text-left px-3 py-2 font-medium text-gray-700">{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {segLog.rows.slice(0, 20).map((row, idx) => (
                    <tr key={idx} className="border-t">
                      {Object.keys(segLog.rows[0] || {}).slice(0, 6).map(k => (
                        <td key={k} className="px-3 py-2 text-gray-800">{String(row[k])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-600">No log data available</p>
        )}
      </div>

      {/* Bottom row: Rankings + Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        {/* Top Performing Drones — Live */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-lg font-semibold mb-4">Top Performing Drones</h3>
          {rankedDrones.length > 0 ? (
            <div className="space-y-3">
              {rankedDrones.map((d, i) => (
                <DroneRanking key={d.drone_id} rank={i + 1} id={d.drone_id} score={`${d.score}%`} battery={d.battery} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">No drones registered</p>
          )}
        </div>

        {/* Mission Success — from fleet */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-lg font-semibold mb-4">Operational Status</h3>
          <div className="text-center">
            <div className={`text-3xl font-bold mb-2 ${healthData?.status === 'ok' ? 'text-green-600' : 'text-red-600'
              }`}>
              {healthData?.status === 'ok' ? 'OPERATIONAL' : 'DEGRADED'}
            </div>
            <p className="text-sm text-gray-600">System Status</p>
            <div className="mt-4 space-y-2 text-left text-sm">
              <StatusRow label="Backend" ok={healthData?.status === 'ok'} />
              <StatusRow label="Redis Bridge" ok={healthData?.status === 'ok'} />
              <StatusRow label="Database" ok={healthData?.status === 'ok'} />
              <StatusRow label="Computer Vision" ok={healthData?.features?.computer_vision} />
              <StatusRow label="Obstacle Avoidance" ok={healthData?.features?.obstacle_avoidance} />
            </div>
          </div>
        </div>

        {/* Live Alerts */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-lg font-semibold mb-4">Live Alerts</h3>
          {alerts.length > 0 ? (
            <div className="space-y-2">
              {alerts.map((a, i) => (
                <AlertItem key={i} type={a.type} message={a.message} time={a.time} />
              ))}
            </div>
          ) : (
            <div className="flex items-center space-x-2 text-green-600">
              <Shield className="h-5 w-5" />
              <span className="text-sm font-medium">All systems nominal</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Helper functions ---

function formatUptime(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

function generateAlerts(drones) {
  const alerts = [];
  const now = new Date();
  drones.forEach(d => {
    if (d.battery < 10) {
      alerts.push({ type: 'error', message: `${d.drone_id} CRITICAL battery (${Math.round(d.battery)}%)`, time: 'Now' });
    } else if (d.battery < 20) {
      alerts.push({ type: 'warning', message: `${d.drone_id} low battery (${Math.round(d.battery)}%)`, time: 'Now' });
    }
    if (d.mode === 'EMERGENCY') {
      alerts.push({ type: 'error', message: `${d.drone_id} in EMERGENCY mode`, time: 'Now' });
    }
  });
  if (drones.length > 0 && alerts.length === 0) {
    alerts.push({ type: 'success', message: 'All systems operational', time: now.toLocaleTimeString() });
  }
  return alerts.slice(0, 5);
}

// --- Sub-components ---

function MetricCard({ title, value, subtitle, icon: Icon, color }) {
  const colorMap = {
    blue: 'from-blue-500 to-blue-600',
    green: 'from-green-500 to-green-600',
    yellow: 'from-yellow-500 to-yellow-600',
    red: 'from-red-500 to-red-600',
    purple: 'from-purple-500 to-purple-600',
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 border-l-4 border-l-blue-500">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500 uppercase tracking-wide">{title}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
          {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
        </div>
        <div className={`h-12 w-12 rounded-lg bg-gradient-to-br ${colorMap[color] || colorMap.blue} flex items-center justify-center`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
      </div>
    </div>
  );
}

function HealthItem({ label, value, color }) {
  const colorClasses = {
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
  };

  return (
    <div className="flex items-center justify-between">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      <div className="flex items-center space-x-2">
        <div className="w-32 bg-gray-200 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-500 ${colorClasses[color]}`}
            style={{ width: `${Math.min(value, 100)}%` }}
          />
        </div>
        <span className="text-sm font-bold text-gray-900 w-12 text-right">{value}%</span>
      </div>
    </div>
  );
}

function DroneRanking({ rank, id, score, battery }) {
  const medalColors = ['text-yellow-500', 'text-gray-400', 'text-amber-600'];
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center space-x-3">
        <div className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${rank <= 3 ? 'bg-blue-100 ' + (medalColors[rank - 1] || 'text-blue-800') : 'bg-gray-100 text-gray-600'
          }`}>
          {rank}
        </div>
        <div>
          <span className="text-sm font-medium text-gray-900">{id}</span>
          <span className="text-xs text-gray-500 ml-2">{Math.round(battery)}% batt</span>
        </div>
      </div>
      <span className="text-sm font-bold text-green-600">{score}</span>
    </div>
  );
}

function StatusRow({ label, ok }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-gray-600">{label}</span>
      <span className={`font-medium ${ok ? 'text-green-600' : 'text-gray-400'}`}>
        {ok ? '● Online' : '○ Offline'}
      </span>
    </div>
  );
}

function AlertItem({ type, message, time }) {
  const typeClasses = {
    warning: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    info: 'bg-blue-100 text-blue-800 border-blue-200',
    success: 'bg-green-100 text-green-800 border-green-200',
    error: 'bg-red-100 text-red-800 border-red-200',
  };

  return (
    <div className="flex items-start space-x-2">
      <div className={`px-2 py-0.5 rounded text-xs font-semibold border ${typeClasses[type]}`}>
        {type.toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-900 truncate">{message}</p>
        <p className="text-xs text-gray-500">{time}</p>
      </div>
    </div>
  );
}

export default Analytics;
