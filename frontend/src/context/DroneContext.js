import React, { createContext, useContext, useReducer, useEffect, useCallback } from 'react';
import api from '../api';
import { appendOperatorAudit, getOperatorIdentity } from '../utils/operatorAudit';
import { TELEMETRY_STALE_MS, getTelemetryAgeMs, isTelemetryStale } from '../utils/operational';

const isDemoDrone = (drone) => String(drone?.drone_id || '').toUpperCase().startsWith('LESNAR-DEMO-');
const sanitizeDrones = (drones) => (Array.isArray(drones) ? drones.filter((drone) => !isDemoDrone(drone)) : []);

// Initial state
const initialState = {
  drones: [],
  selectedDrone: null,
  loading: false,
  error: null,
  telemetry: null,
  lastTelemetryReceivedAt: null,
  fleetStatus: {
    total_drones: 0,
    armed_drones: 0,
    flying_drones: 0,
    low_battery_drones: 0
  }
};

// Action types
const actionTypes = {
  SET_LOADING: 'SET_LOADING',
  SET_ERROR: 'SET_ERROR',
  SET_DRONES: 'SET_DRONES',
  ADD_DRONE: 'ADD_DRONE',
  UPDATE_DRONE: 'UPDATE_DRONE',
  REMOVE_DRONE: 'REMOVE_DRONE',
  SELECT_DRONE: 'SELECT_DRONE',
  UPDATE_TELEMETRY: 'UPDATE_TELEMETRY',
  UPDATE_FLEET_STATUS: 'UPDATE_FLEET_STATUS',
  SET_LAST_TELEMETRY_AT: 'SET_LAST_TELEMETRY_AT'
};

function ensureConfirmed(response, fallbackMessage) {
  const payload = response?.data || {};
  if (payload.success) {
    return payload;
  }
  if (payload.accepted) {
    return payload;
  }
  const error = new Error(payload.message || payload.error || fallbackMessage || 'Command not confirmed');
  error.accepted = Boolean(payload.accepted);
  error.confirmed = Boolean(payload.confirmed);
  error.payload = payload;
  throw error;
}

const CONTROL_WAIT_TIMEOUT_MS = 25000;
const CONTROL_WAIT_INTERVAL_MS = 500;

async function waitForDroneState(apiClient, droneId, predicate, timeoutMs = CONTROL_WAIT_TIMEOUT_MS) {
  const deadline = Date.now() + timeoutMs;
  let lastDrone = null;
  while (Date.now() < deadline) {
    try {
      const response = await apiClient.get('/api/drones');
      const drones = Array.isArray(response?.data?.drones) ? response.data.drones : [];
      const drone = drones.find((d) => d?.drone_id === droneId) || null;
      if (drone) {
        lastDrone = drone;
        if (predicate(drone)) {
          return { success: true, drone };
        }
      }
    } catch {
    }
    await new Promise((resolve) => setTimeout(resolve, CONTROL_WAIT_INTERVAL_MS));
  }
  return { success: false, drone: lastDrone };
}

async function resolveAcceptedCommand(apiClient, droneId, action, payload) {
  if (!payload?.accepted || payload?.success) {
    return payload;
  }

  const targetAlt = Number(payload?.target_altitude || 1);
  const isTakeoffConfirmed = (drone) => {
    const altitude = Number(drone?.altitude || 0);
    const inAir = Boolean(drone?.in_air);
    const armed = Boolean(drone?.armed);
    return armed && (inAir || altitude >= Math.min(targetAlt, 1.0));
  };
  const isLandConfirmed = (drone) => {
    const altitude = Number(drone?.altitude || 0);
    const armed = Boolean(drone?.armed);
    return !armed || altitude <= 0.5;
  };

  const predicates = {
    arm: (drone) => Boolean(drone?.armed),
    disarm: (drone) => !Boolean(drone?.armed),
    takeoff: isTakeoffConfirmed,
    land: isLandConfirmed,
  };

  const predicate = predicates[action];
  if (!predicate) {
    return payload;
  }

  const waited = await waitForDroneState(apiClient, droneId, predicate);
  if (waited.success) {
    return {
      ...payload,
      success: true,
      confirmed: true,
      accepted: false,
      state: waited.drone || payload.state,
      message: payload.message?.replace('accepted', 'confirmed after synchronization') || `Command confirmed for ${droneId}.`,
    };
  }

  const error = new Error(payload.message || `Command not confirmed for ${droneId}`);
  error.accepted = true;
  error.confirmed = false;
  error.payload = payload;
  throw error;
}

