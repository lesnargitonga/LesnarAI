export function getDroneFlags(drone) {
  const toNumberOrNull = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  };

  const altitude = toNumberOrNull(drone?.altitude);
  const speed = toNumberOrNull(drone?.speed);
  const battery = toNumberOrNull(drone?.battery);
  const armed = Boolean(drone?.armed);
  const inAir = Boolean(drone?.in_air);
  const mode = String(drone?.mode || '').toUpperCase();

  const directFlightMode = ['TAKEOFF', 'OFFBOARD', 'MISSION', 'RTL'].some((token) => mode.includes(token));
  const managedFlightMode = ['AUTO', 'LOITER', 'HOLD'].some((token) => mode.includes(token));
  const speedForLogic = speed ?? 0;
  const altitudeForLogic = altitude ?? 0;
  const moving = speedForLogic > 0.8;
  const airborneByAlt = altitudeForLogic > 1.0;
  const flying = inAir || airborneByAlt || (directFlightMode && (airborneByAlt || moving || armed)) || (managedFlightMode && (airborneByAlt || moving)) || (armed && moving);

  return { altitude, speed, battery, armed, inAir, mode, flying };
}

export function getDroneStatus(drone) {
  if (drone?.telemetry_missing) {
    return { key: 'no_link', label: 'NO LINK', dot: 'bg-lesnar-danger', text: 'text-lesnar-danger' };
  }
  const { battery, armed, flying } = getDroneFlags(drone);
  if (Number.isFinite(battery) && battery < 20) {
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
