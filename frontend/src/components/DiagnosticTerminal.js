import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Shield, ChevronRight, X } from 'lucide-react';

function DiagnosticTerminal({ logs = [], socket, onClose }) {
    const [terminalLogs, setTerminalLogs] = useState([]);
    const bottomRef = useRef(null);

    // Helper to add a log entry
    const handleLog = (type, message, level = 'INFO') => {
        setTerminalLogs(prev => [
            ...prev,
            {
                id: Date.now() + Math.random(),
                type,
                message,
                level,
                time: new Date().toLocaleTimeString()
            }
        ].slice(-100));
    };

    // Socket listeners
    useEffect(() => {
        if (!socket) return;

        socket.on('telemetry_update', (data) => {
            handleLog('telemetry', `Syncing Telemetry: ${data.telemetry?.length || 0} assets found.`, 'info');
        });

        socket.on('drone_status', (data) => {
            handleLog('asset', `Unit ${data.drone_id} reported: ${data.status}`, 'warning');
        });

        socket.on('mission_update', (data) => {
            handleLog('mission', `Mission ${data.mission_id} progress: ${data.progress}%`, 'success');
        });

        return () => {
            socket.off('telemetry_update');
            socket.off('drone_status');
            socket.off('mission_update');
        };
    }, [socket]);

    // Initialize with boot sequence
    useEffect(() => {
        const bootSequence = [
            '>> INITIATING LESNAR.AI TACTICAL LINK...',
            '>> SYNCING MAVLINK PROTOCOLS...',
            '>> ENCRYPTION LAYER: AES-256-GCM ACTIVE',
            '>> DRONE FLEET HANDSHAKE: SUCCESS',
            '>> SYSTEM STATUS: OPTIMAL'
        ];

        let i = 0;
        const interval = setInterval(() => {
            if (i < bootSequence.length) {
                handleLog('info', bootSequence[i], 'info');
                i++;
            } else {
                clearInterval(interval);
            }
        }, 300);

        return () => clearInterval(interval);
    }, []);

    // Sync with incoming logs from props
    useEffect(() => {
        if (logs.length > 0) {
            setTerminalLogs(prev => [...prev, ...logs.map(l => ({
                ...l,
                id: Date.now() + Math.random(),
                time: new Date().toLocaleTimeString()
            }))].slice(-100));
        }
    }, [logs]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [terminalLogs]);

    return (
        <div className="glass-dark border border-white/10 rounded-2xl flex flex-col h-full overflow-hidden shadow-2xl relative">
            {/* Header */}
            <div className="bg-white/5 border-b border-white/5 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center space-x-2">
                    <Terminal className="h-4 w-4 text-lesnar-accent animate-pulse" />
                    <span className="text-[10px] font-mono font-bold text-white uppercase tracking-widest">Diagnostic Console // T-X7</span>
                </div>
                <div className="flex items-center space-x-2">
                    <div className="h-1.5 w-1.5 bg-lesnar-success rounded-full" />
                    <span className="text-[8px] font-mono text-lesnar-success uppercase px-1">Live_Stream</span>
                    {onClose && (
                        <button onClick={onClose} className="ml-2 hover:bg-white/5 p-1 rounded transition-colors text-gray-500 hover:text-white">
                            <X className="h-4 w-4" />
                        </button>
                    )}
                </div>
            </div>

            {/* Log Area */}
            <div className="flex-1 overflow-y-auto p-4 font-mono text-[10px] space-y-1.5 scrollbar-hide">
                {terminalLogs.map((log) => (
                    <div key={log.id} className="flex items-start space-x-2 group animate-fade-in">
                        <span className="text-gray-600 shrink-0">[{log.time}]</span>
                        <ChevronRight className="h-3 w-3 mt-0.5 text-lesnar-accent shrink-0 opacity-40 group-hover:opacity-100" />
                        <span className={`
                            ${log.level === 'error' || log.type === 'error' ? 'text-lesnar-danger' :
                                log.level === 'warning' || log.type === 'warning' ? 'text-lesnar-warning' :
                                    log.level === 'success' || log.type === 'success' ? 'text-lesnar-success' :
                                        'text-lesnar-accent'}
                        `}>
                            {log.message || log.text}
                        </span>
                    </div>
                ))}
                <div ref={bottomRef} />
            </div>

            {/* Footer / Stats */}
            <div className="bg-navy-black/60 p-3 border-t border-white/5 flex items-center justify-between">
                <div className="flex items-center space-x-4">
                    <div className="flex flex-col">
                        <span className="text-[7px] text-gray-600 font-mono uppercase">Buffer Size</span>
                        <span className="text-[9px] text-white/70 font-mono">1024 KB</span>
                    </div>
                    <div className="flex flex-col">
                        <span className="text-[7px] text-gray-600 font-mono uppercase">Signal Strength</span>
                        <div className="flex space-x-0.5 mt-0.5">
                            <div className="h-2 w-1 bg-lesnar-accent" />
                            <div className="h-2 w-1 bg-lesnar-accent" />
                            <div className="h-2 w-1 bg-lesnar-accent" />
                            <div className="h-2 w-1 bg-gray-700" />
                        </div>
                    </div>
                </div>
                <div className="flex items-center space-x-2">
                    <Shield className="h-3 w-3 text-lesnar-success" />
                    <span className="text-[8px] font-mono text-gray-500 uppercase">Secure Link // OK</span>
                </div>
            </div>
        </div>
    );
}

export default DiagnosticTerminal;
