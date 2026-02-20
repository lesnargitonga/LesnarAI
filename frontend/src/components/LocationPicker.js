import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { MapContainer, TileLayer, Marker, Popup, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for default markers in React Leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const DEFAULT_PRESETS = [
  { key: 'nyc', label: 'New York City (Default)', lat: 40.7128, lng: -74.0060 },
  { key: 'times_square', label: 'Times Square', lat: 40.7589, lng: -73.9851 },
  { key: 'statue_liberty', label: 'Statue of Liberty', lat: 40.6892, lng: -74.0445 },
];

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function parseLatLng(text) {
  if (!text) return null;
  const m = String(text).trim().match(/^\s*(-?\d+(?:\.\d+)?)\s*[,\s]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (!m) return null;
  const lat = Number(m[1]);
  const lng = Number(m[2]);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  return { lat, lng };
}

function ClickCapture({ onPick }) {
  useMapEvents({
    click(e) {
      onPick && onPick(e.latlng);
    },
  });
  return null;
}

export default function LocationPicker({
  title = 'Location',
  initialLat = 40.7128,
  initialLng = -74.0060,
  presets = DEFAULT_PRESETS,
  onConfirm,
}) {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [pending, setPending] = useState({ lat: initialLat, lng: initialLng });
  const [pendingLabel, setPendingLabel] = useState('');
  const [confirmed, setConfirmed] = useState({ lat: initialLat, lng: initialLng, label: '' });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const mapRef = useRef(null);

  const localSuggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return presets;
    return presets.filter(p => p.label.toLowerCase().includes(q)).slice(0, 6);
  }, [query, presets]);

  // Debounced suggest
  useEffect(() => {
    let cancelled = false;
    const q = query.trim();
    const parsed = parseLatLng(q);
    if (parsed) {
      setSuggestions([]);
      setPending({ lat: parsed.lat, lng: parsed.lng });
      setPendingLabel(`${parsed.lat.toFixed(6)}, ${parsed.lng.toFixed(6)}`);
      return;
    }

    if (q.length < 3) {
      setSuggestions([]);
      setErr(null);
      return;
    }

    setLoading(true);
    setErr(null);
    const t = setTimeout(async () => {
      try {
        const res = await axios.get('/api/geocode/suggest', { params: { q } });
        if (cancelled) return;
        if (res.data?.success) {
          setSuggestions(res.data.results || []);
        } else {
          setSuggestions([]);
        }
      } catch (e) {
        if (!cancelled) {
          setErr('Suggestions unavailable');
          setSuggestions([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query]);

  const centerMap = (lat, lng) => {
    const map = mapRef.current;
    if (!map) return;
    const clat = clamp(lat, -90, 90);
    const clng = clamp(lng, -180, 180);
    map.setView([clat, clng], Math.max(map.getZoom(), 13));
  };

  const pickLatLng = async (lat, lng, labelHint = '') => {
    setPending({ lat, lng });
    setPendingLabel(labelHint || `${lat.toFixed(6)}, ${lng.toFixed(6)}`);
    centerMap(lat, lng);
    // Try reverse geocode for confirmation label
    try {
      const res = await axios.get('/api/geocode/reverse', { params: { lat, lng } });
      if (res.data?.success && res.data.display_name) {
        setPendingLabel(res.data.display_name);
      }
    } catch {
      // ignore
    }
  };

  const confirm = () => {
    const next = { lat: pending.lat, lng: pending.lng, label: pendingLabel };
    setConfirmed(next);
    onConfirm && onConfirm(next);
  };

  const showSuggestionList = query.trim().length > 0;

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700 mb-1">{title}</label>

      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder="Type an address/place, paste Google Maps, or 'lat,lng'"
        />
        {(loading || err) && (
          <div className="absolute right-3 top-2.5 text-xs text-gray-500">
            {loading ? 'Searching…' : err}
          </div>
        )}
      </div>

      {/* Suggestions */}
      <div className="border rounded-md bg-white overflow-hidden">
        {!showSuggestionList && (
          <div className="px-3 py-2 text-xs text-gray-500">Suggestions (presets)</div>
        )}
        <div className="max-h-40 overflow-auto">
          {(showSuggestionList ? suggestions : localSuggestions).map((s) => {
            const label = s.display_name || s.label;
            const lat = Number(s.lat);
            const lng = Number(s.lng);
            const key = s.key || `${label}-${lat}-${lng}`;
            return (
              <button
                type="button"
                key={key}
                onClick={() => pickLatLng(lat, lng, label)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 border-t first:border-t-0"
              >
                <div className="text-gray-900 truncate">{label}</div>
                <div className="text-xs text-gray-500">{lat.toFixed(6)}, {lng.toFixed(6)}</div>
              </button>
            );
          })}
          {(showSuggestionList && suggestions.length === 0 && query.trim().length >= 3 && !loading) && (
            <div className="px-3 py-3 text-sm text-gray-500">No suggestions. Try a broader query or click the map.</div>
          )}
        </div>
      </div>

      {/* Map */}
      <div className="border rounded-md overflow-hidden">
        <MapContainer
          center={[pending.lat, pending.lng]}
          zoom={13}
          scrollWheelZoom={true}
          zoomControl={true}
          className="w-full"
          style={{ height: 220 }}
          ref={mapRef}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <ClickCapture onPick={(ll) => pickLatLng(ll.lat, ll.lng)} />
          <Marker position={[pending.lat, pending.lng]}>
            <Popup>
              <div className="text-sm">
                <div className="font-medium">Selected</div>
                <div>{pending.lat.toFixed(6)}, {pending.lng.toFixed(6)}</div>
              </div>
            </Popup>
          </Marker>
        </MapContainer>
      </div>

      {/* Confirmation */}
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs text-gray-600 flex-1 truncate" title={pendingLabel || ''}>
          Pending: {pendingLabel ? pendingLabel : `${pending.lat.toFixed(6)}, ${pending.lng.toFixed(6)}`}
        </div>
        <button
          type="button"
          onClick={confirm}
          className="btn-primary py-2 px-3"
        >
          Confirm
        </button>
      </div>

      <div className="text-xs text-gray-500">
        Confirmed: {confirmed.label ? confirmed.label : `${confirmed.lat.toFixed(6)}, ${confirmed.lng.toFixed(6)}`}
      </div>
    </div>
  );
}
