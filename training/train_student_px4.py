import argparse
import csv
import glob
import json
import math
import os
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler


# ── Feature schema ───────────────────────────────────────────────────────────
# The enriched feature vector uses all meaningful columns from the 58-col CSV.
# Legacy mode (--legacy) falls back to the original 75-dim LIDAR-only features.

ENRICHED_SCALAR_KEYS = [
    # Scalars appended after 72 LIDAR beams
    "rel_alt",          # 1
    # yaw is encoded as sin/cos → 2
    "front_lidar_min",  # 1
    "cross_track_m",    # 1
    "heading_error_deg",# 1
    "sideslip_deg",     # 1
    "progress_mps",     # 1
    "geom_clearance_m", # 1
    "geom_threat",      # 1
    "tilt_target_deg",  # 1
    "roll_deg",         # 1
    "pitch_deg",        # 1
    "roll_rate_dps",    # 1
    "pitch_rate_dps",   # 1
    "yaw_rate_dps",     # 1
    "ground_speed_mps", # 1
    "distance_to_goal_m", # 1
    "wind_north_mps",   # 1
    "wind_east_mps",    # 1
]
# Total enriched: 72 (LIDAR) + 2 (sin/cos yaw) + len(ENRICHED_SCALAR_KEYS) = 93
ENRICHED_FEATURE_DIM = 72 + 2 + len(ENRICHED_SCALAR_KEYS)
LEGACY_FEATURE_DIM = 75  # 72 LIDAR + rel_alt + sin(yaw) + cos(yaw)


def _safe_float(row: dict, key: str, default: float = 0.0) -> float:
    try:
        v = row.get(key, "")
        if v == "" or v is None:
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


class Px4TeacherDataset(Dataset):
    """Multi-file, enriched-feature dataset with threat-weighted sampling support."""

    def __init__(self, csv_paths: list[Path], enriched: bool = True):
        X, Y, W = [], [], []
        for csv_path in csv_paths:
            self._load_csv(csv_path, X, Y, W, enriched)
        if not X:
            raise ValueError(f"No valid rows found in {len(csv_paths)} CSV file(s)")
        self.X = torch.tensor(np.array(X), dtype=torch.float32)
        self.Y = torch.tensor(np.array(Y), dtype=torch.float32)
        self.weights = np.array(W, dtype=np.float64)
        self.enriched = enriched

    def _load_csv(self, csv_path: Path, X: list, Y: list, W: list, enriched: bool):
        rows = []
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
        except Exception as exc:
            print(f"[WARN] Skipping {csv_path}: {exc}")
            return

        has_enriched = "geom_threat" in (rows[0] if rows else {})
        use_enriched = enriched and has_enriched

        for row in rows:
            try:
                lidar = json.loads(row["lidar_json"])
            except (json.JSONDecodeError, KeyError):
                continue
            if not isinstance(lidar, list) or len(lidar) == 0:
                continue
            lidar = [float(v) for v in lidar]

            yaw_deg = _safe_float(row, "yaw")
            yaw_rad = math.radians(yaw_deg)

            if use_enriched:
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

            # Compute sample weight: avoidance manoeuvres (high geom_threat)
            # are weighted up so the student doesn't ignore obstacles.
            threat = _safe_float(row, "geom_threat") if has_enriched else 0.0
            weight = 1.0 + 4.0 * min(threat, 1.0)  # 1× cruise → 5× critical avoidance

            X.append(feat)
            Y.append(target)
            W.append(weight)

    def __len__(self):
        return self.X.shape[0]

    def __getitem__(self, idx):
        return self.X[idx], self.Y[idx]

    def make_weighted_sampler(self) -> WeightedRandomSampler:
        """Return a sampler that oversamples high-threat rows."""
        return WeightedRandomSampler(self.weights, num_samples=len(self.weights), replacement=True)


