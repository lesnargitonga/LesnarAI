import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Menu, Bell, Map as MapIcon, Shield, Sun, Moon } from 'lucide-react';
import { useDrones } from '../context/DroneContext';
import { getDroneFlags } from '../utils/droneState';
import { requireTypedConfirmation } from '../utils/operatorAudit';
import api from '../api';
import { clearSession, getStoredSession, sessionAuthRequired } from '../utils/sessionAuth';

function Header({ onMenuClick, connected, themeMode, onThemeToggle, linkMetrics }) {
  const navigate = useNavigate();
  const { drones, telemetryStale, emergencyLandAll } = useDrones();
  const session = getStoredSession();
  const alertCount = drones.filter((drone) => {
    const { battery } = getDroneFlags(drone);
    return Number.isFinite(battery) && battery < 20;
  }).length;
  const actionableCount = drones.filter((drone) => {
    const flags = getDroneFlags(drone);
    return flags.armed || flags.flying;
  }).length;
  const degraded = Boolean(linkMetrics?.degradedMode);

  return (
    <header className="glass-dark border-b border-white/5 z-30 shrink-0 sticky top-0">
      <div className="flex items-center justify-between px-4 md:px-6 py-2.5 md:py-4">
        {/* Left side */}
        <div className="flex items-center space-x-4">
          <button
            onClick={onMenuClick}
            className="p-2 rounded-lg hover:bg-white/5 transition-colors lg:hidden"
          >
            <Menu className="h-5 w-5 text-gray-400" />
          </button>

          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 bg-lesnar-accent/10 border border-lesnar-accent/20 rounded-xl flex items-center justify-center neo-glow">
              <Shield className="h-6 w-6 text-lesnar-accent" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-widest uppercase text-glow">
                Lesnar AI
              </h1>
              <p className="text-[10px] text-lesnar-accent/60 font-mono tracking-tighter uppercase">
                Tactical Interface // v1.0.0
              </p>
            </div>
          </div>
        </div>

        {/* Right side */}
        <div className="flex items-center space-x-6">
          {/* E-STOP BUTTON (Human in the loop override) */}
          {actionableCount > 0 && (
            <button
              onClick={async () => {
                if (telemetryStale) {
                  alert('Emergency action locked: telemetry is stale.');
                  return;
                }
                if (requireTypedConfirmation('CRITICAL WARNING: Initiate Global Emergency Stop? All drones will RTL/Land immediately.', 'CONFIRM')) {
                  try {
                    await emergencyLandAll();
                    alert("E-STOP INITIATED.");
                  } catch (e) {
                    alert("E-Stop Failed: " + e.message);
                  }
                }
              }}
              disabled={telemetryStale}
              className="flex items-center space-x-2 px-4 py-1.5 rounded-full border border-lesnar-danger/50 bg-lesnar-danger/20 hover:bg-lesnar-danger/40 transition-all cursor-pointer shadow-[0_0_15px_rgba(255,0,85,0.4)] hover:shadow-[0_0_25px_rgba(255,0,85,0.8)] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <div className="h-2 w-2 rounded-full bg-lesnar-danger animate-pulse" />
              <span className="text-xs font-black text-white uppercase tracking-widest">
                Emergency Kill [Shift+Esc]
              </span>
            </button>
          )}

          <div className="h-6 w-[1px] bg-white/10 hidden md:block" />

          {/* Connection status */}
          <div className={`flex items-center space-x-2 px-3 py-1.5 rounded-full border ${connected ? 'border-lesnar-success/20 bg-lesnar-success/5' : 'border-lesnar-danger/20 bg-lesnar-danger/5'
            }`}>
            <div className={`h-2 w-2 rounded-full ${connected ? 'bg-lesnar-success animate-pulse' : 'bg-lesnar-danger'}`} />
            <span className={`text-xs font-mono uppercase tracking-wider ${connected ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>
              {connected ? 'Sync Active' : 'Link Severed'}
            </span>
          </div>

          <div className={`hidden lg:flex items-center space-x-2 px-3 py-1.5 rounded-full border ${degraded ? 'border-lesnar-warning/30 bg-lesnar-warning/10 text-lesnar-warning' : 'border-lesnar-accent/20 bg-lesnar-accent/5 text-lesnar-accent'}`}>
            <span className="text-[10px] font-mono uppercase tracking-widest">{linkMetrics?.linkMode?.label || 'UNKNOWN'}</span>
            <span className="text-[10px] font-mono">RTT {linkMetrics?.latencyMs ?? '—'}ms</span>
            <span className="text-[10px] font-mono">AGE {Number.isFinite(linkMetrics?.telemetryAgeMs) ? Math.round(linkMetrics.telemetryAgeMs) : '—'}ms</span>
          </div>

          <div className="h-6 w-[1px] bg-white/10 hidden md:block" />

          {/* Quick buttons */}
          <div className="hidden md:flex items-center space-x-2">
            <button
              onClick={onThemeToggle}
              title={themeMode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-all"
            >
              {themeMode === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
            </button>
            <button
              onClick={() => navigate('/analytics')}
              title={alertCount > 0 ? `${alertCount} critical alerts` : 'No active critical alerts'}
              className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-all relative"
            >
              <Bell className="h-5 w-5" />
              {alertCount > 0 && (
                <>
                  <span className="absolute top-2 right-2 h-1.5 w-1.5 bg-lesnar-danger rounded-full shadow-[0_0_5px_rgba(255,0,85,0.8)]"></span>
                  <span className="absolute -top-0.5 -right-1.5 min-w-[14px] h-[14px] px-1 rounded-full bg-lesnar-danger text-[8px] leading-[14px] text-white font-bold text-center">
                    {alertCount > 9 ? '9+' : alertCount}
                  </span>
                </>
              )}
            </button>

            <Link
              to="/map"
              className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-lesnar-accent/10 border border-lesnar-accent/30 text-lesnar-accent hover:bg-lesnar-accent/20 transition-all group"
            >
              <MapIcon className="h-4 w-4 group-hover:scale-110 transition-transform" />
              <span className="text-xs font-bold uppercase tracking-widest">Tactical Map</span>
            </Link>
          </div>

          {/* User profile */}
          <div className="flex items-center pl-4 border-l border-white/10">
            <div className="group relative cursor-pointer">
              <div className="h-10 w-10 p-[2px] rounded-full bg-gradient-to-tr from-lesnar-accent to-purple-500 hover:rotate-180 transition-all duration-500">
                <div className="h-full w-full bg-navy-black rounded-full flex items-center justify-center overflow-hidden">
                    <span className="text-xs font-bold text-white group-hover:rotate-180 transition-all duration-500">{(session?.userId || 'LA').slice(0, 2).toUpperCase()}</span>
                </div>
              </div>
              <div className="absolute top-0 right-0 h-3 w-3 bg-lesnar-success border-2 border-navy-black rounded-full" />
            </div>
              {sessionAuthRequired() && session?.userId && (
                <div className="ml-3 hidden md:flex flex-col">
                  <span className="text-[10px] font-mono uppercase tracking-widest text-gray-400">{session.userId}</span>
                  <button
                    onClick={async () => {
                      try { await api.post('/api/auth/logout'); } catch {}
                      clearSession();
                      window.location.reload();
                    }}
                    className="text-[9px] font-mono uppercase tracking-widest text-lesnar-warning text-left"
                  >
                    {(session.role || 'viewer') + ' • logout'}
                  </button>
                </div>
              )}
          </div>
        </div>
      </div>
      <div className="px-4 md:px-6 pb-2 flex flex-wrap gap-2 text-[9px] font-mono uppercase tracking-widest text-gray-400">
        <span className="px-2 py-1 rounded border border-white/10 bg-white/5">[1-3] Quick Select</span>
        <span className="px-2 py-1 rounded border border-white/10 bg-white/5">[G] Tactical Map</span>
        <span className="px-2 py-1 rounded border border-white/10 bg-white/5">[D] Fleet</span>
        {telemetryStale && <span className="px-2 py-1 rounded border border-lesnar-danger/30 bg-lesnar-danger/10 text-lesnar-danger">Command Lockout: Telemetry Stale</span>}
      </div>
    </header>
  );
}

export default Header;
