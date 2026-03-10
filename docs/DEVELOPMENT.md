# Development Manual

NOTE: This document contains legacy Windows-centric notes. The canonical, submission-grade runbook is in the root `README.md` (WSL2 + PX4/Gazebo + Docker stack).

## 1. Environment Setup

### 1.1 Prerequisites
-   **Language Runtimes**: Python 3.10+, Node.js 16+ (LTS).
-   **Platform**: Windows 10/11 + WSL2 (Ubuntu) for PX4/Gazebo simulation.
-   **Build Tools**: CMake, Make, Visual Studio Build Tools (C++14).

### 1.2 Automated Initialization
The repository contains scripts to automate environment provisioning:

```powershell
# Initialize Python virtual environments and dependencies
.\bin\setup.bat
```

This script provisions (legacy):
1.  `backend-env`: Flask API and Core Logic.
2.  `airsim-env`: legacy AirSim environment (moved to `legacy/airsim-env`).
3.  `frontend`: NPM dependencies for the dashboard.

---

## 2. Operational Procedures

### 2.1 System Launch
To initiate the legacy Windows-centric system stack (not the canonical WSL PX4/Gazebo flow):

```powershell
.\bin\start_all.bat
```

### 2.2 Component Isolation
For targeted development, services can be launched independently via `bin/`:
-   `start_backend.bat`: REST API (Port 5000).
-   `start_frontend.bat`: React Dashboard (Port 3000).
-   `start_simulation.bat`: Standalone drone physics engine.

For the canonical stack, use `python3 scripts/bootstrap_secure_deployment.py`, then `docker compose --env-file .env.secure up -d --build` (backend/redis/db) and `npm start` (frontend). Use session auth via `python3 scripts/request_session_token.py` for API checks, then run PX4/Gazebo + the teacher in WSL as described in the root README.

---

## 3. Architecture

### 3.1 System Context
The storage-compute architecture consists of three primary subsystems:
1.  **Frontend (React)**: User Interface for command and control.
2.  **Backend (Flask)**: Business logic, API gateway, and data persistence.
3.  **Simulation Kernel (Python/C++)**: Physics execution and sensor emulation.

### 3.2 Inter-Process Communication
-   **Telemetry**: UDP/MAVLink (Port 14540).
-   **State Updates**: WebSocket (Socket.IO).
-   **Command Interface**: HTTP/REST.

---

## 4. Contribution Standards

### 4.1 Code Quality
-   **Python**: Strict adherence to PEP 8.
-   **JavaScript**: ESLint compliance required.
-   **Documentation**: All public interfaces must include docstrings.

### 4.2 Git Workflow
-   **Branching**: Feature-branch workflow (`feature/description`).
-   **Commits**: Conventional Commits format (`feat:`, `fix:`, `docs:`).

### 4.3 Testing
-   **Unit Tests**: `pytest` for backend logic.
-   **Integration Tests**: Validated via HITL/SITL simulation runs.
