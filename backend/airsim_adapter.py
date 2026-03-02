from __future__ import annotations

import time
import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import airsim


@dataclass
class AirSimDroneState:
    drone_id: str
    latitude: float   # reused field name; stores AirSim X (m)
    longitude: float  # reused field name; stores AirSim Y (m)
    altitude: float   # positive up (m) from NED
    heading: float
    speed: float
    battery: float
    armed: bool
    mode: str
    timestamp: str

    def to_dict(self) -> Dict:
        return asdict(self)


class AirSimAdapter:
    def __init__(self, vehicle_names: Optional[List[str]] = None):
        self.client = airsim.MultirotorClient()
        self.client.confirmConnection()
        # Try to discover vehicles; fallback to SimpleFlight
        names: List[str] = []
        try:
            # listVehicles is available on newer AirSim servers; ignore if not
            if hasattr(self.client, 'listVehicles'):
                names = self.client.listVehicles()
        except Exception:
            names = []
        if not names:
            names = vehicle_names or ["SimpleFlight"]
        self.vehicle_names = names

    @staticmethod
    def _quat_to_yaw(rad_q) -> float:
        # AirSim util helper
        r, p, y = airsim.to_eularian_angles(rad_q)
        return math.degrees(y)

    def get_all_states(self) -> List[AirSimDroneState]:
        from datetime import datetime
        states: List[AirSimDroneState] = []
        for name in self.vehicle_names:
            try:
                st = self.client.getMultirotorState(vehicle_name=name)
                kin = st.kinematics_estimated
                pos = kin.position
                vel = kin.linear_velocity
                yaw_deg = self._quat_to_yaw(kin.orientation)
                speed = float(math.sqrt(vel.x_val**2 + vel.y_val**2 + vel.z_val**2))
                # Map AirSim NED to dashboard fields (lat/lon reused for X/Y meters)
                alt = float(-pos.z_val)
                armed = bool(getattr(st, 'rc_data', None).is_connected) if hasattr(st, 'rc_data') else True
                states.append(
                    AirSimDroneState(
                        drone_id=name,
                        latitude=float(pos.x_val),
                        longitude=float(pos.y_val),
                        altitude=alt,
                        heading=float(yaw_deg),
                        speed=speed,
                        battery=100.0,
                        armed=armed,
                        mode="AIRSIM",
                        timestamp=datetime.now().isoformat(),
                    )
                )
            except Exception:
                # Skip vehicles that failed this tick
                continue
        return states

    def get_state(self, drone_id: str) -> Optional[AirSimDroneState]:
        for s in self.get_all_states():
            if s.drone_id == drone_id:
                return s
        return None

    def goto(self, drone_id: str, lat: float, lon: float, alt: float) -> bool:
        """
        Sends a 'NAVIGATE' command to the RL brain via the mission bridge.
        'lat' is interpreted as X (North), 'lon' as Y (East).
        """
        try:
            # Lazy import to avoid circular dependency issues if any
            from mission_bridge import send_mission_override
            # Note: airsim uses NED. Alt is positive down.
            # If UI sends positive Altitude (Height), we convert to negative Z.
            z_target = -abs(alt) if alt != 0 else -5.0
            
            # Send the override
            send_mission_override(x=lat, y=lon, z=z_target, cmd="NAVIGATE")
            return True
        except Exception as e:
            print(f"[AirSimAdapter] Goto failed: {e}")
            return False

    def takeoff(self, drone_id: str, altitude: float = 10.0) -> bool:
        """
        Signals the RL brain to enter Hover/Takeoff mode at specific altitude.
        """
        try:
            from mission_bridge import send_mission_override
            z_target = -abs(altitude)
            # We treat Takeoff as a Navigate command to current X,Y but higher Z? 
            # Or just a generic TAKEOFF. Let's use NAVIGATE to 0,0,Z for now or preserve position.
            # Best is to just set Z target. 
            # For simplicity, we assume takeoff usually happens at origin or we want to just set height.
            # But the 'NAVIGATE' command in the brain expects a 3D point.
            # We'll send a signal; the brain logic will need to handle it.
            # For now, let's just make it go to a safe height at current location logic (handled in brain)
            send_mission_override(x=0.0, y=0.0, z=z_target, cmd="TAKEOFF") 
            return True
        except Exception:
            return False

    def land(self, drone_id: str) -> bool:
        """Signals the RL brain to Land."""
        try:
            from mission_bridge import send_mission_override
            send_mission_override(x=0.0, y=0.0, z=0.0, cmd="RETURN_HOME")
            return True
        except Exception:
            return False
