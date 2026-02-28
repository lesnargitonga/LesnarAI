import React, { createContext, useContext, useReducer, useEffect, useCallback } from 'react';
import api from '../api';

// Initial state
const initialState = {
  drones: [],
  selectedDrone: null,
  loading: false,
  error: null,
  telemetry: null,
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
  UPDATE_FLEET_STATUS: 'UPDATE_FLEET_STATUS'
};

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
    
    default:
      return state;
  }
}

// Create context
const DroneContext = createContext();

// Provider component
export function DroneProvider({ children }) {
  const [state, dispatch] = useReducer(droneReducer, initialState);

  // API functions
  const fetchDrones = async () => {
    try {
      dispatch({ type: actionTypes.SET_LOADING, payload: true });
      const response = await api.get('/api/drones');
      dispatch({ type: actionTypes.SET_DRONES, payload: response.data.drones });
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
    }
  };

  const createDrone = async (droneData) => {
    try {
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
      const response = await api.post(`/api/drones/${droneId}/arm`);
      if (response.data.success) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: response.data.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      return response.data;
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const disarmDrone = async (droneId) => {
    try {
      const response = await api.post(`/api/drones/${droneId}/disarm`);
      if (response.data.success) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: response.data.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      return response.data;
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const takeoffDrone = async (droneId, altitude = 10) => {
    try {
      const response = await api.post(`/api/drones/${droneId}/takeoff`, { altitude });
      if (response.data.success) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: response.data.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      return response.data;
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const landDrone = async (droneId) => {
    try {
      const response = await api.post(`/api/drones/${droneId}/land`);
      if (response.data.success) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: response.data.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      return response.data;
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const gotoDrone = async (droneId, latitude, longitude, altitude) => {
    try {
      const response = await api.post(`/api/drones/${droneId}/goto`, {
        latitude,
        longitude,
        altitude
      });
      if (response.data.success) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: response.data.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      return response.data;
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const executeMission = async (droneId, waypoints, missionType) => {
    try {
      const response = await api.post(`/api/drones/${droneId}/mission`, {
        waypoints,
        mission_type: missionType
      });
      if (response.data.success) {
        dispatch({ type: actionTypes.UPDATE_DRONE, payload: response.data.state });
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
      }
      return response.data;
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const emergencyLandAll = async () => {
    try {
      const response = await api.post('/api/emergency');
      if (response.data.success) {
        dispatch({ type: actionTypes.SET_ERROR, payload: null });
        await fetchDrones();
      }
      return response.data;
    } catch (error) {
      dispatch({ type: actionTypes.SET_ERROR, payload: error.message });
      throw error;
    }
  };

  const updateTelemetry = useCallback((telemetryData) => {
    dispatch({ type: actionTypes.UPDATE_TELEMETRY, payload: telemetryData });
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

  const value = {
    ...state,
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
