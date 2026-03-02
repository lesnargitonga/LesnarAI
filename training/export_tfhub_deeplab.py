"""
Export a pretrained DeepLabV3 segmentation model from TensorFlow Hub
into the local models/ folder for immediate inference use.

By default exports a Cityscapes-tuned or general DeepLab depending on availability.
"""

import argparse
from pathlib import Path

import tensorflow as tf
import tensorflow_hub as hub


DEFAULT_HUB_URLS = [
    # Prefer Cityscapes if available; fallback to generic DeepLabV3
    "https://tfhub.dev/tensorflow/deeplabv3-cityscapes/1",
    "https://tfhub.dev/tensorflow/deeplabv3/1",
]


def export_model(hub_url: str, export_dir: Path):
    print(f"Loading TFHub model: {hub_url}")
    export_dir.mkdir(parents=True, exist_ok=True)

    # First try KerasLayer (works for TF2 SavedModels with Keras signatures)
    try:
        layer = hub.KerasLayer(hub_url)
        inp = tf.keras.Input(shape=(None, None, 3), dtype=tf.float32, name="image")
        out = layer(inp)
        wrapped = tf.keras.Model(inputs=inp, outputs=out, name="deeplabv3_hub")
        wrapped.save(export_dir.as_posix())
        print("SavedModel exported to:", export_dir)
        return
    except Exception as e:
        print("KerasLayer load failed, trying hub.load():", e)

    # Fallback: hub.load (general SavedModel). We'll re-save it to export_dir.
    module = hub.load(hub_url)
    # Save the module directly; signature is preserved.
    tf.saved_model.save(module, export_dir.as_posix())
    print("Saved raw module to:", export_dir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", type=str, default=None, help="TF Hub URL for DeepLabV3 model")
    parser.add_argument("--out", type=str, default="models/deeplabv3_cityscapes")
    args = parser.parse_args()

    out = Path(args.out)
    urls = [args.url] if args.url else DEFAULT_HUB_URLS

    last_err = None
    for u in urls:
        try:
            export_model(u, out)
            return
        except Exception as e:
            print("Failed to export from:", u, "=>", e)
            last_err = e
    raise SystemExit(f"All TF Hub URLs failed. Last error: {last_err}")


if __name__ == "__main__":
    main()
