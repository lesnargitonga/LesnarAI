import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { MapContainer, TileLayer, Marker, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import { Search, MapPin, Check, Navigation } from 'lucide-react';
import 'leaflet/dist/leaflet.css';

// Fix for default markers
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const DEFAULT_PRESETS = [
  { key: 'hq', label: 'Tactical HQ (NYC)', lat: 40.7128, lng: -74.0060 },
  { key: 'perimeter_a', label: 'Perimeter Sector Alpha', lat: 40.7306, lng: -73.9352 },
  { key: 'outpost_1', label: 'Surveillance Outpost 01', lat: 40.6782, lng: -73.9442 },
];

function ClickCapture({ onPick }) {
  useMapEvents({
    click(e) {
      onPick && onPick(e.latlng);
    },
  });
  return null;
}

export default function LocationPicker({
  title = 'Target Selection',
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

  useEffect(() => {
    let cancelled = false;
    const q = query.trim();
    if (q.length < 3) {
      setSuggestions([]);
      setErr(null);
      return;
    }

    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const res = await axios.get('/api/geocode/suggest', { params: { q } });
        if (cancelled) return;
        if (res.data?.success) setSuggestions(res.data.results || []);
      } catch (e) {
        if (!cancelled) setErr('GEO_LINK_FAILURE');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 400);

    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query]);

  const pickLatLng = (lat, lng, labelHint = '') => {
    setPending({ lat, lng });
    setPendingLabel(labelHint || `${lat.toFixed(6)}, ${lng.toFixed(6)}`);
    mapRef.current?.setView([lat, lng], 14);
  };

  const handleConfirm = () => {
    const next = { ...pending, label: pendingLabel };
    setConfirmed(next);
    onConfirm && onConfirm(next);
  };

  return (
    <div className="space-y-4 fade-in">
      <h3 className="text-[10px] font-mono text-gray-500 uppercase tracking-[0.2em] flex items-center">
        <MapPin className="h-3 w-3 mr-2 text-lesnar-accent" />
        {title}
      </h3>

      <div className="relative group">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-600 group-hover:text-lesnar-accent transition-colors" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="SEARCH_COORDINATES_OR_PLACE..."
          className="w-full bg-black/60 border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-xs font-mono text-white focus:outline-none focus:border-lesnar-accent/40"
        />
        {loading && <div className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 border-2 border-lesnar-accent/30 border-t-lesnar-accent rounded-full animate-spin" />}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar pr-2">
          {(query ? suggestions : localSuggestions).map((s, idx) => (
            <button
              key={idx}
              onClick={() => pickLatLng(Number(s.lat), Number(s.lng), s.display_name || s.label)}
              className="w-full text-left p-3 rounded-xl border border-white/5 bg-white/[0.02] hover:bg-lesnar-accent/5 hover:border-lesnar-accent/20 transition-all group"
            >
              <div className="text-[11px] font-bold text-gray-300 truncate group-hover:text-white uppercase tracking-tight">{s.display_name || s.label}</div>
              <div className="text-[9px] font-mono text-gray-600 uppercase mt-1">LAT: {Number(s.lat).toFixed(4)} // LNG: {Number(s.lng).toFixed(4)}</div>
            </button>
          ))}
        </div>

        <div className="h-64 rounded-2xl border border-white/10 overflow-hidden relative shadow-inner">
          <MapContainer
            center={[pending.lat, pending.lng]}
            zoom={13}
            className="w-full h-full grayscale brightness-50 contrast-125 invert-[0.9] hue-rotate-180"
            ref={mapRef}
            zoomControl={false}
          >
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            <ClickCapture onPick={ll => pickLatLng(ll.lat, ll.lng)} />
            <Marker position={[pending.lat, pending.lng]} />
          </MapContainer>
          <div className="absolute top-2 right-2 z-[1000] p-1.5 bg-black/60 backdrop-blur-md rounded-lg border border-white/10">
            <Navigation className="h-3 w-3 text-lesnar-accent" />
          </div>
        </div>
      </div>

      <div className="bg-black/40 border border-white/5 rounded-2xl p-4 flex items-center justify-between">
        <div className="min-w-0 pr-4">
          <p className="text-[9px] font-mono text-gray-600 uppercase tracking-widest mb-1">Target_Acquired</p>
          <p className="text-xs font-mono text-white truncate uppercase tracking-tighter">
            {pendingLabel || 'NO_FIX'}
          </p>
        </div>
        <button
          onClick={handleConfirm}
          className="btn-primary py-2 px-6 flex items-center"
        >
          <Check className="h-4 w-4 mr-2" />
          LOCK TARGET
        </button>
      </div>

      {confirmed.label && (
        <div className="text-[9px] font-mono text-lesnar-success uppercase flex items-center opacity-60">
          <div className="h-1 w-1 bg-lesnar-success rounded-full mr-2 animate-pulse" />
          CONFIRMED: {confirmed.label}
        </div>
      )}
    </div>
  );
}
