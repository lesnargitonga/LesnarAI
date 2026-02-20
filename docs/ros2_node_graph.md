# ROS 2 / MAVSDK Runtime Node Graph

## Overview

Operation Sentinel uses **MAVSDK** (not MAVROS) for direct MAVLink communication with PX4.
This provides lower-latency, lighter-weight integration compared to the full ROS 2 / MAVROS stack.

The architecture below shows all runtime nodes, interfaces, and data flow.

---

## Runtime Node Graph

```mermaid
graph TB
    subgraph WSL2["WSL2 (Ubuntu)"]
        subgraph GZ["Gazebo Harmonic (Physics Engine)"]
            GZ_WORLD["gz::sim::World<br/>obstacles.sdf<br/>(85 obstacles)"]
            GZ_PHYS["gz::physics<br/>DART Engine"]
            GZ_SENSORS["gz::sensors<br/>IMU, Barometer, GPS"]
            GZ_TRANSPORT["gz::transport<br/>(Protobuf pub/sub)"]
        end

        subgraph PX4["PX4 SITL Autopilot"]
            EKF2["EKF2<br/>State Estimation<br/>250 Hz"]
            MC_ATT["mc_att_control<br/>Attitude Controller<br/>250 Hz"]
            MC_POS["mc_pos_control<br/>Position Controller<br/>50 Hz"]
            COMMANDER["commander<br/>Flight Mode Manager"]
            MAVLINK["mavlink<br/>MAVLink Bridge<br/>UDP :14540"]
        end

        subgraph BRIDGE["Bridge Process (Python)"]
            MAVSDK_CLIENT["MAVSDK Client<br/>Async gRPC"]
            MAVSDK_SERVER["mavsdk_server<br/>MAVLink ↔ gRPC<br/>UDP :14540"]
            LIDAR_SIM["Simulated LiDAR<br/>72 rays, 360°, 20 m"]
            ASTAR["A* Pathfinder<br/>Grid-based"]
            SDF_PARSER["SDF Parser<br/>Obstacle Extraction"]
            REDIS_PUB["Redis Publisher<br/>Telemetry + Status"]
            REDIS_SUB["Redis Subscriber<br/>Commands"]
        end
    end

    subgraph DOCKER["Docker Desktop (Windows Host)"]
        subgraph BACKEND["Flask Backend Container"]
            FLASK_API["Flask REST API<br/>:5000"]
            SOCKETIO["Socket.IO<br/>WebSocket Server<br/>5 Hz"]
            REDIS_BRIDGE["Redis Bridge<br/>Pub/Sub Listener"]
            ORM["SQLAlchemy ORM<br/>Models + Migrations"]
        end

        REDIS["Redis<br/>:6379<br/>Pub/Sub + Cache"]
        TSDB["TimescaleDB<br/>:5432<br/>Time-Series Storage"]
        ADMINER["Adminer<br/>:8080<br/>DB Viewer"]
    end

    subgraph FRONTEND["React Frontend"]
        DASHBOARD["Dashboard<br/>Fleet Overview"]
        MAP["DroneMap<br/>Leaflet + Markers"]
        ANALYTICS["Analytics<br/>Live Fleet Metrics"]
        WS_CLIENT["Socket.IO Client<br/>WebSocket"]
    end

    %% Gazebo ↔ PX4
    GZ_WORLD -->|"gz::transport<br/>pose, velocity"| GZ_TRANSPORT
    GZ_PHYS -->|"Physics step"| GZ_WORLD
    GZ_SENSORS -->|"IMU, Baro, GPS"| GZ_TRANSPORT
    GZ_TRANSPORT <-->|"gz_bridge<br/>Protobuf"| PX4

    %% PX4 internal
    EKF2 -->|"vehicle_local_position"| MC_POS
    MC_POS -->|"vehicle_attitude_setpoint"| MC_ATT
    MC_ATT -->|"actuator_outputs"| GZ_TRANSPORT
    COMMANDER -->|"vehicle_command"| MC_POS

    %% PX4 ↔ Bridge
    MAVLINK <-->|"MAVLink UDP<br/>:14540"| MAVSDK_SERVER
    MAVSDK_SERVER <-->|"gRPC"| MAVSDK_CLIENT

    %% Bridge internal
    SDF_PARSER -->|"Obstacle map"| LIDAR_SIM
    SDF_PARSER -->|"Obstacle map"| ASTAR
    MAVSDK_CLIENT -->|"Position, velocity,<br/>battery, mode"| REDIS_PUB
    LIDAR_SIM -->|"Distance readings"| ASTAR
    ASTAR -->|"Waypoint commands"| MAVSDK_CLIENT
    REDIS_SUB -->|"goto, takeoff, land"| MAVSDK_CLIENT

    %% Bridge ↔ Redis
    REDIS_PUB -->|"PUBLISH telemetry"| REDIS
    REDIS -->|"SUBSCRIBE commands"| REDIS_SUB

    %% Backend ↔ Redis/DB
    REDIS -->|"Pub/Sub"| REDIS_BRIDGE
    REDIS_BRIDGE -->|"Telemetry data"| SOCKETIO
    REDIS_BRIDGE -->|"State updates"| ORM
    ORM <-->|"SQL"| TSDB
    FLASK_API <-->|"Queries"| ORM
    FLASK_API -->|"PUBLISH commands"| REDIS
    ADMINER <-->|"SQL"| TSDB

    %% Frontend ↔ Backend
    WS_CLIENT <-->|"WebSocket<br/>5 Hz telemetry"| SOCKETIO
    DASHBOARD --- WS_CLIENT
    MAP --- WS_CLIENT
    ANALYTICS --- WS_CLIENT
    FRONTEND -->|"REST API<br/>HTTP :5000"| FLASK_API

    classDef gazebo fill:#4CAF50,color:white,stroke:#2E7D32
    classDef px4 fill:#2196F3,color:white,stroke:#1565C0
    classDef bridge fill:#FF9800,color:white,stroke:#E65100
    classDef docker fill:#9C27B0,color:white,stroke:#6A1B9A
    classDef frontend fill:#00BCD4,color:white,stroke:#00838F
    classDef data fill:#607D8B,color:white,stroke:#37474F

    class GZ_WORLD,GZ_PHYS,GZ_SENSORS,GZ_TRANSPORT gazebo
    class EKF2,MC_ATT,MC_POS,COMMANDER,MAVLINK px4
    class MAVSDK_CLIENT,MAVSDK_SERVER,LIDAR_SIM,ASTAR,SDF_PARSER,REDIS_PUB,REDIS_SUB bridge
    class FLASK_API,SOCKETIO,REDIS_BRIDGE,ORM docker
    class DASHBOARD,MAP,ANALYTICS,WS_CLIENT frontend
    class REDIS,TSDB,ADMINER data
```

