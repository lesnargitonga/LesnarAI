#!/usr/bin/env python3
"""Generate supervisor PDFs without validation framing language."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / 'docs'


def styles_bundle():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleX', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#0B2A4A')))
    styles.add(ParagraphStyle(name='H2X', parent=styles['Heading2'], fontSize=13, leading=16, textColor=colors.HexColor('#123A63')))
    styles.add(ParagraphStyle(name='H3X', parent=styles['Heading3'], fontSize=11, leading=14, textColor=colors.HexColor('#1D4E78')))
    styles.add(ParagraphStyle(name='BodyX', parent=styles['BodyText'], fontSize=10, leading=14, alignment=TA_LEFT))
    return styles


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(18 * mm, 10 * mm, 'Operation Sentinel - Supervisor Documentation')
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f'Page {doc.page}')
    canvas.restoreState()


def add_header(story, styles, title, subtitle):
    story.append(Paragraph(title, styles['TitleX']))
    story.append(Spacer(1, 4))
    story.append(Paragraph(subtitle, styles['BodyX']))
    story.append(Spacer(1, 10))


def build_challenges_pdf(out_path: Path):
    styles = styles_bundle()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story = []

    add_header(
        story,
        styles,
        'Supervisor Challenges Report',
        'This document intentionally includes only challenges: constraints outside direct control and active workstreams in progress.',
    )

    story.append(Paragraph('1) Purpose of This Report', styles['H2X']))
    story.append(Paragraph(
        'This report is limited to outstanding challenge areas so supervisory decisions can focus on risk, constraints, and support needs. '
        'Resolved items are intentionally excluded from this document.',
        styles['BodyX'],
    ))

    story.append(Spacer(1, 8))
    story.append(Paragraph('2) Challenges Outside Direct Team Control', styles['H2X']))
    constraints = [
        (
            'GPU power and thermal variability',
            'Observed impact: fluctuating inference and rendering timing under changing host load can alter controller smoothness, latency, and repeatability.',
            'Why this is hard to control: power/thermal behavior and competing host load are infrastructure-level conditions outside application logic.',
            'Current status: managed partially with conservative profiles, but not fully eliminable at software layer.',
        ),
        (
            'Simulator scheduling lag (Gazebo/PX4)',
            'Observed impact: stale telemetry windows, delayed command confirmation, and variable run-to-run behavior in the same scenario.',
            'Why this is hard to control: simulation scheduler behavior depends on host timing and process pressure, not only code correctness.',
            'Current status: reduced via safeguards, but full determinism still not guaranteed.',
        ),
        (
            'Host process contention',
            'Observed impact: duplicate/stale processes can produce false network symptoms and inconsistent operator behavior.',
            'Why this is hard to control: process hygiene is partly an operational discipline issue, especially under rapid demo/test cycles.',
            'Current status: guarded startup reduces this risk but cannot fully prevent manual misuse.',
        ),
        (
            'Cross-machine runtime heterogeneity',
            'Observed impact: behavior differs across machines because of driver versions, thermal state, and background utilization.',
            'Why this is hard to control: environment parity across all machines is rarely perfect in practice.',
            'Current status: requires baseline machine profile and controlled test windows for fair comparison.',
        ),
    ]
    for title, impact, controls, risk in constraints:
        story.append(Paragraph(title, styles['H3X']))
        story.append(Paragraph(f'• {impact}', styles['BodyX']))
        story.append(Paragraph(f'• {controls}', styles['BodyX']))
        story.append(Paragraph(f'• {risk}', styles['BodyX']))
        if title == 'GPU power and thermal variability':
            story.append(Paragraph('• Additional detail: model inference and sensor processing share compute windows with simulation/render pipelines, which amplifies frame-time jitter when GPU clocks down under thermal pressure.', styles['BodyX']))
            story.append(Paragraph('• What we need: a dedicated GPU test profile (high-performance power mode, stable cooling, minimal background GPU tasks), and where possible a workstation-class NVIDIA GPU for final benchmark and demo sessions.', styles['BodyX']))
            story.append(Paragraph('• Suggested operational controls: pre-demo thermal warm-up check, fixed driver version, and reserved machine window to keep utilization predictable.', styles['BodyX']))
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 10))
    story.append(Paragraph('3) Challenges Currently Being Worked On', styles['H2X']))
    in_progress = [
        'Telemetry continuity challenge: obtaining uninterrupted live telemetry throughout full measurement windows.',
        'Stability under dynamic load challenge: maintaining consistent behavior under simulator and host load spikes.',
        'PID refinement challenge: converging to robust gains that remain stable across multiple environment profiles.',
        'Quantitative evidence challenge: producing repeated, comparable, supervisor-ready measurement sets under fixed conditions.',
        'Demo reproducibility challenge: guaranteeing same startup/run behavior under strict time pressure before presentation.',
    ]
    for x in in_progress:
        story.append(Paragraph(f'• {x}', styles['BodyX']))

    story.append(Spacer(1, 8))
    story.append(Paragraph('4) Dependencies Needed to Close the Challenge Gap', styles['H2X']))
    dependencies = [
        'Dedicated high-performance machine window for controlled runs and supervisor demos.',
        'Strict runbook adherence for startup order and process isolation during measurement sessions.',
        'Approval to use repeated-run criteria for assessment (instead of single-run judgments).',
        'Time allocation for iterative control tuning cycles before final acceptance runs.',
    ]
    for x in dependencies:
        story.append(Paragraph(f'• {x}', styles['BodyX']))

    story.append(Spacer(1, 8))
    story.append(Paragraph('5) Supervisor Decision Focus', styles['H2X']))
    story.append(Paragraph(
        'The key supervisory decision is not whether challenges exist, but whether the current mitigation path, required dependencies, '
        'and staged closure plan are acceptable for submission and subsequent milestone review.',
        styles['BodyX'],
    ))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def build_full_doc_pdf(out_path: Path):
    styles = styles_bundle()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story = []

    add_header(
        story,
        styles,
        'Supervisor App Documentation',
        'A professional application document describing purpose, capabilities, AI-driven control model, operational readiness, and next actions.',
    )

    story.append(Paragraph('A) Application Overview', styles['H2X']))
    story.append(Paragraph(
        'Operation Sentinel is an autonomous drone mission platform that combines secure supervision, real-time telemetry visibility, and AI-driven mission behavior. '
        'The application is designed to support practical mission execution in constrained environments while maintaining operator oversight and safety boundaries.',
        styles['BodyX'],
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph('B) Primary Objectives', styles['H2X']))
    objectives = [
        'Enable supervised autonomous navigation with improving reliability across repeated runs.',
        'Provide clear operational awareness through continuous telemetry and health state visibility.',
        'Enforce controlled access and accountability for command operations.',
        'Support repeatable testing and measurable progress for supervisor evaluation.',
    ]
    for item in objectives:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Spacer(1, 6))
    story.append(Paragraph('C) Stakeholders and Intended Users', styles['H2X']))
    stakeholders = [
        'Project supervisor: evaluates readiness, risk posture, and milestone alignment.',
        'Mission operators: monitor status, execute approved commands, and respond to alerts.',
        'Engineering team: maintains AI behavior quality, deployment reliability, and safety boundaries.',
        'Review panel and assessors: require clear evidence of capability, limitations, and professional controls.',
    ]
    for item in stakeholders:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Spacer(1, 6))
    story.append(Paragraph('D) User-Facing Capabilities', styles['H2X']))
    operator_value = [
        'Unified control interface for monitoring flight state and issuing mission commands.',
        'Live status and link posture indicators for early response to degraded conditions.',
        'Session-based secure access to reduce unauthorized control exposure.',
        'Operational logging support for review and accountability.',
    ]
    for item in operator_value:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Spacer(1, 6))
    story.append(Paragraph('E) AI-Driven Final Brain', styles['H2X']))
    story.append(Paragraph(
        'The final decision layer is AI-driven. The system is intended to use learned and adaptive logic as the primary mission brain for path selection, response behavior, and dynamic adjustment under changing conditions. '
        'Rule-based safeguards remain in place for safety boundaries, but mission intelligence and behavior adaptation are centered on AI execution.',
        styles['BodyX'],
    ))

    story.append(Paragraph(
        'AI responsibility in this project is therefore explicit: it is not an auxiliary module, but the core autonomy decision component expected to produce resilient behavior in dynamic mission contexts.',
        styles['BodyX'],
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph('F) System Scope and Boundaries', styles['H2X']))
    scope = [
        'In scope: simulation-integrated mission control, telemetry visibility, AI behavior iteration, and secure operator workflows.',
        'In scope: reproducibility and stability improvements under defined runtime conditions.',
        'Out of scope: organizational enterprise controls that require infrastructure beyond repository-level implementation.',
    ]
    for item in scope:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Spacer(1, 6))
    story.append(Paragraph('G) Mission Workflow Summary', styles['H2X']))
    workflow = [
        'Pre-mission: environment and service readiness checks, operator access verification, and mission profile selection.',
        'Execution: AI-driven navigation with supervised command oversight and continuous telemetry observation.',
        'Post-mission: run review, operational notes, issue logging, and corrective action planning.',
    ]
    for item in workflow:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Paragraph('H) Functional Architecture Summary', styles['H2X']))
    story.append(Paragraph(
        'The application consists of a user interface layer, a backend command/policy layer, and an autonomy execution layer. '
        'The interface supports supervision, the backend governs control/security flow, and the autonomy layer executes AI-driven mission behavior with safety constraints.',
        styles['BodyX'],
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph('I) Security and Operational Readiness', styles['H2X']))
    sec = [
        'Containerized backend services support more repeatable deployment behavior.',
        'Session authentication and role-aware request handling reduce unauthorized control risk.',
        'Secure logging and audit-oriented event records support accountability and review.',
        'Security checks are integrated into deployment workflow for key and policy consistency.',
    ]
    for x in sec:
        story.append(Paragraph(f'• {x}', styles['BodyX']))

    story.append(Spacer(1, 6))
    story.append(Paragraph('J) Success Criteria for Supervisor Acceptance', styles['H2X']))
    acceptance = [
        'Stable startup sequence and controlled mission execution with minimal manual recovery.',
        'Clear operator visibility of mission health, status, and command outcomes.',
        'Demonstrable AI-driven behavior with safety-boundary compliance across repeated runs.',
        'Documented limitations and mitigation approach reviewed and accepted by supervisor.',
    ]
    for item in acceptance:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Spacer(1, 6))
    story.append(Paragraph('K) Operational Conditions and Dependencies', styles['H2X']))
    env = [
        'Performance depends on controlled host load and stable simulation timing conditions.',
        'Deployment quality depends on disciplined startup order and clean runtime process state.',
        'Supervisor support is required for dedicated windows when producing final submission evidence.',
    ]
    for item in env:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Spacer(1, 8))
    story.append(Paragraph('L) Governance, Risks, and Follow-Up Actions', styles['H2X']))
    governance = [
        'Governance posture: maintain change traceability for configuration and behavior tuning decisions.',
        'Risk posture: treat infrastructure variability as an explicit acceptance constraint until dedicated runtime resources are secured.',
        'Follow-up actions: complete repeated-run evidence pack, finalize tuned control profile, and submit supervisor sign-off checklist.',
    ]
    for item in governance:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    story.append(Spacer(1, 8))
    story.append(Paragraph('M) Detailed Review Points', styles['H2X']))
    detailed_points = [
        'AI behavior detail: verify how the autonomy layer selects actions under changing mission context and whether observed behavior remains inside defined safety limits.',
        'Telemetry detail: check continuity, freshness, and gap frequency during full mission windows rather than short snapshots.',
        'Runtime stability detail: compare behavior across repeated runs under the same environment profile to identify variance sources.',
        'Operator workflow detail: confirm command intent, system response, and audit records remain consistent and traceable end-to-end.',
        'Dependency detail: review whether GPU profile, cooling, and process isolation conditions were controlled during evidence collection.',
        'Risk closure detail: ensure each open challenge has a named mitigation action, owner, and expected verification step.',
    ]
    for item in detailed_points:
        story.append(Paragraph(f'• {item}', styles['BodyX']))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> int:
    out1 = DOCS / 'Supervisor_Challenges_and_Blockers_March_2026.pdf'
    out2 = DOCS / 'Supervisor_Complete_Technical_Documentation_March_2026.pdf'
    build_challenges_pdf(out1)
    build_full_doc_pdf(out2)
    print(f'Created: {out1}')
    print(f'Created: {out2}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
