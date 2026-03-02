#!/usr/bin/env python3
"""
Evaluate a segmentation model on dataset/val (or train) and save metrics + visualizations.

Usage example:
  python training/eval_unet.py --data dataset \
    --weights runs/unet_torch/best.pt --img_size 256 256 --split val --out runs/eval_unet

Supports both TorchScript (.pt traced) and state_dict checkpoints from training/pytorch_unet.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import csv

import numpy as np
import cv2

# Ensure project root is importable
import sys
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ai_modules.segmentation_inference_torch import TorchSegmenter
from shared.dataset_utils import resolve_dataset_root


def iou_dice(pred: np.ndarray, gt: np.ndarray) -> tuple[float, float]:
    """Compute IoU and Dice for binary masks (uint8 0/255 or 0/1)."""
    p = (pred > 0).astype(np.uint8)
    g = (gt > 0).astype(np.uint8)
    inter = int((p & g).sum())
    union = int((p | g).sum())
    iou = inter / union if union > 0 else (1.0 if g.sum() == 0 and p.sum() == 0 else 0.0)
    dice = (2 * inter) / (p.sum() + g.sum()) if (p.sum() + g.sum()) > 0 else (1.0 if g.sum() == 0 and p.sum() == 0 else 0.0)
    return float(iou), float(dice)


def colorize(mask: np.ndarray, color=(0, 255, 0)) -> np.ndarray:
    m = (mask > 0).astype(np.uint8)
    out = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
    out[m == 1] = color
    return out


def overlay(img_bgr: np.ndarray, mask_u8: np.ndarray, color=(0, 255, 0), alpha=0.4) -> np.ndarray:
    col = colorize(mask_u8, color)
    return cv2.addWeighted(img_bgr, 1.0, col, alpha, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default="dataset")
    ap.add_argument("--weights", type=str, required=True, help="Path to .pt TorchScript or state_dict")
    ap.add_argument("--img_size", type=int, nargs=2, default=[256, 256])
    ap.add_argument("--split", type=str, default="val", choices=["val", "train"]) 
    ap.add_argument("--classes", type=int, default=1)
    ap.add_argument("--max", type=int, default=0, help="Evaluate at most N samples (0 = all)")
    ap.add_argument("--out", type=str, default="runs/eval_unet")
    args = ap.parse_args()

    data_root = resolve_dataset_root(args.data)
    print("Data root:", data_root)
    img_dir = data_root / args.split / "images"
    msk_dir = data_root / args.split / "masks"
    imgs = sorted(img_dir.glob("*.png"))
    msks = [msk_dir / p.name for p in imgs]
    if not imgs:
        raise SystemExit(f"No images found under {img_dir}")
    if args.max > 0:
        imgs = imgs[:args.max]
        msks = msks[:args.max]

    out_dir = Path(args.out)
    vis_dir = out_dir / "vis"
    out_dir.mkdir(parents=True, exist_ok=True)
    vis_dir.mkdir(parents=True, exist_ok=True)

    seg = TorchSegmenter(args.weights, img_size=tuple(args.img_size), classes=args.classes)

    rows = []
    ious, dices = [], []
    for i, (ip, mp) in enumerate(zip(imgs, msks)):
        img = cv2.imread(str(ip), cv2.IMREAD_COLOR)
        if img is None:
            continue
        gt = cv2.imread(str(mp), cv2.IMREAD_GRAYSCALE)
        if gt is None:
            continue
        pred = seg.predict_mask(img)
        if args.classes == 1:
            iou, dice = iou_dice(pred, gt)
        else:
            # For multi-class, compute mean IoU over non-background classes (>0)
            iou_list = []
            for cid in np.unique(gt):
                if cid == 0:
                    continue
                iou_c, _ = iou_dice((pred == cid).astype(np.uint8), (gt == cid).astype(np.uint8))
                iou_list.append(iou_c)
            iou = float(np.mean(iou_list)) if iou_list else 0.0
            dice = 0.0
        ious.append(iou)
        dices.append(dice)
        rows.append([ip.name, iou, dice])

        # Visualization side-by-side
        vis_pred = overlay(img, pred, (0, 255, 0), 0.4)
        vis_gt = overlay(img, gt, (0, 0, 255), 0.4)
        cat = np.concatenate([img, vis_gt, vis_pred], axis=1)
        cv2.putText(cat, f"IoU={iou:.3f} Dice={dice:.3f}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        cv2.imwrite(str(vis_dir / ip.name), cat)

    # Write CSV and summary
    csv_path = out_dir / "metrics.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "iou", "dice"])
        w.writerows(rows)
        w.writerow(["AVERAGE", float(np.mean(ious)) if ious else 0.0, float(np.mean(dices)) if dices else 0.0])

    print(f"Evaluated {len(rows)} samples. Mean IoU={float(np.mean(ious)) if ious else 0.0:.3f}, Dice={float(np.mean(dices)) if dices else 0.0:.3f}")
    print("Visualizations:", vis_dir)
    print("CSV:", csv_path)


if __name__ == "__main__":
    main()
