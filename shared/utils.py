"""
Shared utilities and constants for Lesnar AI Drone System
"""

import math
from typing import Tuple, Dict, List
from dataclasses import dataclass
from datetime import datetime
import json
import logging

# Constants
DEFAULT_TAKEOFF_ALTITUDE = 10.0
DEFAULT_MAX_SPEED = 15.0  # m/s
DEFAULT_MAX_ALTITUDE = 120.0  # meters (400 feet - FAA limit)
EARTH_RADIUS = 6371000  # meters
BATTERY_WARNING_LEVEL = 20.0
BATTERY_CRITICAL_LEVEL = 5.0

# Coordinate system
@dataclass
class GeoPosition:
    """GPS coordinates with altitude"""
    latitude: float
    longitude: float
    altitude: float
    
    def to_dict(self) -> Dict:
        return {
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude
        }

@dataclass
class Vector3D:
    """3D vector for velocities, forces, etc."""
    x: float
    y: float
    z: float
    
    def magnitude(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)
    
    def normalize(self) -> 'Vector3D':
        mag = self.magnitude()
        if mag == 0:
            return Vector3D(0, 0, 0)
        return Vector3D(self.x/mag, self.y/mag, self.z/mag)
    
    def scale(self, factor: float) -> 'Vector3D':
        return Vector3D(self.x*factor, self.y*factor, self.z*factor)

def calculate_distance_3d(pos1: GeoPosition, pos2: GeoPosition) -> float:
    """
    Calculate 3D distance between two GPS positions
    Uses haversine formula for lat/lon and adds altitude difference
    """
    # Haversine formula for lat/lon distance
    lat1, lon1, alt1 = math.radians(pos1.latitude), math.radians(pos1.longitude), pos1.altitude
    lat2, lon2, alt2 = math.radians(pos2.latitude), math.radians(pos2.longitude), pos2.altitude
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = (math.sin(dlat/2)**2 + 
         math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2)
    c = 2 * math.asin(math.sqrt(a))
    
    # Horizontal distance
    horizontal_distance = EARTH_RADIUS * c
    
    # Add altitude difference
    altitude_difference = alt2 - alt1
    
    # Total 3D distance
    return math.sqrt(horizontal_distance**2 + altitude_difference**2)

def calculate_bearing(pos1: GeoPosition, pos2: GeoPosition) -> float:
    """
    Calculate bearing from pos1 to pos2 in degrees
    """
    lat1, lon1 = math.radians(pos1.latitude), math.radians(pos1.longitude)
    lat2, lon2 = math.radians(pos2.latitude), math.radians(pos2.longitude)
    
    dlon = lon2 - lon1
    
    y = math.sin(dlon) * math.cos(lat2)
    x = (math.cos(lat1) * math.sin(lat2) - 
         math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    
    bearing = math.atan2(y, x)
    bearing = math.degrees(bearing)
    bearing = (bearing + 360) % 360  # Normalize to 0-360
    
    return bearing

def offset_position(position: GeoPosition, bearing: float, distance: float) -> GeoPosition:
    """
    Calculate new position given current position, bearing (degrees), and distance (meters)
    """
    lat1, lon1 = math.radians(position.latitude), math.radians(position.longitude)
    bearing_rad = math.radians(bearing)
    
    angular_distance = distance / EARTH_RADIUS
    
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance) +
        math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    
    lon2 = lon1 + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2)
    )
    
    return GeoPosition(
        latitude=math.degrees(lat2),
        longitude=math.degrees(lon2),
        altitude=position.altitude
    )

def is_position_in_bounds(position: GeoPosition, center: GeoPosition, radius: float) -> bool:
    """
    Check if position is within radius of center point
    """
    distance = calculate_distance_3d(position, center)
    return distance <= radius

def calculate_speed_from_positions(pos1: GeoPosition, pos2: GeoPosition, time_delta: float) -> float:
    """
    Calculate speed between two positions over time
    """
    if time_delta <= 0:
        return 0.0
    
    distance = calculate_distance_3d(pos1, pos2)
    return distance / time_delta

