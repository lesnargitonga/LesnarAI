import React, { useEffect, useRef, useState } from 'react';
import api from '../api';
import { MapContainer, TileLayer, Marker, Popup, useMap, LayersControl, useMapEvents, GeoJSON } from 'react-leaflet';
import L from 'leaflet';
import {
  Crosshair,
  Navigation,
  Map as MapIcon,
  Shield,
  Activity,
  Maximize2
} from 'lucide-react';
import { useDrones } from '../context/DroneContext';
import 'leaflet/dist/leaflet.css';

// Fix for default markers
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// Tactical Drone Icon
const createTacticalDroneIcon = (drone) => {
  const isCritical = drone.mode === 'EMERGENCY' || drone.battery < 20;
  const color = isCritical ? '#FF1F6D' : (drone.altitude > 1 ? '#00FF9D' : '#00FDFF');

  return L.divIcon({
    className: 'tactical-drone-marker',
    html: `
      <div style="transform: rotate(${drone.heading}deg); transition: transform 0.5s ease-out;">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M20 5L32 30L20 24L8 30L20 5Z" fill="${color}" fill-opacity="0.2" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>
          <circle cx="20" cy="24" r="3" fill="${color}" />
          ${isCritical ? `<circle cx="20" cy="24" r="10" stroke="${color}" stroke-width="1" opacity="0.5">
            <animate attributeName="r" from="5" to="15" dur="1s" repeatCount="indefinite" />
            <animate attributeName="opacity" from="0.5" to="0" dur="1s" repeatCount="indefinite" />
          </circle>` : ''}
        </svg>
      </div>
    `,
    iconSize: [40, 40],
    iconAnchor: [20, 20]
  });
};

function MapUpdater({ drones, autoFollow }) {
  const map = useMap();
  useEffect(() => {
    if (!autoFollow) return;
    if (drones.length > 0) {
      const group = new L.featureGroup(
        drones.map(drone => L.marker([drone.latitude, drone.longitude]))
      );
      map.fitBounds(group.getBounds().pad(0.2));
    }
  }, [drones, map, autoFollow]);
  return null;
}

