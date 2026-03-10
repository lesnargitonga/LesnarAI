import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import io from 'socket.io-client';
import './App.css';

import { BACKEND_URL } from './config';

import api from './api';
import { getLinkMode } from './utils/operational';
// Components
import Header from './components/Header';
import HealthStatusIndicator from './components/HealthStatusIndicator';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import DroneMap from './components/DroneMap';
import DroneList from './components/DroneList';
import MissionControl from './components/MissionControl';
import Analytics from './components/Analytics';
import Settings from './components/Settings';
import DiagnosticTerminal from './components/DiagnosticTerminal';
import ErrorBoundary from './components/ErrorBoundary';
import AuthGate from './components/AuthGate';

import TacticalHotkeys from './components/TacticalHotkeys';
// Context for global state
import { DroneProvider } from './context/DroneContext';

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [connected, setConnected] = useState(false);
  const [socket, setSocket] = useState(null);
  const [latencyMs, setLatencyMs] = useState(null);
  const [lastTelemetryAt, setLastTelemetryAt] = useState(null);
  const [terminalOpen, setTerminalOpen] = useState(true);
  const [themeMode, setThemeMode] = useState(() => window.localStorage.getItem('lesnar.ui.theme') || 'dark');

  useEffect(() => {
    window.localStorage.setItem('lesnar.ui.theme', themeMode);
  }, [themeMode]);

  useEffect(() => {
    // Initialize socket connection
    const newSocket = io(BACKEND_URL);

    newSocket.on('connect', () => {
      console.log('Connected to Lesnar AI backend');
      setConnected(true);

      // Subscribe to telemetry updates
      newSocket.emit('subscribe_telemetry');
    });

    newSocket.on('disconnect', () => {
      console.log('Disconnected from backend');
      setConnected(false);
    });

    newSocket.on('telemetry_update', () => {
      setLastTelemetryAt(Date.now());
    });

    setSocket(newSocket);

    // Cleanup on unmount
    return () => {
      newSocket.close();
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    const probe = async () => {
      const started = performance.now();
      try {
        await api.get('/api/health');
        if (mounted) setLatencyMs(Math.round(performance.now() - started));
      } catch {
        if (mounted) setLatencyMs(null);
      }
    };
    probe();
    const timer = setInterval(probe, 10000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  const telemetryAgeMs = lastTelemetryAt == null ? Number.POSITIVE_INFINITY : Math.max(0, Date.now() - lastTelemetryAt);
  const linkMode = getLinkMode({ connected, latencyMs, telemetryAgeMs });
  const linkMetrics = { connected, latencyMs, telemetryAgeMs, lastTelemetryAt, linkMode, degradedMode: linkMode.degraded };

  return (
    <AuthGate>
      <DroneProvider socketConnected={connected}>
        <Router>
          <div className={`min-h-screen bg-navy-black text-white flex overflow-hidden relative ${themeMode === 'light' ? 'theme-light' : 'theme-dark'} ${linkMetrics.degradedMode ? 'ops-degraded' : ''}`}>
            <TacticalHotkeys />
            <div className="pointer-events-none absolute inset-0 tactical-vignette opacity-90" />
            <div className="pointer-events-none absolute inset-0 tactical-grid opacity-60" />
            {/* Sidebar */}
            <Sidebar
              isOpen={sidebarOpen}
              onClose={() => setSidebarOpen(false)}
              connected={connected}
              linkMetrics={linkMetrics}
            />

          {/* Main content */}
          <div className="flex-1 flex flex-col overflow-hidden relative">
            {/* Header */}
            <Header
              onMenuClick={() => setSidebarOpen(!sidebarOpen)}
              connected={connected}
              themeMode={themeMode}
              onThemeToggle={() => setThemeMode((prev) => (prev === 'dark' ? 'light' : 'dark'))}
              linkMetrics={linkMetrics}
            />

            {/* Page content */}
            <main className="flex-1 overflow-x-hidden overflow-y-auto bg-navy-black/50 custom-scrollbar pt-2">
              <ErrorBoundary>
                <Routes>
                  <Route path="/" element={<Dashboard socket={socket} linkMetrics={linkMetrics} />} />
                  <Route path="/map" element={<DroneMap socket={socket} linkMetrics={linkMetrics} />} />
                  <Route path="/drones" element={<DroneList socket={socket} />} />
                  <Route path="/missions" element={<MissionControl socket={socket} linkMetrics={linkMetrics} />} />
                  <Route path="/analytics" element={<Analytics socket={socket} linkMetrics={linkMetrics} />} />
                  <Route path="/settings" element={<Settings />} />
                </Routes>
              </ErrorBoundary>
            </main>

            {/* Diagnostic Terminal - hacker style bottom panel */}
            <div className={`transition-all duration-500 ease-in-out border-t border-white/5 ${terminalOpen ? 'h-64' : 'h-10'}`}>
              <div className="bg-black/60 backdrop-blur-md px-4 py-2 flex items-center justify-between border-b border-white/5">
                <div className="flex items-center space-x-2">
                  <div className="h-2 w-2 rounded-full bg-lesnar-accent animate-pulse" />
                  <span className="text-[10px] font-mono text-lesnar-accent uppercase tracking-widest font-bold">System_Diagnostic_v1.0.4</span>
                </div>
                <button
                  onClick={() => setTerminalOpen(!terminalOpen)}
                  className="text-[10px] font-mono text-gray-500 hover:text-white uppercase"
                >
                  {terminalOpen ? '[ Minimize ]' : '[ Maximize ]'}
                </button>
              </div>
              {terminalOpen && <DiagnosticTerminal socket={socket} linkMetrics={linkMetrics} />}
            </div>
          </div>

          {/* Global health status indicator - refined position */}
          <div className="fixed bottom-12 right-6 z-50">
            <HealthStatusIndicator linkMetrics={linkMetrics} />
          </div>
          </div>
        </Router>
      </DroneProvider>
    </AuthGate>
  );
}

export default App;
