"""
Lesnar AI Drone Simulation System
Advanced drone simulation with AI capabilities
"""

import time
import math
import random
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
import threading
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class DroneState:
    """Represents the current state of a drone"""
    drone_id: str
    latitude: float
    longitude: float
    altitude: float
    heading: float
    speed: float
    battery: float
    armed: bool
    mode: str
    timestamp: str
    
    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class Mission:
    """Represents a drone mission"""
    waypoints: List[Tuple[float, float, float]]  # lat, lon, alt
    mission_type: str = "navigation"
    current_waypoint_index: int = 0

    def get_current_waypoint(self):
        if self.current_waypoint_index < len(self.waypoints):
            return self.waypoints[self.current_waypoint_index]
        return None

    def advance_waypoint(self):
        self.current_waypoint_index += 1
        return self.get_current_waypoint() is not None

class DroneSimulator:
    """
    Advanced drone simulator with realistic physics and AI capabilities
    """
    
    def __init__(self, drone_id: str, initial_position: Tuple[float, float, float] = (40.7128, -74.0060, 0)):
        self.drone_id = drone_id
        self.position = list(initial_position)  # [lat, lon, alt]
        self.heading = 0.0
        self.speed = 0.0
        self.battery = 100.0
        self.armed = False
        self.mode = "STABILIZE"
        self.target_position = None
        self.mission = None
        self._mission_started_at = None
        self.is_flying = False
        self.max_speed = 15.0  # m/s
        self.battery_drain_rate = 0.1  # % per minute

        # AI-related attributes
        self.obstacles_detected = []
        self.ai_enabled = True
        self.auto_avoidance = True

        # Map-based obstacle avoidance
        self._obstacle_polygons = self._load_obstacle_polygons()
        self._avoid_until = 0.0
        self._avoid_heading = None

        # Simulation thread
        self.simulation_thread = None
        self.running = False

        logger.info(f"Drone {self.drone_id} initialized at position {initial_position}")

    def _load_obstacle_polygons(self) -> List[List[Tuple[float, float]]]:
        """Load obstacle polygons from GeoJSON. Returns list of polygons as [(lat, lon), ...]."""
        try:
            data_path = os.path.join(os.path.dirname(__file__), 'data', 'obstacles.geojson')
            if not os.path.exists(data_path):
                return []
            with open(data_path, 'r') as f:
                gj = json.load(f)
            polys: List[List[Tuple[float, float]]] = []
            for feat in gj.get('features', []):
                geom = feat.get('geometry', {})
                gtype = geom.get('type')
                coords = geom.get('coordinates', [])

                if gtype == 'Polygon':
                    # GeoJSON coords: [ [ [lon, lat], ... ] ]
                    rings = coords
                    if rings:
                        ring = rings[0]
                        poly = [(lat, lon) for lon, lat in ring]
                        polys.append(poly)

                elif gtype == 'MultiPolygon':
                    # GeoJSON coords: [ [ [ [lon, lat], ... ] ], ... ]
                    for poly_coords in coords or []:
                        if not poly_coords:
                            continue
                        ring = poly_coords[0]
                        if not ring:
                            continue
                        poly = [(lat, lon) for lon, lat in ring]
                        polys.append(poly)
            return polys
        except Exception as e:
            logger.warning(f"{self.drone_id}: Failed to load obstacle polygons: {e}")
            return []

    @staticmethod
    def _point_in_polygon(lat: float, lon: float, polygon: List[Tuple[float, float]]) -> bool:
        """Ray casting algorithm for point-in-polygon. polygon given as [(lat, lon), ...]."""
        inside = False
        n = len(polygon)
        for i in range(n):
            j = (i - 1) % n
            yi, xi = polygon[i]
            yj, xj = polygon[j]
            # Check if point is between yi and yj vertically
            intersect = ((yi > lat) != (yj > lat)) and (
                lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi
            )
            if intersect:
                inside = not inside
        return inside

    def _would_collide(self, new_lat: float, new_lon: float) -> bool:
        for poly in self._obstacle_polygons:
            if self._point_in_polygon(new_lat, new_lon, poly):
                return True
        return False
    
    def arm(self) -> bool:
        """Arm the drone for flight"""
        if self.battery > 10:
            self.armed = True
            self.mode = "ARMED"
            logger.info(f"Drone {self.drone_id} armed")
            return True
        else:
            logger.warning(f"Drone {self.drone_id} cannot arm - low battery ({self.battery}%)")
            return False
    
    def disarm(self) -> bool:
        """Disarm the drone"""
        self.armed = False
        self.mode = "STABILIZE"
        self.is_flying = False
        self.speed = 0.0
        logger.info(f"Drone {self.drone_id} disarmed")
        return True
    
    def takeoff(self, target_altitude: float = 10.0) -> bool:
        """Initiate takeoff to specified altitude"""
        if not self.armed:
            logger.error(f"Drone {self.drone_id} must be armed before takeoff")
            return False
        
        self.mode = "TAKEOFF"
        self.target_position = [self.position[0], self.position[1], target_altitude]
        self.is_flying = True
        logger.info(f"Drone {self.drone_id} taking off to {target_altitude}m")
        return True
    
    def land(self) -> bool:
        """Land the drone"""
        self.mode = "LAND"
        self.target_position = [self.position[0], self.position[1], 0]
        logger.info(f"Drone {self.drone_id} landing")
        return True
    
    def goto(self, latitude: float, longitude: float, altitude: float) -> bool:
        """Navigate to specific coordinates"""
        if not self.is_flying:
            logger.error(f"Drone {self.drone_id} must be airborne to navigate")
            return False
        
        self.target_position = [latitude, longitude, altitude]
        self.mode = "AUTO"
        logger.info(f"Drone {self.drone_id} navigating to ({latitude}, {longitude}, {altitude})")
        return True
    
    def execute_mission(self, mission: Mission) -> bool:
        """Execute a predefined mission"""
        if not self.is_flying:
            logger.error(f"Drone {self.drone_id} must be airborne to execute mission")
            return False
        
        self.mission = mission
        self.mission.current_waypoint_index = 0
        first_waypoint = self.mission.get_current_waypoint()
        
        if first_waypoint:
            self.target_position = list(first_waypoint)
            self.mode = "MISSION"
            self._mission_started_at = time.time()
            logger.info(f"Drone {self.drone_id} executing {mission.mission_type} mission, heading to waypoint 1")
            return True
        else:
            logger.error(f"Drone {self.drone_id} received an empty mission.")
            return False

    def pause_mission(self) -> bool:
        """Pause an active mission in place."""
        if not self.mission or self.mode != "MISSION":
            return False
        # Freeze movement while keeping mission state intact.
        self.mode = "HOLD"
        self.target_position = None
        self.speed = 0.0
        logger.info(f"Drone {self.drone_id} paused mission")
        return True

    def resume_mission(self) -> bool:
        """Resume a paused mission."""
        if not self.mission or self.mode != "HOLD":
            return False
        wp = self.mission.get_current_waypoint()
        if not wp:
            return False
        self.target_position = list(wp)
        self.mode = "MISSION"
        logger.info(f"Drone {self.drone_id} resumed mission")
        return True

    def stop_mission(self) -> bool:
        """Stop/cancel the current mission."""
        if not self.mission:
            return False
        self.mission = None
        self._mission_started_at = None
        self.target_position = None
        self.speed = 0.0
        self.mode = "LOITER" if self.is_flying else "STABILIZE"
        logger.info(f"Drone {self.drone_id} stopped mission")
        return True

    def get_mission_info(self) -> Optional[Dict]:
        """Return mission details suitable for API/UI."""
        if not self.mission:
            return None
        total = len(self.mission.waypoints)
        idx0 = int(self.mission.current_waypoint_index or 0)
        # Rough estimate: 60s per waypoint remaining.
        remaining_s = max(0, int((total - idx0) * 60))
        status = "ACTIVE" if self.mode == "MISSION" else ("PAUSED" if self.mode == "HOLD" else "UNKNOWN")
        return {
            'drone_id': self.drone_id,
            'mission_type': getattr(self.mission, 'mission_type', 'CUSTOM'),
            'total_waypoints': total,
            'current_waypoint_index': min(total, max(0, idx0 + 1)),
            'estimated_remaining_s': remaining_s,
            'status': status,
            'started_at': datetime.fromtimestamp(self._mission_started_at).isoformat() if self._mission_started_at else None,
        }
    
    def detect_obstacles(self) -> Optional[Dict]:
        """Simulate AI-based obstacle detection, returning only new obstacles"""
        if not self.ai_enabled:
            return None
        
        # Simulate random obstacle detection for demo
        if random.random() < 0.05:  # 5% chance of detecting obstacle
            obstacle = {
                "type": random.choice(["building", "tree", "other_drone", "bird"]),
                "distance": random.uniform(5, 50),
                "bearing": random.uniform(0, 360),
                "timestamp": datetime.now().isoformat()
            }
            self.obstacles_detected.append(obstacle)
            logger.warning(f"Drone {self.drone_id} detected obstacle: {obstacle['type']} at {obstacle['distance']:.1f}m")
            return obstacle
        
        return None
    
    def avoid_obstacle(self, obstacle: Dict) -> bool:
        """AI-based obstacle avoidance"""
        if not self.auto_avoidance:
            return False
        
        # Simple avoidance: adjust heading by 45 degrees
        avoidance_heading = (self.heading + 45) % 360
        self.heading = avoidance_heading
        logger.info(f"Drone {self.drone_id} avoiding {obstacle['type']}, new heading: {avoidance_heading:.1f}°")
        return True
    
    def calculate_distance(self, pos1: List[float], pos2: List[float]) -> float:
        """Calculate distance between two positions"""
        # Simplified distance calculation (not accounting for Earth's curvature)
        lat_diff = pos1[0] - pos2[0]
        lon_diff = pos1[1] - pos2[1]
        alt_diff = pos1[2] - pos2[2]
        
        # Convert lat/lon to approximate meters (rough calculation)
        lat_meters = lat_diff * 111000
        lon_meters = lon_diff * 111000 * math.cos(math.radians(pos1[0]))
        
        return math.sqrt(lat_meters**2 + lon_meters**2 + alt_diff**2)
    
    def update_physics(self, dt: float):
        """Update drone physics simulation"""
        if not self.target_position or not self.is_flying:
            return

        # Calculate movement towards target
        distance_to_target = self.calculate_distance(self.position, self.target_position)

        # Close to target handling
        if distance_to_target < 1.0:
            if self.mode == "LAND" and self.position[2] <= 0.1:
                self.is_flying = False
                self.position[2] = 0
                self.speed = 0
                self.mode = "LANDED"
                return
            elif self.mode == "TAKEOFF" or self.mode == "AUTO":
                self.mode = "LOITER"
                self.speed = 0
                return
            # If in mission, we'll try to advance after movement/battery update below

        # Calculate direction to target
        lat_diff = self.target_position[0] - self.position[0]
        lon_diff = self.target_position[1] - self.position[1]
        alt_diff = self.target_position[2] - self.position[2]

        now = time.time()
        # Determine step speed
        self.speed = min(self.max_speed, max(2.0, distance_to_target * 0.5))
        step_m = self.speed * dt

        if self._avoid_until > now and self._avoid_heading is not None:
            # Move along avoidance heading
            rad = math.radians(self._avoid_heading)
            d_lat_m = math.cos(rad) * step_m
            d_lon_m = math.sin(rad) * step_m
            new_lat = self.position[0] + d_lat_m / 111000.0
            denom = max(1e-3, 111000.0 * max(0.1, abs(math.cos(math.radians(self.position[0])))))
            new_lon = self.position[1] + d_lon_m / denom
            if self._would_collide(new_lat, new_lon):
                # Rotate avoidance heading and retry next tick
                self._avoid_heading = (self._avoid_heading + 45) % 360
            else:
                self.position[0] = new_lat
                self.position[1] = new_lon
        else:
            # Normal heading towards target
            if lat_diff != 0 or lon_diff != 0:
                self.heading = math.degrees(math.atan2(lon_diff, lat_diff))
            rad = math.radians(self.heading)
            d_lat_m = math.cos(rad) * step_m
            d_lon_m = math.sin(rad) * step_m
            cand_lat = self.position[0] + d_lat_m / 111000.0
            denom = max(1e-3, 111000.0 * max(0.1, abs(math.cos(math.radians(self.position[0])))))
            cand_lon = self.position[1] + d_lon_m / denom
            if self._would_collide(cand_lat, cand_lon):
                # Set avoidance for 2 seconds perpendicular to current heading
                self._avoid_heading = (self.heading + 90) % 360
                self._avoid_until = time.time() + 2.0
                logger.info(f"Drone {self.drone_id} avoiding map obstacle, new temporary heading: {self._avoid_heading:.1f}°")
            else:
                self.position[0] = cand_lat
                self.position[1] = cand_lon
                self._avoid_heading = None
                self._avoid_until = 0.0

        # Adjust altitude gradually
        climb_rate = 2.0  # m/s
        max_d_alt = climb_rate * dt
        d_alt = max(-max_d_alt, min(max_d_alt, alt_diff))
        self.position[2] = max(0.0, self.position[2] + d_alt)

        # Update battery
        power_consumption = 1.0 + (self.speed / self.max_speed) * 2.0  # More power at higher speeds
        self.battery -= (self.battery_drain_rate * power_consumption * dt / 60.0)
        self.battery = max(0, self.battery)

        # Emergency land if battery critical
        if self.battery < 5 and self.mode != "LAND":
            logger.warning(f"Drone {self.drone_id} emergency landing - critical battery!")
            self.land()
        elif self.mode == "MISSION" and distance_to_target < 1.0:
            # Advance mission when close enough
            if self.mission and self.mission.advance_waypoint():
                next_waypoint = self.mission.get_current_waypoint()
                if next_waypoint:
                    self.target_position = list(next_waypoint)
                    logger.info(f"Drone {self.drone_id} reached waypoint {self.mission.current_waypoint_index}, heading to next.")
            else:
                logger.info(f"Drone {self.drone_id} completed mission.")
                self.mode = "LOITER"
                self.mission = None
                self.speed = 0
    
    def get_state(self) -> DroneState:
        """Get current drone state"""
        return DroneState(
            drone_id=self.drone_id,
            latitude=self.position[0],
            longitude=self.position[1],
            altitude=self.position[2],
            heading=self.heading,
            speed=self.speed,
            battery=self.battery,
            armed=self.armed,
            mode=self.mode,
            timestamp=datetime.now().isoformat()
        )
    
    def start_simulation(self):
        """Start the simulation loop"""
        if self.running:
            return
        
        self.running = True
        self.simulation_thread = threading.Thread(target=self._simulation_loop)
        self.simulation_thread.start()
        logger.info(f"Drone {self.drone_id} simulation started")
    
    def stop_simulation(self):
        """Stop the simulation loop"""
        self.running = False
        if self.simulation_thread:
            self.simulation_thread.join()
        logger.info(f"Drone {self.drone_id} simulation stopped")
    
    def _simulation_loop(self):
        """Main simulation loop"""
        last_time = time.time()
        
        while self.running:
            current_time = time.time()
            dt = current_time - last_time
            
            # Update physics
            self.update_physics(dt)
            
            # AI obstacle detection
            if self.ai_enabled:
                obstacle = self.detect_obstacles()
                if obstacle and self.auto_avoidance:
                    self.avoid_obstacle(obstacle)
            
            last_time = current_time
            time.sleep(0.1)  # 10Hz update rate