def validate_coordinates(latitude: float, longitude: float, altitude: float) -> bool:
    """
    Validate GPS coordinates
    """
    if not (-90 <= latitude <= 90):
        return False
    if not (-180 <= longitude <= 180):
        return False
    if not (0 <= altitude <= DEFAULT_MAX_ALTITUDE):
        return False
    return True

def generate_waypoints_circle(center: GeoPosition, radius: float, num_points: int) -> List[GeoPosition]:
    """
    Generate waypoints in a circular pattern
    """
    waypoints = []
    angle_step = 360.0 / num_points
    
    for i in range(num_points):
        angle = i * angle_step
        waypoint = offset_position(center, angle, radius)
        waypoints.append(waypoint)
    
    return waypoints

def generate_waypoints_grid(center: GeoPosition, spacing: float, grid_size: int) -> List[GeoPosition]:
    """
    Generate waypoints in a grid pattern
    """
    waypoints = []
    start_offset = -(grid_size - 1) * spacing / 2
    
    for i in range(grid_size):
        for j in range(grid_size):
            # Calculate offset from center
            north_offset = start_offset + i * spacing
            east_offset = start_offset + j * spacing
            
            # Convert to bearing and distance
            distance = math.sqrt(north_offset**2 + east_offset**2)
            if distance == 0:
                waypoint = center
            else:
                bearing = math.degrees(math.atan2(east_offset, north_offset))
                waypoint = offset_position(center, bearing, distance)
            
            waypoints.append(waypoint)
    
    return waypoints

def interpolate_path(start: GeoPosition, end: GeoPosition, num_points: int) -> List[GeoPosition]:
    """
    Generate intermediate waypoints between start and end positions
    """
    waypoints = []
    
    for i in range(num_points):
        t = i / max(1, num_points - 1)  # Avoid division by zero
        
        lat = start.latitude + t * (end.latitude - start.latitude)
        lon = start.longitude + t * (end.longitude - start.longitude)
        alt = start.altitude + t * (end.altitude - start.altitude)
        
        waypoints.append(GeoPosition(lat, lon, alt))
    
    return waypoints

def format_coordinates(position: GeoPosition) -> str:
    """
    Format coordinates for display
    """
    lat_dir = "N" if position.latitude >= 0 else "S"
    lon_dir = "E" if position.longitude >= 0 else "W"
    
    return (f"{abs(position.latitude):.6f}°{lat_dir}, "
            f"{abs(position.longitude):.6f}°{lon_dir}, "
            f"{position.altitude:.1f}m")

def get_battery_status(battery_level: float) -> str:
    """
    Get battery status description
    """
    if battery_level >= 80:
        return "EXCELLENT"
    elif battery_level >= 60:
        return "GOOD"
    elif battery_level >= 40:
        return "FAIR"
    elif battery_level >= BATTERY_WARNING_LEVEL:
        return "LOW"
    elif battery_level >= BATTERY_CRITICAL_LEVEL:
        return "CRITICAL"
    else:
        return "EMPTY"

def estimate_flight_time(battery_level: float, power_consumption_rate: float = 1.0) -> float:
    """
    Estimate remaining flight time in minutes
    """
    if power_consumption_rate <= 0:
        return 0.0
    
    # Reserve 10% for landing
    usable_battery = max(0, battery_level - 10.0)
    return usable_battery / power_consumption_rate

def calculate_safe_landing_zone(position: GeoPosition, radius: float = 50.0) -> List[GeoPosition]:
    """
    Generate potential safe landing zones around a position
    """
    # Simple implementation: generate points in cardinal directions
    landing_zones = []
    
    for bearing in [0, 90, 180, 270]:  # North, East, South, West
        zone = offset_position(position, bearing, radius)
        zone.altitude = 0.0  # Landing zones are on ground
        landing_zones.append(zone)
    
    return landing_zones

