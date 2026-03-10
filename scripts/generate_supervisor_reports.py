#!/usr/bin/env python3
"""Generate supervisor-facing detailed challenge + technical dossier PDFs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / 'docs'
SUPERVISOR = DOCS / 'supervisor'
VALIDATION_REPORT = DOCS / 'validation' / 'stability_verification_latest.json'


def load_validation() -> dict:
    if not VALIDATION_REPORT.exists():
        return {
            'status': 'missing',
            'message': 'No automated stability verification report found yet.',
        }
    try:
        return json.loads(VALIDATION_REPORT.read_text(encoding='utf-8'))
    except Exception as exc:
        return {'status': 'invalid', 'message': f'Failed to parse validation report: {exc}'}


def styles_bundle():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name='TitleX', parent=base['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#0B2A4A')))
    base.add(ParagraphStyle(name='H2X', parent=base['Heading2'], fontSize=13, leading=16, textColor=colors.HexColor('#123A63')))
    base.add(ParagraphStyle(name='BodyX', parent=base['BodyText'], fontSize=10, leading=14, alignment=TA_LEFT))
    base.add(ParagraphStyle(name='MonoX', parent=base['BodyText'], fontName='Courier', fontSize=9, leading=12))
    return base


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(18 * mm, 10 * mm, 'Operation Sentinel - Supervisor Reporting Pack')
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f'Page {doc.page}')
    canvas.restoreState()


def add_title(story, styles, title: str, subtitle: str):
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    story.append(Paragraph(title, styles['TitleX']))
    story.append(Spacer(1, 6))
    story.append(Paragraph(subtitle, styles['BodyX']))
    story.append(Paragraph(f'Generated (UTC): {generated}', styles['BodyX']))
    story.append(Spacer(1, 12))


def challenge_report(out_path: Path, validation: dict):
    styles = styles_bundle()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story = []

    add_title(
        story,
        styles,
        'Challenges and Constraints Report (Supervisor Edition)',
        'Detailed record of controllable fixes, uncontrollable constraints, risks, and recommendations.',
    )

    story.append(Paragraph('1) Executive Summary', styles['H2X']))
    story.append(Paragraph(
        'The project is functionally operational but constrained by system-level factors outside direct software control. '
        'Core deployment, authentication, and control-loop safety stabilizations are implemented. Remaining risk is dominated by runtime '
        'resource variability (GPU power envelope, simulator timing jitter, and host process contention).',
        styles['BodyX'],
    ))

    story.append(Spacer(1, 8))
    story.append(Paragraph('2) Uncontrollable or Hard-to-Control Constraints', styles['H2X']))
    rows = [
        ['Constraint', 'Observed Impact', 'Evidence/Signal', 'Mitigation in Place', 'Residual Risk'],
        ['GPU performance envelope', 'Inference and rendering can spike latency; timing variance increases control jitter.', 'Frame-time spikes, unstable cycle times under load.', 'Conservative control profile + lower command aggressiveness.', 'Medium'],
        ['Simulation lag (Gazebo/PX4 scheduling)', 'Temporal drift causes stale telemetry and delayed command confirmation.', 'Intermittent stale telemetry and inconsistent realtime factor.', 'Stale telemetry lockout, watchdogs, safety holds.', 'Medium-High'],
        ['WSL/host process contention', 'Duplicate services and port conflicts create false "network" symptoms.', 'Multiple frontend instances, port drift 3000/3001.', 'Guarded frontend startup script to enforce single instance.', 'Low-Medium'],
        ['Hardware heterogeneity', 'Different machine load and thermal behavior shifts stability baseline.', 'Run-to-run variance in same scenario.', 'Quantitative validation script with thresholds and repeatability protocol.', 'Medium'],
    ]
    table = Table(rows, colWidths=[30 * mm, 45 * mm, 35 * mm, 45 * mm, 20 * mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#123A63')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(table)

    story.append(Spacer(1, 10))
    story.append(Paragraph('3) What Has Been Fixed', styles['H2X']))
    fixed_items = [
        'Session-auth deployment path stabilized with persistent login endpoints and secure token flow.',
        'Dockerized backend stack validated with health checks and secure env validation tooling.',
        'Frontend network/login reliability hardened (single-instance startup guard + API base resilience).',
        'Bridge controller safety improved with conservative profile and instability recovery logic.',
        'Operational geofence, stale telemetry lockout, and command confirmation safeguards active.',
        'Documentation baseline and secure runbook updated for presentation and reproducibility.',
    ]
    for item in fixed_items:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Spacer(1, 8))
    story.append(Paragraph('4) What Is Not Fully Solved Yet', styles['H2X']))
    open_items = [
        'Cross-machine deterministic timing is not guaranteed under variable GPU/CPU pressure.',
        'PX4/Gazebo runtime jitter still requires controlled test windows for high-confidence demos.',
        'PID refinement remains an iterative process tied to environmental load and scenario complexity.',
        'Full production security controls (KMS/HSM custody, SIEM integration, immutable retention) are external to repo scope.',
    ]
    for item in open_items:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Spacer(1, 8))
    story.append(Paragraph('5) Quantitative Validation Snapshot', styles['H2X']))
    if 'metrics' in validation:
        metrics = validation.get('metrics', {})
        evaln = validation.get('evaluation', {})
        story.append(Paragraph(f"Automated verdict: {'PASS' if evaln.get('pass') else 'FAIL'}", styles['BodyX']))
        story.append(Paragraph(f"End-to-end drift (m): {metrics.get('end_to_end_drift_m')}", styles['MonoX']))
        story.append(Paragraph(f"RMS jitter (m): {metrics.get('rms_jitter_from_centroid_m')}", styles['MonoX']))
        story.append(Paragraph(f"Telemetry availability: {validation.get('telemetry_availability_ratio')}", styles['MonoX']))
        story.append(Paragraph(f"Reasons: {', '.join(evaln.get('reasons', [])) or 'none'}", styles['MonoX']))
    else:
        story.append(Paragraph(validation.get('message', 'Validation report unavailable.'), styles['BodyX']))

    story.append(Spacer(1, 8))
    story.append(Paragraph('6) Supervisor-Facing Requests / Dependencies', styles['H2X']))
    asks = [
        'Dedicated high-power profile for repeatable GPU performance during flight validation windows.',
        'Reserved machine slot during demos to avoid host contention and simulator lag spikes.',
        'Acceptance criteria to be based on repeated quantitative runs (not single-run anecdotal behavior).',
        'Approval for staged tuning cycles focused on bounded environments before broader scenarios.',
    ]
    for item in asks:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def technical_dossier(out_path: Path, validation: dict):
    styles = styles_bundle()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story = []

    add_title(
        story,
        styles,
        'Technical Dossier (Detailed)',
        'Comprehensive status: architecture, automation, optimization, quantitative validation, PID test protocol, environment definition, and security controls.',
    )

    story.append(Paragraph('A) Automation Implemented', styles['H2X']))
    story.append(Paragraph('Script: scripts/telemetry_stability_autologin.py', styles['MonoX']))
    story.append(Paragraph(
        'Function: performs session login, polls telemetry via authenticated endpoints, computes drift/jitter/availability metrics, writes machine-readable JSON + CSV, and returns PASS/FAIL based on thresholds.',
        styles['BodyX'],
    ))

    story.append(Paragraph('B) Configuration Optimization Baseline', styles['H2X']))
    config_points = [
        'Frontend startup guard prevents duplicate React instances and port drift.',
        'Safe presentation control profile constrains yaw/tilt/lateral aggressiveness for stability.',
        'Secure CORS origin list aligned with active local runtime ports.',
        'Session authentication required in secure mode; legacy browser API-key fallback disabled.',
        'Telemetry stale lockout and command confirmation timeout enforce safer control semantics.',
    ]
    for point in config_points:
        story.append(Paragraph(f'• {point}', styles['BodyX']))

    story.append(Paragraph('C) Quantitative Validation Method', styles['H2X']))
    story.append(Paragraph(
        'Primary metrics: end-to-end drift (m), RMS jitter from centroid (m), telemetry availability ratio, max/avg telemetry age, altitude span.',
        styles['BodyX'],
    ))
    story.append(Paragraph(
        'Decision rule: PASS if drift and jitter remain below threshold and telemetry availability stays above minimum threshold.',
        styles['BodyX'],
    ))

    if 'metrics' in validation:
        metrics = validation.get('metrics', {})
        evaln = validation.get('evaluation', {})
        story.append(Paragraph('Latest measured values:', styles['BodyX']))
        for key in [
            'end_to_end_drift_m',
            'rms_jitter_from_centroid_m',
            'p95_jitter_from_centroid_m',
            'altitude_span_m',
            'speed_avg_mps',
            'avg_telemetry_age_s',
        ]:
            story.append(Paragraph(f'- {key}: {metrics.get(key)}', styles['MonoX']))
        story.append(Paragraph(f"Validation verdict: {'PASS' if evaln.get('pass') else 'FAIL'}", styles['BodyX']))
    else:
        story.append(Paragraph('Latest measured values: not yet generated. Run the automation script to populate.', styles['BodyX']))

    story.append(PageBreak())

    story.append(Paragraph('D) PID Refinement and Control Test Protocol', styles['H2X']))
    pid_steps = [
        'Step 1: Run baseline hover-hold test (60-120s) in no-wind synthetic environment.',
        'Step 2: Sweep one gain axis at a time (P, then D, then I) with fixed environmental conditions.',
        'Step 3: Quantify overshoot, settling time, and steady-state drift using telemetry export.',
        'Step 4: Validate safety envelope under obstacle-presence with conservative motion bounds.',
        'Step 5: Promote gains only after three consecutive PASS runs.',
    ]
    for step in pid_steps:
        story.append(Paragraph(f'• {step}', styles['BodyX']))

    story.append(Paragraph('E) Environmental Conditions Definition', styles['H2X']))
    env_rows = [
        ['Condition Class', 'Definition', 'Control Level', 'Reason'],
        ['CPU/GPU load', 'Host utilization during run', 'Partially controllable', 'Affects cycle timing and lag'],
        ['Simulator timestep', 'Gazebo/PX4 realtime behavior', 'Partially controllable', 'Impacts dynamics consistency'],
        ['Obstacle density', 'World complexity and clutter', 'Controllable', 'Affects navigation stress level'],
        ['Wind/weather model', 'Injected disturbances', 'Controllable', 'Defines robustness envelope'],
        ['Network/socket behavior', 'Local loopback + service health', 'Controllable', 'Affects telemetry freshness'],
    ]
    env_table = Table(env_rows, colWidths=[32 * mm, 52 * mm, 30 * mm, 52 * mm])
    env_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#123A63')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(env_table)

    story.append(Spacer(1, 10))
    story.append(Paragraph('F) Security Status (Containerization, Auth, Logging)', styles['H2X']))
    sec_points = [
        'Containerized backend stack with redis + timescaledb + adminer orchestration.',
        'Session authentication endpoints enabled and enforced in secure mode.',
        'Audit-related event and command logging with role/operator context.',
        'Secure deployment validation script checks secrets, auth mode, and boundary consistency.',
        'Residual gap: enterprise controls (KMS/HSM, SIEM, immutable storage policy) are outside repository scope.',
    ]
    for point in sec_points:
        story.append(Paragraph(f'• {point}', styles['BodyX']))

    story.append(Spacer(1, 10))
    story.append(Paragraph('G) Recommended Next Validation Sprint', styles['H2X']))
    sprint = [
        'Run automated stability verification for 3 x 120s trials in fixed environment profile.',
        'Compare drift/jitter distributions before and after each PID adjustment.',
        'Freeze a “demo-safe” gain/profile once pass-rate reaches 100% in controlled conditions.',
        'Extend to stress profile with documented deltas and risk acceptance statement.',
    ]
    for item in sprint:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def write_markdown_summary(md_path: Path, validation: dict):
    lines = [
        '# Supervisor Reporting Summary',
        '',
        f'Generated (UTC): {datetime.now(timezone.utc).isoformat()}',
        '',
        '## Deliverables',
        '- Challenges and constraints PDF',
        '- Detailed technical dossier PDF',
        '- Automated session login + telemetry drift validation script',
        '',
        '## Validation Snapshot',
        f'- Validation report source: {VALIDATION_REPORT.relative_to(REPO)}',
        f'- Status: {validation.get("evaluation", {}).get("pass") if isinstance(validation, dict) else "unknown"}',
        '',
        '## Notes',
        '- Uncontrollable factors are explicitly separated from software-fixable issues.',
        '- Security section includes implemented controls and external gaps.',
    ]
    md_path.write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    SUPERVISOR.mkdir(parents=True, exist_ok=True)
    validation = load_validation()

    challenges_pdf = DOCS / 'Challenges_Supervisor_Detail_March_2026.pdf'
    dossier_pdf = DOCS / 'Technical_Dossier_Supervisor_March_2026.pdf'
    summary_md = SUPERVISOR / 'SUPERVISOR_REPORT_SUMMARY.md'

    challenge_report(challenges_pdf, validation)
    technical_dossier(dossier_pdf, validation)
    write_markdown_summary(summary_md, validation)

    print(f'Created: {challenges_pdf}')
    print(f'Created: {dossier_pdf}')
    print(f'Created: {summary_md}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
