import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Activity, ChevronRight, X, Download } from 'lucide-react';
import { readOperatorAuditLog, subscribeOperatorAudit } from '../utils/operatorAudit';

const MAX_ENTRIES = 100;

// Colours for the three link modes App derives from measured state (utils/operational.js).
const LINK_TONES = {
    nominal: { dot: 'bg-lesnar-success', text: 'text-lesnar-success' },
    degraded: { dot: 'bg-lesnar-warning', text: 'text-lesnar-warning' },
    lost: { dot: 'bg-lesnar-danger', text: 'text-lesnar-danger' },
};
const UNKNOWN_TONE = { dot: 'bg-gray-600', text: 'text-gray-500' };

function DiagnosticTerminal({ logs = [], socket, onClose, linkMetrics }) {
    const [terminalLogs, setTerminalLogs] = useState([]);
    const bottomRef = useRef(null);
    const linkTone = LINK_TONES[linkMetrics?.linkMode?.key] || UNKNOWN_TONE;
    const linkLabel = linkMetrics?.linkMode?.label || 'Unknown';

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
        ].slice(-MAX_ENTRIES));
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

    // Report the backend link as App measures it, once on open and on every change.
    // Degraded is reported by the link metrics effect below.
    const linkKey = linkMetrics?.linkMode?.key;
    const prevLinkKey = useRef(null);
    useEffect(() => {
        const prev = prevLinkKey.current;
        prevLinkKey.current = linkKey;
        if (!linkKey || linkKey === prev) return;
        if (linkKey === 'lost') {
            if (prev === null) handleLog('info', 'Waiting for the backend socket.', 'info');
            else handleLog('error', 'Backend socket disconnected.', 'error');
        } else if (prev === null || prev === 'lost') {
            // Degraded and nominal both mean the socket is connected (getLinkMode).
            handleLog('info', 'Backend socket connected.', 'success');
        } else if (linkKey === 'nominal') {
            handleLog('info', 'Link back to nominal.', 'success');
        }
    }, [linkKey]);

    useEffect(() => {
        const existing = readOperatorAuditLog().slice(-12).map((entry) => ({
            id: entry.id,
            type: entry.type || 'audit',
            message: entry.message,
            level: entry.level || 'info',
            time: new Date(entry.timestamp).toLocaleTimeString(),
        }));
        if (existing.length > 0) {
            setTerminalLogs((prev) => [...prev, ...existing].slice(-MAX_ENTRIES));
        }
        return subscribeOperatorAudit((entry) => {
            handleLog(entry.type || 'audit', entry.message, entry.level || 'info');
        });
    }, []);

    useEffect(() => {
        if (linkMetrics?.degradedMode && linkKey !== 'lost') {
            handleLog('warning', `Link degraded: RTT ${linkMetrics?.latencyMs ?? '—'}ms, telemetry age ${Number.isFinite(linkMetrics?.telemetryAgeMs) ? Math.round(linkMetrics.telemetryAgeMs) : '—'}ms.`, 'warning');
        }
    }, [linkKey, linkMetrics?.degradedMode, linkMetrics?.latencyMs, linkMetrics?.telemetryAgeMs]);

    // Sync with incoming logs from props
    useEffect(() => {
        if (logs.length > 0) {
            setTerminalLogs(prev => [...prev, ...logs.map(l => ({
                ...l,
                id: Date.now() + Math.random(),
                time: new Date().toLocaleTimeString()
            }))].slice(-MAX_ENTRIES));
        }
    }, [logs]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [terminalLogs]);

    const downloadConsoleLog = () => {
        const text = terminalLogs.map((log) => `[${log.time}] ${String(log.level || 'info').toUpperCase()} ${log.message || log.text || ''}`).join('\n');
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `lesnar-diagnostic-console-${new Date().toISOString().replace(/[:.]/g, '-')}.log`;
        link.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="glass-dark border border-white/10 rounded-2xl flex flex-col h-full overflow-hidden shadow-2xl relative">
            {/* Header */}
            <div className="bg-white/5 border-b border-white/5 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center space-x-2">
                    <Terminal className="h-4 w-4 text-lesnar-accent animate-pulse" />
                    <span className="text-[10px] font-mono font-bold text-white uppercase tracking-widest">Diagnostic Console // T-X7</span>
                </div>
                <div className="flex items-center space-x-2">
                    <button onClick={downloadConsoleLog} className="hover:bg-white/5 p-1 rounded transition-colors text-gray-500 hover:text-white" title="Download console log">
                        <Download className="h-4 w-4" />
                    </button>
                    <div className={`h-1.5 w-1.5 rounded-full ${linkTone.dot}`} />
                    <span className={`text-[8px] font-mono uppercase px-1 ${linkTone.text}`}>{linkLabel}</span>
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
                        <span className="text-[7px] text-gray-600 font-mono uppercase">Entries</span>
                        <span className="text-[9px] text-white/70 font-mono">{terminalLogs.length} / {MAX_ENTRIES}</span>
                    </div>
                    <div className="flex flex-col">
                        <span className="text-[7px] text-gray-600 font-mono uppercase">Health RTT</span>
                        <span className="text-[9px] text-white/70 font-mono">{Number.isFinite(linkMetrics?.latencyMs) ? `${linkMetrics.latencyMs} ms` : 'n/a'}</span>
                    </div>
                </div>
                <div className="flex items-center space-x-2">
                    <Activity className={`h-3 w-3 ${linkTone.text}`} />
                    <span className="text-[8px] font-mono text-gray-500 uppercase">Backend link // {linkLabel}</span>
                </div>
            </div>
        </div>
    );
}

export default DiagnosticTerminal;
