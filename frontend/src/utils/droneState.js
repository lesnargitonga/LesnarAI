export function getDroneFlags(drone) {
  const altitude = Number(drone?.altitude || 0);
  const speed = Number(drone?.speed || 0);
  const battery = Number(drone?.battery || 0);
  const armed = Boolean(drone?.armed);
  const inAir = Boolean(drone?.in_air);
  const mode = String(drone?.mode || '').toUpperCase();

  const directFlightMode = ['TAKEOFF', 'OFFBOARD', 'MISSION', 'RTL'].some((token) => mode.includes(token));
  const managedFlightMode = ['AUTO', 'LOITER', 'HOLD'].some((token) => mode.includes(token));
  const moving = speed > 0.8;
  const airborneByAlt = altitude > 1.0;
  const flying = inAir || airborneByAlt || (directFlightMode && (airborneByAlt || moving || armed)) || (managedFlightMode && (airborneByAlt || moving)) || (armed && moving);

  return { altitude, speed, battery, armed, inAir, mode, flying };
}

export function getDroneStatus(drone) {
  const { battery, armed, flying } = getDroneFlags(drone);
  if (battery > 0 && battery < 20) {
    return { key: 'low_power', label: 'LOW POWER', dot: 'bg-lesnar-danger', text: 'text-lesnar-danger' };
  }
  if (flying) {
    return { key: 'airborne', label: 'AIRBORNE', dot: 'bg-lesnar-success animate-pulse', text: 'text-lesnar-success' };
  }
  if (armed) {
    return { key: 'armed', label: 'ARMED', dot: 'bg-lesnar-warning', text: 'text-lesnar-warning' };
  }
  return { key: 'standby', label: 'STANDBY', dot: 'bg-gray-500', text: 'text-gray-300' };
}
