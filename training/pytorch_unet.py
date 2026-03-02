"""
PyTorch UNet training for segmentation on the AirSim dataset structure.

- Dataset layout:
  dataset/
    train/images/*.png
    train/masks/*.png (uint8/uint16; 0=bg, >0=fg for binary)
    val/images/*.png
    val/masks/*.png

- Features:
  * GPU/AMP (mixed precision)
  * TensorBoard logging
  * Checkpoints (best by val loss)
"""

from pathlib import Path
import sys
import argparse
import time
from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image

# Project util to resolve D:/datasets automatically
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from shared.dataset_utils import resolve_dataset_root


class DoubleConv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class UNet(nn.Module):
    def __init__(self, in_ch=3, num_classes=1, base=64):
        super().__init__()
        self.down1 = DoubleConv(in_ch, base)
        self.pool1 = nn.MaxPool2d(2)
        self.down2 = DoubleConv(base, base*2)
        self.pool2 = nn.MaxPool2d(2)
        self.down3 = DoubleConv(base*2, base*4)
        self.pool3 = nn.MaxPool2d(2)
        self.down4 = DoubleConv(base*4, base*8)
        self.pool4 = nn.MaxPool2d(2)
        self.bridge = DoubleConv(base*8, base*16)

        self.up1 = nn.ConvTranspose2d(base*16, base*8, 2, stride=2)
        self.dec1 = DoubleConv(base*16, base*8)
        self.up2 = nn.ConvTranspose2d(base*8, base*4, 2, stride=2)
        self.dec2 = DoubleConv(base*8, base*4)
        self.up3 = nn.ConvTranspose2d(base*4, base*2, 2, stride=2)
        self.dec3 = DoubleConv(base*4, base*2)
        self.up4 = nn.ConvTranspose2d(base*2, base, 2, stride=2)
        self.dec4 = DoubleConv(base*2, base)

        self.outc = nn.Conv2d(base, num_classes, 1)
        self.num_classes = num_classes

    def forward(self, x):
        s1 = self.down1(x); p1 = self.pool1(s1)
        s2 = self.down2(p1); p2 = self.pool2(s2)
        s3 = self.down3(p2); p3 = self.pool3(s3)
        s4 = self.down4(p3); p4 = self.pool4(s4)
        b = self.bridge(p4)
        x = self.up1(b); x = torch.cat([x, s4], dim=1); x = self.dec1(x)
        x = self.up2(x); x = torch.cat([x, s3], dim=1); x = self.dec2(x)
        x = self.up3(x); x = torch.cat([x, s2], dim=1); x = self.dec3(x)
        x = self.up4(x); x = torch.cat([x, s1], dim=1); x = self.dec4(x)
        x = self.outc(x)
        if self.num_classes == 1:
            return x  # logits for BCEWithLogitsLoss
        else:
            return x  # logits for CrossEntropyLoss


