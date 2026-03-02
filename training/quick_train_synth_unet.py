"""
Quickly train a small UNet on synthetic blobs to produce a demo model fast.
This avoids long dataset capture while still generating a workable SavedModel.
"""

import argparse
from pathlib import Path
import numpy as np
import tensorflow as tf
import keras

from model_unet import build_unet


def make_blobs_dataset(n: int, img_size=(128, 128)):
    H, W = img_size
    X = np.zeros((n, H, W, 3), dtype=np.float32)
    Y = np.zeros((n, H, W, 1), dtype=np.float32)
    rng = np.random.default_rng(42)
    for i in range(n):
        img = np.zeros((H, W, 3), dtype=np.float32)
        msk = np.zeros((H, W, 1), dtype=np.float32)
        # draw 1-3 random circles
        for _ in range(rng.integers(1, 4)):
            r = int(rng.integers(8, 20))
            cy = int(rng.integers(r, H - r))
            cx = int(rng.integers(r, W - r))
            color = rng.random(3)
            yy, xx = np.ogrid[:H, :W]
            mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= r ** 2
            img[mask] = color
            msk[mask] = 1.0
        X[i] = img
        Y[i] = msk
    return X, Y


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, default="models/unet_synth")
    parser.add_argument("--size", type=int, nargs=2, default=[128, 128])
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--epochs", type=int, default=5)
    args = parser.parse_args()

    X, Y = make_blobs_dataset(args.samples, tuple(args.size))
    model = build_unet((args.size[0], args.size[1], 3), num_classes=1, base_filters=16)
    model.compile(optimizer=keras.optimizers.Adam(1e-3), loss=keras.losses.BinaryCrossentropy(), metrics=["accuracy"])

    model.fit(X, Y, batch_size=16, epochs=args.epochs, validation_split=0.1, verbose=2)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    keras_path = out / "model.keras"
    model.save(keras_path.as_posix())
    print("Saved quick UNet to:", keras_path)


if __name__ == "__main__":
    main()