function assertRole(required = 'operator') {
  const order = { viewer: 0, operator: 1, admin: 2 };
  const role = getOperatorIdentity().role || 'viewer';
  if ((order[role] ?? 0) < (order[required] ?? 1)) {
    throw new Error(`RBAC: ${required.toUpperCase()} role required.`);
  }
}

// Reducer
function droneReducer(state, action) {
  switch (action.type) {
    case actionTypes.SET_LOADING:
      return {
        ...state,
        loading: action.payload
      };
    
    case actionTypes.SET_ERROR:
      return {
        ...state,
        error: action.payload,
        loading: false
      };
    
    case actionTypes.SET_DRONES:
      return {
        ...state,
        drones: action.payload,
        loading: false,
        error: null
      };
    
    case actionTypes.ADD_DRONE:
      return {
        ...state,
        drones: [...state.drones, action.payload]
      };
    
    case actionTypes.UPDATE_DRONE:
      return {
        ...state,
        drones: state.drones.map(drone => 
          drone.drone_id === action.payload.drone_id 
            ? { ...drone, ...action.payload }
            : drone
        )
      };
    
    case actionTypes.REMOVE_DRONE:
      return {
        ...state,
        drones: state.drones.filter(drone => drone.drone_id !== action.payload),
        selectedDrone: state.selectedDrone?.drone_id === action.payload ? null : state.selectedDrone
      };
    
    case actionTypes.SELECT_DRONE:
      return {
        ...state,
        selectedDrone: action.payload
      };
    
    case actionTypes.UPDATE_TELEMETRY:
      return {
        ...state,
        telemetry: action.payload,
        drones: action.payload.telemetry || state.drones
      };
    
    case actionTypes.UPDATE_FLEET_STATUS:
      return {
        ...state,
        fleetStatus: action.payload
      };

    case actionTypes.SET_LAST_TELEMETRY_AT:
      return {
        ...state,
        lastTelemetryReceivedAt: action.payload
      };
    
    default:
      return state;
  }
}

// Create context
const DroneContext = createContext();

