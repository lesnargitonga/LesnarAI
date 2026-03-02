import argparse
from pathlib import Path
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import cv2
import numpy as np
from tqdm import tqdm
from training.models.unet import UNet


class SimpleSegDataset(Dataset):
    def __init__(self, root: Path, binary_from_ids: bool = False):
        # Support either rgb/ or images/
        img_dir = (root / 'rgb') if (root / 'rgb').exists() else (root / 'images')
        self.imgs = sorted(list(img_dir.glob('*.png')))
        self.masks = sorted(list((root / 'masks').glob('*.png')))
        self.binary = bool(binary_from_ids)
        assert len(self.imgs) == len(self.masks), f'RGB/mask count mismatch: {len(self.imgs)} vs {len(self.masks)}'

    def __len__(self):
        return len(self.imgs)

    def __getitem__(self, idx):
        img = cv2.imread(str(self.imgs[idx]), cv2.IMREAD_COLOR)
        # Read mask (16-bit or 8-bit). If binary mode, collapse any nonzero to 1.
        msk = cv2.imread(str(self.masks[idx]), cv2.IMREAD_UNCHANGED)
        if msk is None:
            msk = np.zeros((img.shape[1], img.shape[2]), dtype=np.uint8)
        if msk.ndim == 3:
            msk = cv2.cvtColor(msk, cv2.COLOR_BGR2GRAY)
        if self.binary:
            msk = (msk > 0).astype(np.uint8)
        img = (img[:, :, ::-1].astype(np.float32) / 255.0).transpose(2, 0, 1)
        msk = msk.astype(np.int64)
        return torch.from_numpy(img), torch.from_numpy(msk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', type=str, required=True)
    ap.add_argument('--epochs', type=int, default=5)
    ap.add_argument('--bs', type=int, default=4)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--out', type=str, default='models/seg_unet.pt')
    ap.add_argument('--binary_from_ids', action='store_true', help='Treat any nonzero mask as class 1 (binary segmentation)')
    args = ap.parse_args()

    ds = SimpleSegDataset(Path(args.data), binary_from_ids=args.binary_from_ids)
    dl = DataLoader(ds, batch_size=args.bs, shuffle=True, num_workers=2)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = UNet(in_ch=3, num_classes=2).to(device)
    criterion = nn.CrossEntropyLoss()
    opt = optim.Adam(model.parameters(), lr=args.lr)

    model.train()
    for ep in range(args.epochs):
        pbar = tqdm(dl, desc=f"epoch {ep+1}/{args.epochs}")
        total = 0.0
        for x, y in pbar:
            x = x.to(device)
            y = y.to(device)
            opt.zero_grad()
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            opt.step()
            total += float(loss.item())
            pbar.set_postfix(loss=f"{total/ (pbar.n+1):.4f}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), args.out)


if __name__ == '__main__':
    main()
