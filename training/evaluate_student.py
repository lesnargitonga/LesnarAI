"""Evaluation harness for student policy network.

Replays teacher telemetry CSVs through the trained student model and reports
accuracy metrics against the teacher's commands. Produces per-metric scores
and an overall "deployment readiness" grade.

Usage:
    python training/evaluate_student.py \
        --model models/student_px4_god.pt \
        --data dataset/px4_teacher/telemetry_god.csv
"""

import argparse
import csv
import glob
import json
import math
import os
from pathlib import Path

import numpy as np
import torch

from train_student_px4 import (
    ENRICHED_SCALAR_KEYS,
    ENRICHED_FEATURE_DIM,
    LEGACY_FEATURE_DIM,
    StudentNet,
    _safe_float,
)


def load_eval_data(csv_paths: list[Path], enriched: bool):
    """Load features + teacher labels from CSV(s). Returns (X, Y_teacher, threats)."""
    X, Y, threats = [], [], []
    for csv_path in csv_paths:
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        lidar = json.loads(row["lidar_json"])
                    except (json.JSONDecodeError, KeyError):
                        continue
                    if not isinstance(lidar, list) or len(lidar) == 0:
                        continue
                    lidar = [float(v) for v in lidar]

                    yaw_deg = _safe_float(row, "yaw")
                    yaw_rad = math.radians(yaw_deg)

                    if enriched:
                        scalars = [_safe_float(row, k) for k in ENRICHED_SCALAR_KEYS]
                        feat = lidar + [math.sin(yaw_rad), math.cos(yaw_rad)] + scalars
                    else:
                        feat = lidar + [_safe_float(row, "rel_alt"), math.sin(yaw_rad), math.cos(yaw_rad)]

                    target = [
                        _safe_float(row, "cmd_vx"),
                        _safe_float(row, "cmd_vy"),
                        _safe_float(row, "cmd_vz"),
                        _safe_float(row, "cmd_yaw"),
                    ]
                    threat = _safe_float(row, "geom_threat")
                    X.append(feat)
                    Y.append(target)
                    threats.append(threat)
        except Exception as exc:
            print(f"[WARN] Skipping {csv_path}: {exc}")
    return (
        np.array(X, dtype=np.float32),
        np.array(Y, dtype=np.float32),
        np.array(threats, dtype=np.float32),
    )


def evaluate_model(model_path: str, csv_paths: list[Path], batch_size: int = 512):
    """Run full evaluation and return metrics dict."""
    ckpt = torch.load(model_path, map_location="cpu", weights_only=False)
    enriched = ckpt.get("enriched", True)
    in_dim = ckpt.get("in_dim", ENRICHED_FEATURE_DIM if enriched else LEGACY_FEATURE_DIM)

    net = StudentNet(in_dim=in_dim)
    net.load_state_dict(ckpt["state_dict"])
    net.eval()

    X, Y_teacher, threats = load_eval_data(csv_paths, enriched)
    if len(X) == 0:
        raise ValueError("No valid evaluation rows found")

    X_t = torch.tensor(X, dtype=torch.float32)
    Y_t = torch.tensor(Y_teacher, dtype=torch.float32)

    # Batch inference
    preds = []
    with torch.no_grad():
        for i in range(0, len(X_t), batch_size):
            batch = X_t[i:i + batch_size]
            preds.append(net(batch))
    Y_pred = torch.cat(preds, dim=0).numpy()

    # Overall MAE per output channel
    abs_err = np.abs(Y_pred - Y_teacher)
    mae_vx = float(np.mean(abs_err[:, 0]))
    mae_vy = float(np.mean(abs_err[:, 1]))
    mae_vz = float(np.mean(abs_err[:, 2]))
    mae_yaw = float(np.mean(abs_err[:, 3]))
    mae_overall = float(np.mean(abs_err))

    # MSE
    mse_overall = float(np.mean((Y_pred - Y_teacher) ** 2))

    # Velocity direction agreement (cosine similarity of XY commands)
    teacher_xy = Y_teacher[:, :2]
    pred_xy = Y_pred[:, :2]
    teacher_norm = np.linalg.norm(teacher_xy, axis=1, keepdims=True) + 1e-8
    pred_norm = np.linalg.norm(pred_xy, axis=1, keepdims=True) + 1e-8
    cos_sim = np.sum((teacher_xy / teacher_norm) * (pred_xy / pred_norm), axis=1)
    direction_agreement = float(np.mean(cos_sim))

    # Speed magnitude error
    teacher_speed = np.linalg.norm(teacher_xy, axis=1)
    pred_speed = np.linalg.norm(pred_xy, axis=1)
    speed_mae = float(np.mean(np.abs(teacher_speed - pred_speed)))

    # Collision proxy: how often student goes faster than teacher when near obstacles
    high_threat_mask = threats > 0.5
    collision_proxy = 0.0
    n_high = int(np.sum(high_threat_mask))
    if n_high > 0:
        teacher_threat_speed = teacher_speed[high_threat_mask]
        pred_threat_speed = pred_speed[high_threat_mask]
        # Fraction where student speed exceeds teacher speed by > 0.5 m/s near obstacles
        collision_proxy = float(np.mean(pred_threat_speed > teacher_threat_speed + 0.5))

    # Avoidance accuracy: MAE in high-threat regions
    avoidance_mae = float(np.mean(abs_err[high_threat_mask])) if n_high > 0 else 0.0

    # Cruise accuracy: MAE in low-threat regions
    low_threat_mask = threats < 0.1
    n_low = int(np.sum(low_threat_mask))
    cruise_mae = float(np.mean(abs_err[low_threat_mask])) if n_low > 0 else 0.0

    # Deployment grade
    grade = "A"
    if mae_overall > 0.8 or collision_proxy > 0.15:
        grade = "F"
    elif mae_overall > 0.5 or collision_proxy > 0.08:
        grade = "D"
    elif mae_overall > 0.3 or collision_proxy > 0.04:
        grade = "C"
    elif mae_overall > 0.15 or collision_proxy > 0.02:
        grade = "B"

    metrics = {
        "model_path": model_path,
        "n_rows": len(X),
        "n_high_threat": n_high,
        "n_low_threat": n_low,
        "enriched": enriched,
        "in_dim": in_dim,
        "train_val_loss": ckpt.get("best_val_loss"),
        "mae_overall": round(mae_overall, 5),
        "mse_overall": round(mse_overall, 5),
        "mae_vx": round(mae_vx, 5),
        "mae_vy": round(mae_vy, 5),
        "mae_vz": round(mae_vz, 5),
        "mae_yaw": round(mae_yaw, 5),
        "direction_agreement": round(direction_agreement, 4),
        "speed_mae": round(speed_mae, 5),
        "collision_proxy_rate": round(collision_proxy, 4),
        "avoidance_mae": round(avoidance_mae, 5),
        "cruise_mae": round(cruise_mae, 5),
        "deployment_grade": grade,
    }
    return metrics


