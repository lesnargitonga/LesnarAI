import React, { useEffect, useState } from 'react';
import api from '../api';
import {
  TrendingUp,
  Activity,
  Clock,
  Shield,
  Compass,
  BarChart3,
  Zap,
  AlertCircle,
  Download,
  FileJson
} from 'lucide-react';
import { XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { useDrones } from '../context/DroneContext';
import { getDroneFlags } from '../utils/droneState';

function Analytics({ socket }) {
  const { drones, updateTelemetry } = useDrones();
  const [segLog, setSegLog] = useState({ file: null, rows: [] });
  const [healthData, setHealthData] = useState(null);
  const [error, setError] = useState(null);
  const [telemetryHistory, setTelemetryHistory] = useState([]);
  const [sessionStart] = useState(Date.now());

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
            avgBattery: data.telemetry?.length
              ? Math.round(data.telemetry.reduce((s, d) => s + (d.battery || 0), 0) / data.telemetry.length)
              : 0,
          },
        ];
        return next.slice(-40);
      });
    };
    socket.on('telemetry_update', handler);
    return () => socket.off('telemetry_update', handler);
  }, [socket, updateTelemetry]);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await api.get('/api/health');
        setHealthData(res.data);
      } catch {
        setHealthData(null);
      }
    };
    fetchHealth();
    const id = setInterval(fetchHealth, 15000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const loadSegmentationLog = async () => {
      try {
        const res = await api.get('/api/logs/segmentation/latest');
        if (res.data?.success && Array.isArray(res.data.rows)) {
          setSegLog({ file: res.data.file, rows: res.data.rows });
          setError(null);
        }
      } catch {
        // non-fatal – keep existing rows if any
      }
    };
    loadSegmentationLog();
    const id = setInterval(loadSegmentationLog, 10000); // refresh every 10 s
    return () => clearInterval(id);
  }, []);

  const flyingDrones = drones.filter((d) => getDroneFlags(d).flying);
  const avgBattery = drones.length
    ? Math.round(drones.reduce((s, d) => s + (d.battery || 0), 0) / drones.length)
    : 0;
  const avgSpeed = flyingDrones.length
    ? (flyingDrones.reduce((s, d) => s + (d.speed || 0), 0) / flyingDrones.length).toFixed(1)
    : '0.0';
  const sessionMinutes = Math.round((Date.now() - sessionStart) / 60000);

  const downloadBlob = (filename, content, type) => {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  const exportTelemetrySnapshot = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      fleet_size: drones.length,
      flying_drones: flyingDrones.length,
      avg_battery: avgBattery,
      avg_speed: avgSpeed,
      telemetry_history: telemetryHistory,
      health: healthData,
    };
    downloadBlob('lesnar-telemetry-snapshot.json', JSON.stringify(payload, null, 2), 'application/json');
  };

  const exportSegmentationCsv = () => {
    if (!segLog.rows.length) return;
    const headers = ['drone_id', 'detected_class', 'confidence', 'timestamp'];
    const rows = segLog.rows.map((row) => headers.map((header) => JSON.stringify(row[header] ?? '')).join(','));
    downloadBlob('lesnar-segmentation-log.csv', [headers.join(','), ...rows].join('\n'), 'text/csv;charset=utf-8');
  };

  return (
    <div className="p-8 space-y-10 fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between border-l-2 border-lesnar-accent pl-6 py-2">
        <div>
          <h1 className="text-3xl font-black text-white uppercase tracking-tighter">
            Fleet Intelligence <span className="text-lesnar-accent">ANALYTICS</span>
          </h1>
          <p className="text-xs font-mono text-gray-500 uppercase tracking-widest mt-1">
            Real-time Telemetry Data & Predictive Diagnostics
          </p>
        </div>
        <div className="mt-4 md:mt-0 flex items-center gap-3">
          <button onClick={exportTelemetrySnapshot} className="p-2.5 rounded-xl border border-white/10 hover:bg-white/5 transition-colors text-gray-300">
            <FileJson className="h-4 w-4" />
          </button>
          <button onClick={exportSegmentationCsv} disabled={!segLog.rows.length} className="btn-primary flex items-center px-5 disabled:opacity-40 disabled:cursor-not-allowed">
            <Download className="h-4 w-4 mr-2" />
            EXPORT LOGS
          </button>
        </div>
      </div>

      {/* Hero Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <MetricBox title="Flight Tempo" value={`${flyingDrones.length}/${drones.length}`} label="Active Sorties" icon={Compass} color="accent" />
        <MetricBox title="Energy Matrix" value={`${avgBattery}%`} label="Fleet Average" icon={Zap} color="success" />
        <MetricBox title="Propulsion" value={`${avgSpeed} m/s`} label="Cruise Velocity" icon={TrendingUp} color="warning" />
        <MetricBox title="Mission Sync" value={`${sessionMinutes}m`} label="Session Elapsed" icon={Clock} color="accent" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
        {/* Live Pulse Graph */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-sm font-black text-white uppercase tracking-widest flex items-center">
              <Activity className="h-4 w-4 mr-2 text-lesnar-accent" />
              Live Telemetry Pulse
            </h3>
            <div className="flex space-x-4">
              <div className="flex items-center space-x-1.5">
                <div className="h-1.5 w-1.5 rounded-full bg-lesnar-accent" />
                <span className="text-[8px] font-mono text-gray-500 uppercase">Sorties</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <div className="h-1.5 w-1.5 rounded-full bg-lesnar-success" />
                <span className="text-[8px] font-mono text-gray-500 uppercase">Battery</span>
              </div>
            </div>
          </div>

          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={telemetryHistory}>
                <defs>
                  <linearGradient id="neonBlue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00F5FF" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#00F5FF" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="neonGreen" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00FF94" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#00FF94" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" hide />
                <YAxis hide domain={[0, 100]} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#05070A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px' }}
                  itemStyle={{ fontSize: '10px', fontFamily: 'monospace', textTransform: 'uppercase' }}
                />
                <Area type="monotone" dataKey="activeDrones" stroke="#00FDFF" strokeWidth={2} fill="url(#neonBlue)" />
                <Area type="monotone" dataKey="avgBattery" stroke="#00FF9D" strokeWidth={2} fill="url(#neonGreen)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Readiness Matrix */}
        <div className="card space-y-8">
          <h3 className="text-sm font-black text-white uppercase tracking-widest flex items-center">
            <Shield className="h-4 w-4 mr-2 text-lesnar-success" />
            Readiness Matrix
          </h3>
          <div className="space-y-6">
            <ProgressMatrix label="Neural Mesh" value={healthData?.features?.computer_vision ? 98 : 0} color="accent" />
            <ProgressMatrix label="Collision Shield" value={healthData?.features?.obstacle_avoidance ? 100 : 0} color="success" />
            <ProgressMatrix label="Command Uplink" value={healthData?.status === 'ok' ? 95 : 0} color="warning" />
            <ProgressMatrix label="Battery Density" value={avgBattery} color="accent" />
          </div>

          <div className="pt-4 border-t border-white/5 flex items-center justify-between">
            <span className="text-[10px] font-mono text-gray-500 uppercase">System Integrity</span>
            <span className={`text-[10px] font-mono font-bold uppercase ${healthData?.status === 'ok' ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>
              {healthData?.status === 'ok' ? 'SECURE' : 'COMPROMISED'}
            </span>
          </div>
        </div>
      </div>

      {/* Log Feed */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-sm font-black text-white uppercase tracking-widest flex items-center">
            <BarChart3 className="h-4 w-4 mr-2 text-lesnar-accent" />
            Environmental Segmentation Feed
          </h3>
          <span className="text-[10px] font-mono text-gray-500 uppercase">File: {segLog.file || 'N/A'}</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-white/5">
                <th className="pb-3 text-[10px] font-mono text-gray-500 uppercase tracking-widest">Asset ID</th>
                <th className="pb-3 text-[10px] font-mono text-gray-500 uppercase tracking-widest">Class</th>
                <th className="pb-3 text-[10px] font-mono text-gray-500 uppercase tracking-widest">Confidence</th>
                <th className="pb-3 text-[10px] font-mono text-gray-500 uppercase tracking-widest">Coordinates</th>
                <th className="pb-3 text-[10px] font-mono text-gray-500 uppercase tracking-widest">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {segLog.rows.slice(0, 10).map((row, idx) => (
                <tr key={idx} className="group hover:bg-white/[0.02] transition-colors">
                  <td className="py-4 text-[11px] font-mono text-white">{row.drone_id || 'UAV-01'}</td>
                  <td className="py-4 text-[11px] font-mono text-lesnar-accent font-bold uppercase">{row.detected_class || row.class_name || row.label || 'OBJECT'}</td>
                  <td className="py-4">
                    <div className="flex items-center space-x-2">
                      <div className="w-16 h-1 bg-white/5 rounded-full overflow-hidden">
                        <div className="h-full bg-lesnar-accent" style={{ width: `${Math.max(0, Math.min(100, Number(row.confidence || row.score || 0) * 100 || 0))}%` }} />
                      </div>
                      <span className="text-[10px] font-mono text-gray-400">{(Math.max(0, Math.min(100, Number(row.confidence || row.score || 0) * 100 || 0))).toFixed(0)}%</span>
                    </div>
                  </td>
                  <td className="py-4 text-[11px] font-mono text-gray-400">{row.coordinates || row.location || row.xy || 'N/A'}</td>
                  <td className="py-4 text-[10px] font-mono text-gray-600 uppercase">{row.timestamp || row.created_at || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!error && segLog.rows.length === 0 && (
            <div className="py-12 flex flex-col items-center justify-center space-y-3 opacity-40">
              <BarChart3 className="h-10 w-10 text-lesnar-accent" />
              <p className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">No segmentation log captured yet</p>
            </div>
          )}
          {error && (
            <div className="py-12 flex flex-col items-center justify-center space-y-3 opacity-30">
              <AlertCircle className="h-10 w-10 text-lesnar-danger" />
              <p className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">Telemetry acquisition offline</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricBox({ title, value, label, icon: Icon, color }) {
  const colors = {
    accent: 'text-lesnar-accent border-lesnar-accent/30 bg-lesnar-accent/10',
    success: 'text-lesnar-success border-lesnar-success/30 bg-lesnar-success/10',
    warning: 'text-lesnar-warning border-lesnar-warning/30 bg-lesnar-warning/10',
  };

  return (
    <div className="card group hover:scale-[1.02] transition-transform cursor-pointer">
      <div className="flex justify-between items-start mb-4">
        <div className={`p-2.5 rounded-xl border ${colors[color]}`}>
          <Icon className="h-5 w-5" />
        </div>
        <span className="text-[8px] font-mono text-gray-600 tracking-widest uppercase">Live_Stream</span>
      </div>
      <p className="text-[10px] font-mono text-gray-500 uppercase tracking-tight">{title}</p>
      <h3 className="text-2xl font-black text-white mt-1 uppercase">{value}</h3>
      <p className="text-[9px] font-mono text-gray-600 mt-2 flex items-center">
        <TrendingUp className="h-3 w-3 mr-1 text-lesnar-success" />
        {label}
      </p>
    </div>
  );
}

function ProgressMatrix({ label, value, color }) {
  const barColors = {
    accent: 'bg-lesnar-accent',
    success: 'bg-lesnar-success',
    warning: 'bg-lesnar-warning',
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-between items-end">
        <span className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">{label}</span>
        <span className="text-[10px] font-mono text-white font-bold">{value}%</span>
      </div>
      <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
        <div
          className={`h-full transition-all duration-1000 ${barColors[color]}`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

export default Analytics;
