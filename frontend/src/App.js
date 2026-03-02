import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import io from 'socket.io-client';
import './App.css';

import { BACKEND_URL } from './config';

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

// Context for global state
import { DroneProvider } from './context/DroneContext';

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [connected, setConnected] = useState(false);
  const [socket, setSocket] = useState(null);
  const [terminalOpen, setTerminalOpen] = useState(true);

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

    setSocket(newSocket);

    // Cleanup on unmount
    return () => {
      newSocket.close();
    };
  }, []);

  return (
    <DroneProvider>
      <Router>
        <div className="h-screen bg-navy-black text-white flex overflow-hidden">
          {/* Sidebar */}
          <Sidebar
            isOpen={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
          />

          {/* Main content */}
          <div className="flex-1 flex flex-col overflow-hidden relative">
            {/* Header */}
            <Header
              onMenuClick={() => setSidebarOpen(!sidebarOpen)}
              connected={connected}
            />

            {/* Page content */}
            <main className="flex-1 overflow-x-hidden overflow-y-auto bg-navy-black/50 custom-scrollbar pt-6">
              <ErrorBoundary>
                <Routes>
                  <Route path="/" element={<Dashboard socket={socket} />} />
                  <Route path="/map" element={<DroneMap socket={socket} />} />
                  <Route path="/drones" element={<DroneList socket={socket} />} />
                  <Route path="/missions" element={<MissionControl socket={socket} />} />
                  <Route path="/analytics" element={<Analytics socket={socket} />} />
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
              {terminalOpen && <DiagnosticTerminal socket={socket} />}
            </div>
          </div>

          {/* Global health status indicator - refined position */}
          <div className="fixed bottom-12 right-6 z-50">
            <HealthStatusIndicator />
          </div>
        </div>
      </Router>
    </DroneProvider>
  );
}

export default App;
