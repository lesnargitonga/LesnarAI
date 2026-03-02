from __future__ import annotations

import argparse
import csv
import random
import shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="Prepare Lesnar Brain collected frames into the train_policy_pl dataset layout")
    ap.add_argument("--raw", type=str, required=True, help="Path created by --collect (contains images/ and labels.csv)")
    ap.add_argument("--out", type=str, required=True, help="Dataset root to write (will create processed/train and processed/val)")
    ap.add_argument("--val_ratio", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=123)
    args = ap.parse_args()

    raw = Path(args.raw)
    images_dir = raw / "images"
    labels_csv = raw / "labels.csv"
    if not images_dir.exists() or not labels_csv.exists():
        raise SystemExit("--raw must contain images/ and labels.csv")

    out = Path(args.out)
    train_images = out / "processed" / "train" / "images"
    val_images = out / "processed" / "val" / "images"
    train_images.mkdir(parents=True, exist_ok=True)
    val_images.mkdir(parents=True, exist_ok=True)

    train_labels = out / "processed" / "train" / "labels.csv"
    val_labels = out / "processed" / "val" / "labels.csv"

    rows = []
    with open(labels_csv, "r", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r, None)
        for row in r:
            if len(row) >= 3:
                rows.append((row[0], row[1], row[2]))

    if not rows:
        raise SystemExit("No rows found in labels.csv")

    random.seed(int(args.seed))
    random.shuffle(rows)
    n_val = max(1, int(len(rows) * float(args.val_ratio)))
    val_set = set(rows[:n_val])

    def write_split(split_rows, img_dst: Path, labels_out: Path):
        with open(labels_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["filename", "cls", "yaw_deg"])
            for fn, cls, yaw in split_rows:
                src = images_dir / fn
                if not src.exists():
                    continue
                shutil.copy2(src, img_dst / fn)
                w.writerow([fn, cls, yaw])

    val_rows = [r for r in rows if r in val_set]
    train_rows = [r for r in rows if r not in val_set]

    write_split(train_rows, train_images, train_labels)
    write_split(val_rows, val_images, val_labels)

    print(f"Wrote train={len(train_rows)} val={len(val_rows)} to {out}")


if __name__ == "__main__":
    main()
