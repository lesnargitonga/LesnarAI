import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { MapContainer, TileLayer, Marker, Popup, useMap, LayersControl, useMapEvents, GeoJSON } from 'react-leaflet';
import L from 'leaflet';
import { useDrones } from '../context/DroneContext';
import 'leaflet/dist/leaflet.css';

// Fix for default markers in React Leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// Custom drone icon
const createDroneIcon = (status, battery) => {
  const getColor = () => {
    if (status === 'EMERGENCY' || battery < 20) return '#ef4444';
    if (status === 'AUTO' || status === 'MISSION') return '#22c55e';
    if (status === 'ARMED' || status === 'TAKEOFF') return '#f59e0b';
    return '#6b7280';
  };

  return L.divIcon({
    className: 'custom-drone-marker',
    html: `
      <div style="
        background-color: ${getColor()};
        border: 2px solid white;
        border-radius: 50%;
        width: 20px;
        height: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        display: flex;
        align-items: center;
        justify-content: center;
      ">
        <div style="
          width: 8px;
          height: 8px;
          background-color: white;
          border-radius: 50%;
        "></div>
      </div>
    `,
    iconSize: [20, 20],
    iconAnchor: [10, 10]
  });
};

function MapUpdater({ drones, autoFollow }) {
  const map = useMap();

  useEffect(() => {
    if (!autoFollow) return;
    if (drones.length > 0) {
      const group = new L.featureGroup(
        drones.map(drone =>
          L.marker([drone.latitude, drone.longitude])
        )
      );
      map.fitBounds(group.getBounds().pad(0.1));
    }
  }, [drones, map, autoFollow]);

  return null;
}

function MapClicker({ onClick }) {
  useMapEvents({
    click(e) {
      if (onClick) onClick(e);
    }
  });
  return null;
}

function MapInteractionWatcher({ onUserInteract }) {
  useMapEvents({
    zoomstart() {
      onUserInteract && onUserInteract();
    },
    dragstart() {
      onUserInteract && onUserInteract();
    }
  });
  return null;
}

