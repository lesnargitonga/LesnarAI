import React, { useEffect, useMemo, useState } from 'react';
import api from '../api';
import {
  Navigation,
  MapPin,
  Clock,
  Pause,
  Play,
  Square,
  Shield,
  Zap,
  Target,
  Cpu,
  Layers,
  ChevronRight,
  TrendingUp,
  AlertTriangle
} from 'lucide-react';
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import { useDrones } from '../context/DroneContext';

function WaypointClickCapture({ onAdd }) {
  useMapEvents({
    click(e) {
      onAdd && onAdd(e.latlng);
    },
  });
  return null;
}

function formatRemaining(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return '—';
  const s = Math.max(0, Number(seconds));
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, '0')}`;
}

function MissionControl({ socket }) {
  const { drones, fetchDrones, executeMission, takeoffDrone } = useDrones();

  const [selectedDroneId, setSelectedDroneId] = useState('');
  const [actionBanner, setActionBanner] = useState(null);
  const [pending, setPending] = useState(false);

  const [missionType, setMissionType] = useState('CUSTOM');
  const [missionDefaultAlt, setMissionDefaultAlt] = useState(10);
  const [missionWaypoints, setMissionWaypoints] = useState([]); // [{lat,lng,alt}]

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [savedTemplates, setSavedTemplates] = useState([]);
  const [selectedTemplateName, setSelectedTemplateName] = useState('');

  const [activeMissions, setActiveMissions] = useState([]);
  const [missionsLoading, setMissionsLoading] = useState(false);

  const selectedDrone = useMemo(() => drones.find(d => d.drone_id === selectedDroneId) || null, [drones, selectedDroneId]);
  const selectedIsFlying = Boolean(selectedDrone && Number(selectedDrone.altitude || 0) > 1);

  useEffect(() => {
    // Load templates
    const raw = window.localStorage.getItem('lesnar.missions.templates');
    setSavedTemplates(raw ? JSON.parse(raw) : []);

    if (socket) {
      socket.on('mission_status', () => refreshActiveMissions());
      return () => socket.off('mission_status');
    }
  }, [socket]);

  useEffect(() => {
    if (!selectedDroneId && drones.length > 0) setSelectedDroneId(drones[0].drone_id);
  }, [drones, selectedDroneId]);

  const refreshActiveMissions = async () => {
    setMissionsLoading(true);
    try {
      const res = await api.get('/api/missions/active');
      if (res.data?.success) setActiveMissions(res.data.missions || []);
    } catch {
      setActiveMissions([]);
    } finally {
      setMissionsLoading(false);
    }
  };

  useEffect(() => {
    refreshActiveMissions();
    const id = setInterval(refreshActiveMissions, 10000);
    return () => clearInterval(id);
  }, []);

  const generatePattern = (pattern) => {
    if (!selectedDrone) return;
    const centerLat = Number(selectedDrone.latitude);
    const centerLng = Number(selectedDrone.longitude);
    const latFactor = 1 / 111000;
    const lonFactor = 1 / (111000 * Math.cos((centerLat * Math.PI) / 180));
    const gen = [];

    if (pattern === 'ORBIT') {
      const pts = 12;
      const r = 80;
      for (let i = 0; i < pts; i++) {
        const a = (2 * Math.PI * i) / pts;
        gen.push({ lat: centerLat + Math.sin(a) * r * latFactor, lng: centerLng + Math.cos(a) * r * lonFactor, alt: missionDefaultAlt });
      }
      setMissionType('SEC_ORBIT');
    } else if (pattern === 'SWEEP') {
      const r = 100;
      gen.push({ lat: centerLat, lng: centerLng, alt: missionDefaultAlt });
      gen.push({ lat: centerLat + r * latFactor, lng: centerLng + r * lonFactor, alt: missionDefaultAlt + 5 });
      gen.push({ lat: centerLat + r * latFactor, lng: centerLng - r * lonFactor, alt: missionDefaultAlt + 10 });
      gen.push({ lat: centerLat, lng: centerLng, alt: missionDefaultAlt });
      setMissionType('TACT_SWEEP');
    }

    setMissionWaypoints(gen);
  };

  return (
    <div className="p-8 space-y-10 fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between border-l-2 border-lesnar-accent pl-6 py-2">
        <div>
          <h1 className="text-3xl font-black text-white uppercase tracking-tighter">
            Mission Control <span className="text-lesnar-accent">// COMMAND</span>
          </h1>
          <p className="text-xs font-mono text-gray-500 uppercase tracking-widest mt-1">
            Tactical Operations Planning & Execution
          </p>
        </div>
      </div>

      {actionBanner && (
        <div className={`rounded-2xl border px-6 py-4 flex items-center space-x-4 animate-pulse ${actionBanner.type === 'error' ? 'bg-lesnar-danger/10 border-lesnar-danger/30 text-lesnar-danger' : 'bg-lesnar-success/10 border-lesnar-success/30 text-lesnar-success'
          }`}>
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p className="text-xs font-mono font-bold uppercase">{actionBanner.message}</p>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-10">
        {/* Planning Engine */}
        <div className="xl:col-span-2 space-y-8">
          <div className="card space-y-8">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="h-10 w-10 bg-lesnar-accent/10 border border-lesnar-accent/30 rounded-xl flex items-center justify-center neo-glow">
                  <Cpu className="h-6 w-6 text-lesnar-accent" />
                </div>
                <h2 className="text-xl font-black text-white uppercase tracking-tight">Mission Engine</h2>
              </div>

              <div className="flex items-center space-x-4">
                <span className="text-[10px] font-mono text-gray-500 uppercase">Target Asset</span>
                <select
                  value={selectedDroneId}
                  onChange={(e) => setSelectedDroneId(e.target.value)}
                  className="bg-navy-black/60 border border-white/10 rounded-xl px-4 py-2 text-xs font-mono text-white focus:border-lesnar-accent outline-none"
                >
                  {drones.map(d => (
                    <option key={d.drone_id} value={d.drone_id}>{d.drone_id}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {/* Tactical Map */}
              <div className="rounded-3xl overflow-hidden border border-white/5 relative group h-[400px]">
                <div className="absolute inset-0 bg-navy-black pointer-events-none opacity-20 z-10" />
                <div className="absolute top-4 left-4 z-20 pointer-events-none">
                  <div className="bg-black/40 backdrop-blur-md border border-white/5 px-3 py-1.5 rounded-lg text-[8px] font-mono text-lesnar-accent uppercase tracking-widest">
                    Live Satellite Relay // Active
                  </div>
                </div>

                <MapContainer
                  center={selectedDrone ? [selectedDrone.latitude, selectedDrone.longitude] : [0, 0]}
                  zoom={15}
                  zoomControl={false}
                  className="w-full h-full filter grayscale brightness-50 contrast-125"
                >
                  <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
                  <WaypointClickCapture
                    onAdd={(ll) => setMissionWaypoints(prev => ([...prev, { lat: ll.lat, lng: ll.lng, alt: missionDefaultAlt }]))}
                  />

                  {missionWaypoints.length > 0 && (
                    <Polyline
                      positions={missionWaypoints.map(w => [w.lat, w.lng])}
                      pathOptions={{ color: '#00FDFF', weight: 2, dashArray: '10, 10' }}
                    />
                  )}

                  {missionWaypoints.map((w, idx) => (
                    <Marker key={idx} position={[w.lat, w.lng]} icon={L.divIcon({
                      className: 'wp-marker',
                      html: `<div class="w-4 h-4 rounded-full border-2 border-lesnar-accent bg-lesnar-accent/20 flex items-center justify-center text-[8px] font-bold text-white shadow-[0_0_10px_rgba(0,253,255,0.5)]">${idx + 1}</div>`,
                      iconSize: [16, 16]
                    })} />
                  ))}
                </MapContainer>

                {/* Map HUD Components */}
                <div className="absolute bottom-4 left-4 right-4 z-20 flex justify-between items-end pointer-events-none">
                  <div className="glass-dark border border-white/5 p-3 rounded-xl pointer-events-auto">
                    <div className="flex items-center space-x-2 text-[8px] font-mono text-gray-500 uppercase mb-2">
                      <Layers className="h-3 w-3" />
                      <span>Generator patterns</span>
                    </div>
                    <div className="flex space-x-2">
                      <button onClick={() => generatePattern('ORBIT')} className="px-3 py-1 bg-white/5 border border-white/10 rounded text-[9px] font-bold text-white hover:border-lesnar-accent/30 transition-all">ORBIT</button>
                      <button onClick={() => generatePattern('SWEEP')} className="px-3 py-1 bg-white/5 border border-white/10 rounded text-[9px] font-bold text-white hover:border-lesnar-accent/30 transition-all">SWEEP</button>
                    </div>
                  </div>
                  <button onClick={() => setMissionWaypoints([])} className="glass-dark border border-white/5 p-3 rounded-xl text-lesnar-danger pointer-events-auto hover:bg-lesnar-danger/10 transition-all">
                    Reset Plane
                  </button>
                </div>
              </div>

              {/* Mission Params */}
              <div className="space-y-6">
                <div className="space-y-4">
                  <h3 className="text-xs font-black text-gray-500 uppercase tracking-widest border-b border-white/5 pb-2">Operation Parameters</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-[10px] font-mono text-gray-600 uppercase">Mission Signature</label>
                      <input
                        value={missionType}
                        onChange={(e) => setMissionType(e.target.value)}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-xs font-mono text-white focus:border-lesnar-accent outline-none"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-mono text-gray-600 uppercase">Ceiling (M)</label>
                      <input
                        type="number"
                        value={missionDefaultAlt}
                        onChange={(e) => setMissionDefaultAlt(Number(e.target.value))}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-xs font-mono text-white focus:border-lesnar-accent outline-none"
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-4 flex-1">
                  <h3 className="text-xs font-black text-gray-500 uppercase tracking-widest border-b border-white/5 pb-2">Waypoint Manifest</h3>
                  <div className="max-h-56 overflow-y-auto space-y-2 pr-2 scrollbar-hide">
                    {missionWaypoints.map((w, idx) => (
                      <div key={idx} className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5 group hover:border-lesnar-accent/20 transition-all">
                        <div className="flex items-center space-x-3">
                          <span className="text-[10px] font-mono text-lesnar-accent font-bold">#{idx + 1}</span>
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
                        <div className="flex items-center space-x-3">
                          <span className="text-[10px] font-mono text-gray-500">{w.alt}M</span>
                          <button onClick={() => setMissionWaypoints(prev => prev.filter((_, i) => i !== idx))} className="text-lesnar-danger opacity-0 group-hover:opacity-100 transition-opacity">
                            <Square className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    ))}
                    {missionWaypoints.length === 0 && (
                      <div className="text-center py-10 border-2 border-dashed border-white/5 rounded-3xl">
                        <p className="text-[10px] font-mono text-gray-600 uppercase">Awaiting Map Handshake...</p>
                      </div>
                    )}
                  </div>
                </div>

                <div className="pt-4 space-y-3">
                  <button
                    disabled={missionWaypoints.length === 0 || pending}
                    onClick={async () => {
                      setPending(true);
                      const payload = missionWaypoints.map(w => [w.lat, w.lng, Number(w.alt)]);
                      await executeMission(selectedDrone.drone_id, payload, missionType);
                      setPending(false);
                      refreshActiveMissions();
                    }}
                    className="w-full py-4 bg-lesnar-accent/10 border border-lesnar-accent/30 rounded-2xl text-xs font-black text-lesnar-accent uppercase tracking-widest hover:bg-lesnar-accent/20 transition-all disabled:opacity-30 neo-glow"
                  >
                    Initiate Deployment
                  </button>
                  <button
                    disabled={selectedIsFlying || !selectedDrone?.armed || pending || missionWaypoints.length === 0}
                    onClick={async () => {
                      if (!selectedDrone) return;
                      setPending(true);
                      try {
                        await takeoffDrone(selectedDrone.drone_id, missionDefaultAlt);
                        const payload = missionWaypoints.map(w => [w.lat, w.lng, Number(w.alt)]);
                        await executeMission(selectedDrone.drone_id, payload, missionType);
                        refreshActiveMissions();
                      } catch (err) {
                        setActionBanner({ type: 'error', message: `Auto-launch failed: ${err.message || 'unknown error'}` });
                      } finally {
                        setPending(false);
                      }
                    }}
                    className="w-full py-4 bg-lesnar-success/10 border border-lesnar-success/30 rounded-2xl text-xs font-black text-lesnar-success uppercase tracking-widest hover:bg-lesnar-success/20 transition-all disabled:opacity-30"
                  >
                    Auto-Launch + Mission
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Live Mission Monitor */}
        <div className="space-y-8">
          <div className="card h-full flex flex-col">
            <div className="flex items-center justify-between mb-8">
              <div className="flex items-center space-x-3">
                <div className="h-8 w-8 bg-lesnar-success/10 border border-lesnar-success/30 rounded-lg flex items-center justify-center">
                  <Target className="h-4 w-4 text-lesnar-success" />
                </div>
                <h2 className="text-sm font-black text-white uppercase tracking-widest">Active Sorties</h2>
              </div>
              <button
                onClick={() => refreshActiveMissions()}
                className="p-2 rounded-lg hover:bg-white/5 text-gray-500 hover:text-white transition-all"
              >
                <TrendingUp className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 space-y-6 overflow-y-auto pr-2 scrollbar-hide">
              {activeMissions.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center space-y-4 opacity-30">
                  <Shield className="h-12 w-12 text-gray-500" />
                  <p className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">No Active Combat Sorties</p>
                </div>
              ) : (
                activeMissions.map((m) => (
                  <div key={m.drone_id} className="p-6 rounded-2xl bg-white/5 border border-white/10 space-y-6 group hover:neo-glow transition-all">
                    <div className="flex justify-between items-start">
                      <div>
                        <h4 className="text-sm font-black text-white uppercase">{m.drone_id}</h4>
                        <p className="text-[10px] font-mono text-lesnar-accent uppercase mt-1">{m.mission_type || 'TACTICAL_OPS'}</p>
                      </div>
                      <div className="h-2 w-2 rounded-full bg-lesnar-success animate-pulse shadow-[0_0_10px_rgba(0,255,148,0.8)]" />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-navy-black/40 p-3 rounded-lg border border-white/5">
                        <span className="text-[8px] font-mono text-gray-600 uppercase block mb-1">Status</span>
                        <span className="text-[10px] font-bold text-white uppercase">{m.status}</span>
                      </div>
                      <div className="bg-navy-black/40 p-3 rounded-lg border border-white/5">
                        <span className="text-[8px] font-mono text-gray-600 uppercase block mb-1">ETA</span>
                        <span className="text-[10px] font-bold text-lesnar-accent font-mono">{formatRemaining(m.estimated_remaining_s)}</span>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <div className="flex justify-between text-[8px] font-mono text-gray-500 uppercase">
                        <span>Waypoint Progression</span>
                        <span>{(m.current_waypoint_index / m.total_waypoints * 100).toFixed(0)}%</span>
                      </div>
                      <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-lesnar-success transition-all duration-1000"
                          style={{ width: `${(m.current_waypoint_index / m.total_waypoints * 100) || 0}%` }}
                        />
                      </div>
                    </div>

                    <div className="flex space-x-3 pt-4 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={async () => {
                          try {
                            await api.post(`/api/drones/${m.drone_id}/mission/stop`);
                            refreshActiveMissions();
                          } catch { }
                        }}
                        className="flex-1 py-3 bg-white/5 border border-white/10 rounded-xl text-[10px] font-black uppercase tracking-widest text-white hover:bg-white/10"
                      >
                        ABORT
                      </button>
                      <button
                        onClick={async () => {
                          try {
                            const endpoint = m.status === 'PAUSED'
                              ? `/api/drones/${m.drone_id}/mission/resume`
                              : `/api/drones/${m.drone_id}/mission/pause`;
                            await api.post(endpoint);
                            refreshActiveMissions();
                          } catch { }
                        }}
                        className="flex-1 py-3 bg-lesnar-accent/10 border border-lesnar-accent/30 rounded-xl text-[10px] font-black uppercase tracking-widest text-lesnar-accent hover:bg-lesnar-accent/20"
                      >
                        {m.status === 'PAUSED' ? 'RESUME' : 'PAUSE'}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default MissionControl;
