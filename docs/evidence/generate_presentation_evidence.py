#!/usr/bin/env python3
import argparse
import datetime as dt
import subprocess
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def sh(repo_root: Path, cmd: list[str]) -> str:
    try:
        out = subprocess.check_output(cmd, cwd=repo_root, text=True)
        return out.strip()
    except Exception:
        return "unknown"


def draw_wrapped_text(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, line_height: float = 14):
    words = text.split()
    line = ""
    cursor_y = y
    for word in words:
        candidate = (line + " " + word).strip()
        if c.stringWidth(candidate, "Helvetica", 10) <= max_width:
            line = candidate
        else:
            c.drawString(x, cursor_y, line)
            cursor_y -= line_height
            line = word
    if line:
        c.drawString(x, cursor_y, line)
        cursor_y -= line_height
    return cursor_y


def build_pack_pdf(repo_root: Path, out_pdf: Path, screenshot: Path, video_dir: Path):
    commit = sh(repo_root, ["git", "rev-parse", "HEAD"])[:10]
    branch = sh(repo_root, ["git", "branch", "--show-current"])
    remote = sh(repo_root, ["git", "remote", "get-url", "origin"])
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 60, "Operation Sentinel - Presentation Evidence Pack")

    c.setFont("Helvetica", 10)
    c.drawString(50, height - 85, f"Generated: {generated_at}")
    c.drawString(50, height - 100, f"Branch: {branch}")
    c.drawString(50, height - 115, f"Commit: {commit}")
    c.drawString(50, height - 130, f"Origin: {remote}")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 165, "Proof Index")
    c.setFont("Helvetica", 10)
    proof_lines = [
        "1) Architecture Proof: docs/architecture.pdf",
        "2) ROS2 Node Graph Proof: docs/ros2_node_graph.pdf",
        "3) Challenges & Engineering Tradeoffs: docs/challenges_report.pdf",
        "4) Visual Simulation Evidence: docs/visual_evidence.png",
        "5) Runtime Logs (FALCON metrics): training/px4_teacher_collect_gz.py output",
        "6) CI Proof Link: GitHub Actions run page for current commit",
    ]
    y = height - 185
    for line in proof_lines:
        c.drawString(60, y, line)
        y -= 16

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y - 8, "Screenshot Evidence")
    y -= 24

    if screenshot.exists():
        img = ImageReader(str(screenshot))
        iw, ih = img.getSize()
        max_w = width - 100
        max_h = 250
        scale = min(max_w / iw, max_h / ih)
        draw_w, draw_h = iw * scale, ih * scale
        c.drawImage(img, 50, y - draw_h, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
        y = y - draw_h - 18
    else:
        c.setFont("Helvetica", 10)
        c.drawString(60, y, "Screenshot file not found. Expected: docs/visual_evidence.png")
        y -= 20

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Video Evidence Slots")
    y -= 18
    c.setFont("Helvetica", 10)
    if video_dir.exists():
        videos = sorted([p.name for p in video_dir.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}])
    else:
        videos = []

    if videos:
        for vid in videos[:12]:
            c.drawString(60, y, f"- {vid}")
            y -= 14
            if y < 70:
                c.showPage()
                y = height - 60
                c.setFont("Helvetica", 10)
    else:
        y = draw_wrapped_text(
            c,
            "No video files detected yet. Place demo recordings under docs/evidence/videos/, "
            "then rerun this script to include filenames in this PDF.",
            60,
            y,
            width - 110,
            14,
        )

    c.save()


