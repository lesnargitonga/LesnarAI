import React, { useEffect, useState } from 'react';
import api from '../api';
import { MapContainer, TileLayer, Marker, Popup, useMap, GeoJSON, Polygon, Polyline } from 'react-leaflet';
import L from 'leaflet';
import {
  Navigation,
  Shield,
  Activity,
  Maximize2
} from 'lucide-react';
import { useDrones } from '../context/DroneContext';
import { getDroneFlags } from '../utils/droneState';
import { MAP_TILE_ATTRIBUTION, MAP_TILE_FALLBACK_URL, MAP_TILE_URL, OPERATIONAL_BOUNDARY } from '../config';
import { normalizeBoundary } from '../utils/operational';
import { subscribeQuickSelect } from './TacticalHotkeys';
import { getMapTileProfile, readUiPreferences } from '../utils/uiPreferences';
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
  const { altitude, battery, flying } = getDroneFlags(drone);
  const heading = Number(drone.heading) || 0;
  const isCritical = drone.mode === 'EMERGENCY' || battery < 20;
  const color = isCritical ? '#FF1F6D' : (flying || altitude > 1 ? '#00FF9D' : '#00FDFF');

  return L.divIcon({
    className: 'tactical-drone-marker',
    html: `
      <div style="transform: rotate(${heading}deg); transition: transform 0.5s ease-out;">
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
    const validDrones = drones.filter(
      (drone) => Number.isFinite(Number(drone.latitude)) && Number.isFinite(Number(drone.longitude))
    );
    if (validDrones.length > 0) {
      const group = new L.featureGroup(
        validDrones.map((drone) => L.marker([Number(drone.latitude), Number(drone.longitude)]))
      );
      map.fitBounds(group.getBounds().pad(0.2));
    }
  }, [drones, map, autoFollow]);
  return null;
}

function SelectedDroneFocus({ drone }) {
  const map = useMap();
  useEffect(() => {
    if (!drone) return;
    const lat = Number(drone.latitude);
    const lon = Number(drone.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    map.flyTo([lat, lon], Math.max(map.getZoom(), 14), { animate: true, duration: 0.8 });
  }, [drone, map]);
  return null;
}

function DroneMap({ socket, linkMetrics }) {
  const { drones, updateTelemetry } = useDrones();
  const [autoFollow, setAutoFollow] = useState(true);
  const [obstacles, setObstacles] = useState(null);
  const [hudVisible, setHudVisible] = useState(true);
  const [selectedDroneId, setSelectedDroneId] = useState(null);
  const boundary = normalizeBoundary(OPERATIONAL_BOUNDARY);
  const [replayMode, setReplayMode] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [uiPrefs, setUiPrefs] = useState(() => readUiPreferences());

  useEffect(() => {
    const handler = (event) => setUiPrefs(event.detail || readUiPreferences());
    window.addEventListener('lesnar:ui-preferences', handler);
    return () => window.removeEventListener('lesnar:ui-preferences', handler);
  }, []);

  const mapTileProfile = getMapTileProfile(uiPrefs.mapProvider);

  const selectedDrone = drones.find((drone) => drone.drone_id === selectedDroneId) || null;

  useEffect(() => {
    if (socket) {
      socket.on('telemetry_update', (data) => updateTelemetry(data));
      return () => socket.off('telemetry_update');
    }
  }, [socket, updateTelemetry]);

  useEffect(() => {
    api.get('/api/obstacles').then(res => setObstacles(res.data)).catch(() => setObstacles(null));
  }, []);

  useEffect(() => subscribeQuickSelect((droneId) => {
    if (droneId) {
      setSelectedDroneId(droneId);
      setAutoFollow(false);
    }
  }), []);

  useEffect(() => {
    if (!replayMode || !selectedDroneId) {
      setHistory([]);
      setHistoryIndex(0);
      return;
    }
    api.get(`/api/drones/${selectedDroneId}/history?limit=300`)
      .then((res) => {
        const samples = Array.isArray(res.data?.samples) ? res.data.samples : [];
        setHistory(samples);
        setHistoryIndex(Math.max(0, samples.length - 1));
      })
      .catch(() => {
        setHistory([]);
        setHistoryIndex(0);
      });
  }, [replayMode, selectedDroneId]);

  const replaySample = history[historyIndex] || null;

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
            onClick={() => setReplayMode((prev) => !prev)}
            className={`glass-dark border p-3 rounded-xl transition-all ${replayMode ? 'border-lesnar-warning/50 text-lesnar-warning' : 'border-white/10 text-gray-500'}`}
            title="Replay telemetry history"
          >
            <Activity className="h-5 w-5" />
          </button>
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
          zoom={Number(uiPrefs.defaultZoom) || 12}
          zoomControl={false}
          className="w-full h-full bg-navy-black"
        >
          <TileLayer
            attribution={MAP_TILE_URL ? MAP_TILE_ATTRIBUTION : mapTileProfile.attribution}
            url={MAP_TILE_URL || mapTileProfile.url || MAP_TILE_FALLBACK_URL}
          />

          {boundary.length > 2 && (
            <Polygon
              positions={boundary}
              pathOptions={{ color: '#FFCE00', weight: 2, fillOpacity: 0.05, dashArray: '6, 6' }}
            />
          )}

          {!linkMetrics?.degradedMode && obstacles && (
            <GeoJSON
              data={obstacles}
              style={{ color: '#FF1F6D', weight: 1, fillOpacity: 0.1, dashArray: '5, 5' }}
            />
          )}

          <MapUpdater drones={drones} autoFollow={autoFollow} />
          <SelectedDroneFocus drone={!autoFollow ? selectedDrone : null} />

          {uiPrefs.showFlightPaths && replayMode && history.length > 1 && (
            <Polyline
              positions={history.map((sample) => [Number(sample.latitude), Number(sample.longitude)])}
              pathOptions={{ color: '#FFCE00', weight: 2 }}
            />
          )}

          {replayMode && replaySample && Number.isFinite(Number(replaySample.latitude)) && Number.isFinite(Number(replaySample.longitude)) && (
            <Marker
              position={[Number(replaySample.latitude), Number(replaySample.longitude)]}
              icon={createTacticalDroneIcon({ ...selectedDrone, ...replaySample })}
            />
          )}

          {!replayMode && drones
            .filter((drone) => Number.isFinite(Number(drone.latitude)) && Number.isFinite(Number(drone.longitude)))
            .map((drone) => {
            const altitude = Number(drone.altitude) || 0;
            const speed = Number(drone.speed) || 0;
            const battery = Number(drone.battery) || 0;
            return (
            <Marker
              key={drone.drone_id}
              position={[Number(drone.latitude), Number(drone.longitude)]}
              icon={createTacticalDroneIcon(drone)}
              eventHandlers={{ click: () => setSelectedDroneId(drone.drone_id) }}
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
                      <span className="text-white">{altitude.toFixed(1)}M</span>
                    </div>
                    <div className="flex justify-between font-bold">
                      <span className="text-gray-500 uppercase">Velocity</span>
                      <span className="text-lesnar-accent">{speed.toFixed(2)} M/S</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500 uppercase">Power</span>
                      <span className={battery < 20 ? 'text-lesnar-danger' : 'text-white'}>{battery.toFixed(0)}%</span>
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      setSelectedDroneId(drone.drone_id);
                      setAutoFollow(false);
                    }}
                    className="w-full mt-4 py-2 bg-lesnar-accent/10 border border-lesnar-accent/30 text-[10px] text-lesnar-accent uppercase font-bold rounded-lg hover:bg-lesnar-accent/20 transition-all"
                  >
                    Establish Direct Link
                  </button>
                </div>
              </Popup>
            </Marker>
            );
          })}
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
            {drones.map((drone) => {
              const { altitude, speed, flying } = getDroneFlags(drone);
              const isSelected = selectedDroneId === drone.drone_id;
              return (
              <div
                key={drone.drone_id}
                onClick={() => {
                  setSelectedDroneId(drone.drone_id);
                  setAutoFollow(false);
                }}
                className={`p-4 rounded-xl bg-white/5 border transition-all group cursor-pointer ${isSelected ? 'border-lesnar-accent/60 bg-lesnar-accent/5' : 'border-white/10 hover:border-lesnar-accent/30'}`}
              >
                <div className="flex justify-between items-center mb-2">
                  <span className="text-[10px] font-bold text-white uppercase group-hover:text-lesnar-accent transition-colors">{drone.drone_id}</span>
                  <div className={`h-1.5 w-1.5 rounded-full ${flying ? 'bg-lesnar-success animate-pulse' : 'bg-gray-600'}`} />
                </div>
                <div className="flex justify-between text-[8px] font-mono text-gray-500">
                  <span>ALT: {altitude.toFixed(1)}M</span>
                  <span>SPD: {speed.toFixed(1)}M/S</span>
                </div>
              </div>
            );
            })}
          </div>

          <div className="pt-4 border-t border-white/5">
            <div className="bg-lesnar-accent/5 p-4 rounded-xl border border-lesnar-accent/10">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono text-gray-400 uppercase">Signal Stability</span>
                <span className={`text-[10px] font-mono ${linkMetrics?.degradedMode ? 'text-lesnar-warning' : 'text-lesnar-success'}`}>{linkMetrics?.degradedMode ? 'DEGRADED' : '98%'}</span>
              </div>
              <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                <div className={`h-full ${linkMetrics?.degradedMode ? 'w-[55%] bg-lesnar-warning' : 'w-[98%] bg-lesnar-accent'}`} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Map Scale Hook - Decorative */}
      {replayMode && history.length > 1 && (
        <div className="absolute left-10 right-10 bottom-24 z-[1000] glass-dark border border-white/10 rounded-2xl px-4 py-3 flex items-center space-x-4">
          <span className="text-[10px] font-mono uppercase text-lesnar-warning whitespace-nowrap">Replay</span>
          <input
            type="range"
            min={0}
            max={Math.max(0, history.length - 1)}
            value={historyIndex}
            onChange={(e) => setHistoryIndex(Number(e.target.value))}
            className="flex-1 accent-lesnar-warning"
          />
          <span className="text-[10px] font-mono uppercase text-gray-400 whitespace-nowrap">{replaySample?.timestamp || '—'}</span>
        </div>
      )}

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
