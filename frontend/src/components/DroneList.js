import RuntimeOrchestratorBlock from './RuntimeOrchestratorBlock';
import React, { useMemo, useState } from 'react';
import {
  Plus,
  Search,
  Power,
  PowerOff,
  Plane,
  PlaneLanding,
  X,
  Target,
  Zap,
  Activity,
  Shield,
  Navigation,
  AlertTriangle
} from 'lucide-react';
import { useDrones } from '../context/DroneContext';
import { MapContainer, TileLayer, Marker } from 'react-leaflet';
import { getDroneFlags, getDroneStatus } from '../utils/droneState';
import { requireTypedConfirmation } from '../utils/operatorAudit';
import { subscribeQuickSelect } from './TacticalHotkeys';
import { MAP_TILE_ATTRIBUTION, MAP_TILE_FALLBACK_URL, MAP_TILE_URL } from '../config';

function DroneList() {
  const {
    drones,
    fleetStatus,
    loading,
    error,
    gazeboSync,
    createDrone,
    armDrone,
    disarmDrone,
    takeoffDrone,
    landDrone,
    gotoDrone,
    executeMission,
    deleteDrone,
    emergencyLandAll,
    clearError,
    isDroneControlAllowed,
    getDroneState,
  } = useDrones();

  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [selectedDroneId, setSelectedDroneId] = useState(null);
  const [actionBanner, setActionBanner] = useState(null);
  const [gotoAlt, setGotoAlt] = useState(10);
  const [takeoffAlt] = useState(10);
  const [gotoLat, setGotoLat] = useState('');
  const [gotoLon, setGotoLon] = useState('');

  const selectedDrone = useMemo(
    () => drones.find((drone) => drone.drone_id === selectedDroneId) || null,
    [drones, selectedDroneId]
  );
  const selectedFlags = selectedDrone ? getDroneFlags(selectedDrone) : null;
  const selectedTelemetryMissing = Boolean(selectedDrone?.telemetry_missing);
  const selectedTelemetryStale = !selectedDrone || !isDroneControlAllowed(selectedDrone);
  const selectedControlLocked = !selectedDrone;

  const formatTelemetryValue = (value, digits = 6, suffix = '') => {
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    return `${num.toFixed(digits)}${suffix}`;
  };

  React.useEffect(() => subscribeQuickSelect((droneId) => {
    if (!droneId) return;
    const drone = drones.find((item) => item.drone_id === droneId);
    if (!drone) return;
    setSelectedDroneId(droneId);
    setGotoLat(Number(drone.latitude || 0).toFixed(6));
    setGotoLon(Number(drone.longitude || 0).toFixed(6));
  }), [drones]);

  React.useEffect(() => {
    if (!actionBanner) return undefined;
    const timer = setTimeout(() => setActionBanner(null), 8000);
    return () => clearTimeout(timer);
  }, [actionBanner]);

  const fleetSummary = useMemo(() => {
    const hasFreshFleetStatus = fleetStatus
      && typeof fleetStatus.total_drones === 'number'
      && (fleetStatus.total_drones > 0 || drones.length === 0);
    if (hasFreshFleetStatus) {
      return {
        total: fleetStatus.total_drones,
        armed: fleetStatus.armed_drones,
        flying: fleetStatus.flying_drones,
        lowBattery: fleetStatus.low_battery_drones,
      };
    }
    const total = drones.length;
    const armed = drones.filter((drone) => drone.armed).length;
    const flying = drones.filter((drone) => getDroneFlags(drone).flying).length;
    const lowBattery = drones.filter((drone) => {
      const { battery } = getDroneFlags(drone);
      return Number.isFinite(battery) && battery < 20;
    }).length;
    return { total, armed, flying, lowBattery };
  }, [drones, fleetStatus]);
  const actionableCount = useMemo(
    () => drones.filter((drone) => {
      const flags = getDroneFlags(drone);
      return flags.armed || flags.flying;
    }).length,
    [drones]
  );

  const filteredDrones = drones.filter((drone) => {
    const droneId = String(drone.drone_id || '').toLowerCase();
    const matchesSearch = droneId.includes(searchTerm.toLowerCase());
    const flags = getDroneFlags(drone);
    const matchesFilter = filterStatus === 'all' ||
      (filterStatus === 'armed' && flags.armed) ||
      (filterStatus === 'flying' && flags.flying) ||
      (filterStatus === 'landed' && !flags.flying && !flags.armed);

    return matchesSearch && matchesFilter;
  });

  const handleDroneAction = async (action, droneId, ...args) => {
    try {
      setActionBanner(null);
      if (selectedDrone && selectedTelemetryMissing) {
        setActionBanner({ type: 'error', message: 'Backend telemetry missing. Attempting command using the live control link.' });
      } else if (selectedDrone && selectedTelemetryStale) {
        setActionBanner({ type: 'error', message: 'Telemetry is stale. Command sent under operator override.' });
      }
      let result = null;
      switch (action) {
        case 'arm': result = await armDrone(droneId); break;
        case 'disarm': result = await disarmDrone(droneId); break;
        case 'takeoff': result = await takeoffDrone(droneId, args[0] || 10); break;
        case 'land': result = await landDrone(droneId); break;
        case 'delete':
          if (window.confirm(`DELETION_PROTOCOL: Purge asset ${droneId}?`)) {
            await deleteDrone(droneId);
            if (selectedDroneId === droneId) setSelectedDroneId(null);
          }
          break;
        default: break;
      }
      setActionBanner({ type: 'success', message: result?.message || `${action.toUpperCase()} confirmed for ${droneId}` });
    } catch (error) {
      setActionBanner({ type: 'error', message: error?.message || `Unable to ${action} ${droneId}` });
    }
  };

  const handleStartTraining = async (drone) => {
    if (!drone) return;
    let liveDrone = drone;
    if (drone.telemetry_missing || !Number.isFinite(Number(drone.latitude)) || !Number.isFinite(Number(drone.longitude))) {
      try {
        const refreshed = await getDroneState(drone.drone_id);
        if (refreshed) {
          liveDrone = { ...drone, ...refreshed };
        }
      } catch {
      }
    }

    const lat0 = Number(liveDrone.latitude);
    const lon0 = Number(liveDrone.longitude);
    if (!Number.isFinite(lat0) || !Number.isFinite(lon0)) {
      setActionBanner({ type: 'error', message: 'Training mission requires valid GPS (lat/lon missing).' });
      return;
    }

    // Small local box pattern around current position (keeps boundary validation happy).
    const meters = 25;
    const dLat = meters / 111319.0;
    const dLon = meters / (111319.0 * Math.max(0.2, Math.cos((lat0 * Math.PI) / 180.0)));
    const alt = Math.max(2, Number(takeoffAlt || 10));
    const waypoints = [
      [lat0 + dLat, lon0, alt],
      [lat0 + dLat, lon0 + dLon, alt],
      [lat0, lon0 + dLon, alt],
      [lat0, lon0, alt],
    ];

    try {
      setActionBanner(null);
      if (liveDrone.telemetry_missing) {
        setActionBanner({ type: 'error', message: 'Telemetry link degraded. Attempting training mission with refreshed live state.' });
      } else if (selectedTelemetryStale) {
        setActionBanner({ type: 'error', message: 'Telemetry is stale. Training mission sent under operator override.' });
      }
      const result = await executeMission(liveDrone.drone_id, waypoints, 'TRAINING');
      setActionBanner({
        type: 'success',
        message: result?.message || `TRAINING MISSION SENT for ${liveDrone.drone_id}`,
      });
    } catch (error) {
      setActionBanner({ type: 'error', message: error?.message || 'Unable to start training mission.' });
    }
  };

  const handleCreateAsset = async () => {
    if (gazeboSync?.enabled) {
      setActionBanner({ type: 'error', message: 'Assets are Gazebo-synced. Spawn in Gazebo/PX4; the UI will auto-discover.' });
      return;
    }
    const id = window.prompt('Asset ID (A-Z, 0-9, -, _, .)', `LESNAR-${Date.now().toString().slice(-4)}`);
    if (!id) return;

    try {
      setActionBanner(null);
      await createDrone({ drone_id: id.trim() });
      setActionBanner({ type: 'success', message: `ASSET CREATED: ${id.trim()}` });
      setSelectedDroneId(id.trim());
    } catch {
      setActionBanner({ type: 'error', message: `Unable to create asset ${id.trim()}` });
    }
  };

  const handleGoto = async () => {
    if (!selectedDrone) return;
    const latitude = Number(gotoLat);
    const longitude = Number(gotoLon);
    const altitude = Number(gotoAlt || 10);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      setActionBanner({ type: 'error', message: 'Invalid GOTO coordinates' });
      return;
    }
    try {
      if (selectedTelemetryMissing) {
        setActionBanner({ type: 'error', message: 'Backend telemetry missing. Attempting navigation using operator-provided coordinates.' });
      } else if (selectedTelemetryStale) {
        setActionBanner({ type: 'error', message: 'Telemetry is stale. Navigation sent under operator override.' });
      }
      const result = await gotoDrone(selectedDrone.drone_id, latitude, longitude, altitude);
      setActionBanner({ type: 'success', message: result?.message || `Navigation confirmed for ${selectedDrone.drone_id}` });
    } catch (error) {
      setActionBanner({ type: 'error', message: error?.message || `GOTO failed for ${selectedDrone.drone_id}` });
    }
  };

  const actionBannerStyles = actionBanner?.type === 'success'
    ? {
      box: 'bg-lesnar-success/10 border-lesnar-success/30',
      icon: 'text-lesnar-success',
      text: 'text-lesnar-success',
    }
    : {
      box: 'bg-lesnar-danger/10 border-lesnar-danger/30',
      icon: 'text-lesnar-danger',
      text: 'text-lesnar-danger',
    };

  return (
    <div className="p-8 space-y-10 fade-in pb-24">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between border-l-2 border-lesnar-accent pl-6 py-2 mb-6">
        <div>
          <h1 className="text-3xl font-black text-white uppercase tracking-tighter">
            Fleet Assets <span className="text-lesnar-accent">DEPLOYMENT</span>
          </h1>
          <p className="text-xs font-mono text-gray-500 uppercase tracking-widest mt-1">
            Tactical Unit Management & Individual Command
          </p>
        </div>

        <div className="mt-4 md:mt-0 flex space-x-3">
          {actionableCount > 0 && (
            <button
              onClick={() => {
                if (requireTypedConfirmation('Global emergency recall for all actionable drones?', 'CONFIRM')) {
                  emergencyLandAll();
                }
              }}
              disabled={drones.every((drone) => !isDroneControlAllowed(drone))}
              className="p-2.5 rounded-xl border border-lesnar-danger/30 bg-lesnar-danger/5 text-lesnar-danger hover:bg-lesnar-danger/10 transition-all flex items-center px-6 font-mono font-bold text-[10px] disabled:opacity-40"
            >
              <AlertTriangle className="h-4 w-4 mr-2" />
              EMERGENCY RECALL
            </button>
          )}
          <button
            onClick={handleCreateAsset}
            disabled={gazeboSync?.enabled}
            className="btn-primary flex items-center px-6"
            title={gazeboSync?.enabled ? 'Gazebo-synced mode: assets are discovered from Gazebo models.' : undefined}
          >
            <Plus className="h-4 w-4 mr-2" />
            NEW ASSET
          </button>
        </div>
      </div>

      <RuntimeOrchestratorBlock />

      {/* Summary Chips */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <UnitChip label="Total Assets" value={fleetSummary.total} color="accent" />
        <UnitChip label="Armed Units" value={fleetSummary.armed} color="warning" />
        <UnitChip label="Active Sorties" value={fleetSummary.flying} color="success" />
        <UnitChip label="Low Energy" value={fleetSummary.lowBattery} color="danger" />
      </div>

      {error && (
        <div className="bg-lesnar-danger/10 border border-lesnar-danger/30 rounded-2xl p-3 flex items-center justify-between">
          <p className="text-xs font-mono text-lesnar-danger uppercase tracking-wider">{error}</p>
          <button onClick={clearError} className="text-gray-400 hover:text-white"><X className="h-4 w-4" /></button>
        </div>
      )}

      {actionBanner && (
        <div className={`rounded-2xl p-4 flex items-center justify-between slide-down border ${actionBannerStyles.box}`}>
          <div className="flex items-center space-x-3">
            <Zap className={`h-5 w-5 ${actionBannerStyles.icon}`} />
            <p className={`text-sm font-mono uppercase font-bold tracking-widest ${actionBannerStyles.text}`}>{actionBanner.message}</p>
          </div>
          <button onClick={() => setActionBanner(null)} className="text-gray-500 hover:text-white"><X className="h-4 w-4" /></button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
        {/* List Side */}
        <div className="lg:col-span-1 space-y-6">
          <div className="relative group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500 group-hover:text-lesnar-accent transition-colors" />
            <input
              type="text"
              placeholder="FILTER_BY_HASH_OR_ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded-2xl pl-12 pr-4 py-3 text-sm font-mono text-white focus:outline-none focus:border-lesnar-accent/40 focus:bg-black/60 transition-all placeholder:text-gray-700"
            />
          </div>

          <div className="flex space-x-2">
            {['all', 'armed', 'flying', 'landed'].map(tab => (
              <button
                key={tab}
                onClick={() => setFilterStatus(tab)}
                className={`flex-1 py-1.5 rounded-lg text-[10px] font-mono uppercase tracking-widest border transition-all ${filterStatus === tab
                    ? 'bg-lesnar-accent/10 border-lesnar-accent/30 text-lesnar-accent'
                    : 'bg-white/5 border-white/5 text-gray-500 hover:text-gray-300'
                  }`}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="space-y-3 custom-scrollbar max-h-[600px] overflow-y-auto pr-2">
            {loading && (
              <div className="text-xs font-mono text-gray-500 uppercase tracking-widest px-2 py-3">Syncing telemetry...</div>
            )}
            {!loading && filteredDrones.length === 0 && (
              <div className="text-xs font-mono text-gray-500 uppercase tracking-widest px-2 py-3">No assets match current filter.</div>
            )}
            {filteredDrones.map(drone => (
              (() => {
                const flags = getDroneFlags(drone);
                const hasBattery = Number.isFinite(flags.battery);
                const isLowBattery = hasBattery && flags.battery < 20;
                const altitudeText = Number.isFinite(flags.altitude) ? Number(flags.altitude).toFixed(1) : '—';
                const speedText = Number.isFinite(flags.speed) ? Number(flags.speed).toFixed(1) : '—';
                const batteryText = hasBattery ? `${Math.round(flags.battery)}%` : '—';

                return (
              <div
                key={drone.drone_id}
                onClick={() => {
                  setSelectedDroneId(drone.drone_id);
                  setGotoLat(Number(drone.latitude || 0).toFixed(6));
                  setGotoLon(Number(drone.longitude || 0).toFixed(6));
                }}
                className={`card p-4 cursor-pointer group transition-all ${selectedDroneId === drone.drone_id
                    ? 'border-lesnar-accent/40 bg-lesnar-accent/5'
                    : 'border-white/5 hover:border-white/20'
                  }`}
              >
                <div className="flex justify-between items-start">
                  <div className="flex items-center space-x-3">
                    <div className={`h-2 w-2 rounded-full ${getDroneStatus(drone).dot}`} />
                    <span className="text-sm font-black text-white uppercase tracking-tighter">{drone.drone_id}</span>
                  </div>
                  <span className={`text-[9px] font-mono uppercase ${getDroneStatus(drone).text}`}>{getDroneStatus(drone).label}</span>
                </div>
                <div className="mt-4 flex justify-between items-end">
                  <div className="space-y-1">
                    <p className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">ALT: {altitudeText}M</p>
                    <p className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">SPD: {speedText}MS</p>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Zap className={`h-3 w-3 ${isLowBattery ? 'text-lesnar-danger animate-bounce' : 'text-lesnar-success'}`} />
                    <span className="text-xs font-mono font-bold text-white">{batteryText}</span>
                  </div>
                </div>
              </div>
                );
              })()
            ))}
          </div>
        </div>

        {/* Command Side */}
        <div className="lg:col-span-2">
          {selectedDrone ? (
            <div className="space-y-8 fade-in">
              <div className="card border-lesnar-accent/20 bg-lesnar-accent/[0.02]">
                <div className="flex justify-between items-start mb-8">
                  <div className="flex items-center space-x-4">
                    <div className="w-12 h-12 bg-lesnar-accent/10 border border-lesnar-accent/20 rounded-2xl flex items-center justify-center neo-glow">
                      <Target className="h-6 w-6 text-lesnar-accent" />
                    </div>
                    <div>
                      <h2 className="text-2xl font-black text-white uppercase tracking-tighter">{selectedDrone.drone_id}</h2>
                      <p className="text-[10px] font-mono text-lesnar-accent uppercase tracking-widest">Active_Tactical_Link_ESTABLISHED</p>
                    </div>
                  </div>
                  <div className="flex space-x-2">
                    {!selectedFlags?.armed && (
                      <ControlButton
                        icon={Power}
                        label="ARM"
                        color="warning"
                        disabled={selectedControlLocked}
                        onClick={() => handleDroneAction('arm', selectedDrone.drone_id)}
                      />
                    )}
                    {selectedFlags?.armed && !selectedFlags?.flying && (
                      <ControlButton
                        icon={Plane}
                        label="TAKEOFF"
                        color="success"
                        disabled={selectedControlLocked}
                        onClick={() => handleDroneAction('takeoff', selectedDrone.drone_id, takeoffAlt)}
                      />
                    )}
                    {selectedFlags?.flying && (
                      <ControlButton
                        icon={PlaneLanding}
                        label="LAND"
                        color="accent"
                        disabled={selectedControlLocked}
                        onClick={() => handleDroneAction('land', selectedDrone.drone_id)}
                      />
                    )}
                    {selectedFlags?.armed && !selectedFlags?.flying && (
                      <ControlButton
                        icon={PowerOff}
                        label="DISARM"
                        color="danger"
                        disabled={selectedControlLocked}
                        onClick={() => handleDroneAction('disarm', selectedDrone.drone_id)}
                      />
                    )}

                    <ControlButton
                      icon={Activity}
                      label="START TRAIN"
                      color="accent"
                      disabled={selectedControlLocked}
                      onClick={() => handleStartTraining(selectedDrone)}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
                  <DataBlock label="Latitude" value={formatTelemetryValue(selectedDrone.latitude, 6)} />
                  <DataBlock label="Longitude" value={formatTelemetryValue(selectedDrone.longitude, 6)} />
                  <DataBlock label="Heading" value={Number.isFinite(Number(selectedDrone.heading)) ? `${Math.round(Number(selectedDrone.heading))}°` : '—'} />
                  <DataBlock
                    label="Battery"
                    value={(() => {
                      const { battery } = getDroneFlags(selectedDrone);
                      return Number.isFinite(battery) ? `${Math.round(battery)}%` : '—';
                    })()}
                  />
                </div>
                {selectedTelemetryMissing && (
                  <div className="mt-4 rounded-xl border border-lesnar-danger/30 bg-lesnar-danger/10 px-4 py-3 text-[10px] font-mono text-lesnar-danger uppercase tracking-widest">
                    Backend telemetry unavailable for this asset. Re-authenticate if the session expired.
                  </div>
                )}
                {selectedTelemetryStale && (
                  <div className="mt-4 rounded-xl border border-lesnar-danger/30 bg-lesnar-danger/10 px-4 py-3 text-[10px] font-mono text-lesnar-danger uppercase tracking-widest">
                    Control Lockout: Selected drone telemetry is stale.
                  </div>
                )}
              </div>

              {/* Advanced Navigation */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="card">
                  <h3 className="text-sm font-black text-white uppercase tracking-widest mb-6 flex items-center">
                    <Navigation className="h-4 w-4 mr-2 text-lesnar-accent" />
                    Point Navigation
                  </h3>
                  <div className="space-y-4">
                    <div className="h-48 rounded-xl border border-white/5 overflow-hidden">
                      <MapContainer
                        center={[selectedDrone.latitude || 0, selectedDrone.longitude || 0]}
                        zoom={15}
                        className="w-full h-full grayscale brightness-50 contrast-125"
                      >
                        <TileLayer attribution={MAP_TILE_ATTRIBUTION} url={MAP_TILE_URL || MAP_TILE_FALLBACK_URL} />
                        <Marker position={[selectedDrone.latitude || 0, selectedDrone.longitude || 0]} />
                      </MapContainer>
                    </div>
                    <div className="flex space-x-3 mt-4">
                      <div className="flex-1">
                        <label className="text-[9px] font-mono text-gray-600 uppercase block mb-1">Transit Ceiling</label>
                        <input
                          type="number"
                          value={gotoAlt}
                          onChange={(e) => setGotoAlt(Number(e.target.value) || 0)}
                          className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white"
                        />
                      </div>
                      <div className="flex-1 grid grid-cols-2 gap-2">
                        <div>
                          <label className="text-[9px] font-mono text-gray-600 uppercase block mb-1">Latitude</label>
                          <input
                            type="number"
                            step="0.000001"
                            value={gotoLat}
                            onChange={(e) => setGotoLat(e.target.value)}
                            className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white"
                          />
                        </div>
                        <div>
                          <label className="text-[9px] font-mono text-gray-600 uppercase block mb-1">Longitude</label>
                          <input
                            type="number"
                            step="0.000001"
                            value={gotoLon}
                            onChange={(e) => setGotoLon(e.target.value)}
                            className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white"
                          />
                        </div>
                      </div>
                      {(selectedFlags?.armed || selectedFlags?.flying) && (
                        <button onClick={handleGoto} disabled={selectedControlLocked} className="btn-primary mt-4 self-end h-9 disabled:opacity-40">INITIATE GOTO</button>
                      )}
                    </div>
                  </div>
                </div>

                <div className="card">
                  <h3 className="text-sm font-black text-white uppercase tracking-widest mb-6 flex items-center">
                    <Activity className="h-4 w-4 mr-2 text-lesnar-success" />
                    System Telemetry
                  </h3>
                  <div className="space-y-4">
                    <TelemetryRow label="ESC Status" ok={selectedFlags?.armed || selectedFlags?.flying} />
                    <TelemetryRow label="GPS Lock" ok={Number.isFinite(Number(selectedDrone.latitude)) && Number.isFinite(Number(selectedDrone.longitude))} />
                    <TelemetryRow label="IMU Health" ok={Boolean(selectedDrone.mode)} />
                    <TelemetryRow label="UAVCAN Link" ok={Boolean(selectedDrone.timestamp)} />
                    <div className="pt-4 mt-4 border-t border-white/5">
                      <button
                        onClick={() => handleDroneAction('delete', selectedDrone.drone_id)}
                        disabled={gazeboSync?.enabled}
                        className="text-[10px] font-mono text-lesnar-danger uppercase hover:underline flex items-center disabled:opacity-40 disabled:cursor-not-allowed"
                        title={gazeboSync?.enabled ? 'Gazebo-synced mode: assets are discovered from Gazebo models.' : undefined}
                      >
                        <X className="h-3 w-3 mr-1" /> Remove Asset Permanent
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-[400px] card flex flex-col items-center justify-center opacity-30 text-center">
              <Shield className="h-16 w-16 mb-4 text-gray-500" />
              <p className="text-xs font-mono uppercase tracking-[0.2em]">Select an active asset to initiate uplink</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function UnitChip({ label, value, color }) {
  const colors = {
    accent: 'text-lesnar-accent border-lesnar-accent/20 bg-lesnar-accent/5',
    warning: 'text-lesnar-warning border-lesnar-warning/20 bg-lesnar-warning/5',
    success: 'text-lesnar-success border-lesnar-success/20 bg-lesnar-success/5',
    danger: 'text-lesnar-danger border-lesnar-danger/20 bg-lesnar-danger/5',
  };
  return (
    <div className={`p-4 rounded-2xl border ${colors[color]} card relative overflow-hidden`}>
      <p className="text-[10px] font-mono text-gray-600 uppercase tracking-widest">{label}</p>
      <h2 className="text-xl font-black mt-1 text-white">{value}</h2>
    </div>
  );
}

function DataBlock({ label, value }) {
  return (
    <div className="bg-black/40 border border-white/5 rounded-2xl p-4">
      <p className="text-[10px] font-mono text-gray-600 uppercase tracking-widest mb-1">{label}</p>
      <p className="text-sm font-mono text-white font-bold">{value}</p>
    </div>
  );
}

function ControlButton({ icon: Icon, label, color, onClick, disabled }) {
  const colors = {
    accent: 'hover:bg-lesnar-accent/20 text-lesnar-accent border-lesnar-accent/30',
    warning: 'hover:bg-lesnar-warning/20 text-lesnar-warning border-lesnar-warning/30',
    success: 'hover:bg-lesnar-success/20 text-lesnar-success border-lesnar-success/30',
    danger: 'hover:bg-lesnar-danger/20 text-lesnar-danger border-lesnar-danger/30',
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex flex-col items-center justify-center w-20 h-20 rounded-2xl border transition-all ${colors[color]} disabled:opacity-40 disabled:cursor-not-allowed`}
    >
      <Icon className="h-6 w-6 mb-1" />
      <span className="text-[8px] font-black uppercase tracking-widest">{label}</span>
    </button>
  );
}

function TelemetryRow({ label, ok }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[10px] font-mono text-gray-500 uppercase">{label}</span>
      <div className="flex items-center space-x-2">
        <div className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-lesnar-success' : 'bg-lesnar-danger'}`} />
        <span className={`text-[10px] font-mono font-bold uppercase ${ok ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>{ok ? 'OK' : 'FAIL'}</span>
      </div>
    </div>
  );
}

export default DroneList;