class StudentNet(nn.Module):
    """Sensor-fusion student policy network.

    Enriched mode: 93 → 128 → 128 → 64 → 4
    Legacy mode:   75 → 64 → 64 → 4
    """
    def __init__(self, in_dim=ENRICHED_FEATURE_DIM, out_dim=4):
        super().__init__()
        if in_dim <= LEGACY_FEATURE_DIM:
            self.net = nn.Sequential(
                nn.Linear(in_dim, 64), nn.ReLU(),
                nn.Linear(64, 64), nn.ReLU(),
                nn.Linear(64, out_dim),
            )
        else:
            self.net = nn.Sequential(
                nn.Linear(in_dim, 128), nn.ReLU(), nn.Dropout(0.1),
                nn.Linear(128, 128), nn.ReLU(), nn.Dropout(0.1),
                nn.Linear(128, 64), nn.ReLU(),
                nn.Linear(64, out_dim),
            )

    def forward(self, x):
        return self.net(x)


def evaluate(net, dl, device, loss_fn):
    """Run a single evaluation pass over the dataloader."""
    net.eval()
    total_loss, n = 0.0, 0
    with torch.no_grad():
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            pred = net(xb)
            total_loss += loss_fn(pred, yb).item() * xb.size(0)
            n += xb.size(0)
    return total_loss / max(1, n)


def main():
    ap = argparse.ArgumentParser(description="Train student policy from teacher telemetry CSVs.")
    data_root = (os.environ.get("LESNAR_DATA_ROOT") or "dataset").strip() or "dataset"
    ap.add_argument("--data", type=str, nargs="+",
                    default=[str(Path(data_root) / "px4_teacher" / "telemetry_god.csv")],
                    help="One or more CSV paths or glob patterns (e.g. runs/*/telemetry_live_0.csv)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--bs", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--val-split", type=float, default=0.1, help="Validation fraction")
    ap.add_argument("--out", type=str, default=str(Path("models/student_px4_god.pt")))
    ap.add_argument("--legacy", action="store_true", help="Use legacy 75-dim feature vector (LIDAR-only)")
    ap.add_argument("--weighted", action="store_true", default=True,
                    help="Oversample high-threat avoidance rows (default: on)")
    ap.add_argument("--no-weighted", action="store_false", dest="weighted")
    args = ap.parse_args()

    # Resolve globs
    csv_paths = []
    for pattern in args.data:
        expanded = glob.glob(pattern, recursive=True)
        if expanded:
            csv_paths.extend(Path(p) for p in sorted(expanded))
        else:
            csv_paths.append(Path(pattern))
    print(f"Loading {len(csv_paths)} CSV file(s)...")

    enriched = not args.legacy
    ds = Px4TeacherDataset(csv_paths, enriched=enriched)
    in_dim = ds.X.shape[1]
    print(f"Dataset: {len(ds)} rows, {in_dim} features per row ({'enriched' if enriched else 'legacy'})")

    # Train/val split
    n_val = max(1, int(len(ds) * args.val_split))
    n_train = len(ds) - n_val
    train_ds, val_ds = torch.utils.data.random_split(ds, [n_train, n_val])

    if args.weighted:
        train_weights = ds.weights[train_ds.indices]
        sampler = WeightedRandomSampler(train_weights, num_samples=len(train_weights), replacement=True)
        train_dl = DataLoader(train_ds, batch_size=args.bs, sampler=sampler)
    else:
        train_dl = DataLoader(train_ds, batch_size=args.bs, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=args.bs, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = StudentNet(in_dim=in_dim).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    loss_fn = nn.MSELoss()

    best_val = float("inf")
    best_state = None

    for epoch in range(args.epochs):
        net.train()
        losses = []
        for xb, yb in train_dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            pred = net(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            losses.append(loss.item())
        scheduler.step()

        val_loss = evaluate(net, val_dl, device, loss_fn)
        train_loss = np.mean(losses)
        lr_now = scheduler.get_last_lr()[0]
        print(f"Epoch {epoch+1:3d}/{args.epochs} | train={train_loss:.5f} val={val_loss:.5f} lr={lr_now:.2e}")

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.clone() for k, v in net.state_dict().items()}

    # Save best model
    if best_state is not None:
        net.load_state_dict(best_state)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    save_data = {
        "state_dict": net.state_dict(),
        "in_dim": in_dim,
        "out_dim": 4,
        "enriched": enriched,
        "best_val_loss": best_val,
        "scalar_keys": ENRICHED_SCALAR_KEYS if enriched else [],
    }
    torch.save(save_data, args.out)
    print(f"Saved student model to {args.out} (val_loss={best_val:.5f}, in_dim={in_dim})")


if __name__ == "__main__":
    main()
