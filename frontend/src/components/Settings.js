import React, { useEffect, useState } from 'react';
import api from '../api';
import { Save, RefreshCw, AlertTriangle, Shield, Zap, Globe, Cpu } from 'lucide-react';

function Settings() {
  const [settings, setSettings] = useState({
    maxAltitude: 120,
    maxSpeed: 15,
    batteryWarningLevel: 20,
    batteryCriticalLevel: 5,
    autoLandBattery: 10,
    updateRate: 10,
    logLevel: 'INFO',
    enableWeatherCheck: true,
    enableCollisionAvoidance: true,
    apiHost: window.location.hostname || 'localhost',
    apiPort: 5000,
    enableSSL: window.location.protocol === 'https:',
    mapProvider: 'carto-dark',
    defaultZoom: 12,
    showFlightPaths: true,
    enableNotifications: true
  });

  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const mapConfigToSettings = (cfg) => {
    const drone = (cfg || {}).drone_settings || {};
    const sim = (cfg || {}).simulation_settings || {};
    const api = (cfg || {}).api_settings || {};
    const logging = (cfg || {}).logging || {};
    return {
      ...settings,
      maxAltitude: Number(drone.max_altitude ?? 120),
      maxSpeed: Number(drone.max_speed ?? 15),
      batteryWarningLevel: Number(drone.battery_warning_level ?? 20),
      batteryCriticalLevel: Number(drone.battery_critical_level ?? 5),
      autoLandBattery: Number(drone.auto_land_battery ?? 10),
      updateRate: Number(sim.update_rate ?? 10),
      logLevel: String(logging.level ?? 'INFO'),
      enableWeatherCheck: Boolean(sim.weather_simulation ?? true),
      enableCollisionAvoidance: Boolean(sim.collision_detection ?? true),
      apiHost: String(api.host ?? window.location.hostname ?? 'localhost'),
      apiPort: Number(api.port ?? 5000),
      enableSSL: Boolean(api.enable_ssl ?? false),
    };
  };

  const mapSettingsToConfig = (currentCfg, ui) => {
    const cfg = { ...(currentCfg || {}) };
    cfg.drone_settings = {
      ...(cfg.drone_settings || {}),
      max_speed: Number(ui.maxSpeed),
      max_altitude: Number(ui.maxAltitude),
      battery_warning_level: Number(ui.batteryWarningLevel),
      battery_critical_level: Number(ui.batteryCriticalLevel),
      auto_land_battery: Number(ui.auto_land_battery),
    };
    cfg.simulation_settings = {
      ...(cfg.simulation_settings || {}),
      update_rate: Number(ui.updateRate),
      weather_simulation: Boolean(ui.enableWeatherCheck),
      collision_detection: Boolean(ui.enableCollisionAvoidance),
    };
    cfg.api_settings = {
      ...(cfg.api_settings || {}),
      host: String(ui.apiHost),
      port: Number(ui.apiPort),
      enable_ssl: Boolean(ui.enableSSL),
    };
    cfg.logging = {
      ...(cfg.logging || {}),
      level: String(ui.logLevel || 'INFO'),
    };
    return cfg;
  };

  useEffect(() => {
    const loadConfig = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get('/api/config');
        if (res.data?.success && res.data.config) {
          setSettings(prev => mapConfigToSettings(res.data.config));
        }
      } catch (e) {
        setError('Config_Sync_Error: Backend bridge unreachable');
      } finally {
        setLoading(false);
      }
    };
    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleChange = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setLoading(true);
    setError(null);
    try {
      const current = await api.get('/api/config');
      const merged = mapSettingsToConfig(current.data?.config || {}, settings);
      const res = await api.post('/api/config', { config: merged });
      if (res.data?.success) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } catch (e) {
      setError('Uplink_Failure: Calibration data rejected');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 space-y-10 fade-in pb-24">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between border-l-2 border-lesnar-accent pl-6 py-2">
        <div>
          <h1 className="text-3xl font-black text-white uppercase tracking-tighter">
            System Config <span className="text-lesnar-accent">// CALIBRATION</span>
          </h1>
          <p className="text-xs font-mono text-gray-500 uppercase tracking-widest mt-1">
            Global Parameters & Operational Protocols
          </p>
        </div>

        <div className="mt-4 md:mt-0 flex space-x-3">
          <button onClick={() => window.location.reload()} className="p-2.5 rounded-xl border border-white/10 hover:bg-white/5 transition-colors text-gray-400">
            <RefreshCw className="h-5 w-5" />
          </button>
          <button
            onClick={handleSave}
            disabled={loading}
            className={`btn-primary flex items-center px-6 ${loading ? 'opacity-50' : ''}`}
          >
            <Save className="h-4 w-4 mr-2" />
            {loading ? 'SYNCING...' : 'COMMIT CHANGES'}
          </button>
        </div>
      </div>

      {saved && (
        <div className="bg-lesnar-success/10 border border-lesnar-success/30 rounded-2xl p-4 flex items-center space-x-3 slide-down">
          <Shield className="h-5 w-5 text-lesnar-success" />
          <p className="text-sm font-mono text-lesnar-success uppercase font-bold tracking-widest">Protocol updated successfully</p>
        </div>
      )}

      {error && (
        <div className="bg-lesnar-danger/10 border border-lesnar-danger/30 rounded-2xl p-4 flex items-center space-x-3 slide-down">
          <AlertTriangle className="h-5 w-5 text-lesnar-danger" />
          <p className="text-sm font-mono text-lesnar-danger uppercase font-bold tracking-widest">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Flight Parameters */}
        <div className="card">
          <div className="flex items-center space-x-3 mb-8">
            <div className="p-2 rounded-lg bg-lesnar-accent/10 border border-lesnar-accent/20">
              <Zap className="h-4 w-4 text-lesnar-accent" />
            </div>
            <h3 className="text-sm font-black text-white uppercase tracking-widest">Flight Dynamics</h3>
          </div>

          <div className="space-y-6">
            <SettingSlider label="Ceiling Altitude (M)" value={settings.maxAltitude} min={10} max={400} onChange={v => handleChange('maxAltitude', v)} />
            <SettingSlider label="Cruise Velocity (M/S)" value={settings.maxSpeed} min={1} max={30} onChange={v => handleChange('maxSpeed', v)} />
            <div className="grid grid-cols-2 gap-4 pt-4">
              <SettingInput label="Battery Warning (%)" value={settings.batteryWarningLevel} type="number" onChange={v => handleChange('batteryWarningLevel', v)} />
              <SettingInput label="Critical Auto-Land" value={settings.autoLandBattery} type="number" onChange={v => handleChange('autoLandBattery', v)} />
            </div>
          </div>
        </div>

        {/* Network & Link */}
        <div className="card">
          <div className="flex items-center space-x-3 mb-8">
            <div className="p-2 rounded-lg bg-lesnar-success/10 border border-lesnar-success/20">
              <Globe className="h-4 w-4 text-lesnar-success" />
            </div>
            <h3 className="text-sm font-black text-white uppercase tracking-widest">Command Uplink</h3>
          </div>

          <div className="space-y-6">
            <SettingInput label="Command Host" value={settings.apiHost} type="text" onChange={v => handleChange('apiHost', v)} />
            <div className="grid grid-cols-2 gap-4">
              <SettingInput label="Comm Port" value={settings.apiPort} type="number" onChange={v => handleChange('apiPort', v)} />
              <div className="flex flex-col justify-end">
                <ToggleItem label="Force SSL Layer" checked={settings.enableSSL} onChange={v => handleChange('enableSSL', v)} />
              </div>
            </div>
            <div className="pt-4 border-t border-white/5">
              <ToggleItem label="Neural Collision Guard" checked={settings.enableCollisionAvoidance} onChange={v => handleChange('enableCollisionAvoidance', v)} />
            </div>
          </div>
        </div>

        {/* Tactical Interface */}
        <div className="card lg:col-span-2">
          <div className="flex items-center space-x-3 mb-8">
            <div className="p-2 rounded-lg bg-lesnar-warning/10 border border-lesnar-warning/20">
              <Cpu className="h-4 w-4 text-lesnar-warning" />
            </div>
            <h3 className="text-sm font-black text-white uppercase tracking-widest">Interface Protocols</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
            <div className="space-y-6">
              <ToggleItem label="Global Notifications" checked={settings.enableNotifications} onChange={v => handleChange('enableNotifications', v)} />
              <ToggleItem label="Render Flight Paths" checked={settings.showFlightPaths} onChange={v => handleChange('showFlightPaths', v)} />
            </div>
            <div className="flex-1 min-w-0 pr-4">
              <SettingSelect label="Map Imagery Logic" value={settings.mapProvider} options={['carto-dark', 'stamen-toner', 'osm-standard']} onChange={v => handleChange('mapProvider', v)} />
              <SettingSlider label="Default Optic Zoom" value={settings.defaultZoom} min={1} max={20} onChange={v => handleChange('defaultZoom', v)} />
            </div>
            <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-6 flex flex-col justify-center items-center text-center">
              <AlertTriangle className="h-8 w-8 text-lesnar-warning mb-3 opacity-50" />
              <p className="text-[10px] font-mono text-gray-500 uppercase tracking-widest leading-relaxed">
                CAUTION: Parameter alterations affect real-world flight kinetics. Ensure all thresholds are within structural tolerances.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SettingSlider({ label, value, min, max, onChange }) {
  return (
    <div className="space-y-3">
      <div className="flex justify-between items-end">
        <label className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">{label}</label>
        <span className="text-xs font-mono text-lesnar-accent font-bold">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 bg-white/5 rounded-full appearance-none cursor-pointer accent-lesnar-accent hover:accent-white transition-all"
      />
    </div>
  );
}

function SettingInput({ label, value, type, onChange }) {
  return (
    <div className="space-y-2">
      <label className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(type === 'number' ? Number(e.target.value) : e.target.value)}
        className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-2.5 text-sm font-mono text-white focus:outline-none focus:border-lesnar-accent/50 focus:bg-black/60 transition-all"
      />
    </div>
  );
}

function SettingSelect({ label, value, options, onChange }) {
  return (
    <div className="space-y-2">
      <label className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-2.5 text-sm font-mono text-white focus:outline-none focus:border-lesnar-accent/50 focus:bg-black/60 transition-all appearance-none"
      >
        {options.map(opt => <option key={opt} value={opt}>{opt.toUpperCase()}</option>)}
      </select>
    </div>
  );
}

function ToggleItem({ label, checked, onChange }) {
  return (
    <div className="flex items-center justify-between group cursor-pointer" onClick={() => onChange(!checked)}>
      <span className="text-[10px] font-mono text-gray-500 uppercase tracking-widest group-hover:text-gray-300 transition-colors">{label}</span>
      <div className={`w-10 h-5 rounded-full relative transition-colors duration-300 border ${checked ? 'bg-lesnar-accent/20 border-lesnar-accent/40' : 'bg-white/5 border-white/10'}`}>
        <div className={`absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full transition-all duration-300 ${checked ? 'left-6 bg-lesnar-accent shadow-[0_0_10px_rgba(0,245,255,0.8)]' : 'left-1 bg-gray-600'}`} />
      </div>
    </div>
  );
}

export default Settings;
