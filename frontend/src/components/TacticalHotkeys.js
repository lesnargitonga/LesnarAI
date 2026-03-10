import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDrones } from '../context/DroneContext';
import { appendOperatorAudit, requireTypedConfirmation } from '../utils/operatorAudit';

const QUICK_SELECT_EVENT = 'lesnar:quick-select-drone';

export function emitQuickSelect(droneId) {
  window.dispatchEvent(new CustomEvent(QUICK_SELECT_EVENT, { detail: { droneId } }));
}

export function subscribeQuickSelect(listener) {
  const handler = (event) => listener(event.detail?.droneId);
  window.addEventListener(QUICK_SELECT_EVENT, handler);
  return () => window.removeEventListener(QUICK_SELECT_EVENT, handler);
}

function TacticalHotkeys() {
  const navigate = useNavigate();
  const { drones, emergencyLandAll } = useDrones();

  useEffect(() => {
    const onKeyDown = async (event) => {
      if (event.target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) return;

      if (event.shiftKey && event.key === 'Escape') {
        event.preventDefault();
        if (!requireTypedConfirmation('Emergency land all assets?', 'CONFIRM')) return;
        try {
          await emergencyLandAll();
          appendOperatorAudit({ type: 'command', level: 'warning', message: 'Hotkey SHIFT+ESC triggered GLOBAL EMERGENCY LAND.', action: 'emergency_land_all' });
        } catch (error) {
          appendOperatorAudit({ type: 'error', level: 'error', message: error.message || 'Hotkey emergency land failed.', action: 'emergency_land_all' });
        }
        return;
      }

      if (event.key === 'g' || event.key === 'G') {
        navigate('/map');
        return;
      }

      if (event.key === 'd' || event.key === 'D') {
        navigate('/drones');
        return;
      }

      if (/^[1-3]$/.test(event.key)) {
        const index = Number(event.key) - 1;
        const drone = drones[index];
        if (drone) {
          emitQuickSelect(drone.drone_id);
          appendOperatorAudit({ type: 'intent', level: 'info', message: `Hotkey ${event.key} selected ${drone.drone_id}.`, droneId: drone.drone_id, action: 'quick_select' });
        }
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [drones, emergencyLandAll, navigate]);

  return null;
}

export default TacticalHotkeys;
