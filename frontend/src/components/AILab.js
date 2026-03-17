import React, { useState, useEffect, useCallback } from 'react';
import {
  Brain,
  Crosshair,
  Shuffle,
  Eye,
  BarChart3,
  Play,
  Square,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Cpu,
  Zap,
  Shield,
  Activity,
  Target,
  Radar,
  Layers,
  TrendingUp,
  Box,
} from 'lucide-react';
import api from '../api';
import { orchestratorStatus, orchestratorStartTraining, getApiErrorMessage } from '../api';
import { useDrones } from '../context/DroneContext';

/* ─── helper: send a Redis command via the backend ─── */
const sendTeacherCommand = async (droneId, action, params = {}) => {
  return api.post(`/api/drones/${droneId}/command`, { action, ...params });
};

/* ─── small reusable pieces ─── */
const StatusDot = ({ active, pulse }) => (
  <div className={`h-2.5 w-2.5 rounded-full flex-shrink-0 ${active
    ? `bg-lesnar-success shadow-[0_0_8px_rgba(16,185,129,0.6)] ${pulse ? 'animate-pulse' : ''}`
    : 'bg-gray-600'
  }`} />
);

const TabButton = ({ icon: Icon, label, active, onClick, badge }) => (
  <button
    onClick={onClick}
    className={`
      flex items-center space-x-2 px-4 py-3 text-xs font-bold uppercase tracking-[0.15em] rounded-xl transition-all duration-300 whitespace-nowrap
      ${active
        ? 'bg-lesnar-accent/10 text-lesnar-accent border border-lesnar-accent/20 neo-glow'
        : 'text-gray-500 hover:text-gray-300 hover:bg-white/5 border border-transparent'
      }
    `}
  >
    <Icon className="h-4 w-4 flex-shrink-0" />
    <span>{label}</span>
    {badge && (
      <span className="ml-1 px-1.5 py-0.5 text-[9px] rounded-full bg-lesnar-accent/20 text-lesnar-accent font-mono">{badge}</span>
    )}
  </button>
);

const MetricCard = ({ label, value, unit, icon: Icon, color = 'text-lesnar-accent' }) => (
  <div className="p-4 rounded-xl bg-black/40 border border-white/5">
    <div className="flex items-center space-x-2 mb-2">
      {Icon && <Icon className={`h-3.5 w-3.5 ${color}`} />}
      <span className="text-[10px] font-mono text-gray-500 uppercase tracking-wider">{label}</span>
    </div>
    <div className="flex items-baseline space-x-1">
      <span className={`text-xl font-black ${color}`}>{value}</span>
      {unit && <span className="text-[10px] text-gray-500">{unit}</span>}
    </div>
  </div>
);

