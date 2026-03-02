from __future__ import annotations

import argparse
from pathlib import Path
import json

import torch
from torch.utils.data import DataLoader

# Local imports when running as a script
from datasets_mixed import ImageFolderDataset
from train_policy_pl import PolicyNet


def accuracy(model, loader, device):
    model.eval()
    correct = 0
    total = 0
    with torch.inference_mode():
        for x, y in loader:
            x = x.to(device)
            ycls = y['cls'].to(device)
            pcls, _ = model(x)
            pred = pcls.argmax(dim=1)
            correct += (pred == ycls).sum().item()
            total += ycls.numel()
    return correct / max(1, total)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', type=str, default=str(Path(__file__).resolve().parents[1] / 'datasets' / 'datasets.json'))
    ap.add_argument('--weights', type=str, required=True)
    ap.add_argument('--batch', type=int, default=64)
    args = ap.parse_args()

    with open(args.config, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    test_sets = []
    for key in ['tum_rgbd', 'euroc', 'kitti', 'airsim']:
        root = cfg.get(key)
        if not root:
            continue
        split_dir = Path(root) / 'processed' / 'test'
        p = split_dir / 'images'
        if p.exists():
            labels_csv = split_dir / 'labels.csv'
            ds = ImageFolderDataset(p, labels_csv=labels_csv if labels_csv.exists() else None)
            test_sets.append((key, ds))

    if not test_sets:
        raise RuntimeError('No test sets found. Run preprocessing/split first.')

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    net = PolicyNet('resnet18')
    sd = torch.load(args.weights, map_location=device)
    net.load_state_dict(sd, strict=False)
    net.to(device)

    for name, ds in test_sets:
        loader = DataLoader(ds, batch_size=args.batch, shuffle=False)
        acc = accuracy(net, loader, device)
        print(f"{name} accuracy: {acc:.3f}")


if __name__ == '__main__':
    main()
