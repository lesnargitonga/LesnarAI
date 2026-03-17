import React, { useEffect, useState } from 'react';
import { RefreshCw, Cpu, AlertTriangle } from 'lucide-react';
import { orchestratorLaunchAll, orchestratorKillAll, orchestratorStatus, getApiErrorMessage } from '../api';

const RuntimePill = ({ label, active }) => (
  <div className="flex items-center justify-between p-3 rounded-lg bg-black/40 border border-white/5">
    <span className="text-xs font-medium text-gray-400">{label}</span>
    <div className={`h-2.5 w-2.5 rounded-full ${active ? 'bg-lesnar-success shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-gray-600'}`} />
  </div>
);

export default function RuntimeOrchestratorBlock() {
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [runtimeError, setRuntimeError] = useState(null);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [launchMode, setLaunchMode] = useState('');
  const [droneCount, setDroneCount] = useState(1);

  const checkRuntimeStatus = async () => {
    try {
      const res = await orchestratorStatus();
      if (res?.success) {
        setRuntimeStatus(res.status);
        setRuntimeError(null);
      }
    } catch (e) {
      setRuntimeError(getApiErrorMessage(e, 'Runtime orchestrator not reachable.'));
    }
  };

  useEffect(() => {
    checkRuntimeStatus();
    const iv = setInterval(checkRuntimeStatus, 5000);
    return () => clearInterval(iv);
  }, []);

  const handleLaunchEverything = async (gzHeadless, modeLabel) => {
    setRuntimeBusy(true);
    setLaunchMode(modeLabel);
    setRuntimeError(null);
    try {
      const res = await orchestratorLaunchAll(droneCount, null, { gzHeadless });
      if (res?.success) setRuntimeStatus(res.status || null);
    } catch (e) {
      setRuntimeError(getApiErrorMessage(e, 'Failed to launch runtime.'));
    } finally {
      setTimeout(() => {
        setRuntimeBusy(false);
        setLaunchMode('');
      }, 2000);
    }
  };

  const handleKillEverything = async () => {
    setRuntimeBusy(true);
    setRuntimeError(null);
    try {
      await orchestratorKillAll();
      setTimeout(checkRuntimeStatus, 1500);
    } catch (e) {
      setRuntimeError(getApiErrorMessage(e, 'Failed to kill runtime.'));
    } finally {
      setTimeout(() => setRuntimeBusy(false), 2000);
    }
  };

  return (
    <div className="card space-y-4 mb-6 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-lesnar-accent/5 to-transparent pointer-events-none" />
      <div className="relative">
        <div className="flex items-center space-x-3 mb-5">
          <div className="p-2 rounded-lg bg-lesnar-accent/10 border border-lesnar-accent/20">
            <Cpu className="h-4 w-4 text-lesnar-accent" />
          </div>
          <h3 className="text-sm font-black text-white uppercase tracking-widest">Simulator Runtime Orchestrator</h3>
          <button
            onClick={checkRuntimeStatus}
            className="ml-auto p-1.5 rounded-lg border border-white/10 hover:bg-white/5 transition-colors text-gray-400"
            title="Refresh runtime state"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>

        {runtimeError && (
          <div className="mb-4 bg-lesnar-danger/10 border border-lesnar-danger/30 rounded-xl p-3 flex items-center space-x-2">
            <AlertTriangle className="h-4 w-4 text-lesnar-danger flex-shrink-0" />
            <p className="text-xs font-mono text-lesnar-danger">{runtimeError}</p>
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <RuntimePill label="Gazebo (Physics)" active={Boolean(runtimeStatus?.gz_running)} />
          <RuntimePill label="PX4 (Autopilot)" active={Boolean(runtimeStatus?.px4_running)} />
          <RuntimePill label="Teacher Bridge" active={Boolean(runtimeStatus?.teacher_running)} />
          <RuntimePill label="Drone Model" active={Boolean(runtimeStatus?.drone_model_present)} />
        </div>

        <div className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-[11px] text-gray-300 mb-4">
          <span className="font-bold text-white uppercase tracking-wider">Launch Modes:</span>{' '}
          <span className="text-gray-200">Headless</span> keeps Gazebo server-only for the most stable synced runtime.
          {' '}
          <span className="text-gray-200">Visible</span> opens the live Gazebo GUI for operator/supervisor observation, but can use much more WSL CPU.
        </div>

        <div className="flex flex-col sm:flex-row space-y-3 sm:space-y-0 sm:space-x-3 items-end sm:items-center mt-6">
          <div className="flex flex-col w-full sm:w-auto">
            <label className="text-xs text-gray-500 mb-1">Agents</label>
            <input 
              type="number" 
              min="1" 
              max="10" 
              value={droneCount} 
              onChange={(e) => {
                const v = Number(e.target.value);
                if (!Number.isFinite(v)) return;
                setDroneCount(Math.max(1, Math.min(10, Math.trunc(v))));
              }}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white w-full sm:w-20"
              title="Number of drones to launch"
            />
          </div>
          <button
            onClick={() => handleLaunchEverything(true, 'HEADLESS')}
            disabled={runtimeBusy}
            className="py-2 px-6 disabled:opacity-50 w-full sm:w-auto flex-1 font-bold tracking-widest text-sm rounded-lg bg-white/5 text-white border border-white/10 hover:bg-white/10 transition-all"
            title="Launch headless Gazebo, PX4, and teacher bridge for maximum stability"
          >
            {runtimeBusy && launchMode === 'HEADLESS' ? 'WORKING...' : 'SPAWN HEADLESS CLUSTER'}
          </button>
          <button
            onClick={() => handleLaunchEverything(false, 'VISIBLE')}
            disabled={runtimeBusy}
            className="btn-primary py-2 px-6 disabled:opacity-50 w-full sm:w-auto flex-1 font-bold tracking-widest text-sm"
            title="Launch visible Gazebo GUI, PX4, and teacher bridge for live observation"
          >
            {runtimeBusy && launchMode === 'VISIBLE' ? 'WORKING...' : 'SPAWN LIVE CLUSTER'}
          </button>
          <button
            onClick={handleKillEverything}
            disabled={runtimeBusy}
            className="px-6 py-2 rounded-lg font-bold text-sm bg-lesnar-danger/20 text-lesnar-danger border border-lesnar-danger/50 hover:bg-lesnar-danger/30 transition-all uppercase tracking-wider w-full sm:w-auto"
          >
            {runtimeBusy ? 'WORKING...' : 'INSTANT KILL ALL'}
          </button>
        </div>
      </div>
    </div>
  );
}
