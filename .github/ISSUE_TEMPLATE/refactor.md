---
name: "Refactor: Remove legacy AirSim configurations"
about: Clean up unused AirSim settings and legacy configs as we migrate to PX4-first workflows
labels: [refactor, cleanup]
---

## Summary
Remove redundant/legacy AirSim configuration files to reduce confusion and drift with the PX4-first stack.

## Acceptance Criteria
- [ ] Identify unused AirSim settings JSON files and examples
- [ ] Remove or relocate to `archive/` if historically valuable
- [ ] Update README to prefer `gz`/`jmavsim` SITL

## Notes
We are standardizing on PX4 SITL (gz/jmavsim) and using AirSim primarily for perception demos.
