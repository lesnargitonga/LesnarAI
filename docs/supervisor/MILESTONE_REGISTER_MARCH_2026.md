# Hackathon Milestone Register and Backfill Plan

As of: 2026-03-07

## Source Alignment

This register aligns milestone dates and required submissions from:
- `docs/ai hackathon guide.docx`
- `scripts/generate_roadmap.py`
- `docs/architecture.md`
- `docs/evidence/README.md`

## Official Milestones and Deadlines

1. Technical roadmap submission — due 2026-01-30
2. Data and development environment submission — due 2026-02-13
3. Functional alpha submission — due 2026-02-27
4. System security and integration submission — due 2026-03-13
5. Top-60 evaluation / final pitch window — 2026-03-20

## Milestone Status Backfill for Portal Update

### Already represented in the portal view (needs status correction where applicable)

- Develop technical roadmap  
  - Due: 2026-01-30  
  - Current portal state: Completed, Approved  
  - Action: Keep as-is

- API Bridge and Protocol Validation  
  - Due: 2026-01-26 (phase-1 internal target)  
  - Current portal state: Completed, Pending Approval  
  - Action: Keep completed; attach evidence links and resubmit for approval

- Compliance Logic and Synthetic Data  
  - Due: 2026-01-26 (phase-1 internal target)  
  - Current portal state: Completed, Pending Approval  
  - Action: Keep completed; attach evidence links and resubmit for approval

- Dynamics Verification (Proof of Flight)  
  - Due: 2026-01-26 (phase-1 internal target)  
  - Current portal state: Completed, Pending Approval  
  - Action: Keep completed; attach evidence links and resubmit for approval

- System Architecture Blueprinting  
  - Due: 2026-01-26 (phase-1 internal target)  
  - Current portal state: Not Started, Pending Approval  
  - Action: Correct to Completed; attach architecture artifacts and submit for approval

### Missing milestones to add immediately

- Environment and Data Submission (Phase 2)
  - Due: 2026-02-13
  - Proposed state now: Completed (Backfilled)
  - Evidence: dataset strategy document, simulator/data pipeline outputs

- Functional Alpha Submission (Phase 3)
  - Due: 2026-02-27
  - Proposed state now: Completed (Backfilled)
  - Evidence: end-to-end stack run, API + UI + simulation bridge flow

- System Security and Integration (Phase 4)
  - Due: 2026-03-13
  - Proposed state now: In Progress
  - Evidence target: secure deployment checks, auth/cors hardening, controlled demo profile

- Final Pitch Readiness / Top-60 Evaluation Package (Phase 5)
  - Due: 2026-03-20
  - Proposed state now: In Progress
  - Evidence target: final presentation evidence pack, proof checklist, runbook compliance

## Detailed Points to Track in Each Milestone Entry

For each portal milestone, include these fields in the description:

- Scope delivered: what was implemented and bounded as part of that milestone
- Evidence attached: exact document/pdf/script outputs used as proof
- Known limitations: constraints still open (GPU variability, runtime timing, telemetry gaps)
- Mitigation in place: what control or process reduces risk now
- Next checkpoint date: when the next measurable update will be posted

## Evidence Mapping for Faster Approval

- Architecture and design proof:
  - `docs/architecture.md`
  - `docs/architecture.pdf`
  - `docs/ros2_node_graph.md`
  - `docs/ros2_node_graph.pdf`

- Demo and operational proof:
  - `PRESENTATION.md`
  - `docs/Presentation_Evidence_Pack.pdf`
  - `docs/Presentation_Proof_Checklist.pdf`
  - `docs/Issues_Encountered_March_2026.pdf`

- Security and deployment proof:
  - `docs/SECURE_DEPLOYMENT_RUNBOOK.md`
  - `docs/DEPLOYMENT_COMPLETION_CHECKLIST.md`
  - `docs/DEFENSE_HARDENING_STATUS.md`

## Immediate Update Sequence (Today)

1. Edit existing milestone: System Architecture Blueprinting → set to Completed and submit with architecture evidence.
2. Re-submit pending Jan milestones with evidence attachments and concise notes.
3. Add missing Feb and Mar milestones listed above.
4. Mark current progress for Mar-13 and Mar-20 milestones as In Progress with explicit next update date.
5. During next presentation, open this register and show milestone-by-milestone evidence mapping.

## Weekly Milestone Hygiene Rule (From now until final pitch)

- Update portal milestones every 3 days (or immediately after each major evidence artifact is generated).
- Never leave a milestone without:
  - status,
  - due date,
  - evidence reference,
  - next action.