class DroneFleet:
    """Manage multiple drones"""
    
    def __init__(self):
        self.drones: Dict[str, DroneSimulator] = {}
        self.logger = logging.getLogger(__name__)
    
    def add_drone(self, drone_id: str, position: Tuple[float, float, float] = None) -> bool:
        """Add a new drone to the fleet"""
        if drone_id in self.drones:
            self.logger.warning(f"Drone {drone_id} already exists")
            return False
        
        if position is None:
            # Random position around NYC area
            position = (
                40.7128 + random.uniform(-0.1, 0.1),
                -74.0060 + random.uniform(-0.1, 0.1),
                0
            )
        
        self.drones[drone_id] = DroneSimulator(drone_id, position)
        self.drones[drone_id].start_simulation()
        self.logger.info(f"Added drone {drone_id} to fleet")
        return True
    
    def remove_drone(self, drone_id: str) -> bool:
        """Remove a drone from the fleet"""
        if drone_id not in self.drones:
            self.logger.warning(f"Drone {drone_id} not found")
            return False
        
        self.drones[drone_id].stop_simulation()
        del self.drones[drone_id]
        self.logger.info(f"Removed drone {drone_id} from fleet")
        return True
    
    def get_drone(self, drone_id: str) -> Optional[DroneSimulator]:
        """Get a specific drone"""
        return self.drones.get(drone_id)
    
    def get_all_states(self) -> List[DroneState]:
        """Get states of all drones"""
        return [drone.get_state() for drone in self.drones.values()]
    
    def emergency_land_all(self):
        """Emergency land all drones"""
        for drone in self.drones.values():
            drone.land()
        self.logger.warning("Emergency landing initiated for all drones")

# Example usage and testing
if __name__ == "__main__":
    # Create a drone fleet
    fleet = DroneFleet()
    
    # Add some drones
    fleet.add_drone("LESNAR-001")
    fleet.add_drone("LESNAR-002")
    
    # Get a drone and test basic operations
    drone = fleet.get_drone("LESNAR-001")
    
    if drone:
        print(f"Initial state: {drone.get_state()}")
        
        # Arm and takeoff
        drone.arm()
        drone.takeoff(15.0)
        
        # Wait a bit
        time.sleep(2)
        
        # Navigate to a location
        drone.goto(40.7500, -73.9857, 20.0)  # Empire State Building area
        
        # Monitor for a few seconds
        for i in range(10):
            state = drone.get_state()
            print(f"Update {i+1}: Alt={state.altitude:.1f}m, Speed={state.speed:.1f}m/s, Battery={state.battery:.1f}%, Mode={state.mode}")
            time.sleep(1)
        
        # Land
        drone.land()
        time.sleep(3)
        
        # Final state
        print(f"Final state: {drone.get_state()}")
    
    # Stop all simulations
    for drone_id in list(fleet.drones.keys()):
        fleet.remove_drone(drone_id)