def create_no_fly_zone(center: GeoPosition, radius: float, altitude_min: float = 0, altitude_max: float = 1000) -> Dict:
    """
    Define a no-fly zone
    """
    return {
        'center': center.to_dict(),
        'radius': radius,
        'altitude_min': altitude_min,
        'altitude_max': altitude_max,
        'type': 'circular',
        'created': datetime.now().isoformat()
    }

def is_in_no_fly_zone(position: GeoPosition, no_fly_zones: List[Dict]) -> bool:
    """
    Check if position is in any no-fly zone
    """
    for zone in no_fly_zones:
        zone_center = GeoPosition(**zone['center'])
        
        # Check horizontal distance
        horizontal_distance = calculate_distance_3d(
            GeoPosition(position.latitude, position.longitude, 0),
            GeoPosition(zone_center.latitude, zone_center.longitude, 0)
        )
        
        if horizontal_distance <= zone['radius']:
            # Check altitude
            if zone['altitude_min'] <= position.altitude <= zone['altitude_max']:
                return True
    
    return False

# Logging utilities
def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Set up logging configuration
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('lesnar_ai.log')
        ]
    )
    
    return logging.getLogger('lesnar_ai')

# Configuration utilities
def load_config(config_file: str = 'config.json') -> Dict:
    """
    Load configuration from JSON file
    """
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        # Return default configuration
        return {
            'drone_settings': {
                'max_speed': DEFAULT_MAX_SPEED,
                'max_altitude': DEFAULT_MAX_ALTITUDE,
                'takeoff_altitude': DEFAULT_TAKEOFF_ALTITUDE,
                'battery_warning_level': BATTERY_WARNING_LEVEL,
                'battery_critical_level': BATTERY_CRITICAL_LEVEL
            },
            'api_settings': {
                'host': '0.0.0.0',
                'port': 5000,
                'debug': False
            },
            'simulation_settings': {
                'update_rate': 10,  # Hz
                'physics_enabled': True,
                'weather_simulation': False
            }
        }

def save_config(config: Dict, config_file: str = 'config.json'):
    """
    Save configuration to JSON file
    """
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

# Performance monitoring
class PerformanceMonitor:
    """
    Monitor system performance metrics
    """
    
    def __init__(self):
        self.start_time = datetime.now()
        self.metrics = {
            'api_calls': 0,
            'simulation_updates': 0,
            'errors': 0,
            'warnings': 0
        }
    
    def increment_metric(self, metric_name: str):
        if metric_name in self.metrics:
            self.metrics[metric_name] += 1
    
    def get_uptime(self) -> float:
        """Get uptime in seconds"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def get_metrics(self) -> Dict:
        """Get all metrics"""
        return {
            **self.metrics,
            'uptime_seconds': self.get_uptime(),
            'uptime_formatted': str(datetime.now() - self.start_time)
        }

# Example usage
if __name__ == "__main__":
    # Test coordinate calculations
    nyc = GeoPosition(40.7128, -74.0060, 20.0)
    times_square = GeoPosition(40.7589, -73.9851, 25.0)
    
    distance = calculate_distance_3d(nyc, times_square)
    bearing = calculate_bearing(nyc, times_square)
    
    print(f"Distance from NYC to Times Square: {distance:.1f} meters")
    print(f"Bearing: {bearing:.1f} degrees")
    print(f"NYC coordinates: {format_coordinates(nyc)}")
    
    # Test waypoint generation
    waypoints = generate_waypoints_circle(nyc, 100, 8)
    print(f"Generated {len(waypoints)} waypoints in circle pattern")
    
    # Test battery status
    for battery in [100, 75, 50, 25, 10, 2]:
        status = get_battery_status(battery)
        flight_time = estimate_flight_time(battery)
        print(f"Battery {battery}%: {status} - {flight_time:.1f} min remaining")
    
    print("Utilities test completed")