def main():
    ap = argparse.ArgumentParser(description="Evaluate trained student against teacher telemetry.")
    data_root = (os.environ.get("LESNAR_DATA_ROOT") or "dataset").strip() or "dataset"
    ap.add_argument("--model", type=str, required=True, help="Path to trained student .pt checkpoint")
    ap.add_argument("--data", type=str, nargs="+",
                    default=[str(Path(data_root) / "px4_teacher" / "telemetry_god.csv")],
                    help="One or more CSV paths or glob patterns")
    ap.add_argument("--report", type=str, default="", help="Optional JSON report output path")
    args = ap.parse_args()

    csv_paths = []
    for pattern in args.data:
        expanded = glob.glob(pattern, recursive=True)
        if expanded:
            csv_paths.extend(Path(p) for p in sorted(expanded))
        else:
            csv_paths.append(Path(pattern))

    print(f"Evaluating {args.model} against {len(csv_paths)} CSV file(s)...")
    metrics = evaluate_model(args.model, csv_paths)

    print("\n" + "=" * 60)
    print("  STUDENT EVALUATION REPORT")
    print("=" * 60)
    print(f"  Model:        {metrics['model_path']}")
    print(f"  Rows:         {metrics['n_rows']:,}")
    print(f"  Features:     {metrics['in_dim']} ({'enriched' if metrics['enriched'] else 'legacy'})")
    print(f"  Train ValLoss:{metrics['train_val_loss']:.5f}" if metrics['train_val_loss'] else "")
    print("-" * 60)
    print(f"  MAE (overall): {metrics['mae_overall']:.5f}")
    print(f"  MSE (overall): {metrics['mse_overall']:.5f}")
    print(f"  MAE vx/vy/vz/yaw: {metrics['mae_vx']:.5f} / {metrics['mae_vy']:.5f} / {metrics['mae_vz']:.5f} / {metrics['mae_yaw']:.5f}")
    print(f"  Direction agreement: {metrics['direction_agreement']:.4f}  (1.0 = perfect)")
    print(f"  Speed MAE:     {metrics['speed_mae']:.5f}")
    print("-" * 60)
    print(f"  High-threat rows:    {metrics['n_high_threat']:,}")
    print(f"  Avoidance MAE:       {metrics['avoidance_mae']:.5f}")
    print(f"  Collision proxy rate: {metrics['collision_proxy_rate']:.4f}")
    print(f"  Cruise MAE:          {metrics['cruise_mae']:.5f}")
    print("=" * 60)
    print(f"  DEPLOYMENT GRADE: {metrics['deployment_grade']}")
    print("=" * 60 + "\n")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        with open(report_path, "w", encoding="utf-8") as f:
            _json.dump(metrics, f, indent=2)
        print(f"Report saved to {args.report}")


if __name__ == "__main__":
    main()