---

## Interface Summary

| Interface | Protocol | Rate | Direction |
|-----------|----------|------|-----------|
| Gazebo ↔ PX4 | gz::transport (Protobuf) | 250 Hz | Bidirectional |
| PX4 ↔ MAVSDK Server | MAVLink over UDP :14540 | 50 Hz | Bidirectional |
| MAVSDK Server ↔ Client | gRPC (local) | 50 Hz | Bidirectional |
| Bridge → Redis | PUBLISH (telemetry channel) | 20 Hz | Unidirectional |
| Redis → Bridge | SUBSCRIBE (commands channel) | Event-driven | Unidirectional |
| Redis → Backend | Pub/Sub listener | 20 Hz | Unidirectional |
| Backend → Frontend | WebSocket (Socket.IO) | 5 Hz | Unidirectional |
| Frontend → Backend | REST API (HTTP) | On-demand | Unidirectional |
| Backend ↔ TimescaleDB | SQL (SQLAlchemy) | ~1.7 Hz | Bidirectional |

## Key Design Decisions

1. **MAVSDK over MAVROS**: Direct MAVLink via MAVSDK provides lower latency and simpler deployment than the full ROS 2 / MAVROS stack. No ROS 2 installation required.

2. **Simulated LiDAR**: Parses `obstacles.sdf` for ground-truth obstacle positions, then ray-casts 72 beams. Produces clean training data without sensor noise.

3. **Redis Pub/Sub**: Decouples the Bridge from the Backend. Enables non-blocking command/telemetry flow across the WSL ↔ Docker boundary.

4. **Hybrid Control**: PX4 handles low-level flight control (250 Hz). AI layer handles mission planning and obstacle avoidance (10-50 Hz). Each operates at its optimal frequency.
