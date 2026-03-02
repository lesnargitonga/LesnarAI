"""
Swarm Intelligence Module for Lesnar AI Drone System
Advanced multi-drone coordination and swarm behaviors
"""

import numpy as np
import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging
from datetime import datetime
import threading
import time

logger = logging.getLogger(__name__)

@dataclass
class SwarmDrone:
    """Represents a drone in the swarm"""
    drone_id: str
    position: Tuple[float, float, float]  # lat, lon, alt
    velocity: Tuple[float, float, float]  # vx, vy, vz
    heading: float
    role: str
    status: str
    battery: float
    timestamp: str

@dataclass
class SwarmFormation:
    """Defines a swarm formation pattern"""
    formation_type: str
    positions: List[Tuple[float, float, float]]
    leader_index: int
    spacing: float
    
class SwarmIntelligence:
    """
    Advanced swarm intelligence system for coordinated drone operations
    Implements flocking behaviors, formation flying, and collaborative missions
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.swarm_drones: Dict[str, SwarmDrone] = {}
        self.formation = None
        self.swarm_center = [0.0, 0.0, 0.0]
        self.swarm_bounds = 100.0  # meters
        
        # Swarm behavior parameters
        self.separation_distance = 10.0  # minimum distance between drones
        self.alignment_radius = 20.0     # radius for velocity alignment
        self.cohesion_radius = 30.0      # radius for cohesion behavior
        
        # Behavior weights
        self.separation_weight = 2.0
        self.alignment_weight = 1.0
        self.cohesion_weight = 1.5
        self.leader_follow_weight = 3.0
        
        self.running = False
        self.coordination_thread = None
    
    def add_drone(self, drone_state: Dict) -> bool:
        """Add a drone to the swarm"""
        try:
            swarm_drone = SwarmDrone(
                drone_id=drone_state['drone_id'],
                position=(drone_state['latitude'], drone_state['longitude'], drone_state['altitude']),
                velocity=(0.0, 0.0, 0.0),  # Will be calculated
                heading=drone_state['heading'],
                role='follower',  # Default role
                status=drone_state['mode'],
                battery=drone_state['battery'],
                timestamp=drone_state['timestamp']
            )
            
            self.swarm_drones[drone_state['drone_id']] = swarm_drone
            self.logger.info(f"Added drone {drone_state['drone_id']} to swarm")
            
            # Assign leader if first drone or no leader exists
            if len(self.swarm_drones) == 1 or not any(d.role == 'leader' for d in self.swarm_drones.values()):
                swarm_drone.role = 'leader'
                self.logger.info(f"Assigned {drone_state['drone_id']} as swarm leader")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add drone to swarm: {e}")
            return False
    
    def remove_drone(self, drone_id: str) -> bool:
        """Remove a drone from the swarm"""
        if drone_id not in self.swarm_drones:
            return False
        
        was_leader = self.swarm_drones[drone_id].role == 'leader'
        del self.swarm_drones[drone_id]
        self.logger.info(f"Removed drone {drone_id} from swarm")
        
        # Assign new leader if the leader was removed
        if was_leader and self.swarm_drones:
            new_leader_id = list(self.swarm_drones.keys())[0]
            self.swarm_drones[new_leader_id].role = 'leader'
            self.logger.info(f"Assigned {new_leader_id} as new swarm leader")
        
        return True
    
    def update_drone_state(self, drone_state: Dict):
        """Update the state of a drone in the swarm"""
        drone_id = drone_state['drone_id']
        if drone_id in self.swarm_drones:
            drone = self.swarm_drones[drone_id]
            
            # Calculate velocity from position change
            old_pos = drone.position
            new_pos = (drone_state['latitude'], drone_state['longitude'], drone_state['altitude'])
            
            # Simple velocity calculation (simplified)
            dt = 1.0  # Assume 1 second update interval
            velocity = (
                (new_pos[0] - old_pos[0]) / dt,
                (new_pos[1] - old_pos[1]) / dt,
                (new_pos[2] - old_pos[2]) / dt
            )
            
            # Update drone properties
            drone.position = new_pos
            drone.velocity = velocity
            drone.heading = drone_state['heading']
            drone.status = drone_state['mode']
            drone.battery = drone_state['battery']
            drone.timestamp = drone_state['timestamp']
    
    def calculate_separation_force(self, drone_id: str) -> Tuple[float, float, float]:
        """Calculate separation force to avoid crowding neighbors"""
        if drone_id not in self.swarm_drones:
            return (0.0, 0.0, 0.0)
        
        current_drone = self.swarm_drones[drone_id]
        separation_force = [0.0, 0.0, 0.0]
        
        for other_id, other_drone in self.swarm_drones.items():
            if other_id == drone_id:
                continue
            
            # Calculate distance
            distance = self.calculate_3d_distance(current_drone.position, other_drone.position)
            
            if distance < self.separation_distance and distance > 0:
                # Calculate direction away from neighbor
                diff = [
                    current_drone.position[0] - other_drone.position[0],
                    current_drone.position[1] - other_drone.position[1],
                    current_drone.position[2] - other_drone.position[2]
                ]
                
                # Normalize and weight by inverse distance
                magnitude = max(distance, 0.1)
                for i in range(3):
                    separation_force[i] += diff[i] / (magnitude * magnitude)
        
        return tuple(separation_force)
    
    def calculate_alignment_force(self, drone_id: str) -> Tuple[float, float, float]:
        """Calculate alignment force to match velocity of neighbors"""
        if drone_id not in self.swarm_drones:
            return (0.0, 0.0, 0.0)
        
        current_drone = self.swarm_drones[drone_id]
        avg_velocity = [0.0, 0.0, 0.0]
        neighbor_count = 0
        
        for other_id, other_drone in self.swarm_drones.items():
            if other_id == drone_id:
                continue
            
            distance = self.calculate_3d_distance(current_drone.position, other_drone.position)
            
            if distance < self.alignment_radius:
                for i in range(3):
                    avg_velocity[i] += other_drone.velocity[i]
                neighbor_count += 1
        
        if neighbor_count > 0:
            for i in range(3):
                avg_velocity[i] /= neighbor_count
                avg_velocity[i] -= current_drone.velocity[i]  # Steering force
        
        return tuple(avg_velocity)
    
    def calculate_cohesion_force(self, drone_id: str) -> Tuple[float, float, float]:
        """Calculate cohesion force to stay near the center of neighbors"""
        if drone_id not in self.swarm_drones:
            return (0.0, 0.0, 0.0)
        
        current_drone = self.swarm_drones[drone_id]
        center_of_mass = [0.0, 0.0, 0.0]
        neighbor_count = 0
        
        for other_id, other_drone in self.swarm_drones.items():
            if other_id == drone_id:
                continue
            
            distance = self.calculate_3d_distance(current_drone.position, other_drone.position)
            
            if distance < self.cohesion_radius:
                for i in range(3):
                    center_of_mass[i] += other_drone.position[i]
                neighbor_count += 1
        
        if neighbor_count > 0:
            for i in range(3):
                center_of_mass[i] /= neighbor_count
                center_of_mass[i] -= current_drone.position[i]  # Steering toward center
        
        return tuple(center_of_mass)
    
    def calculate_leader_following_force(self, drone_id: str) -> Tuple[float, float, float]:
        """Calculate force to follow the swarm leader"""
        if drone_id not in self.swarm_drones:
            return (0.0, 0.0, 0.0)
        
        current_drone = self.swarm_drones[drone_id]
        
        # Don't apply leader following to the leader itself
        if current_drone.role == 'leader':
            return (0.0, 0.0, 0.0)
        
        # Find the leader
        leader = None
        for other_drone in self.swarm_drones.values():
            if other_drone.role == 'leader':
                leader = other_drone
                break
        
        if not leader:
            return (0.0, 0.0, 0.0)
        
        # Calculate force toward leader's position (with some offset)
        force = [
            leader.position[0] - current_drone.position[0],
            leader.position[1] - current_drone.position[1],
            leader.position[2] - current_drone.position[2]
        ]
        
        return tuple(force)
    
    def calculate_swarm_forces(self, drone_id: str) -> Dict[str, Tuple[float, float, float]]:
        """Calculate all swarm forces for a drone"""
        separation = self.calculate_separation_force(drone_id)
        alignment = self.calculate_alignment_force(drone_id)
        cohesion = self.calculate_cohesion_force(drone_id)
        leader_follow = self.calculate_leader_following_force(drone_id)
        
        return {
            'separation': separation,
            'alignment': alignment,
            'cohesion': cohesion,
            'leader_follow': leader_follow
        }
    
    def calculate_desired_velocity(self, drone_id: str) -> Tuple[float, float, float]:
        """Calculate the desired velocity for a drone based on swarm forces"""
        forces = self.calculate_swarm_forces(drone_id)
        
        # Combine all forces with weights
        desired_velocity = [0.0, 0.0, 0.0]
        
        for i in range(3):
            desired_velocity[i] = (
                forces['separation'][i] * self.separation_weight +
                forces['alignment'][i] * self.alignment_weight +
                forces['cohesion'][i] * self.cohesion_weight +
                forces['leader_follow'][i] * self.leader_follow_weight
            )
        
        # Limit velocity magnitude
        max_velocity = 10.0  # m/s
        magnitude = math.sqrt(sum(v*v for v in desired_velocity))
        if magnitude > max_velocity:
            for i in range(3):
                desired_velocity[i] = (desired_velocity[i] / magnitude) * max_velocity
        
        return tuple(desired_velocity)
    
    def calculate_3d_distance(self, pos1: Tuple[float, float, float], pos2: Tuple[float, float, float]) -> float:
        """Calculate 3D distance between two positions"""
        return math.sqrt(
            (pos1[0] - pos2[0])**2 + 
            (pos1[1] - pos2[1])**2 + 
            (pos1[2] - pos2[2])**2
        )
    
    def create_formation(self, formation_type: str, spacing: float = 20.0) -> SwarmFormation:
        """Create a formation pattern for the swarm"""
        drone_count = len(self.swarm_drones)
        if drone_count == 0:
            return None
        
        positions = []
        leader_index = 0
        
        if formation_type == "line":
            for i in range(drone_count):
                positions.append((i * spacing, 0.0, 0.0))
        
        elif formation_type == "v_formation":
            positions.append((0.0, 0.0, 0.0))  # Leader at front
            for i in range(1, drone_count):
                side = -1 if i % 2 == 1 else 1
                row = (i + 1) // 2
                positions.append((side * spacing * 0.5, -row * spacing, 0.0))
        
        elif formation_type == "circle":
            if drone_count == 1:
                positions.append((0.0, 0.0, 0.0))
            else:
                angle_step = 2 * math.pi / drone_count
                for i in range(drone_count):
                    angle = i * angle_step
                    x = spacing * math.cos(angle)
                    y = spacing * math.sin(angle)
                    positions.append((x, y, 0.0))
        
        elif formation_type == "diamond":
            if drone_count >= 4:
                positions = [
                    (0.0, 0.0, 0.0),      # Front
                    (-spacing, -spacing, 0.0),  # Left
                    (spacing, -spacing, 0.0),   # Right
                    (0.0, -2*spacing, 0.0)      # Back
                ]
                # Add extra drones in a second diamond
                for i in range(4, drone_count):
                    offset = ((i-4) % 4) * spacing * 0.5
                    positions.append((offset, -3*spacing, 0.0))
            else:
                # Fallback to line formation
                for i in range(drone_count):
                    positions.append((i * spacing, 0.0, 0.0))
        
        else:  # Default: grid formation
            grid_size = int(math.ceil(math.sqrt(drone_count)))
            for i in range(drone_count):
                row = i // grid_size
                col = i % grid_size
                positions.append((col * spacing, row * spacing, 0.0))
        
        return SwarmFormation(
            formation_type=formation_type,
            positions=positions,
            leader_index=leader_index,
            spacing=spacing
        )
    
    def get_swarm_status(self) -> Dict:
        """Get comprehensive swarm status"""
        if not self.swarm_drones:
            return {'status': 'empty', 'drone_count': 0}
        
        # Calculate swarm center
        center_lat = sum(d.position[0] for d in self.swarm_drones.values()) / len(self.swarm_drones)
        center_lon = sum(d.position[1] for d in self.swarm_drones.values()) / len(self.swarm_drones)
        center_alt = sum(d.position[2] for d in self.swarm_drones.values()) / len(self.swarm_drones)
        
        # Calculate swarm spread
        max_distance = 0
        for drone in self.swarm_drones.values():
            distance = self.calculate_3d_distance(drone.position, (center_lat, center_lon, center_alt))
            max_distance = max(max_distance, distance)
        
        # Find leader
        leader_id = None
        for drone_id, drone in self.swarm_drones.items():
            if drone.role == 'leader':
                leader_id = drone_id
                break
        
        # Calculate average battery
        avg_battery = sum(d.battery for d in self.swarm_drones.values()) / len(self.swarm_drones)
        
        return {
            'status': 'active',
            'drone_count': len(self.swarm_drones),
            'leader_id': leader_id,
            'center_position': (center_lat, center_lon, center_alt),
            'spread_radius': max_distance,
            'average_battery': avg_battery,
            'formation_type': self.formation.formation_type if self.formation else None,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_coordination_commands(self) -> Dict[str, Dict]:
        """Generate coordination commands for all drones"""
        commands = {}
        
        for drone_id in self.swarm_drones:
            desired_velocity = self.calculate_desired_velocity(drone_id)
            forces = self.calculate_swarm_forces(drone_id)
            
            # Convert velocity to navigation command
            current_pos = self.swarm_drones[drone_id].position
            
            # Simple integration: new position = current + velocity * dt
            dt = 1.0  # 1 second lookahead
            target_pos = (
                current_pos[0] + desired_velocity[0] * dt / 111000,  # Convert to lat
                current_pos[1] + desired_velocity[1] * dt / 111000,  # Convert to lon
                current_pos[2] + desired_velocity[2] * dt            # Alt in meters
            )
            
            commands[drone_id] = {
                'target_position': target_pos,
                'desired_velocity': desired_velocity,
                'forces': forces,
                'priority': 'swarm_coordination'
            }
        
        return commands

# Example usage and testing
if __name__ == "__main__":
    # Initialize swarm intelligence
    swarm = SwarmIntelligence()
    
    # Add test drones
    test_drones = [
        {
            'drone_id': 'SWARM-001',
            'latitude': 40.7128,
            'longitude': -74.0060,
            'altitude': 20.0,
            'heading': 0.0,
            'mode': 'AUTO',
            'battery': 85.0,
            'timestamp': datetime.now().isoformat()
        },
        {
            'drone_id': 'SWARM-002',
            'latitude': 40.7130,
            'longitude': -74.0058,
            'altitude': 22.0,
            'heading': 45.0,
            'mode': 'AUTO',
            'battery': 78.0,
            'timestamp': datetime.now().isoformat()
        },
        {
            'drone_id': 'SWARM-003',
            'latitude': 40.7126,
            'longitude': -74.0062,
            'altitude': 18.0,
            'heading': 90.0,
            'mode': 'AUTO',
            'battery': 92.0,
            'timestamp': datetime.now().isoformat()
        }
    ]
    
    # Add drones to swarm
    for drone_data in test_drones:
        swarm.add_drone(drone_data)
    
    # Create formation
    formation = swarm.create_formation("v_formation", 15.0)
    swarm.formation = formation
    
    # Get swarm status
    status = swarm.get_swarm_status()
    print(f"Swarm Status: {status}")
    
    # Generate coordination commands
    commands = swarm.get_coordination_commands()
    print(f"\nGenerated {len(commands)} coordination commands:")
    
    for drone_id, command in commands.items():
        print(f"  {drone_id}:")
        print(f"    Target: {command['target_position']}")
        print(f"    Velocity: {command['desired_velocity']}")
    
    print("\nSwarm intelligence test completed")