class SegDataset(Dataset):
    def __init__(self, root: Path, split: str = "train", img_size: Tuple[int, int] = (256, 256), num_classes: int = 1, augment: bool = False):
        super().__init__()
        self.imgs = sorted((root / split / "images").glob("*.png"))
        self.msks = [root / split / "masks" / p.name for p in self.imgs]
        self.size = img_size
        self.num_classes = num_classes
        self.to_tensor = transforms.ToTensor()
        self.split = split
        self.augment = augment and (split == "train")

    def __len__(self):
        return len(self.imgs)

    def _load_mask(self, p: Path):
        # Load mask as grayscale; support uint16
        with Image.open(p) as im:
            if im.mode != "I;16" and im.mode != "L":
                im = im.convert("L")
            arr = np.array(im)
        if self.num_classes == 1:
            # Binary: any >0 => 1
            m = (arr > 0).astype(np.float32)
            return torch.from_numpy(m)[None, ...]  # 1xHxW
        else:
            # Multi-class: expect IDs in [0..N-1]
            return torch.from_numpy(arr.astype(np.int64))  # HxW

    def __getitem__(self, idx):
        img_p = self.imgs[idx]
        msk_p = self.msks[idx]
        with Image.open(img_p) as im:
            im = im.convert("RGB")
            # Resize first to target canvas to keep deterministic geometry
            im = im.resize(self.size[::-1], Image.BILINEAR)
            # Basic color jitter for robustness (train only)
            if self.augment:
                # Random horizontal flip
                if np.random.rand() < 0.5:
                    im = im.transpose(Image.FLIP_LEFT_RIGHT)
                # Light color jitter
                if np.random.rand() < 0.8:
                    # Implement simple jitter manually to avoid adding new deps
                    arr = np.asarray(im).astype(np.float32)
                    gain = 0.9 + 0.2 * np.random.rand()
                    bias = (np.random.rand(3) - 0.5) * 0.1 * 255.0
                    arr = np.clip(arr * gain + bias, 0, 255).astype(np.uint8)
                    im = Image.fromarray(arr)
            x = self.to_tensor(im)  # 3xHxW in [0,1]
        m = self._load_mask(msk_p)
        if m.ndim == 2:  # HxW => resize as PIL then to tensor
            m_img = Image.fromarray(m.numpy().astype(np.uint8))
            # Apply same flip as image if augmentation flipped (heuristic: re-check previous random)
            # Note: since flips were stochastic above, we reapply a new random with same prob to avoid tight coupling
            if self.augment and np.random.rand() < 0.5:
                m_img = m_img.transpose(Image.FLIP_LEFT_RIGHT)
            m_img = m_img.resize(self.size[::-1], Image.NEAREST)
            m = torch.from_numpy(np.array(m_img).astype(np.int64))
        else:
            # 1xHxW float
            m_img = Image.fromarray((m.squeeze(0).numpy() * 255).astype(np.uint8))
            if self.augment and np.random.rand() < 0.5:
                m_img = m_img.transpose(Image.FLIP_LEFT_RIGHT)
            m_img = m_img.resize(self.size[::-1], Image.NEAREST)
            m = torch.from_numpy((np.array(m_img) > 127).astype(np.float32))[None, ...]
        return x, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default="dataset")
    ap.add_argument("--img_size", type=int, nargs=2, default=[256, 256])
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--classes", type=int, default=1)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--out", type=str, default="runs/unet_torch")
    ap.add_argument("--base", type=int, default=32)
    ap.add_argument("--aug", action="store_true", help="Enable light data augmentation (flip, color jitter)")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", device)

    data_root = resolve_dataset_root(args.data)
    print("Data root:", data_root)
    train_ds = SegDataset(data_root, "train", tuple(args.img_size), args.classes, augment=args.aug)
    val_imgs = list((data_root / "val" / "images").glob("*.png"))
    val_ds = SegDataset(data_root, "val", tuple(args.img_size), args.classes, augment=False) if val_imgs else None

    if len(train_ds) == 0:
        raise SystemExit("No training data found. Run the AirSim collector first.")

    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True, num_workers=2, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch, shuffle=False, num_workers=2, pin_memory=True) if val_ds else None

    model = UNet(in_ch=3, num_classes=args.classes, base=args.base).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    scaler = torch.cuda.amp.GradScaler(enabled=(device.type == "cuda"))

    if args.classes == 1:
        criterion = nn.BCEWithLogitsLoss()
    else:
        criterion = nn.CrossEntropyLoss()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    from torch.utils.tensorboard import SummaryWriter
    writer = SummaryWriter(log_dir=(out_dir / "tb").as_posix())

    best_val = float("inf")
    global_step = 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        t0 = time.time()
        for x, y in train_loader:
            x = x.to(device, non_blocking=True)
            if args.classes == 1:
                y = y.to(device, non_blocking=True)
            else:
                y = y.to(device, non_blocking=True)  # HxW long
            optimizer.zero_grad(set_to_none=True)
            with torch.cuda.amp.autocast(enabled=(device.type == "cuda")):
                logits = model(x)
                if args.classes == 1:
                    loss = criterion(logits, y)
                else:
                    loss = criterion(logits, y.long())
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            epoch_loss += loss.item()
            writer.add_scalar("train/loss", loss.item(), global_step)
            global_step += 1

        dur = time.time() - t0
        print(f"Epoch {epoch}/{args.epochs} - train_loss={epoch_loss/len(train_loader):.4f} in {dur:.1f}s")

        # Validation
        if val_loader is not None:
            model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for x, y in val_loader:
                    x = x.to(device, non_blocking=True)
                    if args.classes == 1:
                        y = y.to(device, non_blocking=True)
                        logits = model(x)
                        loss = criterion(logits, y)
                    else:
                        y = y.to(device, non_blocking=True)
                        logits = model(x)
                        loss = criterion(logits, y.long())
                    val_loss += loss.item()
            val_loss /= max(1, len(val_loader))
            writer.add_scalar("val/loss", val_loss, epoch)
            print(f"  val_loss={val_loss:.4f}")
            if val_loss < best_val:
                best_val = val_loss
                torch.save(model.state_dict(), (out_dir / "best.pt").as_posix())

        # Save last each epoch
        torch.save(model.state_dict(), (out_dir / "last.pt").as_posix())

    # Save TorchScript for easier deployment
    model.eval()
    example = torch.randn(1, 3, args.img_size[0], args.img_size[1]).to(device)
    traced = torch.jit.trace(model, example)
    traced.save((out_dir / "model_ts.pt").as_posix())
    print("Training complete. Artifacts at:", out_dir)


if __name__ == "__main__":
    main()
