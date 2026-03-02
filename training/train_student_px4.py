import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader


class Px4TeacherDataset(Dataset):
    def __init__(self, csv_path: Path):
        rows = []
        with open(csv_path, "r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                rows.append(row)
        X = []
        Y = []
        for row in rows:
            # God-Mode schema:
            # timestamp, lat, lon, rel_alt, vx, vy, vz, yaw,
            # cmd_vx, cmd_vy, cmd_vz, cmd_yaw,
            # lidar_min, lidar_json, goal_x, goal_y

            # Parse lidar vector
            lidar = json.loads(row["lidar_json"])
            # Expect 72 beams (360° / 5°)
            if not isinstance(lidar, list) or len(lidar) == 0:
                continue

            lidar = [float(v) for v in lidar]

            rel_alt = float(row["rel_alt"])
            yaw_deg = float(row["yaw"])
            yaw_rad = math.radians(yaw_deg)

            # Features: lidar + rel_alt + sin(yaw) + cos(yaw)
            feat = lidar + [rel_alt, math.sin(yaw_rad), math.cos(yaw_rad)]

            cmd_vx = float(row["cmd_vx"])
            cmd_vy = float(row["cmd_vy"])
            cmd_vz = float(row["cmd_vz"])
            cmd_yaw = float(row["cmd_yaw"])

            X.append(feat)
            Y.append([cmd_vx, cmd_vy, cmd_vz, cmd_yaw])
        self.X = torch.tensor(np.array(X), dtype=torch.float32)
        self.Y = torch.tensor(np.array(Y), dtype=torch.float32)

    def __len__(self):
        return self.X.shape[0]

    def __getitem__(self, idx):
        return self.X[idx], self.Y[idx]


class StudentNet(nn.Module):
    def __init__(self, in_dim=75, out_dim=4):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 64), nn.ReLU(),
            nn.Linear(64, 64), nn.ReLU(),
            nn.Linear(64, out_dim)
        )

    def forward(self, x):
        return self.net(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default=str(Path("dataset/px4_teacher/telemetry_god.csv")))
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--bs", type=int, default=128)
    ap.add_argument("--out", type=str, default=str(Path("models/student_px4_god.pt")))
    args = ap.parse_args()

    ds = Px4TeacherDataset(Path(args.data))
    dl = DataLoader(ds, batch_size=args.bs, shuffle=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = StudentNet().to(device)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()

    for epoch in range(args.epochs):
        net.train()
        losses = []
        for xb, yb in dl:
            xb = xb.to(device); yb = yb.to(device)
            opt.zero_grad()
            pred = net(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            opt.step()
            losses.append(loss.item())
        print(f"Epoch {epoch+1}/{args.epochs} loss={np.mean(losses):.4f}")

    torch.save(net.state_dict(), args.out)
    print(f"Saved student model to {args.out}")


if __name__ == "__main__":
    main()
