# Presentation Evidence Runbook

This folder is used to assemble proof artifacts for hackathon presentations.

## Expected Artifacts

- `../Presentation_Evidence_Pack.pdf`
- `../Presentation_Proof_Checklist.pdf`
- `../visual_evidence.png`
- `videos/*.mp4` (or `.mov`, `.mkv`, `.webm`)

## Generate PDF Evidence Pack

From repo root:

```bash
python3 docs/evidence/generate_presentation_evidence.py
```

This creates:

- `docs/Presentation_Evidence_Pack.pdf`
- `docs/Presentation_Proof_Checklist.pdf`

## Suggested Video File Names

1. `videos/01_startup_sequence.mp4`
2. `videos/02_autonomous_avoidance.mp4`
3. `videos/03_api_commands_takeoff_goto_land.mp4`
4. `videos/04_safety_emergency_stop.mp4`

## Suggested Screenshot File Names

- `screenshots/backend_health.png`
- `screenshots/frontend_dashboard.png`
- `screenshots/adminer_telemetry.png`
- `screenshots/gazebo_world.png`
- `screenshots/px4_ready_terminal.png`
- `screenshots/teacher_falcon_metrics.png`