const Toggle = ({ label, checked, onChange, description }) => (
  <div className="flex items-center justify-between p-3 rounded-lg bg-black/30 border border-white/5">
    <div>
      <span className="text-xs font-bold text-white uppercase tracking-wider">{label}</span>
      {description && <p className="text-[10px] text-gray-500 mt-0.5">{description}</p>}
    </div>
    <button
      onClick={() => onChange(!checked)}
      className={`relative w-11 h-6 rounded-full transition-colors ${checked ? 'bg-lesnar-accent' : 'bg-gray-700'}`}
    >
      <span className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : ''}`} />
    </button>
  </div>
);

const Slider = ({ label, value, min, max, step, onChange, unit = '' }) => (
  <div className="p-3 rounded-lg bg-black/30 border border-white/5">
    <div className="flex justify-between mb-2">
      <span className="text-xs font-bold text-white uppercase tracking-wider">{label}</span>
      <span className="text-xs font-mono text-lesnar-accent">{value}{unit}</span>
    </div>
    <input
      type="range" min={min} max={max} step={step} value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full h-1.5 rounded-full appearance-none bg-white/10 accent-lesnar-accent cursor-pointer"
    />
  </div>
);

/* ═══════════════════════════════════════════════════════════════════
   TAB 1: OBSTACLE AVOIDANCE
   ═══════════════════════════════════════════════════════════════════ */
function ObstacleAvoidanceTab({ droneId, runtimeStatus }) {
  const [params, setParams] = useState({
    lookahead: 14.0, corridor: 65, safetyMargin: 2.0, avoidanceGain: 1.2,
    maxBlend: 0.85, precisionMode: true, safePresentation: true,
  });
  const [status, setStatus] = useState(null);

  const handleApply = async () => {
    try {
      await sendTeacherCommand(droneId, 'update_avoidance', {
        obstacle_lookahead_m: params.lookahead,
        obstacle_corridor_deg: params.corridor,
        obstacle_safety_margin_m: params.safetyMargin,
        avoidance_gain: params.avoidanceGain,
        max_avoidance_blend: params.maxBlend,
        precision_mode: params.precisionMode,
        safe_presentation_profile: params.safePresentation,
      });
      setStatus({ ok: true, msg: 'Parameters applied' });
    } catch (e) {
      setStatus({ ok: false, msg: getApiErrorMessage(e) });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-3 mb-2">
        <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20">
          <Shield className="h-5 w-5 text-red-400" />
        </div>
        <div>
          <h3 className="text-sm font-black text-white uppercase tracking-widest">Obstacle Avoidance System</h3>
          <p className="text-[10px] text-gray-500 mt-0.5">Two-layer hybrid: A* deliberative + potential-field reactive</p>
        </div>
        <StatusDot active={runtimeStatus?.teacher_running} pulse />
      </div>

      {/* Architecture diagram */}
      <div className="p-4 rounded-xl bg-black/40 border border-white/10">
        <p className="text-[10px] font-mono text-gray-400 uppercase tracking-wider mb-3">System Architecture</p>
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-lg bg-gradient-to-br from-red-500/10 to-transparent border border-red-500/10">
            <p className="text-[10px] font-bold text-red-400 uppercase mb-1">Reactive Layer</p>
            <p className="text-[10px] text-gray-400">72-ray LIDAR → potential field → escape vector → avoidance blend</p>
          </div>
          <div className="p-3 rounded-lg bg-gradient-to-br from-blue-500/10 to-transparent border border-blue-500/10">
            <p className="text-[10px] font-bold text-blue-400 uppercase mb-1">Deliberative Layer</p>
            <p className="text-[10px] text-gray-400">A* pathfinding → BFS clearance → string-pull smoothing → replan</p>
          </div>
          <div className="p-3 rounded-lg bg-gradient-to-br from-yellow-500/10 to-transparent border border-yellow-500/10">
            <p className="text-[10px] font-bold text-yellow-400 uppercase mb-1">Recovery Systems</p>
            <p className="text-[10px] text-gray-400">Anti-stall strikes • stuck-hover timer • oscillation escape • heading guard</p>
          </div>
          <div className="p-3 rounded-lg bg-gradient-to-br from-green-500/10 to-transparent border border-green-500/10">
            <p className="text-[10px] font-bold text-green-400 uppercase mb-1">Safety Guards</p>
            <p className="text-[10px] text-gray-400">Roll/pitch limits • sideslip guard • tilt cap • front debounced hard-stop</p>
          </div>
        </div>
      </div>

      {/* Tuning parameters */}
      <div className="space-y-3">
        <p className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">Live Parameters</p>
        <Slider label="Lookahead Range" value={params.lookahead} min={6} max={25} step={0.5} onChange={(v) => setParams(p => ({...p, lookahead: v}))} unit="m" />
        <Slider label="Corridor Angle" value={params.corridor} min={30} max={120} step={5} onChange={(v) => setParams(p => ({...p, corridor: v}))} unit="°" />
        <Slider label="Safety Margin" value={params.safetyMargin} min={1} max={5} step={0.5} onChange={(v) => setParams(p => ({...p, safetyMargin: v}))} unit="m" />
        <Slider label="Avoidance Gain" value={params.avoidanceGain} min={0.3} max={3.0} step={0.1} onChange={(v) => setParams(p => ({...p, avoidanceGain: v}))} />
        <Slider label="Max Blend" value={params.maxBlend} min={0.2} max={1.0} step={0.05} onChange={(v) => setParams(p => ({...p, maxBlend: v}))} />
        <Toggle label="Precision Mode" checked={params.precisionMode} onChange={(v) => setParams(p => ({...p, precisionMode: v}))} description="Falcon path-tracking controller with cross-track correction" />
        <Toggle label="Safe Presentation Profile" checked={params.safePresentation} onChange={(v) => setParams(p => ({...p, safePresentation: v}))} description="Conservative limits for live demos (lower speed, tilt, avoidance)" />
      </div>

      <button onClick={handleApply}
        className="w-full py-3 rounded-xl bg-red-500/20 border border-red-500/30 text-red-400 text-xs font-bold uppercase tracking-widest hover:bg-red-500/30 transition-all neo-glow">
        Apply Avoidance Parameters
      </button>
      {status && (
        <div className={`flex items-center space-x-2 text-xs ${status.ok ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>
          {status.ok ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          <span>{status.msg}</span>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 2: STUDENT MODEL INFERENCE
   ═══════════════════════════════════════════════════════════════════ */
function StudentInferenceTab({ droneId, runtimeStatus }) {
  const [blend, setBlend] = useState(0.0);
  const [modelPath, setModelPath] = useState('models/student_px4_god.pt');
  const [active, setActive] = useState(false);
  const [status, setStatus] = useState(null);

  const handleToggle = async () => {
    try {
      if (!active) {
        await sendTeacherCommand(droneId, 'enable_student', {
          student_model: modelPath,
          student_blend: blend,
        });
        setActive(true);
        setStatus({ ok: true, msg: `Student active at ${(blend * 100).toFixed(0)}% blend` });
      } else {
        await sendTeacherCommand(droneId, 'disable_student', {});
        setActive(false);
        setStatus({ ok: true, msg: 'Student disabled — teacher only' });
      }
    } catch (e) {
      setStatus({ ok: false, msg: getApiErrorMessage(e) });
    }
  };

  const handleBlendUpdate = async (newBlend) => {
    setBlend(newBlend);
    if (active) {
      try {
        await sendTeacherCommand(droneId, 'update_student_blend', { student_blend: newBlend });
      } catch { /* best-effort */ }
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-3 mb-2">
        <div className="p-2 rounded-lg bg-purple-500/10 border border-purple-500/20">
          <Brain className="h-5 w-5 text-purple-400" />
        </div>
        <div>
          <h3 className="text-sm font-black text-white uppercase tracking-widest">Student Model Inference</h3>
          <p className="text-[10px] text-gray-500 mt-0.5">Closed-loop neural policy — blends with teacher commands</p>
        </div>
        <StatusDot active={active} pulse />
      </div>

      {/* Architecture */}
      <div className="p-4 rounded-xl bg-black/40 border border-white/10">
        <p className="text-[10px] font-mono text-gray-400 uppercase tracking-wider mb-3">Pipeline</p>
        <div className="flex items-center space-x-2 text-[10px] font-mono text-gray-400">
          <span className="px-2 py-1 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">LIDAR 72</span>
          <span>+</span>
          <span className="px-2 py-1 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">sin/cos yaw</span>
          <span>+</span>
          <span className="px-2 py-1 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">18 scalars</span>
          <span>→</span>
          <span className="px-2 py-1 rounded bg-lesnar-accent/10 text-lesnar-accent border border-lesnar-accent/20">StudentNet 92→128→128→64→4</span>
          <span>→</span>
          <span className="px-2 py-1 rounded bg-green-500/10 text-green-400 border border-green-500/20">cmd_vx,vy,vz,yaw</span>
        </div>
      </div>

      {/* Controls */}
      <div className="space-y-3">
        <div className="p-3 rounded-lg bg-black/30 border border-white/5">
          <label className="text-xs font-bold text-white uppercase tracking-wider block mb-2">Model Checkpoint</label>
          <input
            type="text" value={modelPath}
            onChange={(e) => setModelPath(e.target.value)}
            className="w-full bg-black/50 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-gray-300 focus:border-purple-500/50 focus:outline-none"
            placeholder="path/to/model.pt"
          />
        </div>

        <Slider
          label="Teacher ↔ Student Blend"
          value={blend} min={0} max={1} step={0.05}
          onChange={handleBlendUpdate}
        />
        <div className="flex justify-between text-[10px] font-mono text-gray-500 px-1">
          <span>0% = Pure Teacher</span>
          <span>100% = Pure Student</span>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <MetricCard label="Feature Dim" value="92" icon={Layers} />
          <MetricCard label="Architecture" value="4-layer" icon={Cpu} />
          <MetricCard label="Output" value="4 cmds" icon={Target} />
        </div>
      </div>

      <button onClick={handleToggle}
        className={`w-full py-3 rounded-xl border text-xs font-bold uppercase tracking-widest transition-all neo-glow ${active
          ? 'bg-red-500/20 border-red-500/30 text-red-400 hover:bg-red-500/30'
          : 'bg-purple-500/20 border-purple-500/30 text-purple-400 hover:bg-purple-500/30'
        }`}>
        {active ? '■  Disable Student' : '▶  Enable Student Inference'}
      </button>
      {status && (
        <div className={`flex items-center space-x-2 text-xs ${status.ok ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>
          {status.ok ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          <span>{status.msg}</span>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 3: TRAINING
   ═══════════════════════════════════════════════════════════════════ */
function TrainingTab({ runtimeStatus }) {
  const [config, setConfig] = useState({ epochs: 50, batchSize: 256, csvIndex: 0 });
  const [training, setTraining] = useState(false);
  const [trainStatus, setTrainStatus] = useState(null);
  const [status, setStatus] = useState(null);

  const pollTrainStatus = useCallback(async () => {
    try {
      const ORCH = process.env.REACT_APP_ORCHESTRATOR_URL || 'http://127.0.0.1:8765';
      const res = await fetch(`${ORCH}/train/status`);
      const data = await res.json();
      setTrainStatus(data);
      if (data?.status === 'running') setTraining(true);
      else setTraining(false);
    } catch { /* orchestrator not available */ }
  }, []);

  useEffect(() => {
    pollTrainStatus();
    const iv = setInterval(pollTrainStatus, 3000);
    return () => clearInterval(iv);
  }, [pollTrainStatus]);

  const handleStartTraining = async () => {
    try {
      setTraining(true);
      setStatus(null);
      await orchestratorStartTraining({
        epochs: config.epochs,
        batchSize: config.batchSize,
        csvIndex: config.csvIndex,
      });
      setStatus({ ok: true, msg: 'Training job started on GPU' });
    } catch (e) {
      setTraining(false);
      setStatus({ ok: false, msg: getApiErrorMessage(e) });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-3 mb-2">
        <div className="p-2 rounded-lg bg-orange-500/10 border border-orange-500/20">
          <TrendingUp className="h-5 w-5 text-orange-400" />
        </div>
        <div>
          <h3 className="text-sm font-black text-white uppercase tracking-widest">Train Student Network</h3>
          <p className="text-[10px] text-gray-500 mt-0.5">GPU-accelerated imitation learning from teacher telemetry CSVs</p>
        </div>
        <StatusDot active={training} pulse />
      </div>

      {/* Pipeline */}
      <div className="p-4 rounded-xl bg-black/40 border border-white/10">
        <p className="text-[10px] font-mono text-gray-400 uppercase tracking-wider mb-3">Training Pipeline</p>
        <div className="flex items-center space-x-2 text-[10px] font-mono text-gray-400 flex-wrap gap-y-2">
          <span className="px-2 py-1 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20">Teacher CSVs (252K rows)</span>
          <span>→</span>
          <span className="px-2 py-1 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20">Threat-weighted sampler</span>
          <span>→</span>
          <span className="px-2 py-1 rounded bg-lesnar-accent/10 text-lesnar-accent border border-lesnar-accent/20">StudentNet → AdamW + CosineAnnealingLR</span>
          <span>→</span>
          <span className="px-2 py-1 rounded bg-green-500/10 text-green-400 border border-green-500/20">Best val checkpoint</span>
        </div>
      </div>

      {/* Config */}
      <div className="space-y-3">
        <Slider label="Epochs" value={config.epochs} min={5} max={200} step={5} onChange={(v) => setConfig(c => ({...c, epochs: v}))} />
        <Slider label="Batch Size" value={config.batchSize} min={32} max={1024} step={32} onChange={(v) => setConfig(c => ({...c, batchSize: v}))} />
        <Slider label="CSV Index" value={config.csvIndex} min={0} max={5} step={1} onChange={(v) => setConfig(c => ({...c, csvIndex: v}))} />
      </div>

      {/* Status */}
      {trainStatus && trainStatus.status === 'running' && (
        <div className="p-4 rounded-xl bg-orange-500/5 border border-orange-500/20">
          <div className="flex items-center space-x-2 mb-2">
            <Activity className="h-4 w-4 text-orange-400 animate-pulse" />
            <span className="text-xs font-bold text-orange-400 uppercase">Training in progress</span>
          </div>
          {trainStatus.epoch && (
            <div className="space-y-1">
              <div className="flex justify-between text-[10px] font-mono text-gray-400">
                <span>Epoch {trainStatus.epoch}/{trainStatus.total_epochs || '?'}</span>
                <span>{trainStatus.loss ? `Loss: ${trainStatus.loss}` : ''}</span>
              </div>
              <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div className="h-full bg-orange-400 transition-all" style={{ width: `${((trainStatus.epoch / (trainStatus.total_epochs || config.epochs)) * 100)}%` }} />
              </div>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <MetricCard label="GPU" value="GTX 1070" icon={Cpu} color="text-orange-400" />
        <MetricCard label="VRAM" value="8 GB" icon={Zap} color="text-orange-400" />
        <MetricCard label="Framework" value="PyTorch" icon={Box} color="text-orange-400" />
      </div>

      <button onClick={handleStartTraining} disabled={training}
        className={`w-full py-3 rounded-xl border text-xs font-bold uppercase tracking-widest transition-all neo-glow ${training
          ? 'bg-gray-700/30 border-gray-600/30 text-gray-500 cursor-not-allowed'
          : 'bg-orange-500/20 border-orange-500/30 text-orange-400 hover:bg-orange-500/30'
        }`}>
        {training ? '■  Training in Progress...' : '▶  Start GPU Training'}
      </button>
      {status && (
        <div className={`flex items-center space-x-2 text-xs ${status.ok ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>
          {status.ok ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          <span>{status.msg}</span>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 4: DOMAIN RANDOMIZATION
   ═══════════════════════════════════════════════════════════════════ */
function DomainRandomizationTab({ droneId, runtimeStatus }) {
  const [enabled, setEnabled] = useState(false);
  const [noiseParams, setNoiseParams] = useState({
    lidarSigma: 0.08, lidarDropout: 0.005,
    imuAccelBias: 0.03, imuAccelNoise: 0.15,
    gyroBias: 0.5, gyroNoise: 1.5,
    gpsNoise: 0.8, headingNoise: 1.5,
    thrustMin: 0.92,
  });
  const [status, setStatus] = useState(null);

  const handleToggle = async () => {
    try {
      await sendTeacherCommand(droneId, enabled ? 'disable_noise' : 'enable_noise', {
        domain_randomization: !enabled,
      });
      setEnabled(!enabled);
      setStatus({ ok: true, msg: enabled ? 'Noise injection disabled' : 'Noise injection enabled' });
    } catch (e) {
      setStatus({ ok: false, msg: getApiErrorMessage(e) });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-3 mb-2">
        <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
          <Shuffle className="h-5 w-5 text-cyan-400" />
        </div>
        <div>
          <h3 className="text-sm font-black text-white uppercase tracking-widest">Domain Randomization</h3>
          <p className="text-[10px] text-gray-500 mt-0.5">SensorNoiseModel — sim2real transfer via realistic sensor noise injection</p>
        </div>
        <StatusDot active={enabled} pulse />
      </div>

      {/* Noise channels */}
      <div className="p-4 rounded-xl bg-black/40 border border-white/10">
        <p className="text-[10px] font-mono text-gray-400 uppercase tracking-wider mb-3">Noise Channels</p>
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-lg bg-gradient-to-br from-cyan-500/10 to-transparent border border-cyan-500/10">
            <p className="text-[10px] font-bold text-cyan-400 uppercase mb-1">LIDAR</p>
            <p className="text-[10px] text-gray-400">σ={noiseParams.lidarSigma}m Gaussian + {(noiseParams.lidarDropout * 100).toFixed(1)}% ray dropout</p>
          </div>
          <div className="p-3 rounded-lg bg-gradient-to-br from-cyan-500/10 to-transparent border border-cyan-500/10">
            <p className="text-[10px] font-bold text-cyan-400 uppercase mb-1">IMU</p>
            <p className="text-[10px] text-gray-400">Accel: ±{noiseParams.imuAccelBias}+σ{noiseParams.imuAccelNoise} | Gyro: ±{noiseParams.gyroBias}°/s+σ{noiseParams.gyroNoise}°/s</p>
          </div>
          <div className="p-3 rounded-lg bg-gradient-to-br from-cyan-500/10 to-transparent border border-cyan-500/10">
            <p className="text-[10px] font-bold text-cyan-400 uppercase mb-1">GPS</p>
            <p className="text-[10px] text-gray-400">Position: σ={noiseParams.gpsNoise}m | Heading: σ={noiseParams.headingNoise}°</p>
          </div>
          <div className="p-3 rounded-lg bg-gradient-to-br from-cyan-500/10 to-transparent border border-cyan-500/10">
            <p className="text-[10px] font-bold text-cyan-400 uppercase mb-1">Thrust</p>
            <p className="text-[10px] text-gray-400">Global factor: {noiseParams.thrustMin}–1.0 (motor asymmetry sim)</p>
          </div>
        </div>
      </div>

      {/* Sliders */}
      <div className="space-y-3">
        <p className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">Noise Intensities</p>
        <Slider label="LIDAR σ" value={noiseParams.lidarSigma} min={0} max={0.5} step={0.01} onChange={(v) => setNoiseParams(p => ({...p, lidarSigma: v}))} unit="m" />
        <Slider label="LIDAR Ray Dropout" value={noiseParams.lidarDropout} min={0} max={0.05} step={0.001} onChange={(v) => setNoiseParams(p => ({...p, lidarDropout: v}))} />
        <Slider label="GPS Position Noise" value={noiseParams.gpsNoise} min={0} max={3.0} step={0.1} onChange={(v) => setNoiseParams(p => ({...p, gpsNoise: v}))} unit="m" />
        <Slider label="Heading Noise" value={noiseParams.headingNoise} min={0} max={5.0} step={0.1} onChange={(v) => setNoiseParams(p => ({...p, headingNoise: v}))} unit="°" />
      </div>

      <button onClick={handleToggle}
        className={`w-full py-3 rounded-xl border text-xs font-bold uppercase tracking-widest transition-all neo-glow ${enabled
          ? 'bg-red-500/20 border-red-500/30 text-red-400 hover:bg-red-500/30'
          : 'bg-cyan-500/20 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/30'
        }`}>
        {enabled ? '■  Disable Noise Injection' : '▶  Enable Domain Randomization'}
      </button>
      {status && (
        <div className={`flex items-center space-x-2 text-xs ${status.ok ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>
          {status.ok ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          <span>{status.msg}</span>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 5: DYNAMIC OBSTACLES
   ═══════════════════════════════════════════════════════════════════ */
function DynamicObstaclesTab({ droneId, runtimeStatus }) {
  const [enabled, setEnabled] = useState(false);
  const [status, setStatus] = useState(null);

  const handleToggle = async () => {
    try {
      await sendTeacherCommand(droneId, enabled ? 'disable_dynamic_obstacles' : 'enable_dynamic_obstacles', {
        dynamic_obstacles: !enabled,
      });
      setEnabled(!enabled);
      setStatus({ ok: true, msg: enabled ? 'Dynamic detection disabled' : 'Dynamic obstacle detection enabled' });
    } catch (e) {
      setStatus({ ok: false, msg: getApiErrorMessage(e) });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-3 mb-2">
        <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <Radar className="h-5 w-5 text-amber-400" />
        </div>
        <div>
          <h3 className="text-sm font-black text-white uppercase tracking-widest">Dynamic Obstacle Detection</h3>
          <p className="text-[10px] text-gray-500 mt-0.5">LIDAR vs. SDF comparison — detects obstacles not in the static map</p>
        </div>
        <StatusDot active={enabled} pulse />
      </div>

      {/* How it works */}
      <div className="p-4 rounded-xl bg-black/40 border border-white/10">
        <p className="text-[10px] font-mono text-gray-400 uppercase tracking-wider mb-3">Detection Pipeline</p>
        <div className="space-y-3">
          <div className="flex items-start space-x-3">
            <div className="h-6 w-6 rounded-full bg-amber-500/20 flex items-center justify-center text-[10px] font-bold text-amber-400 flex-shrink-0">1</div>
            <div><p className="text-[10px] text-gray-300">Compare actual LIDAR readings vs. expected SDF geometry per ray</p></div>
          </div>
          <div className="flex items-start space-x-3">
            <div className="h-6 w-6 rounded-full bg-amber-500/20 flex items-center justify-center text-[10px] font-bold text-amber-400 flex-shrink-0">2</div>
            <div><p className="text-[10px] text-gray-300">Where actual &lt; expected − 2m → ray-cast hit to world coordinates</p></div>
          </div>
          <div className="flex items-start space-x-3">
            <div className="h-6 w-6 rounded-full bg-amber-500/20 flex items-center justify-center text-[10px] font-bold text-amber-400 flex-shrink-0">3</div>
            <div><p className="text-[10px] text-gray-300">Mark new cells as blocked in GridMap with incremental BFS clearance update</p></div>
          </div>
          <div className="flex items-start space-x-3">
            <div className="h-6 w-6 rounded-full bg-amber-500/20 flex items-center justify-center text-[10px] font-bold text-amber-400 flex-shrink-0">4</div>
            <div><p className="text-[10px] text-gray-300">A* automatically routes around newly detected obstacles on next replan</p></div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <MetricCard label="Method" value="LIDAR Δ" icon={Radar} color="text-amber-400" />
        <MetricCard label="Update" value="Incremental" icon={RefreshCw} color="text-amber-400" />
      </div>

      <button onClick={handleToggle}
        className={`w-full py-3 rounded-xl border text-xs font-bold uppercase tracking-widest transition-all neo-glow ${enabled
          ? 'bg-red-500/20 border-red-500/30 text-red-400 hover:bg-red-500/30'
          : 'bg-amber-500/20 border-amber-500/30 text-amber-400 hover:bg-amber-500/30'
        }`}>
        {enabled ? '■  Disable Dynamic Detection' : '▶  Enable Dynamic Obstacle Detection'}
      </button>
      {status && (
        <div className={`flex items-center space-x-2 text-xs ${status.ok ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>
          {status.ok ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          <span>{status.msg}</span>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 6: EVALUATION
   ═══════════════════════════════════════════════════════════════════ */
function EvaluationTab() {
  const [config, setConfig] = useState({ modelPath: 'models/student_px4_god.pt', dataGlob: 'dataset/px4_teacher/telemetry_god_*.csv' });
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState(null);

  const handleEvaluate = async () => {
    setRunning(true);
    setStatus(null);
    try {
      const ORCH = process.env.REACT_APP_ORCHESTRATOR_URL || 'http://127.0.0.1:8765';
      const res = await fetch(`${ORCH}/eval/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: config.modelPath, data: config.dataGlob }),
      });
      const data = await res.json();
      if (data.success) {
        setResult(data.metrics);
        setStatus({ ok: true, msg: `Evaluation complete — Grade: ${data.metrics?.grade || '?'}` });
      } else {
        setStatus({ ok: false, msg: data.error || 'Evaluation failed' });
      }
    } catch (e) {
      setStatus({ ok: false, msg: 'Orchestrator not reachable or eval endpoint not available' });
    } finally {
      setRunning(false);
    }
  };

  const gradeColor = (grade) => {
    if (!grade) return 'text-gray-500';
    const g = grade.toUpperCase();
    if (g === 'A') return 'text-lesnar-success';
    if (g === 'B') return 'text-blue-400';
    if (g === 'C') return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-3 mb-2">
        <div className="p-2 rounded-lg bg-green-500/10 border border-green-500/20">
          <BarChart3 className="h-5 w-5 text-green-400" />
        </div>
        <div>
          <h3 className="text-sm font-black text-white uppercase tracking-widest">Evaluation Harness</h3>
          <p className="text-[10px] text-gray-500 mt-0.5">Replay teacher CSVs through student model — accuracy & deployment grade</p>
        </div>
      </div>

      {/* Config */}
      <div className="space-y-3">
        <div className="p-3 rounded-lg bg-black/30 border border-white/5">
          <label className="text-xs font-bold text-white uppercase tracking-wider block mb-2">Model Path</label>
          <input type="text" value={config.modelPath}
            onChange={(e) => setConfig(c => ({...c, modelPath: e.target.value}))}
            className="w-full bg-black/50 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-gray-300 focus:border-green-500/50 focus:outline-none" />
        </div>
        <div className="p-3 rounded-lg bg-black/30 border border-white/5">
          <label className="text-xs font-bold text-white uppercase tracking-wider block mb-2">Data Glob</label>
          <input type="text" value={config.dataGlob}
            onChange={(e) => setConfig(c => ({...c, dataGlob: e.target.value}))}
            className="w-full bg-black/50 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-gray-300 focus:border-green-500/50 focus:outline-none" />
        </div>
      </div>

      {/* Metrics list */}
      <div className="p-4 rounded-xl bg-black/40 border border-white/10">
        <p className="text-[10px] font-mono text-gray-400 uppercase tracking-wider mb-3">Metrics Computed</p>
        <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-gray-400">
          <span>• MAE (overall + per-channel)</span>
          <span>• MSE (mean squared error)</span>
          <span>• Direction agreement (%)</span>
          <span>• Speed MAE (m/s)</span>
          <span>• Collision proxy rate</span>
          <span>• Avoidance MAE (high-threat)</span>
          <span>• Cruise MAE (low-threat)</span>
          <span>• Deployment grade (A–F)</span>
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="p-4 rounded-xl bg-green-500/5 border border-green-500/20">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold text-green-400 uppercase">Results</span>
            <span className={`text-3xl font-black ${gradeColor(result.grade)}`}>{result.grade}</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(result).filter(([k]) => k !== 'grade').map(([k, v]) => (
              <div key={k} className="flex justify-between text-[10px] font-mono">
                <span className="text-gray-500">{k}</span>
                <span className="text-gray-300">{typeof v === 'number' ? v.toFixed(4) : String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <button onClick={handleEvaluate} disabled={running}
        className={`w-full py-3 rounded-xl border text-xs font-bold uppercase tracking-widest transition-all neo-glow ${running
          ? 'bg-gray-700/30 border-gray-600/30 text-gray-500 cursor-not-allowed'
          : 'bg-green-500/20 border-green-500/30 text-green-400 hover:bg-green-500/30'
        }`}>
        {running ? '■  Evaluating...' : '▶  Run Evaluation'}
      </button>
      {status && (
        <div className={`flex items-center space-x-2 text-xs ${status.ok ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>
          {status.ok ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          <span>{status.msg}</span>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   MAIN: AI LAB PAGE
   ═══════════════════════════════════════════════════════════════════ */
const TABS = [
  { id: 'avoidance', label: 'Obstacle Avoidance', icon: Shield, color: 'red' },
  { id: 'student', label: 'Student Inference', icon: Brain, color: 'purple' },
  { id: 'training', label: 'Training', icon: TrendingUp, color: 'orange' },
  { id: 'noise', label: 'Domain Randomization', icon: Shuffle, color: 'cyan' },
  { id: 'dynamic', label: 'Dynamic Obstacles', icon: Radar, color: 'amber' },
  { id: 'eval', label: 'Evaluation', icon: BarChart3, color: 'green' },
];

export default function AILab() {
  const [activeTab, setActiveTab] = useState('avoidance');
  const { drones } = useDrones();
  const [runtimeStatus, setRuntimeStatus] = useState(null);

  const droneId = drones.length > 0 ? (drones[0].drone_id || drones[0].id) : 'x500_0';

  useEffect(() => {
    const check = async () => {
      try {
        const res = await orchestratorStatus();
        if (res?.success) setRuntimeStatus(res.status);
      } catch { /* orchestrator down */ }
    };
    check();
    const iv = setInterval(check, 5000);
    return () => clearInterval(iv);
  }, []);

  const renderTab = () => {
    switch (activeTab) {
      case 'avoidance': return <ObstacleAvoidanceTab droneId={droneId} runtimeStatus={runtimeStatus} />;
      case 'student': return <StudentInferenceTab droneId={droneId} runtimeStatus={runtimeStatus} />;
      case 'training': return <TrainingTab runtimeStatus={runtimeStatus} />;
      case 'noise': return <DomainRandomizationTab droneId={droneId} runtimeStatus={runtimeStatus} />;
      case 'dynamic': return <DynamicObstaclesTab droneId={droneId} runtimeStatus={runtimeStatus} />;
      case 'eval': return <EvaluationTab />;
      default: return null;
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 pb-8 pt-4">
      {/* Hero */}
      <div className="mb-6">
        <div className="flex items-center space-x-4">
          <div className="p-3 rounded-2xl bg-lesnar-accent/10 border border-lesnar-accent/20 neo-glow">
            <Brain className="h-7 w-7 text-lesnar-accent" />
          </div>
          <div>
            <h1 className="text-xl font-black text-white uppercase tracking-[0.2em]">AI Lab</h1>
            <p className="text-[11px] text-gray-500 mt-0.5">Neural policy control • obstacle avoidance • sim2real • evaluation</p>
          </div>
          <div className="ml-auto flex items-center space-x-3">
            <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-black/40 border border-white/10">
              <span className="text-[10px] font-mono text-gray-500 uppercase">Runtime</span>
              <StatusDot active={runtimeStatus?.teacher_running} pulse />
            </div>
            <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-black/40 border border-white/10">
              <span className="text-[10px] font-mono text-gray-500 uppercase">Drone</span>
              <span className="text-[10px] font-mono text-lesnar-accent">{droneId}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex space-x-2 mb-6 overflow-x-auto pb-2 custom-scrollbar">
        {TABS.map(tab => (
          <TabButton
            key={tab.id}
            icon={tab.icon}
            label={tab.label}
            active={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
          />
        ))}
      </div>

      {/* Tab content */}
      <div className="card relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-lesnar-accent/3 to-transparent pointer-events-none" />
        <div className="relative p-6">
          {renderTab()}
        </div>
      </div>
    </div>
  );
}
