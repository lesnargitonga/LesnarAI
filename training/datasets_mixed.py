from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Iterator, Optional

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset, Sampler


class ImageFolderDataset(Dataset):
    def __init__(self, root: str | Path, transform=None, labels_csv: Optional[Path] = None, augment: bool = False, normalize: bool = True):
        self.root = Path(root)
        self.files = sorted([p for p in self.root.glob('**/*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg')])
        self.transform = transform
        self.augment = augment
        self.normalize = normalize
        self.labels: Dict[str, Tuple[int, float]] = {}
        if labels_csv and Path(labels_csv).exists():
            # Expect CSV header: filename, cls, yaw_deg
            import csv
            with open(labels_csv, 'r', encoding='utf-8') as f:
                r = csv.reader(f)
                header = next(r, None)
                for row in r:
                    if len(row) >= 3:
                        self.labels[row[0]] = (int(row[1]), float(row[2]))
    def __len__(self):
        return len(self.files)
    def __getitem__(self, idx: int):
        p = self.files[idx]
        img = cv2.imread(p.as_posix(), cv2.IMREAD_COLOR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, _ = img.shape
        # Lightweight augmentations that don't change semantic left/right mapping
        if self.augment:
            # Random brightness/contrast
            if np.random.rand() < 0.8:
                alpha = float(np.random.uniform(0.8, 1.2))  # contrast
                beta = float(np.random.uniform(-20, 20))    # brightness
                img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
            # Random gaussian blur
            if np.random.rand() < 0.2:
                img = cv2.GaussianBlur(img, (3, 3), 0)
            # Random resized crop (keep center-of-view mostly)
            if np.random.rand() < 0.5:
                scale = float(np.random.uniform(0.8, 1.0))
                ch, cw = max(1, int(h * scale)), max(1, int(w * scale))
                y0 = int(np.random.uniform(0, h - ch + 1))
                x0 = int(np.random.uniform(0, w - cw + 1))
                crop = img[y0:y0 + ch, x0:x0 + cw]
                img = cv2.resize(crop, (w, h), interpolation=cv2.INTER_AREA)
            # Random color jitter via HSV shift
            if np.random.rand() < 0.3:
                hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV).astype(np.float32)
                hsv[..., 1] = np.clip(hsv[..., 1] * np.random.uniform(0.8, 1.2), 0, 255)
                hsv[..., 2] = np.clip(hsv[..., 2] * np.random.uniform(0.8, 1.2), 0, 255)
                img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

        if self.transform:
            img = self.transform(img)
            # Expect transform returns CHW tensor; leave normalization to transform
        else:
            img = torch.from_numpy(img.transpose(2, 0, 1)).float() / 255.0
            if self.normalize:
                mean = torch.tensor([0.485, 0.456, 0.406])[:, None, None]
                std = torch.tensor([0.229, 0.224, 0.225])[:, None, None]
                img = (img - mean) / std
        # Labels: use CSV if available, else fallback to neutral
        if p.name in self.labels:
            y_cls = torch.tensor(self.labels[p.name][0], dtype=torch.long)
            y_reg = torch.tensor([self.labels[p.name][1], 0.0, 0.0], dtype=torch.float32)  # yaw, pitch=0, roll=0
        else:
            y_cls = torch.tensor(1, dtype=torch.long)  # assume forward
            y_reg = torch.zeros(3, dtype=torch.float32)
        return img, {'cls': y_cls, 'reg': y_reg}


@dataclass
class DatasetSpec:
    name: str
    path: Path
    weight: int = 1


class RoundRobinSampler(Sampler[int]):
    """Cycles through multiple datasets in round-robin fashion by weight.
    Provide lengths per dataset and it will yield indices in a combined index space.
    """
    def __init__(self, lengths: List[int], weights: List[int]):
        self.lengths = lengths
        self.weights = weights
        self.num_datasets = len(lengths)
        self.max_len = max(lengths) if lengths else 0
        # Precompute order of dataset selection per cycle
        self.order = []
        for i, w in enumerate(weights):
            self.order.extend([i] * max(1, int(w)))

    def __iter__(self) -> Iterator[int]:
        # Map (dataset_id, local_index) to a global linearized index
        offsets = np.cumsum([0] + self.lengths[:-1]).tolist()
        loc_idx = [0] * self.num_datasets
        total = sum(self.lengths)
        yielded = 0
        while yielded < total:
            for d in self.order:
                if loc_idx[d] < self.lengths[d]:
                    yield offsets[d] + loc_idx[d]
                    loc_idx[d] += 1
                    yielded += 1
                if yielded >= total:
                    break

    def __len__(self) -> int:
        return sum(self.lengths)
