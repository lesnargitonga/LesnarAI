"""
Train a UNet segmentation model on images/masks collected from AirSim.

Features:
- GPU autodetect with TensorFlow
- Mixed precision (if GPU with Tensor Cores)
- tf.data pipeline with augmentation
- TensorBoard logs and model checkpoints
"""

import os
import argparse
from pathlib import Path

import numpy as np
import tensorflow as tf
import keras

from model_unet import build_unet


def list_pairs(root: Path, split: str):
    img_dir = root / split / "images"
    msk_dir = root / split / "masks"
    images = sorted([p for p in img_dir.glob("*.png")])
    masks = [msk_dir / p.name for p in images]
    return images, masks


def decode_png(path):
    img = tf.io.read_file(path)
    img = tf.image.decode_png(img, channels=3)
    img = tf.image.convert_image_dtype(img, tf.float32)
    return img


def decode_mask(path, num_classes: int):
    m = tf.io.read_file(path)
    # Allow uint16 or uint8 masks
    mask = tf.image.decode_png(m, channels=1, dtype=tf.uint16)
    mask = tf.cast(mask, tf.int32)
    if num_classes == 1:
        # Binary: consider any non-zero as foreground
        mask = tf.where(mask > 0, 1, 0)
        mask = tf.cast(mask, tf.float32)
    else:
        # Assume mask contains class IDs in [0, num_classes-1]. If not, users should map ahead.
        mask = tf.one_hot(tf.clip_by_value(mask[..., 0], 0, num_classes - 1), num_classes)
        mask = tf.cast(mask, tf.float32)
    return mask


def augment(img, mask, size):
    # Random flip
    flip_lr = tf.random.uniform(()) > 0.5
    img = tf.cond(flip_lr, lambda: tf.image.flip_left_right(img), lambda: img)
    mask = tf.cond(flip_lr, lambda: tf.image.flip_left_right(mask), lambda: mask)

    # Random crop + resize
    concat = tf.concat([img, mask], axis=-1)
    concat = tf.image.resize_with_pad(concat, size[0] + 32, size[1] + 32)
    concat = tf.image.random_crop(concat, size=[size[0], size[1], tf.shape(concat)[-1]])
    img = concat[..., :3]
    mask = concat[..., 3:]
    return img, mask


def build_dataset(images, masks, img_size, batch, training: bool, num_classes: int):
    def _load(img_path, msk_path):
        img = decode_png(img_path)
        mask = decode_mask(msk_path, num_classes)
        img = tf.image.resize(img, img_size)
        if num_classes == 1:
            mask = tf.image.resize(mask, img_size, method="nearest")
        else:
            mask = tf.image.resize(mask, img_size, method="nearest")
        return img, mask

    ds = tf.data.Dataset.from_tensor_slices((list(map(str, images)), list(map(str, masks))))
    if training:
        ds = ds.shuffle(buffer_size=min(1000, len(images)))
    ds = ds.map(lambda x, y: _load(x, y), num_parallel_calls=tf.data.AUTOTUNE)
    if training:
        ds = ds.map(lambda x, y: augment(x, y, img_size), num_parallel_calls=tf.data.AUTOTUNE)
    ds = ds.batch(batch).prefetch(tf.data.AUTOTUNE)
    return ds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="dataset")
    parser.add_argument("--img_size", type=int, nargs=2, default=[256, 256])
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--classes", type=int, default=1, help="1 for binary; N for multi-class")
    parser.add_argument("--out", type=str, default="runs/unet")
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--fp16", action="store_true", help="Enable mixed precision if GPU available")
    args = parser.parse_args()

    # GPU & mixed precision
    gpus = tf.config.list_physical_devices("GPU")
    if gpus:
        try:
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
            print(f"Using GPU(s): {[g.name for g in gpus]}")
        except Exception as e:
            print("GPU init error:", e)
    if args.fp16 and gpus:
        from tensorflow.keras import mixed_precision
        mixed_precision.set_global_policy("mixed_float16")
        dtype_policy = mixed_precision.global_policy().name
        print("Mixed precision policy:", dtype_policy)

    data_root = Path(args.data)
    train_imgs, train_msks = list_pairs(data_root, "train")
    val_imgs, val_msks = list_pairs(data_root, "val")

    if not train_imgs:
        raise SystemExit("No training images found. Run the dataset collector first.")

    train_ds = build_dataset(train_imgs, train_msks, args.img_size, args.batch, True, args.classes)
    val_ds = build_dataset(val_imgs, val_msks, args.img_size, args.batch, False, args.classes) if val_imgs else None

    model = build_unet((args.img_size[0], args.img_size[1], 3), num_classes=args.classes)

    if args.classes == 1:
        loss = keras.losses.BinaryCrossentropy()
        metrics = [keras.metrics.BinaryAccuracy(name="bin_acc")]
    else:
        loss = keras.losses.CategoricalCrossentropy()
        metrics = [keras.metrics.CategoricalAccuracy(name="cat_acc")]

    optimizer = keras.optimizers.Adam(learning_rate=args.lr)
    model.compile(optimizer=optimizer, loss=loss, metrics=metrics)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if val_ds is not None:
        ckpt = keras.callbacks.ModelCheckpoint(
            str(out_dir / "model.{epoch:03d}-{val_loss:.3f}.keras"),
            save_best_only=True, monitor="val_loss", mode="min"
        )
    else:
        ckpt = keras.callbacks.ModelCheckpoint(
            str(out_dir / "model.{epoch:03d}-{loss:.3f}.keras"),
            save_best_only=True, monitor="loss", mode="min"
        )

    callbacks = [ckpt, keras.callbacks.TensorBoard(log_dir=str(out_dir / "tb"), histogram_freq=1)]

    model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=args.epochs,
        callbacks=callbacks,
    )

    model.save(str(out_dir / "final_model.keras"))
    print("Training complete. Model saved to", out_dir)


if __name__ == "__main__":
    main()
