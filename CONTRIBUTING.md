# Contributing to Operation Sentinel

**Security Notice:** This project involves autonomous flight control logic. All contributions must adhere to the strict safety and security protocols defined below. Code that compromises failsafe mechanisms or introduces non-deterministic behavior in the Reflex Layer will be rejected.

## 1. Development Standards

### 1.1 Python (Mission Layer)
-   **Style:** PEP 8 compliance is mandatory.
-   **Type Hinting:** All function signatures must be fully typed.
-   **Docstrings:** Google-style docstrings for all classes and public methods.

### 1.2 C++ (Reflex Layer / PX4)
-   **Standard:** C++14 or later.
-   **Memory Safety:** Zero raw pointer usage. Use `std::shared_ptr` or `std::unique_ptr`.
-   **Real-Time constraints:** No blocking I/O or heap allocation in the critical control loop.

## 2. Pull Request Protocol

1.  **Branch Naming:** `feature/category-description` (e.g., `feature/path-planning-astar`).
2.  **Verification:** All PRs must include a `walkthrough.md` or simulation log demonstrating successful flight in Gazebo.
3.  **Review:** Security audit required for any changes to `src/mavlink_bridge.py` or network interfaces.

## 3. Reporting Vulnerabilities

Do not open public GitHub issues for security vulnerabilities.
Contact a maintainer directly or follow the internal disclosure process.