function DroneMap({ socket }) {
  const { drones, updateTelemetry } = useDrones();
  const mapRef = useRef();
  const [autoFollow, setAutoFollow] = useState(false);
  const [obstacles, setObstacles] = useState(null);
  const [rpcOk, setRpcOk] = useState(null);

  useEffect(() => {
    if (socket) {
      socket.on('telemetry_update', (data) => {
        updateTelemetry(data);
      });

      return () => {
        socket.off('telemetry_update');
      };
    }
  }, [socket, updateTelemetry]);

  useEffect(() => {
    // Load obstacles GeoJSON from backend
    axios.get('/api/obstacles')
      .then(res => setObstacles(res.data))
      .catch(err => {
        console.error('Failed to load obstacles', err);
        setObstacles(null);
      });
  }, []);

  useEffect(() => {
    // Poll backend health for AirSim RPC status
    const poll = async () => {
      try {
        const res = await axios.get('/api/health');
        setRpcOk(res.data?.airsim_rpc_ok);
      } catch {
        setRpcOk(null);
      }
    };
    poll();
    const id = setInterval(poll, 20000);
    return () => clearInterval(id);
  }, []);

  const handleMapClick = (e) => {
    const { lat, lng } = e.latlng;
    console.log(`Clicked at: ${lat.toFixed(6)}, ${lng.toFixed(6)}`);
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-white shadow-sm border-b border-gray-200 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Live Map</h1>
            <p className="mt-1 text-sm text-gray-600">
              Real-time drone positions and flight paths
            </p>
          </div>

          <div className="flex items-center space-x-4">
            <div className="text-sm text-gray-600">
              <span className="font-medium">{drones.length}</span> drones active
            </div>

            {/* RPC status */}
            <div className={`px-2 py-1 rounded text-xs font-medium ${rpcOk === true ? 'bg-green-100 text-green-800' : rpcOk === false ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800'}`} title="AirSim RPC connectivity">
              RPC: {rpcOk === true ? 'OK' : rpcOk === false ? 'Not Confirmed' : 'Unknown'}
            </div>

            {/* Legend */}
            <div className="flex items-center space-x-3 text-xs">
              <div className="flex items-center">
                <div className="w-3 h-3 bg-green-500 rounded-full mr-1"></div>
                <span>Flying</span>
              </div>
              <div className="flex items-center">
                <div className="w-3 h-3 bg-yellow-500 rounded-full mr-1"></div>
                <span>Armed</span>
              </div>
              <div className="flex items-center">
                <div className="w-3 h-3 bg-red-500 rounded-full mr-1"></div>
                <span>Emergency</span>
              </div>
              <div className="flex items-center">
                <div className="w-3 h-3 bg-gray-500 rounded-full mr-1"></div>
                <span>Idle</span>
              </div>
            </div>

            {/* Auto-follow toggle */}
            <div className="flex items-center space-x-2">
              <label className="text-sm text-gray-600">Auto-follow</label>
              <button
                onClick={() => setAutoFollow(v => !v)}
                className={`px-2 py-1 text-xs rounded ${autoFollow ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}
                title="Automatically fit all drones into view"
              >
                {autoFollow ? 'On' : 'Off'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Map */}
      <div className="flex-1">
        <MapContainer
          center={[40.7128, -74.0060]}
          zoom={13}
          scrollWheelZoom={true}
          zoomControl={true}
          className="w-full h-full"
          ref={mapRef}
        >
          <LayersControl position="topright">
            <LayersControl.BaseLayer checked name="Street Map">
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
            </LayersControl.BaseLayer>
            <LayersControl.BaseLayer name="Satellite View">
              <TileLayer
                url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                attribution='&copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
              />
            </LayersControl.BaseLayer>
            {obstacles && (
              <LayersControl.Overlay checked name="Obstacles">
                <GeoJSON
                  data={obstacles}
                  style={{ color: '#ef4444', weight: 2, fillOpacity: 0.2 }}
                  onEachFeature={(feature, layer) => {
                    if (feature.properties?.name) {
                      layer.bindPopup(feature.properties.name);
                    }
                  }}
                />
              </LayersControl.Overlay>
            )}
          </LayersControl>

          <MapUpdater drones={drones} autoFollow={autoFollow} />
          <MapClicker onClick={handleMapClick} />
          <MapInteractionWatcher onUserInteract={() => setAutoFollow(false)} />

          {drones.map((drone) => (
            <Marker
              key={drone.drone_id}
              position={[drone.latitude, drone.longitude]}
              icon={createDroneIcon(drone.mode, drone.battery)}
            >
              <Popup>
                <div className="p-2">
                  <h3 className="font-semibold text-gray-900 mb-2">
                    {drone.drone_id}
                  </h3>

                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Status:</span>
                      <span className={`font-medium ${drone.mode === 'EMERGENCY' ? 'text-red-600' :
                          drone.altitude > 1 ? 'text-green-600' :
                            drone.armed ? 'text-yellow-600' :
                              'text-gray-600'
                        }`}>
                        {drone.mode}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-gray-600">Altitude:</span>
                      <span>{drone.altitude.toFixed(1)}m</span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-gray-600">Battery:</span>
                      <span className={`font-medium ${drone.battery < 20 ? 'text-red-600' :
                          drone.battery < 40 ? 'text-yellow-600' :
                            'text-green-600'
                        }`}>
                        {drone.battery.toFixed(0)}%
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-gray-600">Speed:</span>
                      <span>{drone.speed.toFixed(1)} m/s</span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-gray-600">Heading:</span>
                      <span>{drone.heading.toFixed(0)}°</span>
                    </div>
                  </div>

                  <div className="mt-3 pt-2 border-t border-gray-200">
                    <p className="text-xs text-gray-500">
                      Position: {drone.latitude.toFixed(6)}, {drone.longitude.toFixed(6)}
                    </p>
                    <p className="text-xs text-gray-500">
                      Last update: {new Date(drone.timestamp).toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              </Popup>
            </Marker>
          ))}

        </MapContainer>
      </div>
    </div>
  );
}

export default DroneMap;