function DroneMap({ socket }) {
  const { drones, updateTelemetry } = useDrones();
  const [autoFollow, setAutoFollow] = useState(true);
  const [obstacles, setObstacles] = useState(null);
  const [hudVisible, setHudVisible] = useState(true);

  useEffect(() => {
    if (socket) {
      socket.on('telemetry_update', (data) => updateTelemetry(data));
      return () => socket.off('telemetry_update');
    }
  }, [socket, updateTelemetry]);

  useEffect(() => {
    api.get('/api/obstacles').then(res => setObstacles(res.data)).catch(() => setObstacles(null));
  }, []);

  return (
    <div className="h-full relative overflow-hidden flex flex-col fade-in">
      {/* HUD Header */}
      <div className="absolute top-6 left-6 right-6 z-[1000] flex justify-between pointer-events-none">
        <div className="glass-dark border border-white/10 p-4 rounded-2xl pointer-events-auto flex items-center space-x-6">
          <div className="flex items-center space-x-3 border-r border-white/10 pr-6">
            <div className="h-10 w-10 bg-lesnar-accent/10 border border-lesnar-accent/30 rounded-xl flex items-center justify-center neo-glow">
              <Navigation className="h-6 w-6 text-lesnar-accent" />
            </div>
            <div>
              <h2 className="text-sm font-black text-white uppercase tracking-widest">Tactical HUD</h2>
              <p className="text-[10px] font-mono text-lesnar-accent uppercase">Live Ops Tracking</p>
            </div>
          </div>

          <div className="flex items-center space-x-4 text-[10px] font-mono text-gray-400">
            <div className="flex flex-col">
              <span className="uppercase text-gray-600">Assets</span>
              <span className="text-white font-bold">{drones.length} ACTIVE</span>
            </div>
            <div className="flex flex-col">
              <span className="uppercase text-gray-600">Region</span>
              <span className="text-white font-bold tracking-tighter">GLOBAL_SECTOR_7</span>
            </div>
          </div>
        </div>

        <div className="flex space-x-3 pointer-events-auto">
          <button
            onClick={() => setAutoFollow(!autoFollow)}
            className={`glass-dark border p-3 rounded-xl transition-all ${autoFollow ? 'border-lesnar-accent/50 text-lesnar-accent' : 'border-white/10 text-gray-500'}`}
            title="Auto-Follow Active Assets"
          >
            <Maximize2 className="h-5 w-5" />
          </button>
          <button
            onClick={() => setHudVisible(!hudVisible)}
            className="glass-dark border border-white/10 p-3 rounded-xl text-gray-500 hover:text-white transition-all"
          >
            <Shield className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Map Implementation */}
      <div className="flex-1 filter grayscale brightness-50 contrast-125">
        <MapContainer
          center={[0, 0]}
          zoom={3}
          zoomControl={false}
          className="w-full h-full bg-navy-black"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />

          {obstacles && (
            <GeoJSON
              data={obstacles}
              style={{ color: '#FF1F6D', weight: 1, fillOpacity: 0.1, dashArray: '5, 5' }}
            />
          )}

          <MapUpdater drones={drones} autoFollow={autoFollow} />

          {drones.map((drone) => (
            <Marker
              key={drone.drone_id}
              position={[drone.latitude, drone.longitude]}
              icon={createTacticalDroneIcon(drone)}
            >
              <Popup className="tactical-popup">
                <div className="p-4 bg-navy-black text-white font-mono min-w-[200px]">
                  <div className="flex justify-between items-center mb-4 border-b border-white/10 pb-2">
                    <span className="text-xs font-bold text-lesnar-accent">{drone.drone_id}</span>
                    <span className="text-[8px] bg-white/5 px-2 py-0.5 rounded text-gray-400 uppercase">Node ID-X4</span>
                  </div>

                  <div className="space-y-3 text-[10px]">
                    <div className="flex justify-between">
                      <span className="text-gray-500 uppercase">Mode</span>
                      <span className={drone.mode === 'EMERGENCY' ? 'text-lesnar-danger' : 'text-lesnar-success'}>{drone.mode}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500 uppercase">Altitude</span>
                      <span className="text-white">{drone.altitude.toFixed(1)}M</span>
                    </div>
                    <div className="flex justify-between font-bold">
                      <span className="text-gray-500 uppercase">Velocity</span>
                      <span className="text-lesnar-accent">{drone.speed.toFixed(2)} M/S</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500 uppercase">Power</span>
                      <span className={drone.battery < 20 ? 'text-lesnar-danger' : 'text-white'}>{drone.battery.toFixed(0)}%</span>
                    </div>
                  </div>

                  <button className="w-full mt-4 py-2 bg-lesnar-accent/10 border border-lesnar-accent/30 text-[10px] text-lesnar-accent uppercase font-bold rounded-lg hover:bg-lesnar-accent/20 transition-all">
                    Establish Direct Link
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>

      {/* Side HUD Panel */}
      {hudVisible && drones.length > 0 && (
        <div className="absolute top-28 right-6 bottom-6 w-72 glass-dark border border-white/5 rounded-2xl overflow-hidden z-[1000] flex flex-col p-6 space-y-6 slide-in-right">
          <div className="flex items-center space-x-2 text-white">
            <Activity className="h-4 w-4 text-lesnar-accent" />
            <h3 className="text-xs font-bold uppercase tracking-widest">Active Sorties</h3>
          </div>

          <div className="flex-1 overflow-y-auto space-y-4 scrollbar-hide">
            {drones.map(drone => (
              <div key={drone.drone_id} className="p-4 rounded-xl bg-white/5 border border-white/10 hover:border-lesnar-accent/30 transition-all group cursor-pointer">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-[10px] font-bold text-white uppercase group-hover:text-lesnar-accent transition-colors">{drone.drone_id}</span>
                  <div className={`h-1.5 w-1.5 rounded-full ${drone.altitude > 1 ? 'bg-lesnar-success animate-pulse' : 'bg-gray-600'}`} />
                </div>
                <div className="flex justify-between text-[8px] font-mono text-gray-500">
                  <span>ALT: {drone.altitude.toFixed(1)}M</span>
                  <span>SPD: {drone.speed.toFixed(1)}M/S</span>
                </div>
              </div>
            ))}
          </div>

          <div className="pt-4 border-t border-white/5">
            <div className="bg-lesnar-accent/5 p-4 rounded-xl border border-lesnar-accent/10">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono text-gray-400 uppercase">Signal Stability</span>
                <span className="text-[10px] font-mono text-lesnar-success">98%</span>
              </div>
              <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                <div className="h-full w-[98%] bg-lesnar-accent" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Map Scale Hook - Decorative */}
      <div className="absolute bottom-10 left-10 z-[1000] pointer-events-none">
        <div className="flex flex-col space-y-2">
          <div className="w-40 h-[10px] border-b border-l border-r border-lesnar-accent/40 relative">
            <div className="absolute inset-0 flex justify-between px-1">
              <div className="h-full w-[1px] bg-lesnar-accent/40" />
              <div className="h-full w-[1px] bg-lesnar-accent/40" />
              <div className="h-full w-[1px] bg-lesnar-accent/40" />
            </div>
          </div>
          <span className="text-[8px] font-mono text-lesnar-accent uppercase tracking-widest pl-1">Grid Scale: 1:25,000</span>
        </div>
      </div>
    </div>
  );
}

export default DroneMap;
