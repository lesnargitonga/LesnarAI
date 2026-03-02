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

function DroneList() {
  const {
    drones,
    armDrone,
    disarmDrone,
    takeoffDrone,
    landDrone,
    deleteDrone,
    emergencyLandAll,
  } = useDrones();

  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [selectedDrone, setSelectedDrone] = useState(null);
  const [actionBanner, setActionBanner] = useState(null);
  const [gotoAlt, setGotoAlt] = useState(10);
  const [takeoffAlt, setTakeoffAlt] = useState(10);

  const fleetSummary = useMemo(() => {
    const total = drones.length;
    const armed = drones.filter(d => d.armed).length;
    const flying = drones.filter(d => (d.altitude || 0) > 1).length;
    const lowBattery = drones.filter(d => (d.battery || 100) < 20).length;
    return { total, armed, flying, lowBattery };
  }, [drones]);

  const filteredDrones = drones.filter(drone => {
    const matchesSearch = drone.drone_id.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = filterStatus === 'all' ||
      (filterStatus === 'armed' && drone.armed) ||
      (filterStatus === 'flying' && drone.altitude > 1) ||
      (filterStatus === 'landed' && drone.altitude <= 1 && !drone.armed);

    return matchesSearch && matchesFilter;
  });

  const handleDroneAction = async (action, droneId, ...args) => {
    try {
      setActionBanner(null);
      switch (action) {
        case 'arm': await armDrone(droneId); break;
        case 'disarm': await disarmDrone(droneId); break;
        case 'takeoff': await takeoffDrone(droneId, args[0] || 10); break;
        case 'land': await landDrone(droneId); break;
        case 'delete':
          if (window.confirm(`DELETION_PROTOCOL: Purge asset ${droneId}?`)) {
            await deleteDrone(droneId);
            if (selectedDrone?.drone_id === droneId) setSelectedDrone(null);
          }
          break;
        default: break;
      }
      setActionBanner({ type: 'success', message: `${action.toUpperCase()} command acknowledged for ${droneId}` });
    } catch {
      setActionBanner({ type: 'error', message: `Uplink failure: Unable to ${action} ${droneId}` });
    }
  };

  return (
    <div className="p-8 space-y-10 fade-in pb-24">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between border-l-2 border-lesnar-accent pl-6 py-2">
        <div>
          <h1 className="text-3xl font-black text-white uppercase tracking-tighter">
            Fleet Assets <span className="text-lesnar-accent">// DEPLOYMENT</span>
          </h1>
          <p className="text-xs font-mono text-gray-500 uppercase tracking-widest mt-1">
            Tactical Unit Management & Individual Command
          </p>
        </div>

        <div className="mt-4 md:mt-0 flex space-x-3">
          <button
            onClick={() => emergencyLandAll()}
            className="p-2.5 rounded-xl border border-lesnar-danger/30 bg-lesnar-danger/5 text-lesnar-danger hover:bg-lesnar-danger/10 transition-all flex items-center px-6 font-mono font-bold text-[10px]"
          >
            <AlertTriangle className="h-4 w-4 mr-2" />
            EMERGENCY RECALL
          </button>
          <button
            onClick={() => { }}
            className="btn-primary flex items-center px-6"
          >
            <Plus className="h-4 w-4 mr-2" />
            NEW ASSET
          </button>
        </div>
      </div>

      {/* Summary Chips */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <UnitChip label="Total Frames" value={fleetSummary.total} color="accent" />
        <UnitChip label="Armed Units" value={fleetSummary.armed} color="warning" />
        <UnitChip label="Active Sorties" value={fleetSummary.flying} color="success" />
        <UnitChip label="Low Energy" value={fleetSummary.lowBattery} color="danger" />
      </div>

      {actionBanner && (
        <div className={`bg-${actionBanner.type === 'success' ? 'lesnar-success' : 'lesnar-danger'}/10 border border-${actionBanner.type === 'success' ? 'lesnar-success' : 'lesnar-danger'}/30 rounded-2xl p-4 flex items-center justify-between slide-down`}>
          <div className="flex items-center space-x-3">
            <Zap className={`h-5 w-5 text-${actionBanner.type === 'success' ? 'lesnar-success' : 'lesnar-danger'}`} />
            <p className={`text-sm font-mono text-${actionBanner.type === 'success' ? 'lesnar-success' : 'lesnar-danger'} uppercase font-bold tracking-widest`}>{actionBanner.message}</p>
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
            {filteredDrones.map(drone => (
              <div
                key={drone.drone_id}
                onClick={() => setSelectedDrone(drone)}
                className={`card p-4 cursor-pointer group transition-all ${selectedDrone?.drone_id === drone.drone_id
                    ? 'border-lesnar-accent/40 bg-lesnar-accent/5'
                    : 'border-white/5 hover:border-white/20'
                  }`}
              >
                <div className="flex justify-between items-start">
                  <div className="flex items-center space-x-3">
                    <div className={`h-2 w-2 rounded-full ${drone.altitude > 1 ? 'bg-lesnar-success animate-pulse' : drone.armed ? 'bg-lesnar-warning' : 'bg-gray-600'}`} />
                    <span className="text-sm font-black text-white uppercase tracking-tighter">{drone.drone_id}</span>
                  </div>
                  <span className="text-[9px] font-mono text-gray-600 uppercase">{drone.mode}</span>
                </div>
                <div className="mt-4 flex justify-between items-end">
                  <div className="space-y-1">
                    <p className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">ALT: {Number(drone.altitude || 0).toFixed(1)}M</p>
                    <p className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">SPD: {Number(drone.speed || 0).toFixed(1)}MS</p>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Zap className={`h-3 w-3 ${drone.battery < 20 ? 'text-lesnar-danger animate-bounce' : 'text-lesnar-success'}`} />
                    <span className="text-xs font-mono font-bold text-white">{Math.round(drone.battery)}%</span>
                  </div>
                </div>
              </div>
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
                    <ControlButton
                      icon={selectedDrone.armed ? PowerOff : Power}
                      label={selectedDrone.armed ? 'DISARM' : 'ARM'}
                      color={selectedDrone.armed ? 'danger' : 'warning'}
                      onClick={() => handleDroneAction(selectedDrone.armed ? 'disarm' : 'arm', selectedDrone.drone_id)}
                    />
                    <ControlButton
                      icon={selectedDrone.altitude > 1 ? PlaneLanding : Plane}
                      label={selectedDrone.altitude > 1 ? 'LAND' : 'TAKEOFF'}
                      color={selectedDrone.altitude > 1 ? 'accent' : 'success'}
                      onClick={() => handleDroneAction(selectedDrone.altitude > 1 ? 'land' : 'takeoff', selectedDrone.drone_id, takeoffAlt)}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
                  <DataBlock label="Latitude" value={Number(selectedDrone.latitude || 0).toFixed(6)} />
                  <DataBlock label="Longitude" value={Number(selectedDrone.longitude || 0).toFixed(6)} />
                  <DataBlock label="Heading" value={`${Math.round(selectedDrone.heading || 0)}°`} />
                  <DataBlock label="Voltage" value="12.4V" />
                </div>
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
                        <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
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
                      <button className="btn-primary mt-4 self-end h-9">INITIATE GOTO</button>
                    </div>
                  </div>
                </div>

                <div className="card">
                  <h3 className="text-sm font-black text-white uppercase tracking-widest mb-6 flex items-center">
                    <Activity className="h-4 w-4 mr-2 text-lesnar-success" />
                    System Telemetry
                  </h3>
                  <div className="space-y-4">
                    <TelemetryRow label="ESC Status" ok />
                    <TelemetryRow label="GPS Lock" ok={selectedDrone.gps_fix > 2} />
                    <TelemetryRow label="IMU Health" ok />
                    <TelemetryRow label="UAVCAN Link" ok />
                    <div className="pt-4 mt-4 border-t border-white/5">
                      <button
                        onClick={() => handleDroneAction('delete', selectedDrone.drone_id)}
                        className="text-[10px] font-mono text-lesnar-danger uppercase hover:underline flex items-center"
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

function ControlButton({ icon: Icon, label, color, onClick }) {
  const colors = {
    accent: 'hover:bg-lesnar-accent/20 text-lesnar-accent border-lesnar-accent/30',
    warning: 'hover:bg-lesnar-warning/20 text-lesnar-warning border-lesnar-warning/30',
    success: 'hover:bg-lesnar-success/20 text-lesnar-success border-lesnar-success/30',
    danger: 'hover:bg-lesnar-danger/20 text-lesnar-danger border-lesnar-danger/30',
  };
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center justify-center w-20 h-20 rounded-2xl border transition-all ${colors[color]}`}
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
