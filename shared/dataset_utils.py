from __future__ import annotations

from pathlib import Path
from typing import List, Tuple


def resolve_dataset_root(preferred: str | None = None) -> Path:
    """
    Resolve a dataset root that contains split/images and split/masks.
    Preference order:
      1) preferred (CLI arg) if valid
      2) D:\\datasets\lesnar_seg
      3) D:\\datasets\dataset
      4) repository ./dataset
      5) any split directory found directly under D:\\datasets (heuristic)
    """
    candidates: List[Path] = []
    if preferred:
        candidates.append(Path(preferred))
    # Common Windows datasets location
    droot = Path("D:/datasets")
    candidates.extend([
        droot / "lesnar_seg",
        droot / "dataset",
        Path("dataset"),
    ])
    # Heuristic: if D:/datasets has a folder with expected layout, consider it
    if droot.exists() and droot.is_dir():
        for child in droot.iterdir():
            if child.is_dir():
                if (child / "train" / "images").exists() and (child / "train" / "masks").exists():
                    candidates.append(child)

    # Return first that looks valid
    for c in candidates:
        if (c / "train" / "images").exists() and (c / "train" / "masks").exists():
            return c
    # Fallback to preferred or repo ./dataset
    return Path(preferred or "dataset")


def list_pairs(root: Path, split: str) -> Tuple[List[Path], List[Path]]:
    img_dir = root / split / "images"
    msk_dir = root / split / "masks"
    images = sorted([p for p in img_dir.glob("*.png")])
    masks = [msk_dir / p.name for p in images]
    return images, masks
