# ROS 2 / MAVROS Runtime Node Graph (High-Fidelity)

## Verification Scope

This diagram verifies the **High-Fidelity Architecture Diagram milestone** for a ROS 2 + MAVROS runtime path, explicitly showing:

- Runtime nodes and process boundaries
- Topics, services, and message interfaces
- Command and telemetry data flow across AI → MAVROS → PX4 → Gazebo

> Note: Current project implementation is MAVSDK-first. The graph below is the ROS 2 / MAVROS reference architecture requested for milestone verification.

---

## Runtime Node Graph

```mermaid
flowchart LR
    subgraph SIM[Simulation Environment]
        GZ[Gazebo Harmonic\nWorld: obstacles.sdf]
        GZS[gz::sensors\nIMU / GPS / Baro / Camera]
        GZT[gz::transport]
        GZ --- GZS
        GZ --- GZT
    end

    subgraph FCU[PX4 SITL Flight Stack]
        PX4CMD[commander]
        PX4NAV[navigator]
        PX4EKF[EKF2]
        PX4POS[mc_pos_control]
        PX4ATT[mc_att_control]
        PX4MAV[mavlink module\nUDP 14540]
    end

    subgraph ROS2[ROS 2 Graph]
        subgraph AI[AI Layer]
            PERCEP[perception_node]
            PLAN[planner_node\n(A* / policy)]
            MISSION[mission_manager_node]
            SAFETY[safety_guard_node]
        end

        subgraph MAVROS[MAVROS Layer]
            MAVROSN[mavros_node]
            PLUGIN_STATE[state plugin]
            PLUGIN_LP[local_position plugin]
            PLUGIN_IMU[imu plugin]
            PLUGIN_SETPT[setpoint_raw plugin]
            PLUGIN_CMD[cmd plugin]
        end
    end

    subgraph APP[App & Ops Layer]
        API[backend_api\nREST/SocketIO]
        REDIS[(Redis Pub/Sub)]
        UI[frontend_dashboard]
    end

    %% Simulation <-> PX4
    GZT <-->|sensor + actuator transport| PX4EKF
    PX4ATT --> PX4POS
    PX4POS --> PX4NAV
    PX4NAV --> PX4CMD
    PX4CMD --> PX4MAV

    %% MAVLink bridge
    PX4MAV <-->|MAVLink UDP| MAVROSN

    %% MAVROS plugin internals
    MAVROSN --> PLUGIN_STATE
    MAVROSN --> PLUGIN_LP
    MAVROSN --> PLUGIN_IMU
    MAVROSN --> PLUGIN_SETPT
    MAVROSN --> PLUGIN_CMD

    %% ROS2 topic/service dataflow
    PLUGIN_STATE -->|/mavros/state\n[mavros_msgs/State]| MISSION
    PLUGIN_LP -->|/mavros/local_position/pose\n[geometry_msgs/PoseStamped]| PLAN
    PLUGIN_IMU -->|/mavros/imu/data\n[sensor_msgs/Imu]| PERCEP

    PERCEP -->|/ai/obstacles\n[sensor_msgs/LaserScan or custom]| PLAN
    PLAN -->|/ai/trajectory\n[nav_msgs/Path]| MISSION
    SAFETY -->|/ai/safety_override\n[std_msgs/Bool]| MISSION

    MISSION -->|/mavros/setpoint_raw/local\n[mavros_msgs/PositionTarget]| PLUGIN_SETPT
    MISSION -->|/mavros/set_mode\n[mavros_msgs/srv/SetMode]| PLUGIN_CMD
    MISSION -->|/mavros/cmd/arming\n[mavros_msgs/srv/CommandBool]| PLUGIN_CMD
    MISSION -->|/mavros/cmd/takeoff\n[mavros_msgs/srv/CommandTOL]| PLUGIN_CMD
    MISSION -->|/mavros/cmd/land\n[mavros_msgs/srv/CommandTOL]| PLUGIN_CMD

    %% App layer integration
    API <-->|command + telemetry| REDIS
    API <-->|websocket + REST| UI
    MISSION <-->|mission command bridge| REDIS

    classDef sim fill:#2E7D32,color:#fff,stroke:#1B5E20
    classDef px4 fill:#1565C0,color:#fff,stroke:#0D47A1
    classDef ai fill:#EF6C00,color:#fff,stroke:#E65100
    classDef mav fill:#6A1B9A,color:#fff,stroke:#4A148C
    classDef app fill:#00838F,color:#fff,stroke:#006064

    class GZ,GZS,GZT sim
    class PX4CMD,PX4NAV,PX4EKF,PX4POS,PX4ATT,PX4MAV px4
    class PERCEP,PLAN,MISSION,SAFETY ai
    class MAVROSN,PLUGIN_STATE,PLUGIN_LP,PLUGIN_IMU,PLUGIN_SETPT,PLUGIN_CMD mav
    class API,REDIS,UI app
```

---

## Interface Matrix (ROS 2 / MAVROS)

| Source | Interface | Type | Sink | Purpose |
|---|---|---|---|---|
| `mavros state plugin` | `/mavros/state` | Topic (`mavros_msgs/State`) | `mission_manager_node` | Mode + arming state feedback |
| `mavros local_position plugin` | `/mavros/local_position/pose` | Topic (`geometry_msgs/PoseStamped`) | `planner_node` | Position feedback for path tracking |
| `mavros imu plugin` | `/mavros/imu/data` | Topic (`sensor_msgs/Imu`) | `perception_node` | Attitude/IMU features |
| `perception_node` | `/ai/obstacles` | Topic (`sensor_msgs/LaserScan` or custom) | `planner_node` | Obstacle representation |
| `planner_node` | `/ai/trajectory` | Topic (`nav_msgs/Path`) | `mission_manager_node` | Planned route |
| `safety_guard_node` | `/ai/safety_override` | Topic (`std_msgs/Bool`) | `mission_manager_node` | Safety gating |
| `mission_manager_node` | `/mavros/setpoint_raw/local` | Topic (`mavros_msgs/PositionTarget`) | `mavros setpoint_raw plugin` | Offboard setpoints |
| `mission_manager_node` | `/mavros/set_mode` | Service (`mavros_msgs/srv/SetMode`) | `mavros cmd plugin` | Mode changes (e.g., OFFBOARD) |
| `mission_manager_node` | `/mavros/cmd/arming` | Service (`mavros_msgs/srv/CommandBool`) | `mavros cmd plugin` | Arm/disarm |
| `mission_manager_node` | `/mavros/cmd/takeoff` | Service (`mavros_msgs/srv/CommandTOL`) | `mavros cmd plugin` | Takeoff command |
| `mission_manager_node` | `/mavros/cmd/land` | Service (`mavros_msgs/srv/CommandTOL`) | `mavros cmd plugin` | Land command |

---

## Dataflow Narrative

1. Gazebo publishes simulated sensor streams and receives actuator outputs through PX4 SITL integration.
2. PX4 estimates state (`EKF2`) and exposes control/telemetry through MAVLink UDP.
3. MAVROS translates MAVLink into ROS 2 topics/services for the AI mission stack.
4. AI nodes compute obstacle-aware trajectories and publish setpoints through MAVROS plugins.
5. Mission and telemetry are mirrored into backend/Redis/frontend for operator visibility.

---

## Milestone Verification Checklist

- Runtime nodes identified by layer (AI, MAVROS, PX4, Simulation)
- Control interfaces specified (setpoint + mode/arm/takeoff/land services)
- Telemetry interfaces specified (state, local position, IMU)
- End-to-end command and feedback paths documented
- Dataflow between ops layer and autonomy layer included