// Provider component
export function DroneProvider({ children, socketConnected = false }) {
  const [state, dispatch] = useReducer(droneReducer, initialState);

  // API functions
  const fetchDrones = async () => {
    try {
      dispatch({ type: actionTypes.SET_LOADING, payload: true });
      const response = await api.get('/api/drones');
      dispatch({ type: actionTypes.SET_DRONES, payload: sanitizeDrones(response.data.drones) });
      dispatch({ type: actionTypes.SET_LAST_TELEMETRY_AT, payload: Date.now() });
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
    }
  };

  const createDrone = async (droneData) => {
    try {
      assertRole('operator');
      const response = await api.post('/api/drones', droneData);
      if (response.data.success) {
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
        await fetchDrones();
        return response.data;
      }
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const deleteDrone = async (droneId) => {
    try {
      assertRole('operator');
      const response = await api.delete(`/api/drones/${droneId}`);
      if (response.data.success) {
        dispatch({ type: actionTypes.REMOVE_DRONE, payload: droneId });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
        return response.data;
      }
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const armDrone = async (droneId) => {
    try {
      assertRole('operator');
      appendOperatorAudit({ type: 'intent', level: 'warning', message: `Operator [${getOperatorIdentity().operatorId}] initiated ARM for ${droneId}.`, droneId, action: 'arm' });
      const response = await api.post(`/api/drones/${droneId}/arm`);
      const payload = await resolveAcceptedCommand(api, droneId, 'arm', ensureConfirmed(response, `Failed to arm ${droneId}`));
      if (payload.state) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: payload.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      appendOperatorAudit({ type: 'command', level: 'success', message: payload.message || `ARM confirmed for ${droneId}.`, droneId, action: 'arm' });
      return payload;
    } catch (error) {
      appendOperatorAudit({ type: 'error', level: 'error', message: error.message || `ARM failed for ${droneId}.`, droneId, action: 'arm' });
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const disarmDrone = async (droneId) => {
    try {
      assertRole('operator');
      appendOperatorAudit({ type: 'intent', level: 'warning', message: `Operator [${getOperatorIdentity().operatorId}] initiated DISARM for ${droneId}.`, droneId, action: 'disarm' });
      const response = await api.post(`/api/drones/${droneId}/disarm`);
      const payload = await resolveAcceptedCommand(api, droneId, 'disarm', ensureConfirmed(response, `Failed to disarm ${droneId}`));
      if (payload.state) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: payload.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      appendOperatorAudit({ type: 'command', level: 'success', message: payload.message || `DISARM confirmed for ${droneId}.`, droneId, action: 'disarm' });
      return payload;
    } catch (error) {
      appendOperatorAudit({ type: 'error', level: 'error', message: error.message || `DISARM failed for ${droneId}.`, droneId, action: 'disarm' });
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const takeoffDrone = async (droneId, altitude = 10) => {
    try {
      assertRole('operator');
      appendOperatorAudit({ type: 'intent', level: 'warning', message: `Operator [${getOperatorIdentity().operatorId}] initiated TAKEOFF for ${droneId} to ${altitude}m.`, droneId, action: 'takeoff' });
      const response = await api.post(`/api/drones/${droneId}/takeoff`, { altitude });
      const payload = await resolveAcceptedCommand(api, droneId, 'takeoff', ensureConfirmed(response, `Failed to verify takeoff for ${droneId}`));
      if (payload.state) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: payload.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      appendOperatorAudit({ type: 'command', level: 'success', message: payload.message || `TAKEOFF confirmed for ${droneId}.`, droneId, action: 'takeoff' });
      return payload;
    } catch (error) {
      appendOperatorAudit({ type: 'error', level: 'error', message: error.message || `TAKEOFF failed for ${droneId}.`, droneId, action: 'takeoff' });
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const landDrone = async (droneId) => {
    try {
      assertRole('operator');
      appendOperatorAudit({ type: 'intent', level: 'warning', message: `Operator [${getOperatorIdentity().operatorId}] initiated LAND for ${droneId}.`, droneId, action: 'land' });
      const response = await api.post(`/api/drones/${droneId}/land`);
      const payload = await resolveAcceptedCommand(api, droneId, 'land', ensureConfirmed(response, `Failed to verify landing for ${droneId}`));
      if (payload.state) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: payload.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      appendOperatorAudit({ type: 'command', level: 'success', message: payload.message || `LAND confirmed for ${droneId}.`, droneId, action: 'land' });
      return payload;
    } catch (error) {
      appendOperatorAudit({ type: 'error', level: 'error', message: error.message || `LAND failed for ${droneId}.`, droneId, action: 'land' });
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const gotoDrone = async (droneId, latitude, longitude, altitude) => {
    try {
      assertRole('operator');
      appendOperatorAudit({ type: 'intent', level: 'warning', message: `Operator [${getOperatorIdentity().operatorId}] initiated GOTO for ${droneId} to ${Number(latitude).toFixed(5)}, ${Number(longitude).toFixed(5)} @ ${altitude}m.`, droneId, action: 'goto' });
      const response = await api.post(`/api/drones/${droneId}/goto`, {
        latitude,
        longitude,
        altitude
      });
      const payload = ensureConfirmed(response, `Failed to verify navigation for ${droneId}`);
      if (payload.state) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: payload.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      appendOperatorAudit({ type: 'command', level: 'success', message: payload.message || `GOTO confirmed for ${droneId}.`, droneId, action: 'goto' });
      return payload;
    } catch (error) {
      appendOperatorAudit({ type: 'error', level: 'error', message: error.message || `GOTO failed for ${droneId}.`, droneId, action: 'goto' });
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const executeMission = async (droneId, waypoints, missionType) => {
    try {
      assertRole('operator');
      appendOperatorAudit({ type: 'intent', level: 'warning', message: `Operator [${getOperatorIdentity().operatorId}] initiated MISSION ${missionType} for ${droneId}.`, droneId, action: 'mission_start' });
      const response = await api.post(`/api/drones/${droneId}/mission`, {
        waypoints,
        mission_type: missionType
      });
      if (response.data.success) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: response.data.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
        appendOperatorAudit({ type: 'command', level: 'success', message: response.data.message || `Mission started for ${droneId}.`, droneId, action: 'mission_start' });
      }
      return response.data;
    } catch (error) {
      appendOperatorAudit({ type: 'error', level: 'error', message: error.message || `Mission start failed for ${droneId}.`, droneId, action: 'mission_start' });
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const emergencyLandAll = async () => {
    try {
      assertRole('operator');
      appendOperatorAudit({ type: 'intent', level: 'warning', message: `Operator [${getOperatorIdentity().operatorId}] initiated GLOBAL EMERGENCY LAND.`, action: 'emergency_land_all' });
      const response = await api.post('/api/emergency');
      if (response.data.success) {
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
        await fetchDrones();
        appendOperatorAudit({ type: 'command', level: 'success', message: response.data.message || 'Global emergency land confirmed.', action: 'emergency_land_all' });
      }
      return response.data;
    } catch (error) {
      appendOperatorAudit({ type: 'error', level: 'error', message: error.message || 'Global emergency land failed.', action: 'emergency_land_all' });
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const updateTelemetry = useCallback((telemetryData) => {
    const sanitizedTelemetry = {
      ...telemetryData,
      telemetry: sanitizeDrones(telemetryData?.telemetry),
    };
    dispatch({ type: actionTypes.UPDATE_TELEMETRY, payload: sanitizedTelemetry });
    dispatch({ type: actionTypes.SET_LAST_TELEMETRY_AT, payload: Date.now() });
    if (telemetryData.fleet_status) {
      dispatch({ type: actionTypes.UPDATE_FLEET_STATUS, payload: telemetryData.fleet_status });
    }
  }, []);

  const selectDrone = (drone) => {
    dispatch({ type: actionTypes.SELECT_DRONE, payload: drone });
  };

  const clearError = () => {
    dispatch({ type: actionTypes.SET_ERROR, payload: null });
  };

  // Load drones on mount
  useEffect(() => {
    fetchDrones();
  }, []);

  useEffect(() => {
    const intervalMs = socketConnected ? 2500 : 5000;
    const timer = setInterval(fetchDrones, intervalMs);
    return () => clearInterval(timer);
  }, [socketConnected]);

  const telemetryAgeMs = state.lastTelemetryReceivedAt == null ? Number.POSITIVE_INFINITY : Math.max(0, Date.now() - state.lastTelemetryReceivedAt);
  const telemetryStale = telemetryAgeMs > TELEMETRY_STALE_MS;
  const isDroneControlAllowed = (drone) => {
    if (!drone) return false;
    const fallbackTimestamp = state.lastTelemetryReceivedAt ? new Date(state.lastTelemetryReceivedAt).toISOString() : null;
    const effectiveDrone = drone.timestamp ? drone : { ...drone, timestamp: fallbackTimestamp };
    return !isTelemetryStale(effectiveDrone);
  };

  const value = {
    ...state,
    telemetryAgeMs,
    telemetryStale,
    isDroneControlAllowed,
    getDroneTelemetryAgeMs: (drone) => getTelemetryAgeMs(drone),
    // Actions
    fetchDrones,
    createDrone,
    deleteDrone,
    armDrone,
    disarmDrone,
    takeoffDrone,
    landDrone,
    gotoDrone,
    executeMission,
    emergencyLandAll,
    updateTelemetry,
    selectDrone,
    clearError
  };

  return (
    <DroneContext.Provider value={value}>
      {children}
    </DroneContext.Provider>
  );
}

// Custom hook to use the drone context
export function useDrones() {
  const context = useContext(DroneContext);
  if (!context) {
    throw new Error('useDrones must be used within a DroneProvider');
  }
  return context;
}

export default DroneContext;
