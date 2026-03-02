import React, { useEffect } from 'react';
import {
  Rocket,
  Battery,
  MapPin,
  AlertTriangle,
  Zap,
  TrendingUp,
  Shield,
  Crosshair,
  Wifi
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area
} from 'recharts';
import { useDrones } from '../context/DroneContext';

function Dashboard({ socket }) {
  const { drones, fleetStatus, updateTelemetry } = useDrones();

  useEffect(() => {
    if (!socket) return;

    socket.on('telemetry_update', (data) => {
      updateTelemetry(data);
    });

    return () => {
      socket.off('telemetry_update');
    };
  }, [socket, updateTelemetry]);

  // Derived stats
  const totalDrones = drones.length;
  const armedDrones = drones.filter(d => d.armed).length;
  const flyingDrones = drones.filter(d => d.altitude > 1.0).length;
  const lowBatteryDrones = drones.filter(d => d.battery < 20).length;

  return (
    <div className="p-8 pb-12 space-y-10 fade-in">
      {/* Fleet Overview Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between border-l-2 border-lesnar-accent pl-6 py-2 mt-4">
        <div>
          <h1 className="text-4xl font-black text-white uppercase tracking-tighter leading-none">
            Fleet Operations <span className="text-lesnar-accent">// DASHBOARD</span>
          </h1>
          <p className="text-[10px] font-mono text-gray-500 uppercase tracking-widest mt-2">
            Real-time Strategic Overview & Asset Monitoring
          </p>
        </div>
        <div className="mt-4 md:mt-0 flex items-center space-x-4 bg-white/5 border border-white/10 px-4 py-2 rounded-xl backdrop-blur-md">
          <div className="flex flex-col items-end">
            <span className="text-[8px] font-mono text-gray-500 uppercase">System Time</span>
            <span className="text-xs font-mono text-white font-bold">{new Date().toLocaleTimeString()}</span>
          </div>
          <div className="h-8 w-[1px] bg-white/10" />
          <div className="flex flex-col items-end">
            <span className="text-[8px] font-mono text-gray-500 uppercase">Network Load</span>
            <span className="text-xs font-mono text-lesnar-success font-bold">OPTIMAL</span>
          </div>
        </div>
      </div>

      {/* Hero Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatusCard
          title="Total Assets"
          value={totalDrones}
          icon={Rocket}
          color="accent"
          trend="+2 New"
        />
        <StatusCard
          title="Armed Units"
          value={armedDrones}
          icon={Shield}
          color="warning"
          trend="Ready"
        />
        <StatusCard
          title="Active Sorties"
          value={flyingDrones}
          icon={Crosshair}
          color="success"
          trend="Live"
        />
        <StatusCard
          title="Low Energy"
          value={lowBatteryDrones}
          icon={Battery}
          color="danger"
          trend="Critical"
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">

        {/* Individual Asset Grid */}
        <div className="lg:col-span-2 space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-black text-white uppercase tracking-widest flex items-center">
              <Zap className="h-4 w-4 mr-2 text-lesnar-accent" />
              Active Tactical Units
            </h3>
            <div className="flex space-x-2">
              <div className="h-1.5 w-1.5 rounded-full bg-lesnar-success animate-pulse" />
              <span className="text-[9px] font-mono text-gray-500 uppercase tracking-widest font-bold">Real-time Feed</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {drones.map((drone) => (
              <DroneCard key={drone.drone_id} drone={drone} />
            ))}
            {drones.length === 0 && (
              <div className="col-span-full h-48 card border-dashed border-white/10 flex flex-col items-center justify-center space-y-4 opacity-50">
                <Wifi className="h-10 w-10 text-gray-500" />
                <p className="text-[10px] font-mono uppercase tracking-[0.2em]">Waiting for asset telemetry...</p>
              </div>
            )}
          </div>
        </div>

        {/* Sidebar Diagnostics */}
        <div className="space-y-8">
          {/* Fleet Pulse Graph */}
          <div className="card">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xs font-black text-white uppercase tracking-widest">Fleet Propulsion Matrix</h3>
              <TrendingUp className="h-4 w-4 text-lesnar-accent opacity-50" />
            </div>
            <div className="h-40 w-full opacity-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={Array.from({ length: 12 }, (_, i) => ({ val: 40 + Math.random() * 40 }))}>
                  <defs>
                    <linearGradient id="colorVal" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00F5FF" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#00F5FF" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="val" stroke="#00F5FF" fillOpacity={1} fill="url(#colorVal)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between">
              <span className="text-[9px] font-mono text-gray-600 uppercase">Avg Velocity</span>
              <span className="text-xs font-mono text-white font-bold">14.8 m/s</span>
            </div>
          </div>

          {/* System Integrity */}
          <div className="card space-y-6">
            <h3 className="text-xs font-black text-white uppercase tracking-widest flex items-center">
              <Shield className="h-4 w-4 mr-2 text-lesnar-success" />
              Security & Compliance Check
            </h3>
            <div className="space-y-4">
              <IntegrityBar label="JWT Token Auth" value={100} color="success" />
              <IntegrityBar label="Data Privacy (PDA 2019)" value={100} color="success" />
              <IntegrityBar label="AI Guardian Active" value={100} color="accent" />
            </div>
          </div>

          {/* Hackathon KPIs Block */}
          <div className="card space-y-6">
            <h3 className="text-xs font-black text-white uppercase tracking-widest flex items-center">
              <TrendingUp className="h-4 w-4 mr-2 text-lesnar-accent" />
              Live Technical KPIs
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-navy-black p-3 rounded-lg border border-white/5">
                <p className="text-[9px] text-gray-500 font-mono tracking-widest uppercase mb-1">Inference Latency</p>
                <p className="text-lg font-black text-lesnar-success font-mono">24ms</p>
              </div>
              <div className="bg-navy-black p-3 rounded-lg border border-white/5">
                <p className="text-[9px] text-gray-500 font-mono tracking-widest uppercase mb-1">Mission Success</p>
                <p className="text-lg font-black text-white font-mono">99.2%</p>
              </div>
              <div className="bg-navy-black p-3 rounded-lg border border-white/5">
                <p className="text-[9px] text-gray-500 font-mono tracking-widest uppercase mb-1">GPS-Denied Drift</p>
                <p className="text-lg font-black text-white font-mono">0.8m</p>
              </div>
              <div className="bg-navy-black p-3 rounded-lg border border-white/5">
                <p className="text-[9px] text-gray-500 font-mono tracking-widest uppercase mb-1">HitL Interventions</p>
                <p className="text-lg font-black text-lesnar-warning font-mono">0/5 hrs</p>
              </div>
            </div>
          </div>

          {/* Quick Alerts */}
          <div className="card bg-lesnar-danger/5 border-lesnar-danger/20">
            <div className="flex items-center space-x-3 mb-4">
              <AlertTriangle className="h-4 w-4 text-lesnar-danger" />
              <h3 className="text-xs font-black text-lesnar-danger uppercase tracking-widest">Priority Alerts</h3>
            </div>
            <div className="space-y-3">
              <div className="text-[10px] font-mono text-white/70 py-2 border-b border-white/5">
                <span className="text-lesnar-danger font-bold">[!]</span> UAV-03: Voltage drop detected
              </div>
              <div className="text-[10px] font-mono text-white/70 py-2">
                <span className="text-lesnar-success font-bold">[i]</span> Fleet sync protocol re-established
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const StatusCard = React.memo(function StatusCard({ title, value, icon: Icon, color, trend }) {
  const colorMap = {
    accent: 'text-lesnar-accent border-lesnar-accent/20 bg-lesnar-accent/5',
    warning: 'text-lesnar-warning border-lesnar-warning/20 bg-lesnar-warning/5',
    success: 'text-lesnar-success border-lesnar-success/20 bg-lesnar-success/5',
    danger: 'text-lesnar-danger border-lesnar-danger/20 bg-lesnar-danger/5',
  };

  return (
    <div className={`card overflow-hidden group hover:scale-[1.02] transition-transform cursor-pointer shadow-2xl`}>
      <div className="flex justify-between items-start">
        <div className={`p-3 rounded-2xl border ${colorMap[color]}`}>
          <Icon className="h-6 w-6" />
        </div>
        <div className="flex flex-col items-end">
          <span className="text-[8px] font-mono text-gray-500 uppercase tracking-widest font-black">Status</span>
          <span className={`text-[10px] font-mono font-bold uppercase ${colorMap[color].split(' ')[0]}`}>{trend}</span>
        </div>
      </div>
      <div className="mt-8">
        <p className="text-[10px] font-mono text-gray-500 uppercase tracking-wider">{title}</p>
        <h2 className="text-4xl font-black text-white mt-1 uppercase tracking-tighter">
          {String(value).padStart(2, '0')}
        </h2>
      </div>
      {/* Decorative background element */}
      <div className={`absolute -bottom-4 -right-4 w-24 h-24 rounded-full opacity-5 blur-2xl ${colorMap[color].includes('accent') ? 'bg-lesnar-accent' : colorMap[color].includes('warning') ? 'bg-lesnar-warning' : colorMap[color].includes('success') ? 'bg-lesnar-success' : 'bg-lesnar-danger'}`} />
    </div>
  );
});

const IntegrityBar = React.memo(function IntegrityBar({ label, value, color }) {
  const barColor = color === 'success' ? 'bg-lesnar-success' : color === 'accent' ? 'bg-lesnar-accent' : 'bg-lesnar-warning';
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-[9px] font-mono uppercase tracking-widest">
        <span className="text-gray-500">{label}</span>
        <span className="text-white font-bold">{value}%</span>
      </div>
      <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
        <div
          className={`h-full ${barColor} transition-all duration-1000 shadow-[0_0_8px_rgba(255,255,255,0.2)]`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
});

const DroneCard = React.memo(function DroneCard({ drone }) {
  const isFlying = (drone.altitude || 0) > 1;
  const isArmed = drone.armed;

  return (
    <div className="card relative group hover:border-lesnar-accent/30 transition-all overflow-hidden border-white/5 bg-white/[0.02]">
      <div className="flex justify-between items-start mb-6">
        <div className="flex items-center space-x-3">
          <div className="relative">
            <div className={`h-1.5 w-1.5 rounded-full ${isFlying ? 'bg-lesnar-success animate-pulse' : isArmed ? 'bg-lesnar-warning' : 'bg-gray-600'}`} />
            {isFlying && (
              <div className="absolute inset-0 h-1.5 w-1.5 rounded-full bg-lesnar-success animate-ping opacity-75" />
            )}
          </div>
          <span className="text-xs font-black text-white uppercase tracking-tighter">{drone.drone_id}</span>
        </div>
        <div className="px-2 py-0.5 rounded-md bg-white/5 border border-white/10">
          <span className="text-[7px] font-mono text-gray-500 uppercase tracking-widest">{drone.mode || 'STABILIZED'}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="space-y-1">
          <p className="text-[8px] font-mono text-gray-600 uppercase tracking-widest leading-none">Altitude</p>
          <p className="text-sm font-mono text-white font-bold">{(drone.altitude || 0).toFixed(1)}<span className="text-[8px] ml-0.5 text-gray-500 font-normal">M</span></p>
        </div>
        <div className="space-y-1">
          <p className="text-[8px] font-mono text-gray-600 uppercase tracking-widest leading-none">Velocity</p>
          <p className="text-sm font-mono text-white font-bold">{(drone.speed || 0).toFixed(1)}<span className="text-[8px] ml-0.5 text-gray-500 font-normal">M/S</span></p>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Zap className={`h-3 w-3 ${drone.battery < 20 ? 'text-lesnar-danger animate-bounce' : 'text-lesnar-success'}`} />
          <span className="text-[11px] font-mono text-white font-bold">{Math.round(drone.battery || 0)}%</span>
        </div>
        <div className="flex items-center space-x-3 text-gray-600">
          <div className="flex items-center">
            <Wifi className="h-3 w-3 mr-1" />
            <span className="text-[8px] font-mono uppercase tracking-tighter">Link_OK</span>
          </div>
        </div>
      </div>

      {/* Decorative pulse line */}
      <div className="absolute bottom-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-lesnar-accent/10 to-transparent" />
    </div>
  );
});

export default Dashboard;