def build_checklist_pdf(repo_root: Path, out_pdf: Path):
    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 60, "Presentation Proof Checklist")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 82, f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    checklist = [
        "Backend health endpoint screenshot (http://localhost:5000/api/health)",
        "Frontend dashboard screenshot (http://localhost:3000)",
        "Adminer telemetry screenshot (http://localhost:8080)",
        "Gazebo world screenshot with active drone",
        "PX4 terminal screenshot showing SITL ready",
        "Teacher terminal screenshot showing FALCON metrics",
        "Video 1: Full startup sequence (WSL-native)",
        "Video 2: Autonomous route following with obstacle avoidance",
        "Video 3: API command demo (takeoff, goto, land)",
        "Video 4: Safety intervention / emergency stop",
    ]

    c.setFont("Helvetica", 11)
    y = height - 120
    for item in checklist:
        c.rect(55, y - 4, 10, 10)
        y = draw_wrapped_text(c, item, 72, y + 4, width - 130, 16)
        y -= 4
        if y < 80:
            c.showPage()
            y = height - 60
            c.setFont("Helvetica", 11)

    c.save()


def build_issues_pdf(repo_root: Path, out_pdf: Path):
    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    commit = sh(repo_root, ["git", "rev-parse", "HEAD"])[:10]
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 60, "Issues Encountered & Resolutions (March 2026)")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 82, f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(50, height - 98, f"Commit context: {commit}")

    issues = [
        (
            "WSL path and shell mismatch",
            "Some start tasks used Windows PowerShell commands in Linux/WSL context, causing startup failures.",
            "Standardized startup on native WSL paths (`~/workspace/LesnarAI`) and bash-based launch sequence.",
        ),
        (
            "PX4 path mismatch",
            "PX4 expected at workspace path but actual source was under `~/PX4-Autopilot`.",
            "Updated launch flow to start SITL from `~/PX4-Autopilot` and validate process health.",
        ),
        (
            "MAVSDK UDP bind conflict on 14540",
            "Teacher connection intermittently failed with `bind error: Address in use`.",
            "Performed hard-stop cleanup of stale processes and restarted stack in strict dependency order.",
        ),
        (
            "Frontend build blocker in dashboard",
            "Dashboard UI had JSX syntax imbalance and an undefined callback, stopping compile.",
            "Fixed JSX closure and removed undefined listener usage so frontend compiles and serves on port 3000.",
        ),
        (
            "Drone sideways/erratic behavior",
            "Controller exhibited unstable progress and non-forward dominant motion around obstacles.",
            "Implemented frame-safe conversions, front-sector obstacle logic, geometry-aware avoidance, and tilt-limited lateral control in teacher bridge.",
        ),
        (
            "Post-push CI failures",
            "GitHub Actions reported lint/build failures despite successful push.",
            "Push confirmed successful; CI issues isolated for follow-up lint/build remediation commit.",
        ),
    ]

    y = height - 130
    c.setFont("Helvetica", 10)
    for index, (title, problem, resolution) in enumerate(issues, start=1):
        c.setFont("Helvetica-Bold", 11)
        y = draw_wrapped_text(c, f"{index}. {title}", 50, y, width - 90, 15)
        c.setFont("Helvetica", 10)
        y = draw_wrapped_text(c, f"Issue: {problem}", 62, y, width - 105, 14)
        y = draw_wrapped_text(c, f"Resolution: {resolution}", 62, y, width - 105, 14)
        y -= 8
        if y < 90:
            c.showPage()
            y = height - 60

    c.save()


def main():
    parser = argparse.ArgumentParser(description="Generate presentation-ready evidence PDFs")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    docs_dir = repo_root / "docs"
    evidence_dir = docs_dir / "evidence"
    videos_dir = evidence_dir / "videos"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    pack_pdf = docs_dir / "Presentation_Evidence_Pack.pdf"
    checklist_pdf = docs_dir / "Presentation_Proof_Checklist.pdf"
    issues_pdf = docs_dir / "Issues_Encountered_March_2026.pdf"
    screenshot = docs_dir / "visual_evidence.png"

    build_pack_pdf(repo_root, pack_pdf, screenshot, videos_dir)
    build_checklist_pdf(repo_root, checklist_pdf)
    build_issues_pdf(repo_root, issues_pdf)

    print(f"Created: {pack_pdf}")
    print(f"Created: {checklist_pdf}")
    print(f"Created: {issues_pdf}")


if __name__ == "__main__":
    main()
