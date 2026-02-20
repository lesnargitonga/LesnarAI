# Architecture Design Document

Last updated: 2026-02-06

## 1. System Overview

Operation Sentinel employs a **Hybrid Cortex Architecture**, a control paradigm that decouples deterministic flight stability from stochastic mission planning.

### 💡 In Plain English
> Think of the system like a human pilot:
> *   **Reflex Layer (The "Spinal Cord"):** Handles muscle movements, balance, and instant reactions to wind gusts. It doesn't "think"—it just keeps the drone flying.
> *   **Mission Layer (The "Brain"):** Uses eyes (cameras/LiDAR) to spot obstacles and decide *where* to go. It plans the path, but trusts the Reflex Layer to execute the actual flying.

---

### 1.1 The Hybrid Cortex Concept

The "Cortex" is divided into two distinct processing layers:

*   **Reflex Layer (Deterministic):**
    *   **Component:** PX4 Autopilot / EKF2
    *   **Function:** State estimation, attitude control, motor mixing, failsafe execution.
    *   **Constraint:** Hard real-time (250Hz+).
    *   **Failure Mode:** Safe landing / Return to Launch.

*   **Mission Layer (Stochastic):**
    *   **Component:** Deep Reinforcement Learning (PPO) Agent.
    *   **Function:** Semantic scene understanding, complex path planning, dynamic obstacle avoidance.
    *   **Constraint:** Soft real-time (10-50Hz).
    *   **Failure Mode:** Local hover / Re-plan.

## 2. Component Design

### 2.1 Computing Substrate
The system operates within a tiered compute environment:
-   **Host:** WSL2 (Ubuntu 22.04) running on x86_64 architecture.
-   **Interconnect:** Localhost UDP/TCP, avoiding overhead of virtualization network bridges.

### 2.2 Simulation Environment (Gazebo Harmonic)
Gazebo Harmonic provides the synthetic ground truth. It utilizes:
-   **Ray Tracing:** For realistic LiDAR point cloud generation.
-   **Physics Engine:** DART/ODE for rigid body dynamics.
-   **Sensor Models:** IMU (Acc/Gyro), Magnetometer, GPS, and Barometer with distinct noise profiles matching real-world hardware.

### 2.3 Flight Core (PX4)
The PX4 stack runs in SITL (Software In The Loop) mode but executes the exact binary code used on physical flight controllers (Pixhawk 6X).
-   **EKF2:** Extended Kalman Filter fusing IMU and GPS data for state estimation.
-   **Commander:** State machine handling arming checks, mode switching, and geofence enforcement.

### 2.4 Mission Brain (AI Agent)
The autonomous agent is a Neural Network trained via Proximal Policy Optimization (PPO).
-   **Input:** 360-degree LiDAR tensor (normalized distance vectors) + Ego-State (Velocity, Orientation).
-   **Output:** Continuous action vector $[v_x, v_y, v_z, \dot{\psi}]$ (Velocity sets in body frame).
-   **Bridge:** MAVSDK-Python acts as the translation layer, converting neural network outputs into MAVLink `SET_POSITION_TARGET_LOCAL_NED` messages.

## 3. Data Flow Architecture

The following Mermaid diagram reflects the current PX4 + Gazebo + MAVSDK + PPO dataflow.

![Architecture diagram](architecture.svg)

## 4. Security Considerations

All inter-process communication is localized. The system is designed to operate with the radio modem as the *only* external interface.
-   **No Cloud Dependency:** Usage of cloud APIS (Google Maps, AWS) is strictly prohibited in the operational loop.
-   **Data Minimization:** Resolution of LiDAR data is downsampled at the pre-processor to the minimum viable density for navigation, reducing the surface area for data reconstruction attacks.
