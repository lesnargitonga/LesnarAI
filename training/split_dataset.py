import argparse
from pathlib import Path
import random


def list_images(root: Path):
    return sorted((root / 'rgb').glob('*.png'))


def main():
    ap = argparse.ArgumentParser(description='Create train/val/test manifest files for a unified dataset')
    ap.add_argument('--data_root', type=str, required=True, help='Root like D:/datasets/unified/KITTI/seq_00')
    ap.add_argument('--train_ratio', type=float, default=0.8)
    ap.add_argument('--val_ratio', type=float, default=0.1)
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    root = Path(args.data_root)
    imgs = list_images(root)
    idxs = list(range(len(imgs)))
    random.Random(args.seed).shuffle(idxs)
    n = len(idxs)
    n_train = int(n * args.train_ratio)
    n_val = int(n * args.val_ratio)
    train_idx = idxs[:n_train]
    val_idx = idxs[n_train:n_train + n_val]
    test_idx = idxs[n_train + n_val:]

    (root / 'manifests').mkdir(parents=True, exist_ok=True)
    def write_list(name, ids):
        with open(root / 'manifests' / f'{name}.txt', 'w', encoding='utf-8') as f:
            for i in ids:
                f.write(f"rgb/{i:06d}.png\n")

    write_list('train', train_idx)
    write_list('val', val_idx)
    write_list('test', test_idx)
    print(f"Wrote manifests under {root / 'manifests'}: train={len(train_idx)} val={len(val_idx)} test={len(test_idx)}")


if __name__ == '__main__':
    main()
