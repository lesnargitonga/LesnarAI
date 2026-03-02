from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import torchvision.models as models
from torch.utils.data import DataLoader, ConcatDataset
import pytorch_lightning as pl

from datasets_mixed import ImageFolderDataset


class PolicyNet(nn.Module):
    def __init__(self, backbone: str = 'resnet18', num_cls: int = 4, reg_dims: int = 3):
        super().__init__()
        if backbone == 'resnet18':
            net = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
            feat_dim = net.fc.in_features
            net.fc = nn.Identity()
            self.backbone = net
        elif backbone == 'mobilenet_v2':
            net = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
            feat_dim = net.last_channel
            self.backbone = net.features
            self.pool = nn.AdaptiveAvgPool2d(1)
        else:
            raise ValueError('Unsupported backbone')
        self.head_cls = nn.Linear(feat_dim, num_cls)
        self.head_reg = nn.Linear(feat_dim, reg_dims)
        self.backbone_name = backbone

    def forward(self, x):
        if self.backbone_name == 'resnet18':
            f = self.backbone(x)
        else:
            f = self.pool(self.backbone(x)).flatten(1)
        return self.head_cls(f), self.head_reg(f)


class LitPolicy(pl.LightningModule):
    def __init__(self, backbone='resnet18', lr=1e-3, num_cls=4, reg_dims=3):
        super().__init__()
        self.save_hyperparameters()
        self.model = PolicyNet(backbone, num_cls=num_cls, reg_dims=reg_dims)
        self.ce = nn.CrossEntropyLoss()
        self.l1 = nn.L1Loss()

    def training_step(self, batch, batch_idx):
        x, y = batch
        ycls, yreg = y['cls'], y['reg']
        pcls, preg = self.model(x)
        loss = self.ce(pcls, ycls) + 0.1 * self.l1(preg, yreg)
        acc = (pcls.argmax(dim=1) == ycls).float().mean()
        self.log('train/loss', loss, on_step=True, on_epoch=True)
        self.log('train/acc', acc, on_step=True, on_epoch=True)
        return loss

    def validation_step(self, batch, batch_idx):
        x, y = batch
        ycls, yreg = y['cls'], y['reg']
        pcls, preg = self.model(x)
        loss = self.ce(pcls, ycls) + 0.1 * self.l1(preg, yreg)
        acc = (pcls.argmax(dim=1) == ycls).float().mean()
        self.log('val/loss', loss, on_epoch=True)
        self.log('val/acc', acc, on_epoch=True)

    def configure_optimizers(self):
        return torch.optim.AdamW(self.parameters(), lr=self.hparams.lr)


def make_datasets(cfg_path: Path, split: str, size: int = 224):
    with open(cfg_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    datasets = []
    for key in ['tum_rgbd', 'euroc', 'kitti', 'airsim']:
        root = cfg.get(key)
        if not root:
            continue
        split_dir = Path(root) / 'processed' / split
        p = split_dir / 'images'
        if p.exists():
            labels_csv = split_dir / 'labels.csv'
            datasets.append(ImageFolderDataset(p, labels_csv=labels_csv if labels_csv.exists() else None))
    if not datasets:
        raise RuntimeError(f"No datasets found for split={split} in config {cfg_path}")
    return ConcatDataset(datasets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', type=str, default=str(Path(__file__).resolve().parents[1] / 'datasets' / 'datasets.json'))
    ap.add_argument('--backbone', type=str, choices=['resnet18', 'mobilenet_v2'], default='resnet18')
    ap.add_argument('--batch', type=int, default=64)
    ap.add_argument('--epochs', type=int, default=20)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--out', type=str, default=str(Path('D:/models/airsim_drone')))
    ap.add_argument('--num_workers', type=int, default=4)
    args = ap.parse_args()

    train_ds = make_datasets(Path(args.config), 'train')
    val_ds = make_datasets(Path(args.config), 'val')
    # Wrap datasets to enable augmentation on training only, with normalization
    def wrap_ds(ds, augment: bool):
        from datasets_mixed import ImageFolderDataset
        # ConcatDataset -> need to map underlying datasets if they are ImageFolderDataset
        if isinstance(ds, ConcatDataset):
            for i, d in enumerate(ds.datasets):
                if isinstance(d, ImageFolderDataset):
                    d.augment = augment
                    d.normalize = True
        return ds

    train_ds = wrap_ds(train_ds, augment=True)
    val_ds = wrap_ds(val_ds, augment=False)

    persistent = args.num_workers > 0
    train_dl = DataLoader(train_ds, batch_size=args.batch, shuffle=True, num_workers=args.num_workers, pin_memory=True, persistent_workers=persistent)
    val_dl = DataLoader(val_ds, batch_size=args.batch, shuffle=False, num_workers=args.num_workers, pin_memory=True, persistent_workers=persistent)

    model = LitPolicy(backbone=args.backbone, lr=args.lr)

    ckpt = Path(args.out)
    ckpt.mkdir(parents=True, exist_ok=True)
    ckpt_cb = pl.callbacks.ModelCheckpoint(dirpath=str(ckpt), monitor='val/acc', mode='max', save_top_k=1, filename='best')
    early = pl.callbacks.EarlyStopping(monitor='val/acc', mode='max', patience=3, min_delta=1e-3)
    trainer = pl.Trainer(max_epochs=args.epochs, precision='16-mixed', accelerator='gpu' if torch.cuda.is_available() else 'cpu', devices=1, callbacks=[ckpt_cb, early])
    trainer.fit(model, train_dl, val_dl)

    # Export best model weights for deployment
    best = list(ckpt.glob('best*.ckpt'))
    if best:
        # Save a simple state_dict for runtime
        torch.save(model.model.state_dict(), ckpt / 'drone_policy.pth')
        print(f"Saved policy to {ckpt / 'drone_policy.pth'}")


if __name__ == '__main__':
    main()
